"""Small-model training pipeline with resource controls and graceful cancellation.

Kept strictly separated from the autonomous debugging runtime.
Supports reproducible random seeding, resource limits, step/epoch capping,
and atomic checkpointing.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.utils.data import DataLoader

from prometheus_ai.learning.lab.checkpoint import CheckpointManager
from prometheus_ai.learning.lab.config import ExperimentConfig, TrainingConfig
from prometheus_ai.learning.lab.dataset import DatasetSplits, TokenizedDataset
from prometheus_ai.learning.lab.evaluator import LabEvaluator
from prometheus_ai.learning.lab.metrics import (
    StepMetrics,
    TrainingLogger,
    calculate_perplexity,
    get_peak_memory_mb,
)
from prometheus_ai.learning.lab.tokenizer import BaseTokenizer


class TrainingInterruptedError(Exception):
    """Raised when training is cancelled or terminated prematurely."""


class CancellationToken:
    """Thread-safe cooperative cancellation token for long-running training jobs."""

    def __init__(self) -> None:
        self._cancelled: bool = False
        self._reason: str = ""

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def reason(self) -> str:
        return self._reason

    def cancel(self, reason: str = "User requested cancellation") -> None:
        """Signal cancellation to the training loop."""
        self._cancelled = True
        self._reason = reason

    def check_cancelled(self) -> None:
        """Raise TrainingInterruptedError if cancellation was requested."""
        if self._cancelled:
            raise TrainingInterruptedError(f"Training interrupted: {self._reason}")


@dataclass
class TrainingSummary:
    """Final outcome and metadata of a training execution."""

    total_steps: int
    total_epochs: int
    final_train_loss: float
    best_val_loss: float | None
    best_val_perplexity: float | None
    duration_seconds: float
    interrupted: bool = False
    interruption_reason: str | None = None
    best_checkpoint_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_steps": self.total_steps,
            "total_epochs": self.total_epochs,
            "final_train_loss": round(self.final_train_loss, 4),
            "best_val_loss": round(self.best_val_loss, 4) if self.best_val_loss else None,
            "best_val_perplexity": (
                round(self.best_val_perplexity, 4) if self.best_val_perplexity else None
            ),
            "duration_seconds": round(self.duration_seconds, 2),
            "interrupted": self.interrupted,
            "interruption_reason": self.interruption_reason,
            "best_checkpoint_path": self.best_checkpoint_path,
        }


class LabTrainer:
    """Trainer module managing small transformer optimization runs."""

    def __init__(
        self,
        model: nn.Module,
        tokenizer: BaseTokenizer,
        config: TrainingConfig,
        splits: DatasetSplits,
        experiment_config: ExperimentConfig | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        logger: TrainingLogger | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        config.validate()
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.splits = splits
        self.experiment_config = experiment_config
        self.checkpoint_manager = checkpoint_manager
        self.logger = logger or TrainingLogger()
        self.cancellation_token = cancellation_token or CancellationToken()

        # Seed setting for reproducible execution
        torch.manual_seed(config.seed)
        random.seed(config.seed)

        self.device = torch.device(
            config.device if (config.device == "cpu" or torch.cuda.is_available()) else "cpu"
        )
        self.model.to(self.device)

        # Context length from model if available
        m_cfg = getattr(model, "config", None)
        context_len: int = int(getattr(m_cfg, "context_length", 64)) if m_cfg is not None else 64

        # PyTorch Dataset and DataLoader preparation
        self.train_dataset = TokenizedDataset(
            texts=splits.train,
            tokenizer=tokenizer,
            context_length=context_len,
        )
        self.val_dataset = TokenizedDataset(
            texts=splits.val,
            tokenizer=tokenizer,
            context_length=context_len,
        )

        self.train_loader = DataLoader(
            self.train_dataset,
            batch_size=min(config.batch_size, max(len(self.train_dataset), 1)),
            shuffle=True,
            drop_last=False,
        )
        self.val_loader = DataLoader(
            self.val_dataset,
            batch_size=min(config.batch_size, max(len(self.val_dataset), 1)),
            shuffle=False,
            drop_last=False,
        )

        self.optimizer = AdamW(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )

        self.current_step = 0
        self.current_epoch = 0
        self.best_val_loss = float("inf")
        self.best_checkpoint_path: Path | None = None

    def train(self, resume_from: Path | str | None = None) -> TrainingSummary:
        """Run the small-model training loop up to configured max_steps or max_epochs."""
        if resume_from and self.checkpoint_manager:
            ckpt_info = self.checkpoint_manager.load_checkpoint(
                resume_from, self.model, self.optimizer
            )
            self.current_step = ckpt_info.get("step", 0)
            self.current_epoch = ckpt_info.get("epoch", 0)
            if ckpt_info.get("val_loss") is not None:
                self.best_val_loss = ckpt_info["val_loss"]

        start_time = time.perf_counter()
        total_tokens_trained = 0
        total_samples_trained = 0
        latest_loss = 0.0

        try:
            for epoch in range(self.current_epoch, self.config.max_epochs):
                self.current_epoch = epoch
                self.model.train()

                for x, y in self.train_loader:
                    # Check cancellation token before every batch
                    self.cancellation_token.check_cancelled()

                    # Resource limit: wall-clock timeout check
                    if self.config.max_train_time_seconds:
                        elapsed = time.perf_counter() - start_time
                        if elapsed >= self.config.max_train_time_seconds:
                            self.cancellation_token.cancel("Exceeded max_train_time_seconds limit")
                            self.cancellation_token.check_cancelled()

                    # Step limit check
                    if self.current_step >= self.config.max_steps:
                        break

                    x, y = x.to(self.device), y.to(self.device)
                    batch_start = time.perf_counter()

                    self.optimizer.zero_grad()
                    _, loss = self.model(x, targets=y)
                    if loss is None:
                        continue

                    loss.backward()

                    # Gradient clipping
                    if self.config.grad_clip > 0:
                        nn.utils.clip_grad_norm_(self.model.parameters(), self.config.grad_clip)

                    self.optimizer.step()

                    self.current_step += 1
                    latest_loss = loss.item()
                    step_duration = max(time.perf_counter() - batch_start, 1e-6)

                    # Throughput calculations
                    tokens_in_batch = x.numel()
                    samples_in_batch = x.size(0)
                    total_tokens_trained += tokens_in_batch
                    total_samples_trained += samples_in_batch

                    throughput_tokens = tokens_in_batch / step_duration
                    throughput_samples = samples_in_batch / step_duration
                    elapsed_total = time.perf_counter() - start_time

                    step_metric = StepMetrics(
                        step=self.current_step,
                        epoch=self.current_epoch,
                        train_loss=round(latest_loss, 4),
                        train_perplexity=round(calculate_perplexity(latest_loss), 4),
                        learning_rate=self.config.learning_rate,
                        throughput_tokens_per_sec=round(throughput_tokens, 2),
                        throughput_samples_per_sec=round(throughput_samples, 2),
                        elapsed_seconds=round(elapsed_total, 2),
                        peak_memory_mb=get_peak_memory_mb(),
                    )
                    self.logger.log_step(step_metric)

                    # Periodic Evaluation
                    if (
                        self.current_step % self.config.eval_every_steps == 0
                        or self.current_step == self.config.max_steps
                    ):
                        val_metrics = LabEvaluator.evaluate(
                            self.model,
                            self.val_loader,
                            self.tokenizer,
                            device=self.device,
                            split_name="validation",
                        )
                        val_metrics.step = self.current_step
                        val_metrics.epoch = self.current_epoch
                        self.logger.log_validation(val_metrics)

                        is_best = val_metrics.val_loss < self.best_val_loss
                        if is_best:
                            self.best_val_loss = val_metrics.val_loss

                        # Periodic Checkpoint
                        if self.checkpoint_manager and (
                            self.current_step % self.config.checkpoint_every_steps == 0 or is_best
                        ):
                            saved_path = self.checkpoint_manager.save_checkpoint(
                                model=self.model,
                                optimizer=self.optimizer,
                                step=self.current_step,
                                epoch=self.current_epoch,
                                train_loss=latest_loss,
                                val_loss=val_metrics.val_loss,
                                dataset_name=self.splits.metadata.name,
                                dataset_version=self.splits.metadata.version,
                                model_config=(
                                    self.experiment_config.model.to_dict()
                                    if self.experiment_config
                                    else {}
                                ),
                                training_config=self.config.__dict__,
                                is_best=is_best,
                            )
                            if is_best:
                                self.best_checkpoint_path = saved_path

                    if self.current_step >= self.config.max_steps:
                        break

                if self.current_step >= self.config.max_steps:
                    break

            total_elapsed = time.perf_counter() - start_time
            best_val = self.best_val_loss if self.best_val_loss != float("inf") else None
            best_perp = calculate_perplexity(best_val) if best_val is not None else None

            # Ensure final checkpoint is saved
            if self.checkpoint_manager:
                final_saved = self.checkpoint_manager.save_checkpoint(
                    model=self.model,
                    optimizer=self.optimizer,
                    step=self.current_step,
                    epoch=self.current_epoch,
                    train_loss=latest_loss,
                    val_loss=best_val,
                    dataset_name=self.splits.metadata.name,
                    dataset_version=self.splits.metadata.version,
                    model_config=(
                        self.experiment_config.model.to_dict() if self.experiment_config else {}
                    ),
                    training_config=self.config.__dict__,
                    is_best=False,
                )
                if not self.best_checkpoint_path:
                    self.best_checkpoint_path = final_saved

            return TrainingSummary(
                total_steps=self.current_step,
                total_epochs=self.current_epoch + 1,
                final_train_loss=latest_loss,
                best_val_loss=best_val,
                best_val_perplexity=best_perp,
                duration_seconds=total_elapsed,
                interrupted=False,
                best_checkpoint_path=(
                    str(self.best_checkpoint_path) if self.best_checkpoint_path else None
                ),
            )

        except TrainingInterruptedError as e:
            total_elapsed = time.perf_counter() - start_time
            # Save emergency interrupted checkpoint
            if self.checkpoint_manager:
                self.checkpoint_manager.save_checkpoint(
                    model=self.model,
                    optimizer=self.optimizer,
                    step=self.current_step,
                    epoch=self.current_epoch,
                    train_loss=latest_loss,
                    val_loss=self.best_val_loss if self.best_val_loss != float("inf") else None,
                    dataset_name=self.splits.metadata.name,
                    dataset_version=self.splits.metadata.version,
                    model_config=(
                        self.experiment_config.model.to_dict() if self.experiment_config else {}
                    ),
                    training_config=self.config.__dict__,
                    is_best=False,
                )
            return TrainingSummary(
                total_steps=self.current_step,
                total_epochs=self.current_epoch + 1,
                final_train_loss=latest_loss,
                best_val_loss=self.best_val_loss if self.best_val_loss != float("inf") else None,
                best_val_perplexity=(
                    calculate_perplexity(self.best_val_loss)
                    if self.best_val_loss != float("inf")
                    else None
                ),
                duration_seconds=total_elapsed,
                interrupted=True,
                interruption_reason=str(e),
                best_checkpoint_path=(
                    str(self.best_checkpoint_path) if self.best_checkpoint_path else None
                ),
            )
