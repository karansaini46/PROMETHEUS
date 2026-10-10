"""Autonomous Debugging Agent State Schemas."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """State schema for the LangGraph cyclic debugging workflow."""

    run_id: str
    issue_description: str
    worktree_path: str
    hypotheses: list[str] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)
    reproduce_script: str | None = None
    patch_diff: str | None = None
    sandbox_logs: list[str] = field(default_factory=list)
    iteration_count: int = 0
    resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
