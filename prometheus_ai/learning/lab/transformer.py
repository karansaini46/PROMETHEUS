"""Compact decoder-only transformer for educational experimentation.

Designed for resource-constrained local execution on CPU or optional GPU acceleration.
No external weights or pretrained checkpoints are downloaded.
"""

from __future__ import annotations

import math
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

from prometheus_ai.learning.lab.config import ModelConfig


class CausalSelfAttention(nn.Module):
    """Multi-head causal self-attention module."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        assert config.d_model % config.n_heads == 0, "d_model must be divisible by n_heads"

        self.n_heads = config.n_heads
        self.head_dim = config.d_model // config.n_heads
        self.d_model = config.d_model
        self.context_length = config.context_length

        # Key, query, value projections combined
        self.c_attn = nn.Linear(config.d_model, 3 * config.d_model, bias=False)
        # Output projection
        self.c_proj = nn.Linear(config.d_model, config.d_model, bias=False)

        # Regularization
        self.attn_dropout = nn.Dropout(config.dropout)
        self.resid_dropout = nn.Dropout(config.dropout)

        # Causal mask buffer
        mask = torch.tril(torch.ones(config.context_length, config.context_length))
        self.register_buffer("bias", mask.view(1, 1, config.context_length, config.context_length))
        self.bias: torch.Tensor

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, t, c = x.size()  # batch_size, seq_len, d_model

        # Calculate query, key, values for all heads in batch and move head forward to be the batch dim
        qkv = self.c_attn(x)
        q, k, v = qkv.chunk(3, dim=-1)

        q = q.view(b, t, self.n_heads, self.head_dim).transpose(1, 2)  # (b, nh, t, hs)
        k = k.view(b, t, self.n_heads, self.head_dim).transpose(1, 2)  # (b, nh, t, hs)
        v = v.view(b, t, self.n_heads, self.head_dim).transpose(1, 2)  # (b, nh, t, hs)

        # Scaled dot-product attention
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        att = att.masked_fill(self.bias[:, :, :t, :t] == 0, float("-inf"))
        att = F.softmax(att, dim=-1)
        att = self.attn_dropout(att)
        y = att @ v  # (b, nh, t, hs)

        # Re-assemble all head outputs side by side
        y = y.transpose(1, 2).contiguous().view(b, t, c)
        out: torch.Tensor = self.resid_dropout(self.c_proj(y))
        return out


class MLP(nn.Module):
    """Feed-forward network with GELU non-linearity."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.c_fc = nn.Linear(config.d_model, config.d_ff, bias=False)
        self.gelu = nn.GELU()
        self.c_proj = nn.Linear(config.d_ff, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.gelu(self.c_fc(x))
        out: torch.Tensor = self.dropout(self.c_proj(h))
        return out


class TransformerBlock(nn.Module):
    """Transformer decoder block with Pre-LayerNorm architecture."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.ln_1 = nn.LayerNorm(config.d_model)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = nn.LayerNorm(config.d_model)
        self.mlp = MLP(config)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln_1(x))
        x = x + self.mlp(self.ln_2(x))
        return x


class CompactDecoderOnlyTransformer(nn.Module):
    """Compact decoder-only transformer architecture for educational ML experimentation."""

    def __init__(self, config: ModelConfig, pad_token_id: int = 0) -> None:
        super().__init__()
        config.validate()
        self.config = config
        self.pad_token_id = pad_token_id

        self.tok_embeddings = nn.Embedding(config.vocab_size, config.d_model)
        self.pos_embeddings = nn.Embedding(config.context_length, config.d_model)
        self.drop = nn.Dropout(config.dropout)

        self.blocks = nn.ModuleList([TransformerBlock(config) for _ in range(config.n_layers)])
        self.ln_f = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        if config.tie_weights:
            self.lm_head.weight = self.tok_embeddings.weight

        # Parameter initialization
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
        elif isinstance(module, nn.LayerNorm):
            torch.nn.init.zeros_(module.bias)
            torch.nn.init.ones_(module.weight)

    def forward(
        self,
        idx: torch.Tensor,
        targets: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        device = idx.device
        _b, t = idx.size()

        if t > self.config.context_length:
            raise ValueError(
                f"Cannot forward sequence of length {t}, block size is {self.config.context_length}"
            )

        pos = torch.arange(0, t, dtype=torch.long, device=device).unsqueeze(0)  # shape (1, t)

        tok_emb = self.tok_embeddings(idx)  # (b, t, d_model)
        pos_emb = self.pos_embeddings(pos)  # (1, t, d_model)
        x = self.drop(tok_emb + pos_emb)

        for block in self.blocks:
            x = block(x)
        x = self.ln_f(x)
        logits = self.lm_head(x)  # (b, t, vocab_size)

        loss: torch.Tensor | None = None
        if targets is not None:
            loss = F.cross_entropy(
                logits.view(-1, logits.size(-1)),
                targets.view(-1),
                ignore_index=self.pad_token_id,
            )

        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        idx: torch.Tensor,
        max_new_tokens: int,
        temperature: float = 1.0,
        top_k: int | None = None,
        eos_token_id: int | None = None,
    ) -> torch.Tensor:
        """Autoregressively generate next tokens given a conditioning context."""
        for _ in range(max_new_tokens):
            # Crop current context if it exceeds context_length
            idx_cond = (
                idx
                if idx.size(1) <= self.config.context_length
                else idx[:, -self.config.context_length :]
            )

            logits, _ = self(idx_cond)
            # Focus only on the last step
            logits = logits[:, -1, :]

            if temperature <= 0.0:
                # Greedy decoding
                idx_next = torch.argmax(logits, dim=-1, keepdim=True)
            else:
                logits = logits / temperature
                if top_k is not None and top_k > 0:
                    v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                    logits[logits < v[:, [-1]]] = float("-inf")
                probs = F.softmax(logits, dim=-1)
                idx_next = torch.multinomial(probs, num_samples=1)

            idx = torch.cat((idx, idx_next), dim=1)

            if eos_token_id is not None and (idx_next == eos_token_id).all():
                break

        return idx

    def count_parameters(self, trainable_only: bool = True) -> int:
        """Count total or trainable parameters in model."""
        if trainable_only:
            return sum(p.numel() for p in self.parameters() if p.requires_grad)
        return sum(p.numel() for p in self.parameters())

    def get_summary(self) -> dict[str, Any]:
        """Return model architectural summary and parameter counts."""
        trainable = self.count_parameters(trainable_only=True)
        total = self.count_parameters(trainable_only=False)
        estimated_size_bytes = total * 4  # 32-bit floats
        return {
            "model_type": "CompactDecoderOnlyTransformer",
            "vocab_size": self.config.vocab_size,
            "context_length": self.config.context_length,
            "n_layers": self.config.n_layers,
            "n_heads": self.config.n_heads,
            "d_model": self.config.d_model,
            "d_ff": self.config.d_ff,
            "trainable_parameters": trainable,
            "total_parameters": total,
            "estimated_size_mb": round(estimated_size_bytes / (1024 * 1024), 4),
        }
