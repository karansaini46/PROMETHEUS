"""Base Tool Protocol for Agent Tool-Calling."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """Schema descriptor for LLM tool binding."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


class BaseTool(ABC):
    """Abstract interface for agent tools."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the schema definition for this tool."""
        raise NotImplementedError

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with validated arguments."""
        raise NotImplementedError
