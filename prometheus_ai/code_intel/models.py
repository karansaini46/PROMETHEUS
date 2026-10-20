"""Data models and descriptors for the Code Intelligence subsystem."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SymbolKind(StrEnum):
    """Categorical classification of indexed source symbols."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    VARIABLE = "variable"
    IMPORT = "import"


@dataclass
class Symbol:
    """Indexed code symbol (function, class, method)."""

    name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    docstring: str | None = None
    signature: str | None = None
    parent_name: str | None = None


@dataclass
class ImportStatement:
    """Import declaration parsed from a source file."""

    source_module: str
    imported_names: list[str]
    alias: str | None = None
    is_from_import: bool = False
    line_number: int = 1


@dataclass
class CodeChunk:
    """Granular code chunk for lexical and semantic retrieval."""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_name: str | None = None
    tokens: list[str] = field(default_factory=list)


@dataclass
class FileIndex:
    """Comprehensive AST and metadata index for a single source file."""

    file_path: str
    content_hash: str
    mtime: float
    size_bytes: int
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportStatement] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    chunks: list[CodeChunk] = field(default_factory=list)
    parse_error: str | None = None


@dataclass
class SearchResult:
    """Ranked search match with small evidence snippet and location."""

    file_path: str
    start_line: int
    end_line: int
    snippet: str
    score: float
    match_type: str  # "lexical", "semantic", "hybrid"
    symbol_name: str | None = None


class IndexState(StrEnum):
    """Lifecycle status of the repository index."""

    IDLE = "idle"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IndexStatus:
    """Progress and telemetry descriptor for repository indexing."""

    state: IndexState = IndexState.IDLE
    progress_pct: float = 0.0
    files_indexed: int = 0
    total_files: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    revision: str | None = None
    last_indexed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "progress_pct": round(self.progress_pct, 2),
            "files_indexed": self.files_indexed,
            "total_files": self.total_files,
            "errors": self.errors,
            "revision": self.revision,
            "last_indexed_at": self.last_indexed_at,
        }


@dataclass
class ChangeImpact:
    """Impact analysis outcome for modified files or proposed patches."""

    modified_files: list[str] = field(default_factory=list)
    directly_affected_symbols: list[str] = field(default_factory=list)
    dependent_files: list[str] = field(default_factory=list)
    suggested_test_files: list[str] = field(default_factory=list)
    risk_level: str = "low"
