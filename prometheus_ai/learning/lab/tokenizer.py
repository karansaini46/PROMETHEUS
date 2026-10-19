"""Lightweight, self-contained tokenizers for the PROMETHEUS ML Laboratory.

Provides character-level and token-based tokenizers suitable for compact
transformer experiments without downloading external tokenizer weights.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseTokenizer(ABC):
    """Abstract base class for lab tokenizers."""

    @property
    @abstractmethod
    def vocab_size(self) -> int:
        """Return the size of the vocabulary."""

    @property
    @abstractmethod
    def pad_token_id(self) -> int:
        """Return pad token id."""

    @property
    @abstractmethod
    def unk_token_id(self) -> int:
        """Return unknown token id."""

    @property
    @abstractmethod
    def bos_token_id(self) -> int:
        """Return beginning of sequence token id."""

    @property
    @abstractmethod
    def eos_token_id(self) -> int:
        """Return end of sequence token id."""

    @abstractmethod
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        """Convert string to list of token IDs."""

    @abstractmethod
    def decode(self, token_ids: list[int], skip_special_tokens: bool = True) -> str:
        """Convert list of token IDs back to string."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize tokenizer configuration and vocabulary."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseTokenizer:
        """Instantiate tokenizer from serialized dictionary."""

    def save(self, file_path: Path | str) -> None:
        """Save tokenizer configuration to file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, file_path: Path | str) -> BaseTokenizer:
        """Load tokenizer from JSON file."""
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        tokenizer_type = data.get("type", "CharTokenizer")
        if tokenizer_type == "CharTokenizer":
            return CharTokenizer.from_dict(data)
        raise ValueError(f"Unknown tokenizer type: {tokenizer_type}")


class CharTokenizer(BaseTokenizer):
    """Deterministic character-level tokenizer with special tokens.

    Supports building vocabulary from arbitrary texts or standard printable ASCII characters.
    Special tokens default to:
        <pad>: 0
        <unk>: 1
        <bos>: 2
        <eos>: 3
    """

    PAD_TOKEN = "<pad>"
    UNK_TOKEN = "<unk>"
    BOS_TOKEN = "<bos>"
    EOS_TOKEN = "<eos>"

    def __init__(self, chars: list[str] | None = None) -> None:
        """Initialize character tokenizer.

        If chars is None, a standard ASCII character set is used.
        """
        self.special_tokens = [self.PAD_TOKEN, self.UNK_TOKEN, self.BOS_TOKEN, self.EOS_TOKEN]

        if chars is None:
            # Standard ASCII printable set + tab + newline + carriage return
            ascii_chars = [chr(i) for i in range(32, 127)]
            extra_chars = ["\n", "\t", "\r"]
            chars = sorted(set(ascii_chars + extra_chars))
        else:
            chars = sorted(set(chars) - set(self.special_tokens))

        self.vocab: list[str] = list(self.special_tokens) + chars
        self.token_to_id: dict[str, int] = {tok: idx for idx, tok in enumerate(self.vocab)}
        self.id_to_token: dict[int, str] = dict(enumerate(self.vocab))

    @property
    def vocab_size(self) -> int:
        """Return the size of the vocabulary."""
        return len(self.vocab)

    @property
    def pad_token_id(self) -> int:
        """Return pad token id."""
        return self.token_to_id[self.PAD_TOKEN]

    @property
    def unk_token_id(self) -> int:
        """Return unknown token id."""
        return self.token_to_id[self.UNK_TOKEN]

    @property
    def bos_token_id(self) -> int:
        """Return beginning of sequence token id."""
        return self.token_to_id[self.BOS_TOKEN]

    @property
    def eos_token_id(self) -> int:
        """Return end of sequence token id."""
        return self.token_to_id[self.EOS_TOKEN]

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        """Convert string to token IDs."""
        ids: list[int] = []
        if add_special_tokens:
            ids.append(self.bos_token_id)

        for ch in text:
            ids.append(self.token_to_id.get(ch, self.unk_token_id))

        if add_special_tokens:
            ids.append(self.eos_token_id)
        return ids

    def decode(self, token_ids: list[int], skip_special_tokens: bool = True) -> str:
        """Convert token IDs back to string."""
        specials = {self.pad_token_id, self.unk_token_id, self.bos_token_id, self.eos_token_id}
        chars: list[str] = []
        for tid in token_ids:
            if skip_special_tokens and tid in specials:
                continue
            token_str = self.id_to_token.get(tid, "")
            if skip_special_tokens and token_str in self.special_tokens:
                continue
            chars.append(token_str)
        return "".join(chars)

    def to_dict(self) -> dict[str, Any]:
        """Serialize tokenizer state to dictionary."""
        return {
            "type": "CharTokenizer",
            "vocab": self.vocab,
            "vocab_size": self.vocab_size,
            "special_tokens": self.special_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharTokenizer:
        """Instantiate CharTokenizer from dictionary."""
        vocab = data["vocab"]
        special_tokens = data.get(
            "special_tokens", [cls.PAD_TOKEN, cls.UNK_TOKEN, cls.BOS_TOKEN, cls.EOS_TOKEN]
        )
        chars = [v for v in vocab if v not in special_tokens]
        return cls(chars=chars)

    @classmethod
    def from_corpus(cls, texts: list[str]) -> CharTokenizer:
        """Construct a CharTokenizer with characters observed in a corpus."""
        unique_chars = sorted(set("".join(texts)))
        return cls(chars=unique_chars)
