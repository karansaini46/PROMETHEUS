"""Code Analysis: Symbol Lookup, Dependencies, Impact Analysis, and Test Discovery."""

import logging
from pathlib import Path
from typing import Any

from prometheus_ai.code_intel.indexer import CodeIntelligenceIndex
from prometheus_ai.code_intel.models import ChangeImpact, Symbol, SymbolKind
from prometheus_ai.execution.git_manager import GitManager

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Performs deep symbol lookup, dependency graph traversal, and change-impact analysis."""

    def __init__(
        self,
        index: CodeIntelligenceIndex,
        git_manager: GitManager | None = None,
    ) -> None:
        self.index = index
        self.git_manager = git_manager or GitManager()

    # --- 1. Symbol and Definition Lookup ---

    def lookup_symbol(
        self,
        symbol_name: str,
        kind: SymbolKind | None = None,
    ) -> list[Symbol]:
        """Look up function or class definitions matching symbol_name."""
        matches: list[Symbol] = []
        for file_idx in self.index.file_indices.values():
            for sym in file_idx.symbols:
                if sym.name == symbol_name:
                    if kind is None or sym.kind == kind:
                        matches.append(sym)
        return matches

    def find_definition(self, symbol_name: str) -> list[dict[str, Any]]:
        """Locate definition sites for a given symbol."""
        symbols = self.lookup_symbol(symbol_name)
        return [
            {
                "symbol_name": sym.name,
                "kind": sym.kind.value,
                "file_path": sym.file_path,
                "start_line": sym.start_line,
                "end_line": sym.end_line,
                "signature": sym.signature,
                "docstring": sym.docstring,
            }
            for sym in symbols
        ]

    def find_references(self, symbol_name: str) -> list[dict[str, Any]]:
        """Find candidate reference/call sites for a symbol across the repository.

        # ponytail: Dynamic language notice: Python runtime polymorphism and dynamic dispatch
        # cannot be completely resolved statically; references represent AST call/attribute matches.
        """
        references: list[dict[str, Any]] = []
        for rel_path, file_idx in self.index.file_indices.items():
            if symbol_name in file_idx.references:
                # Find matching lines
                full_path = self.index.repo_path / rel_path
                if full_path.exists():
                    try:
                        with open(full_path, encoding="utf-8", errors="replace") as f:
                            for line_no, line in enumerate(f, start=1):
                                if symbol_name in line:
                                    references.append(
                                        {
                                            "file_path": rel_path,
                                            "line_number": line_no,
                                            "line_content": line.strip(),
                                        }
                                    )
                    except Exception:
                        pass
        return references

    # --- 2. Import & Dependency Graph ---

    def get_dependencies(self, file_path: str) -> list[str]:
        """Get all internal repository files imported by file_path."""
        file_idx = self.index.file_indices.get(file_path)
        if not file_idx:
            return []

        internal_deps: set[str] = set()
        for imp in file_idx.imports:
            mod = imp.source_module.replace(".", "/")
            # Check if matching module path exists in indexed files
            for other_file in self.index.file_indices:
                other_stem = str(Path(other_file).with_suffix(""))
                if other_stem.endswith(mod) or mod.endswith(other_stem):
                    internal_deps.add(other_file)

        return sorted(internal_deps)

    def get_dependents(self, file_path: str) -> list[str]:
        """Get all repository files that import file_path."""
        dependents: set[str] = set()
        stem = str(Path(file_path).with_suffix("")).replace("/", ".")
        file_name = Path(file_path).stem

        for other_file, file_idx in self.index.file_indices.items():
            if other_file == file_path:
                continue
            for imp in file_idx.imports:
                if (
                    imp.source_module == stem
                    or imp.source_module.endswith(f".{file_name}")
                    or imp.source_module == file_name
                    or file_name in imp.imported_names
                ):
                    dependents.add(other_file)

        return sorted(dependents)

    # --- 3. Relevant Test Discovery ---

    def discover_tests_for_file(self, file_path: str) -> list[str]:
        """Identify test files relevant to a source module."""
        stem = Path(file_path).stem
        relevant_tests: set[str] = set()

        for indexed_file in self.index.file_indices:
            # Check standard test naming conventions
            idx_name = Path(indexed_file).name
            if idx_name in (f"test_{stem}.py", f"{stem}_test.py"):
                relevant_tests.add(indexed_file)

            # Check if test file imports the source file
            if "test" in indexed_file.lower():
                deps = self.get_dependencies(indexed_file)
                if file_path in deps:
                    relevant_tests.add(indexed_file)

        return sorted(relevant_tests)

    def discover_tests_for_symbol(self, symbol_name: str) -> list[str]:
        """Identify test files that reference or test a specific symbol."""
        refs = self.find_references(symbol_name)
        test_files = {r["file_path"] for r in refs if "test" in r["file_path"].lower()}
        return sorted(test_files)

    # --- 4. Git History Inspection ---

    def get_file_history(self, file_path: str, limit: int = 10) -> list[dict[str, str]]:
        """Retrieve recent git commit history for a file."""
        ret, out, _ = self.git_manager._run_git(
            ["log", f"-n{limit}", "--oneline", "--", file_path],
            cwd=self.index.repo_path,
        )
        if ret != 0 or not out.strip():
            return []

        entries = []
        for line in out.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                entries.append({"commit_hash": parts[0], "message": parts[1]})
        return entries

    # --- 5. Change Impact Analysis ---

    def analyze_change_impact(
        self,
        modified_files: list[str],
        patch_diff: str | None = None,
    ) -> ChangeImpact:
        """Calculate the cascading impact of modified files on dependent modules and tests."""
        affected_symbols: set[str] = set()
        dependent_files: set[str] = set()
        suggested_tests: set[str] = set()

        for mod_file in modified_files:
            file_idx = self.index.file_indices.get(mod_file)
            if file_idx:
                for sym in file_idx.symbols:
                    affected_symbols.add(sym.name)

            # Discover dependents
            deps = self.get_dependents(mod_file)
            dependent_files.update(deps)

            # Discover tests
            tests = self.discover_tests_for_file(mod_file)
            suggested_tests.update(tests)

        # Also discover tests for affected symbols
        for sym_name in affected_symbols:
            sym_tests = self.discover_tests_for_symbol(sym_name)
            suggested_tests.update(sym_tests)

        # Risk scoring
        dep_count = len(dependent_files)
        if dep_count > 5:
            risk = "high"
        elif dep_count > 1:
            risk = "medium"
        else:
            risk = "low"

        return ChangeImpact(
            modified_files=modified_files,
            directly_affected_symbols=sorted(affected_symbols),
            dependent_files=sorted(dependent_files),
            suggested_test_files=sorted(suggested_tests),
            risk_level=risk,
        )
