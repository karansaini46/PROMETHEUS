"""Model evaluation and inference benchmarking for the PROMETHEUS ML Lab.

Evaluates loss, perplexity, and token accuracy on held-out data partitions,
and measures inference latency percentiles and token throughput.
"""

from __future__ import annotations

import statistics
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from prometheus_ai.learning.lab.metrics import (
    InferenceBenchmarkMetrics,
    ValidationMetrics,
    calculate_perplexity,
    get_peak_memory_mb,
)
from prometheus_ai.learning.lab.tokenizer import BaseTokenizer


class LabEvaluator:
    """Evaluates transformer checkpoints and benchmarks inference performance."""

    @staticmethod
    @torch.no_grad()
    def evaluate(
        model: nn.Module,
        dataloader: DataLoader[tuple[torch.Tensor, torch.Tensor]],
        tokenizer: BaseTokenizer,
        device: torch.device | str = "cpu",
        split_name: str = "validation",
        sample_prompts: list[str] | None = None,
        max_generate_tokens: int = 24,
    ) -> ValidationMetrics:
        """Evaluate model loss, perplexity, and token accuracy across dataloader batches."""
        model.eval()
        device_obj = torch.device(device)
        model.to(device_obj)

        total_loss = 0.0
        total_tokens = 0
        correct_tokens = 0
        num_batches = 0

        start_time = time.perf_counter()

        for x, y in dataloader:
            x, y = x.to(device_obj), y.to(device_obj)
            logits, loss = model(x, targets=y)
            if loss is not None:
                total_loss += loss.item()
                num_batches += 1

            # Compute next-token accuracy excluding padding tokens
            preds = torch.argmax(logits, dim=-1)
            valid_mask = y != tokenizer.pad_token_id
            num_valid = valid_mask.sum().item()
            if num_valid > 0:
                correct = ((preds == y) & valid_mask).sum().item()
                correct_tokens += int(correct)
                total_tokens += int(num_valid)

        avg_loss = total_loss / max(num_batches, 1)
        perplexity = calculate_perplexity(avg_loss)
        accuracy = (correct_tokens / total_tokens) if total_tokens > 0 else 0.0
        elapsed = time.perf_counter() - start_time

        # Generate sample completions if prompts provided
        completions: list[str] = []
        if sample_prompts:
            for prompt in sample_prompts:
                prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
                if not prompt_ids:
                    continue
                input_tensor = torch.tensor([prompt_ids], dtype=torch.long, device=device_obj)
                generate_fn = getattr(model, "generate", None)
                if callable(generate_fn):
                    out = generate_fn(
                        input_tensor,
                        max_new_tokens=max_generate_tokens,
                        temperature=0.8,
                        top_k=20,
                        eos_token_id=tokenizer.eos_token_id,
                    )
                    gen_text = tokenizer.decode(out[0].tolist(), skip_special_tokens=True)
                    completions.append(f"Prompt: {prompt!r} -> Completion: {gen_text!r}")

        return ValidationMetrics(
            step=0,
            epoch=0,
            val_loss=round(avg_loss, 4),
            val_perplexity=round(perplexity, 4),
            token_accuracy=round(accuracy, 4),
            eval_duration_seconds=round(elapsed, 4),
            split_name=split_name,
            sample_generations=completions,
        )

    @staticmethod
    @torch.no_grad()
    def benchmark_inference(
        model: nn.Module,
        tokenizer: BaseTokenizer,
        prompt: str = "BUG: ",
        max_new_tokens: int = 32,
        batch_size: int = 1,
        iterations: int = 10,
        warmup_iterations: int = 3,
        device: torch.device | str = "cpu",
    ) -> InferenceBenchmarkMetrics:
        """Measure inference latency percentiles and token throughput."""
        model.eval()
        device_obj = torch.device(device)
        model.to(device_obj)

        prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
        if not prompt_ids:
            prompt_ids = [tokenizer.bos_token_id]

        input_batch = torch.tensor([prompt_ids], dtype=torch.long, device=device_obj).repeat(
            batch_size, 1
        )
        prompt_tokens = input_batch.size(1)

        generate_fn = getattr(model, "generate", None)

        # Warmup passes
        for _ in range(warmup_iterations):
            if callable(generate_fn):
                _ = generate_fn(
                    input_batch,
                    max_new_tokens=min(max_new_tokens, 8),
                    temperature=0.0,
                )

        latencies_ms: list[float] = []
        total_tokens_generated = 0

        for _ in range(iterations):
            t0 = time.perf_counter()
            if callable(generate_fn):
                out = generate_fn(
                    input_batch,
                    max_new_tokens=max_new_tokens,
                    temperature=0.0,
                )
                tokens_produced = out.size(1) - prompt_tokens
            else:
                out = model(input_batch)[0]
                tokens_produced = 1

            if device_obj.type == "cuda":
                torch.cuda.synchronize()

            t1 = time.perf_counter()
            elapsed_ms = (t1 - t0) * 1000.0
            latencies_ms.append(elapsed_ms)
            total_tokens_generated += tokens_produced * batch_size

        latencies_ms.sort()
        mean_lat = statistics.mean(latencies_ms)
        p50 = statistics.median(latencies_ms)
        p90 = (
            latencies_ms[int(0.9 * len(latencies_ms))]
            if len(latencies_ms) >= 10
            else latencies_ms[-1]
        )
        p99 = latencies_ms[-1]

        total_elapsed_sec = sum(latencies_ms) / 1000.0
        throughput = (total_tokens_generated / total_elapsed_sec) if total_elapsed_sec > 0 else 0.0

        model_params = sum(p.numel() for p in model.parameters())
        model_size_mb = (model_params * 4) / (1024 * 1024)

        return InferenceBenchmarkMetrics(
            model_type=model.__class__.__name__,
            device=str(device_obj),
            batch_size=batch_size,
            prompt_tokens=prompt_tokens,
            generated_tokens=max_new_tokens,
            total_tokens=prompt_tokens + max_new_tokens,
            iterations=iterations,
            latency_ms_mean=round(mean_lat, 2),
            latency_ms_p50=round(p50, 2),
            latency_ms_p90=round(p90, 2),
            latency_ms_p99=round(p99, 2),
            throughput_tokens_per_sec=round(throughput, 2),
            model_size_mb=round(model_size_mb, 4),
            peak_memory_mb=get_peak_memory_mb(),
        )
