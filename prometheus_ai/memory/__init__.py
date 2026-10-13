"""Memory and Persistence Subsystem Package."""

from abc import ABC, abstractmethod
from typing import Any

from prometheus_ai.memory.embedder import BaseEmbedder, DeterministicHashEmbedder
from prometheus_ai.memory.manager import MemoryManager
from prometheus_ai.memory.sanitizer import (
    format_untrusted_operational_context,
    sanitize_instruction_text,
)
from prometheus_ai.memory.schema import (
    MemoryFilter,
    MemoryRecord,
    MemoryRecordCreate,
    MemoryType,
    VerificationStatus,
)


class BaseCheckpointer(ABC):
    """Abstract interface for checkpoint storage (kept for backwards compatibility)."""

    @abstractmethod
    async def save_checkpoint(self, thread_id: str, step: str, state: dict[str, Any]) -> None:
        """Persist state checkpoint."""
        raise NotImplementedError

    @abstractmethod
    async def load_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        """Load latest checkpoint for thread."""
        raise NotImplementedError


__all__ = [
    "BaseCheckpointer",
    "BaseEmbedder",
    "DeterministicHashEmbedder",
    "MemoryFilter",
    "MemoryManager",
    "MemoryRecord",
    "MemoryRecordCreate",
    "MemoryType",
    "VerificationStatus",
    "format_untrusted_operational_context",
    "sanitize_instruction_text",
]
