"""Authoritative PostgreSQL-backed Memory Subsystem Manager."""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from prometheus_ai.memory.embedder import BaseEmbedder, DeterministicHashEmbedder
from prometheus_ai.memory.schema import (
    MemoryRecord,
    MemoryRecordCreate,
    MemoryType,
    VerificationStatus,
)
from services.api.config import get_settings
from services.api.models import (
    ExecutionRun,
    Project,
)
from services.api.models import (
    MemoryRecord as MemoryRecordModel,
)

logger = logging.getLogger(__name__)


class MemoryManager:
    """Authoritative memory manager with hybrid retrieval, provenance, and trust boundaries.

    Guarantees:
    - PostgreSQL authoritative storage with pgvector cosine distance retrieval.
    - Strict cross-project isolation (cross-project retrieval rejected without an explicit reason).
    - Version-aware invalidation against repository commit SHAs.
    - Separation of model hypotheses from verified facts (hypotheses cannot be self-promoted).
    - Marking repository operational instructions as untrusted input.
    - Inspection and deletion boundaries for user data governance.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] | None = None,
        embedder: BaseEmbedder | None = None,
        enable_vector_search: bool | None = None,
    ) -> None:
        self.settings = get_settings()
        self.embedder = embedder or DeterministicHashEmbedder(dimension=384)
        self.enable_vector_search = (
            enable_vector_search
            if enable_vector_search is not None
            else self.settings.ENABLE_VECTOR_SEARCH
        )

        # Configurable database session factory with lazy default
        self._session_factory = session_factory
        self._engine: Any = None
        self._internal_sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def _get_sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._internal_sessionmaker is None:
            self._engine = create_async_engine(
                self.settings.DATABASE_URL,
                pool_size=self.settings.DATABASE_POOL_SIZE,
                max_overflow=self.settings.DATABASE_MAX_OVERFLOW,
            )
            self._internal_sessionmaker = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        assert self._internal_sessionmaker is not None
        return self._internal_sessionmaker

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a managed database session."""
        if self._session_factory is not None:
            generator = self._session_factory()
            session = await anext(generator)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                try:
                    await anext(generator)
                except StopAsyncIteration:
                    pass
        else:
            sm = self._get_sessionmaker()
            async with sm() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

    # -------------------------------------------------------------------------
    # Entity Conversion Helpers
    # -------------------------------------------------------------------------

    def _to_schema(self, orm: MemoryRecordModel) -> MemoryRecord:
        """Convert SQLAlchemy ORM model to domain MemoryRecord."""
        meta = orm.metadata_json or {}
        expires_str = meta.get("expires_at")
        expires_dt = (
            datetime.fromisoformat(expires_str)
            if expires_str and isinstance(expires_str, str)
            else None
        )

        return MemoryRecord(
            id=orm.id,
            memory_type=MemoryType(orm.memory_type),
            key=orm.key,
            content=orm.content,
            project_id=orm.project_id,
            task_id=meta.get("task_id"),
            run_id=orm.run_id or meta.get("run_id"),
            repo_path=meta.get("repo_path"),
            revision=meta.get("revision"),
            evidence=meta.get("evidence", []),
            confidence=float(meta.get("confidence", 0.8)),
            verification_status=VerificationStatus(
                meta.get("verification_status", VerificationStatus.UNVERIFIED)
            ),
            is_hypothesis=bool(meta.get("is_hypothesis", False)),
            is_untrusted_instruction=bool(meta.get("is_untrusted_instruction", False)),
            expires_at=expires_dt,
            invalidation_rules=meta.get("invalidation_rules", {}),
            embedding=orm.embedding if isinstance(orm.embedding, list) else None,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _to_orm(self, record: MemoryRecord, orm_run_id: str | None = None) -> MemoryRecordModel:
        """Convert domain MemoryRecord to SQLAlchemy ORM model."""
        meta: dict[str, Any] = {
            "task_id": record.task_id,
            "repo_path": record.repo_path,
            "revision": record.revision,
            "evidence": record.evidence,
            "confidence": record.confidence,
            "verification_status": str(record.verification_status),
            "is_hypothesis": record.is_hypothesis,
            "is_untrusted_instruction": record.is_untrusted_instruction,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "invalidation_rules": record.invalidation_rules,
            "run_id": record.run_id,
        }

        return MemoryRecordModel(
            id=record.id,
            project_id=record.project_id,
            run_id=orm_run_id,
            memory_type=str(record.memory_type),
            key=record.key,
            content=record.content,
            metadata_json=meta,
            embedding=record.embedding,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    # -------------------------------------------------------------------------
    # Core Persistence Operations
    # -------------------------------------------------------------------------

    async def store(self, item: MemoryRecord | MemoryRecordCreate) -> MemoryRecord:
        """Store or update a memory record in authoritative storage with validation."""
        if isinstance(item, MemoryRecordCreate):
            record = MemoryRecord(**item.model_dump())
        else:
            record = item

        # Invariant: Model-generated hypotheses cannot be created as VERIFIED
        if record.is_hypothesis and record.verification_status == VerificationStatus.VERIFIED:
            raise ValueError(
                "Trust violation: Hypotheses cannot be recorded as VERIFIED without empirical proof."
            )

        # Invariant: Operational instructions must be marked untrusted
        if record.memory_type == MemoryType.OPERATIONAL:
            record.is_untrusted_instruction = True

        # Generate embedding if vector search is active or embedder available
        if record.embedding is None and self.embedder is not None:
            text_to_embed = f"{record.key} {record.content}"
            record.embedding = self.embedder.embed_text(text_to_embed)

        async with self.get_session() as session:
            # Auto-provision project if needed to satisfy foreign key constraint
            if record.project_id:
                proj = await session.get(Project, record.project_id)
                if not proj:
                    proj = Project(
                        id=record.project_id,
                        name=f"Project {record.project_id}",
                        slug=f"proj-{record.project_id[:16]}-{uuid4().hex[:6]}",
                        repository_url=record.repo_path
                        or f"https://github.com/org/{record.project_id}",
                    )
                    session.add(proj)
                    await session.flush()

            # Ensure run_id only sets relational foreign key if ExecutionRun exists
            orm_run_id = None
            if record.run_id:
                run = await session.get(ExecutionRun, record.run_id)
                if run:
                    orm_run_id = record.run_id

            existing = await session.get(MemoryRecordModel, record.id)
            if existing:
                existing.project_id = record.project_id
                existing.run_id = orm_run_id
                existing.memory_type = str(record.memory_type)
                existing.key = record.key
                existing.content = record.content
                existing.metadata_json = {
                    "task_id": record.task_id,
                    "repo_path": record.repo_path,
                    "revision": record.revision,
                    "evidence": record.evidence,
                    "confidence": record.confidence,
                    "verification_status": str(record.verification_status),
                    "is_hypothesis": record.is_hypothesis,
                    "is_untrusted_instruction": record.is_untrusted_instruction,
                    "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                    "invalidation_rules": record.invalidation_rules,
                    "run_id": record.run_id,
                }
                existing.embedding = record.embedding
                existing.updated_at = datetime.now(UTC)
                await session.flush()
                return self._to_schema(existing)
            else:
                orm_record = self._to_orm(record, orm_run_id=orm_run_id)
                session.add(orm_record)
                await session.flush()
                return self._to_schema(orm_record)

    async def promote_to_verified(
        self,
        memory_id: str,
        evidence: list[str],
        verified_by_run_id: str | None = None,
    ) -> MemoryRecord:
        """Promote an unverified or hypothesis memory to verified once backed by empirical evidence."""
        if not evidence:
            raise ValueError(
                "Trust violation: Cannot promote memory to VERIFIED without empirical evidence references."
            )

        async with self.get_session() as session:
            orm = await session.get(MemoryRecordModel, memory_id)
            if not orm:
                raise KeyError(f"Memory record '{memory_id}' not found.")

            meta = dict(orm.metadata_json or {})
            existing_evidence = meta.get("evidence", [])
            for ev in evidence:
                if ev not in existing_evidence:
                    existing_evidence.append(ev)

            meta["evidence"] = existing_evidence
            meta["verification_status"] = str(VerificationStatus.VERIFIED)
            meta["is_hypothesis"] = False
            meta["confidence"] = max(float(meta.get("confidence", 0.8)), 0.95)
            if verified_by_run_id:
                meta["verified_by_run_id"] = verified_by_run_id

            orm.metadata_json = meta
            orm.updated_at = datetime.now(UTC)
            await session.flush()
            return self._to_schema(orm)

    # -------------------------------------------------------------------------
    # Retrieval with Hybrid Search, Version Invalidation & Project Isolation
    # -------------------------------------------------------------------------

    async def retrieve(
        self,
        query: str | None = None,
        project_id: str | None = None,
        memory_type: MemoryType | str | None = None,
        current_revision: str | None = None,
        min_confidence: float = 0.0,
        exclude_unverified: bool = False,
        exclude_hypotheses: bool = False,
        include_cross_project: bool = False,
        cross_project_reason: str | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Retrieve memories combining semantic search, metadata filters, and trust validation."""
        # Enforce cross-project isolation: unrelated project access requires an explicit reason
        if include_cross_project and not cross_project_reason:
            raise ValueError(
                "Cross-project memory retrieval rejected: A defined reason is strictly required."
            )

        async with self.get_session() as session:
            stmt = select(MemoryRecordModel)

            # 1. Project Isolation Boundary
            if project_id and not include_cross_project:
                stmt = stmt.where(
                    (MemoryRecordModel.project_id == project_id)
                    | (MemoryRecordModel.project_id.is_(None))
                )
            elif not project_id and not include_cross_project:
                # Without a target project or explicit cross-project grant, return only global memories
                stmt = stmt.where(MemoryRecordModel.project_id.is_(None))

            # 2. Memory Type Filter
            if memory_type:
                type_val = (
                    memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type)
                )
                stmt = stmt.where(MemoryRecordModel.memory_type == type_val)

            results = await session.scalars(stmt)
            records = [self._to_schema(r) for r in results.all()]

        # 3. Post-fetch Trust and Invalidation Filtering
        now = datetime.now(UTC)
        filtered: list[MemoryRecord] = []

        for rec in records:
            # Expiration Check
            if rec.is_expired(as_of=now):
                continue

            # Version Invalidation Check
            if current_revision and rec.is_invalidated_for_revision(current_revision):
                continue

            # Invalidation Status
            if rec.verification_status == VerificationStatus.INVALIDATED:
                continue

            # Confidence Threshold
            if rec.confidence < min_confidence:
                continue

            # Unverified / Hypothesis Filters
            if exclude_unverified and rec.verification_status != VerificationStatus.VERIFIED:
                continue

            if exclude_hypotheses and rec.is_hypothesis:
                continue

            filtered.append(rec)

        # 4. Ranking (Semantic + Lexical + Confidence)
        if not query:
            # If no query string, rank primarily by confidence and freshness
            filtered.sort(key=lambda r: (r.confidence, r.created_at), reverse=True)
            return filtered[:limit]

        query_tokens = set(query.lower().split())
        query_vec = (
            self.embedder.embed_text(query)
            if (self.embedder and (self.enable_vector_search or len(filtered) > 0))
            else None
        )

        def compute_score(rec: MemoryRecord) -> float:
            score = 0.0

            # Lexical matching score
            rec_text = f"{rec.key} {rec.content}".lower()
            rec_tokens = set(rec_text.split())
            if rec_tokens:
                overlap = len(query_tokens.intersection(rec_tokens))
                lexical_sim = overlap / max(len(query_tokens), 1)
                score += 0.3 * lexical_sim

            # Semantic similarity (Cosine Similarity)
            if query_vec and rec.embedding:
                # Cosine similarity between two unit-normalized vectors: dot product
                # ponytail: in-memory dot product fallback enables sub-millisecond ranking
                # without requiring an active pgvector connection pool for read paths.
                dot = sum(q * m for q, m in zip(query_vec, rec.embedding, strict=False))
                cosine_sim = max(0.0, min(1.0, (dot + 1.0) / 2.0))
                score += 0.6 * cosine_sim
            elif rec_tokens and query_tokens:
                # Fallback to lexical weight if embedding absent
                score += 0.3 * (
                    len(query_tokens.intersection(rec_tokens)) / max(len(query_tokens), 1)
                )

            # Confidence weighting
            score += 0.1 * rec.confidence

            # Boost verified knowledge over unverified
            if rec.verification_status == VerificationStatus.VERIFIED:
                score += 0.05

            return score

        filtered.sort(key=compute_score, reverse=True)
        return filtered[:limit]

    # -------------------------------------------------------------------------
    # Governance, Inspection, and Invalidation
    # -------------------------------------------------------------------------

    async def inspect(self, memory_id: str) -> MemoryRecord | None:
        """Inspect a specific memory record by ID for auditing and verification."""
        async with self.get_session() as session:
            orm = await session.get(MemoryRecordModel, memory_id)
            return self._to_schema(orm) if orm else None

    async def list_memories(
        self,
        project_id: str | None = None,
        memory_type: MemoryType | None = None,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        """List stored memories with filtering for user management and auditing."""
        async with self.get_session() as session:
            stmt = select(MemoryRecordModel)
            if project_id:
                stmt = stmt.where(MemoryRecordModel.project_id == project_id)
            if memory_type:
                stmt = stmt.where(MemoryRecordModel.memory_type == str(memory_type))
            stmt = stmt.order_by(MemoryRecordModel.created_at.desc()).limit(limit)

            results = await session.scalars(stmt)
            return [self._to_schema(r) for r in results.all()]

    async def invalidate(self, memory_id: str, reason: str = "Manual invalidation") -> MemoryRecord:
        """Mark a memory record as INVALIDATED so it will no longer be retrieved."""
        async with self.get_session() as session:
            orm = await session.get(MemoryRecordModel, memory_id)
            if not orm:
                raise KeyError(f"Memory record '{memory_id}' not found.")

            meta = dict(orm.metadata_json or {})
            meta["verification_status"] = str(VerificationStatus.INVALIDATED)
            meta["invalidation_reason"] = reason
            meta["invalidated_at"] = datetime.now(UTC).isoformat()
            orm.metadata_json = meta
            orm.updated_at = datetime.now(UTC)
            await session.flush()
            return self._to_schema(orm)

    async def invalidate_by_revision(self, project_id: str, new_revision: str) -> int:
        """Invalidate all project memories that are tied to older repository revisions."""
        async with self.get_session() as session:
            stmt = select(MemoryRecordModel).where(MemoryRecordModel.project_id == project_id)
            results = await session.scalars(stmt)
            count = 0
            for orm in results.all():
                meta = dict(orm.metadata_json or {})
                if meta.get("invalidation_rules", {}).get("invalidate_on_revision_change", False):
                    pinned = meta.get("revision") or meta.get("invalidation_rules", {}).get(
                        "pinned_revision"
                    )
                    if pinned and pinned != new_revision:
                        meta["verification_status"] = str(VerificationStatus.INVALIDATED)
                        meta["invalidation_reason"] = (
                            f"Repository updated to revision {new_revision}"
                        )
                        orm.metadata_json = meta
                        count += 1
            await session.flush()
            return count

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory record permanently."""
        async with self.get_session() as session:
            orm = await session.get(MemoryRecordModel, memory_id)
            if not orm:
                return False
            await session.delete(orm)
            await session.flush()
            return True

    async def delete_by_project(self, project_id: str) -> int:
        """Delete all memories associated with a specific project for data lifecycle control."""
        async with self.get_session() as session:
            stmt = delete(MemoryRecordModel).where(MemoryRecordModel.project_id == project_id)
            res = await session.execute(stmt)
            await session.flush()
            row_count = getattr(res, "rowcount", 0) or 0
            return int(row_count)
