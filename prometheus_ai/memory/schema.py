"""Data models, types, and schemas for the PROMETHEUS Memory Subsystem."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class MemoryType(StrEnum):
    """Authoritative memory classifications."""

    EPISODIC = "episodic"  # Previous investigations, tool actions, outcomes, and failures
    SEMANTIC = "semantic"  # Stable technical facts, repository documentation, verified architecture
    PROCEDURAL = "procedural"  # Reusable investigation strategies and workflows
    OPERATIONAL = "operational"  # Repository setup requirements, test constraints, environment instructions


class VerificationStatus(StrEnum):
    """Trust and provenance verification levels."""

    OBSERVED = "observed"  # Direct empirical tool or sandbox observation
    VERIFIED = "verified"  # Verified by deterministic test execution or human approval
    UNVERIFIED = "unverified"  # Proposed knowledge awaiting verification
    HYPOTHESIS = "hypothesis"  # Model-generated hypothesis (unverified by definition)
    INVALIDATED = "invalidated"  # Deprecated due to repository revision change or rule trigger


class MemoryRecord(BaseModel):
    """Canonical memory record entity with provenance, trust, and invalidation rules."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    memory_type: MemoryType
    key: str = Field(description="Short identifier or topic for lexical indexing")
    content: str = Field(description="Memory content, insight, or instruction")
    project_id: str | None = Field(default=None, description="Owning project ID for isolation")
    task_id: str | None = Field(default=None, description="Source task identifier")
    run_id: str | None = Field(default=None, description="Source execution run identifier")
    repo_path: str | None = Field(default=None, description="Repository filesystem or URL reference")
    revision: str | None = Field(default=None, description="Commit SHA or version where recorded")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence references")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score")
    verification_status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED)
    is_hypothesis: bool = Field(default=False, description="Flag distinguishing hypothesis from fact")
    is_untrusted_instruction: bool = Field(
        default=False,
        description="Flag indicating operational instructions that must not be executed blindly",
    )
    expires_at: datetime | None = Field(default=None, description="Optional time-based expiration")
    invalidation_rules: dict[str, Any] = Field(
        default_factory=dict,
        description="Version or event invalidation rules (e.g. pinned_revision, invalidate_on_revision_change)",
    )
    embedding: list[float] | None = Field(default=None, description="384-dim semantic embedding vector")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_trust_invariants(self) -> "MemoryRecord":
        """Enforce trust boundary: hypotheses cannot be promoted to verified fact on creation."""
        # Never promote a proposed solution to a verified fact merely because the model repeated it
        if self.is_hypothesis and self.verification_status == VerificationStatus.VERIFIED:
            raise ValueError(
                "Trust violation: Model-generated hypotheses cannot be marked as VERIFIED without empirical evidence."
            )

        # Operational memories represent external repository instructions and are untrusted by default
        if self.memory_type == MemoryType.OPERATIONAL:
            self.is_untrusted_instruction = True

        return self

    def is_expired(self, as_of: datetime | None = None) -> bool:
        """Check whether the memory has passed its TTL expiration timestamp."""
        if not self.expires_at:
            return False
        current_time = as_of or datetime.now(UTC)
        return current_time > self.expires_at

    def is_invalidated_for_revision(self, current_revision: str | None) -> bool:
        """Check whether the memory has been invalidated by a revision change."""
        if self.verification_status == VerificationStatus.INVALIDATED:
            return True

        # Check explicit pinned revision in invalidation rules
        pinned = self.invalidation_rules.get("pinned_revision") or self.revision
        invalidate_on_change = self.invalidation_rules.get("invalidate_on_revision_change", False)

        if invalidate_on_change and pinned and current_revision and pinned != current_revision:
            return True

        return False


class MemoryRecordCreate(BaseModel):
    """Payload for creating a new memory record."""

    memory_type: MemoryType
    key: str
    content: str
    project_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    repo_path: str | None = None
    revision: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    is_hypothesis: bool = False
    expires_at: datetime | None = None
    invalidation_rules: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class MemoryFilter(BaseModel):
    """Query filters for memory retrieval."""

    query: str | None = None
    project_id: str | None = None
    memory_type: MemoryType | None = None
    current_revision: str | None = None
    min_confidence: float = 0.0
    exclude_unverified: bool = False
    exclude_hypotheses: bool = False
    include_cross_project: bool = False
    cross_project_reason: str | None = None
    limit: int = 10
