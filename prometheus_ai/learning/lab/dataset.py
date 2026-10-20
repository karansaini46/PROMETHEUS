"""Dataset registration, validation, splitting, and PyTorch dataset adapters.

Enforces strict data quality checks, documentation of origin/license/intended use,
and leak-proof train/validation/test partitioning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from prometheus_ai.learning.lab.config import DatasetConfig
from prometheus_ai.learning.lab.tokenizer import BaseTokenizer


class DatasetValidationError(Exception):
    """Raised when dataset fails structural, encoding, or format validation."""


class DataLeakageError(Exception):
    """Raised when overlap is detected between train, validation, or test partitions."""


@dataclass
class DatasetMetadata:
    """Detailed audit metadata for registered datasets."""

    name: str
    version: str
    origin: str
    license: str
    intended_use: str
    description: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    sha256_hash: str = ""
    total_samples: int = 0
    split_counts: dict[str, int] = field(default_factory=dict)
    preprocessing_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return asdict(self)


@dataclass
class DatasetSplits:
    """Encapsulates strictly partitioned dataset splits with metadata."""

    train: list[str]
    val: list[str]
    test: list[str]
    metadata: DatasetMetadata

    @property
    def total_count(self) -> int:
        return len(self.train) + len(self.val) + len(self.test)


class DatasetValidator:
    """Validates dataset formats, text bounds, and enforces zero-leakage partitions."""

    @staticmethod
    def validate_raw_texts(
        texts: list[str],
        min_samples: int = 1,
        min_chars_per_sample: int = 1,
        max_chars_per_sample: int = 50000,
    ) -> None:
        """Validate an iterable of text samples."""
        if not isinstance(texts, list):
            raise DatasetValidationError("Dataset must be provided as a list of strings")
        if len(texts) < min_samples:
            raise DatasetValidationError(
                f"Dataset contains {len(texts)} samples; minimum required is {min_samples}"
            )

        for idx, text in enumerate(texts):
            if not isinstance(text, str):
                raise DatasetValidationError(
                    f"Sample at index {idx} is type {type(text).__name__}, expected str"
                )
            stripped = text.strip()
            if len(stripped) < min_chars_per_sample:
                raise DatasetValidationError(
                    f"Sample at index {idx} has length {len(stripped)}, expected >= {min_chars_per_sample}"
                )
            if len(text) > max_chars_per_sample:
                raise DatasetValidationError(
                    f"Sample at index {idx} exceeds max allowed chars ({len(text)} > {max_chars_per_sample})"
                )
            if "\x00" in text:
                raise DatasetValidationError(f"Sample at index {idx} contains invalid null byte")

    @staticmethod
    def verify_no_leakage(
        train_texts: list[str],
        val_texts: list[str],
        test_texts: list[str],
    ) -> None:
        """Verify that no sample in train leaks into validation or test splits."""

        def _hash(t: str) -> str:
            return hashlib.sha256(t.strip().encode("utf-8")).hexdigest()

        train_hashes = {_hash(t): t for t in train_texts}
        val_hashes = {_hash(t): t for t in val_texts}
        test_hashes = {_hash(t): t for t in test_texts}

        train_val_overlap = set(train_hashes.keys()) & set(val_hashes.keys())
        if train_val_overlap:
            sample_preview = train_hashes[next(iter(train_val_overlap))][:80]
            raise DataLeakageError(
                f"Data leakage detected! {len(train_val_overlap)} samples overlap between "
                f"training and validation splits. Example: {sample_preview!r}"
            )

        train_test_overlap = set(train_hashes.keys()) & set(test_hashes.keys())
        if train_test_overlap:
            sample_preview = train_hashes[next(iter(train_test_overlap))][:80]
            raise DataLeakageError(
                f"Data leakage detected! {len(train_test_overlap)} samples overlap between "
                f"training and test splits. Example: {sample_preview!r}"
            )

        val_test_overlap = set(val_hashes.keys()) & set(test_hashes.keys())
        if val_test_overlap:
            sample_preview = val_hashes[next(iter(val_test_overlap))][:80]
            raise DataLeakageError(
                f"Data leakage detected! {len(val_test_overlap)} samples overlap between "
                f"validation and test splits. Example: {sample_preview!r}"
            )


class DatasetRegistry:
    """Registry for managing and versioning laboratory datasets."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._in_memory_registry: dict[str, DatasetSplits] = {}

    def register(
        self,
        config: DatasetConfig,
        samples: list[str],
        description: str = "",
        preprocessing_notes: str = "",
    ) -> DatasetSplits:
        """Register, validate, partition, and compute checksums for a dataset."""
        config.validate()

        # Deduplicate raw samples to guarantee pristine partitions
        unique_samples = list(dict.fromkeys(samples))
        if config.max_samples is not None:
            unique_samples = unique_samples[: config.max_samples]

        DatasetValidator.validate_raw_texts(unique_samples, min_samples=3)

        # Compute full dataset SHA-256
        combined_text = "\n".join(unique_samples)
        sha256 = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()

        # Compute split indices
        n = len(unique_samples)
        r_train, r_val, _r_test = config.split_ratios
        n_train = max(1, int(n * r_train))
        n_val = max(1, int(n * r_val))
        n_test = max(1, n - n_train - n_val)

        # Re-adjust if total exceeds n due to rounding
        while (n_train + n_val + n_test) > n:
            if n_train > 1:
                n_train -= 1
            elif n_val > 1:
                n_val -= 1
            else:
                break

        train_texts = unique_samples[:n_train]
        val_texts = unique_samples[n_train : n_train + n_val]
        test_texts = unique_samples[n_train + n_val : n_train + n_val + n_test]

        # Enforce zero leakage
        DatasetValidator.verify_no_leakage(train_texts, val_texts, test_texts)

        metadata = DatasetMetadata(
            name=config.name,
            version=config.version,
            origin=config.origin,
            license=config.license,
            intended_use=config.intended_use,
            description=description,
            sha256_hash=sha256,
            total_samples=n,
            split_counts={
                "train": len(train_texts),
                "val": len(val_texts),
                "test": len(test_texts),
            },
            preprocessing_notes=preprocessing_notes,
        )

        splits = DatasetSplits(
            train=train_texts,
            val=val_texts,
            test=test_texts,
            metadata=metadata,
        )

        key = f"{config.name}@{config.version}"
        self._in_memory_registry[key] = splits

        # Persist to disk if storage_dir is configured
        if self.storage_dir:
            ds_dir = self.storage_dir / config.name / config.version
            ds_dir.mkdir(parents=True, exist_ok=True)
            (ds_dir / "metadata.json").write_text(
                json.dumps(metadata.to_dict(), indent=2), encoding="utf-8"
            )
            (ds_dir / "train.txt").write_text("\n".join(train_texts), encoding="utf-8")
            (ds_dir / "val.txt").write_text("\n".join(val_texts), encoding="utf-8")
            (ds_dir / "test.txt").write_text("\n".join(test_texts), encoding="utf-8")

        return splits

    def get(self, name: str, version: str = "1.0.0") -> DatasetSplits:
        """Retrieve dataset splits by name and version."""
        key = f"{name}@{version}"
        if key in self._in_memory_registry:
            return self._in_memory_registry[key]

        if self.storage_dir:
            ds_dir = self.storage_dir / name / version
            meta_path = ds_dir / "metadata.json"
            if meta_path.exists():
                meta_dict = json.loads(meta_path.read_text(encoding="utf-8"))
                metadata = DatasetMetadata(**meta_dict)
                train_texts = (ds_dir / "train.txt").read_text(encoding="utf-8").splitlines()
                val_texts = (ds_dir / "val.txt").read_text(encoding="utf-8").splitlines()
                test_texts = (ds_dir / "test.txt").read_text(encoding="utf-8").splitlines()
                splits = DatasetSplits(
                    train=train_texts,
                    val=val_texts,
                    test=test_texts,
                    metadata=metadata,
                )
                self._in_memory_registry[key] = splits
                return splits

        raise KeyError(f"Dataset {key} not found in registry")

    def list_datasets(self) -> list[dict[str, Any]]:
        """List metadata summaries of all registered datasets."""
        results = []
        for _key, splits in self._in_memory_registry.items():
            results.append(splits.metadata.to_dict())
        return results


def create_synthetic_debug_corpus() -> list[str]:
    """Generate a clean synthetic educational corpus of Python bugs and fixes.

    License: Apache-2.0
    Origin: Synthetic educational dataset for PROMETHEUS ML laboratory.
    Intended Use: Educational tokenization and small-model training experiments.
    """
    corpus = [
        "BUG: NameError 'x' is not defined. CODE: print(x) FIX: x = 10; print(x)",
        "BUG: ZeroDivisionError division by zero. CODE: y = 5 / 0 FIX: y = 5 / max(d, 1)",
        "BUG: IndexError list index out of range. CODE: a = [1]; print(a[5]) FIX: if len(a) > 5: print(a[5])",
        "BUG: KeyError 'token' not in dict. CODE: v = data['token'] FIX: v = data.get('token', None)",
        "BUG: TypeError unsupported operand + for int and str. CODE: z = 1 + '2' FIX: z = 1 + int('2')",
        "BUG: AttributeError 'NoneType' has no attribute 'get'. CODE: res.get('k') FIX: if res is not None: res.get('k')",
        "BUG: ValueError invalid literal for int() with base 10: 'abc'. CODE: int('abc') FIX: try: int(s) except ValueError: pass",
        "BUG: RecursionError maximum recursion depth exceeded. CODE: def f(): f() FIX: add base case to terminate recursion",
        "BUG: UnboundLocalError local variable referenced before assignment. CODE: count += 1 FIX: global count; count += 1",
        "BUG: FileNotFoundError no such file. CODE: open('missing.txt') FIX: if os.path.exists('missing.txt'): open('missing.txt')",
        "BUG: SyntaxError invalid syntax. CODE: if True print(1) FIX: if True: print(1)",
        "BUG: IndentationError unexpected indent. CODE:  x = 1 FIX: x = 1",
        "BUG: TimeoutError operation timed out. CODE: sock.connect(addr) FIX: sock.settimeout(5.0); sock.connect(addr)",
        "BUG: PermissionError permission denied. CODE: open('/root/sys', 'w') FIX: check file permissions and user privileges",
        "BUG: AssertionError assertion failed. CODE: assert x == 4 FIX: assert x == expected_value",
        "BUG: OverflowError math range error. CODE: math.exp(1000) FIX: clip input to avoid exponential overflow",
    ]
    return corpus


class TokenizedDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """PyTorch Dataset that maps texts to next-token prediction sequence pairs."""

    def __init__(
        self,
        texts: list[str],
        tokenizer: BaseTokenizer,
        context_length: int,
    ) -> None:
        self.tokenizer = tokenizer
        self.context_length = context_length
        self.samples: list[tuple[torch.Tensor, torch.Tensor]] = []

        pad_id = tokenizer.pad_token_id

        for text in texts:
            # Tokenize with special BOS and EOS tokens
            tokens = tokenizer.encode(text, add_special_tokens=True)
            if len(tokens) < 2:
                continue

            # Crop or pad to context_length + 1 tokens
            target_len = context_length + 1
            if len(tokens) < target_len:
                tokens = tokens + [pad_id] * (target_len - len(tokens))
            else:
                tokens = tokens[:target_len]

            # x = input tokens, y = target tokens shifted right
            x = torch.tensor(tokens[:-1], dtype=torch.long)
            y = torch.tensor(tokens[1:], dtype=torch.long)
            self.samples.append((x, y))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.samples[idx]
