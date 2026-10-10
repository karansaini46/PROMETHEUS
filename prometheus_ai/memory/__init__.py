"""Memory and Persistence Subsystem Package."""

from abc import ABC, abstractmethod
from typing import Any


class BaseCheckpointer(ABC):
    """Abstract interface for checkpoint storage."""

    @abstractmethod
    async def save_checkpoint(self, thread_id: str, step: str, state: dict[str, Any]) -> None:
        """Persist state checkpoint."""
        raise NotImplementedError("Milestone 3 Deliverable: Checkpoint storage not yet configured.")

    @abstractmethod
    async def load_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        """Load latest checkpoint for thread."""
        raise NotImplementedError("Milestone 3 Deliverable: Checkpoint storage not yet configured.")
