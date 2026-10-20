"""Atomic checkpoint saving, recovery, and version tracking for the ML Lab.

Ensures training state (model weights, optimizer state, scheduler, random seeds)
can be safely saved, verified, and resumed without state corruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from torch.optim import Optimizer


@dataclass
class CheckpointMetadata:
    """Metadata recorded with every saved checkpoint."""

    step: int
    epoch: int
    train_loss: float
    val_loss: float | None
    dataset_name: str
    dataset_version: str
    model_config: dict[str, Any]
    training_config: dict[str, Any]
    checkpoint_file: str
    sha256_hash: str = ""
    is_best: bool = False
    saved_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckpointManager:
    """Handles atomic checkpoint persistence and resumption."""

    def __init__(self, checkpoint_dir: Path | str, max_to_keep: int = 5) -> None:
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.max_to_keep = max_to_keep

    def save_checkpoint(
        self,
        model: nn.Module,
        optimizer: Optimizer | None,
        step: int,
        epoch: int,
        train_loss: float,
        val_loss: float | None,
        dataset_name: str,
        dataset_version: str,
        model_config: dict[str, Any],
        training_config: dict[str, Any],
        is_best: bool = False,
    ) -> Path:
        """Atomically persist checkpoint state dict and associated metadata."""
        ckpt_filename = f"checkpoint_step_{step:06d}.pt"
        final_ckpt_path = self.checkpoint_dir / ckpt_filename
        meta_filename = f"checkpoint_step_{step:06d}_meta.json"
        final_meta_path = self.checkpoint_dir / meta_filename

        state: dict[str, Any] = {
            "step": step,
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict() if optimizer else None,
            "torch_rng_state": torch.get_rng_state(),
        }
        if torch.cuda.is_available():
            state["cuda_rng_state"] = torch.cuda.get_rng_state_all()

        # Atomic write to temporary file in the same directory, then rename
        with tempfile.NamedTemporaryFile(
            dir=self.checkpoint_dir, delete=False, suffix=".tmp"
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            torch.save(state, tmp_path)

        os.replace(tmp_path, final_ckpt_path)

        # Compute SHA-256 checksum of checkpoint
        file_bytes = final_ckpt_path.read_bytes()
        sha256 = hashlib.sha256(file_bytes).hexdigest()

        metadata = CheckpointMetadata(
            step=step,
            epoch=epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            model_config=model_config,
            training_config=training_config,
            checkpoint_file=ckpt_filename,
            sha256_hash=sha256,
            is_best=is_best,
        )

        final_meta_path.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")

        if is_best:
            best_ckpt_path = self.checkpoint_dir / "best_model.pt"
            best_meta_path = self.checkpoint_dir / "best_model_meta.json"
            best_ckpt_path.write_bytes(file_bytes)
            best_meta_path.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")

        self._prune_checkpoints()
        return final_ckpt_path

    def load_checkpoint(
        self,
        checkpoint_path: Path | str,
        model: nn.Module,
        optimizer: Optimizer | None = None,
    ) -> dict[str, Any]:
        """Restore model weights and training state from checkpoint file."""
        path = Path(checkpoint_path)
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {path}")

        # Check for matching metadata
        meta_path = path.with_name(path.stem + "_meta.json")
        metadata: dict[str, Any] = {}
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))

        state = torch.load(path, map_location="cpu", weights_only=False)
        model.load_state_dict(state["model_state_dict"])

        if optimizer is not None and state.get("optimizer_state_dict") is not None:
            optimizer.load_state_dict(state["optimizer_state_dict"])

        if "torch_rng_state" in state:
            torch.set_rng_state(state["torch_rng_state"])

        return {
            "step": state.get("step", 0),
            "epoch": state.get("epoch", 0),
            "train_loss": state.get("train_loss", 0.0),
            "val_loss": state.get("val_loss", None),
            "metadata": metadata,
        }

    def get_latest_checkpoint(self) -> Path | None:
        """Find the checkpoint with the highest step number in directory."""
        ckpts = sorted(self.checkpoint_dir.glob("checkpoint_step_*.pt"))
        if not ckpts:
            return None
        return ckpts[-1]

    def get_best_checkpoint(self) -> Path | None:
        """Find the designated best checkpoint."""
        best_path = self.checkpoint_dir / "best_model.pt"
        if best_path.exists():
            return best_path
        return self.get_latest_checkpoint()

    def _prune_checkpoints(self) -> None:
        """Retain only the last max_to_keep regular checkpoints."""
        ckpts = sorted(self.checkpoint_dir.glob("checkpoint_step_*.pt"))
        if len(ckpts) > self.max_to_keep:
            to_remove = ckpts[: len(ckpts) - self.max_to_keep]
            for p in to_remove:
                meta = p.with_name(p.stem + "_meta.json")
                if p.exists():
                    p.unlink()
                if meta.exists():
                    meta.unlink()
