"""Repository Indexing Engine with Incremental Hashing and Fault Isolation."""

import hashlib
import logging
import time
from pathlib import Path

from prometheus_ai.code_intel.models import (
    FileIndex,
    IndexState,
    IndexStatus,
)
from prometheus_ai.code_intel.parser import LanguageRegistry
from prometheus_ai.execution.git_manager import GitManager
from services.api.telemetry import trace_span

logger = logging.getLogger(__name__)


def compute_file_hash(content: str | bytes) -> str:
    """Compute SHA-256 hash of file content."""
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(raw).hexdigest()


class CodeIntelligenceIndex:
    """Persistent in-memory and incremental repository index.

    Guarantees:
    - Incremental indexing: unchanged files (identical SHA-256) are skipped.
    - Deleted file reconciliation: removed files are purged from the index.
    - Fault isolation: syntax errors or malformed files in one module never corrupt or abort indexing for other files.
    - Stale index detection: checks active git commit hash against indexed revision.
    """

    def __init__(
        self,
        repo_path: str | Path,
        git_manager: GitManager | None = None,
        language_registry: LanguageRegistry | None = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.git_manager = git_manager or GitManager()
        self.registry = language_registry or LanguageRegistry()

        self.file_indices: dict[str, FileIndex] = {}
        self.status = IndexStatus()

    def is_stale(self) -> bool:
        """Check whether the repository HEAD has diverged from the indexed revision."""
        if not self.status.revision:
            return True
        try:
            # Query current HEAD commit
            meta = self.git_manager.register_repository(self.repo_path)
            return meta.head_commit != self.status.revision
        except Exception:
            return True

    def build_index(self, incremental: bool = True) -> IndexStatus:
        """Index the repository with incremental hashing and per-file fault isolation."""
        with trace_span(
            "code_intel.index",
            attributes={
                "repo.name": self.repo_path.name,
                "incremental": incremental,
            },
        ) as span:
            self.status.state = IndexState.INDEXING
            self.status.errors.clear()
            start_time = time.time()

            try:
                # 1. Fetch current repository commit revision
                meta = self.git_manager.register_repository(self.repo_path)
                current_revision = meta.head_commit
                self.status.revision = current_revision

                # 2. Enumerate permitted source files
                permitted_files = self.git_manager.list_permitted_files(
                    self.repo_path, max_files=5000
                )
                self.status.total_files = len(permitted_files)
                self.status.files_indexed = 0

                # 3. Purge deleted files from index
                current_set = set(permitted_files)
                deleted_files = [f for f in self.file_indices if f not in current_set]
                for df in deleted_files:
                    self.file_indices.pop(df, None)

                # 4. Index permitted files
                for idx, rel_path in enumerate(permitted_files, start=1):
                    full_path = self.repo_path / rel_path

                    try:
                        # Check file existence and stats
                        if not full_path.exists() or not full_path.is_file():
                            continue

                        stat = full_path.stat()
                        mtime = stat.st_mtime
                        size_bytes = stat.st_size

                        # Read file content safely
                        with open(full_path, encoding="utf-8", errors="replace") as f:
                            source_code = f.read(2 * 1024 * 1024)  # 2MB max read guard

                        content_hash = compute_file_hash(source_code)

                        # Incremental skip if unchanged
                        if incremental and rel_path in self.file_indices:
                            existing = self.file_indices[rel_path]
                            if existing.content_hash == content_hash:
                                self.status.files_indexed += 1
                                self.status.progress_pct = (idx / self.status.total_files) * 100.0
                                continue

                        # Parse with language adapter
                        adapter = self.registry.get_adapter(rel_path)
                        symbols, imports, refs, chunks, parse_err = adapter.parse_source(
                            file_path=rel_path,
                            source_code=source_code,
                        )

                        if parse_err:
                            self.status.errors.append({"file": rel_path, "error": parse_err})

                        self.file_indices[rel_path] = FileIndex(
                            file_path=rel_path,
                            content_hash=content_hash,
                            mtime=mtime,
                            size_bytes=size_bytes,
                            language=adapter.language_name,
                            symbols=symbols,
                            imports=imports,
                            references=refs,
                            chunks=chunks,
                            parse_error=parse_err,
                        )

                    except Exception as file_err:
                        # Fault isolation: log and record error, but do not stop indexing
                        logger.warning("Error indexing file %s: %s", rel_path, file_err)
                        self.status.errors.append({"file": rel_path, "error": str(file_err)})

                    self.status.files_indexed += 1
                    self.status.progress_pct = (idx / self.status.total_files) * 100.0

                self.status.state = IndexState.COMPLETED
                self.status.last_indexed_at = time.time()
                span.set_attribute("repo.files_indexed", self.status.files_indexed)
                span.set_attribute("repo.errors_count", len(self.status.errors))
                logger.info(
                    "Indexed %d files for repo %s in %.2fs (errors: %d)",
                    len(self.file_indices),
                    self.repo_path.name,
                    time.time() - start_time,
                    len(self.status.errors),
                )

            except Exception as repo_err:
                self.status.state = IndexState.FAILED
                self.status.errors.append(
                    {"repository": str(self.repo_path), "error": str(repo_err)}
                )
                logger.error("Repository indexing failed: %s", repo_err)

            return self.status

    def clear(self) -> None:
        """Clear all indexed data and reset state."""
        self.file_indices.clear()
        self.status = IndexStatus()
