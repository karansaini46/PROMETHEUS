"""AST source parsing and multi-language adapter framework."""

import ast
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

from prometheus_ai.code_intel.models import (
    CodeChunk,
    ImportStatement,
    Symbol,
    SymbolKind,
)

logger = logging.getLogger(__name__)


def tokenize_code(text: str) -> list[str]:
    """Tokenize source text into normalized word/symbol tokens."""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)
    return [t.lower() for t in tokens if len(t) >= 2]


class BaseLanguageAdapter(ABC):
    """Abstract interface for language-specific AST and symbol extractors."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_extensions(self) -> frozenset[str]:
        raise NotImplementedError

    @abstractmethod
    def parse_source(
        self,
        file_path: str,
        source_code: str,
    ) -> tuple[list[Symbol], list[ImportStatement], list[str], list[CodeChunk], str | None]:
        """Parse source code into symbols, imports, references, chunks, and optional parse error."""
        raise NotImplementedError


class PythonAstAdapter(BaseLanguageAdapter):
    """Python language adapter using standard library AST.

    # ponytail: Python's standard library `ast` handles complete 3.12 syntax, docstrings,
    # async functions, and imports with zero external C dependencies or runtime overhead.
    # Upgrade path: tree-sitter or LSP when cross-language multi-file semantic types are required.
    """

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".py", ".pyi"})

    def parse_source(
        self,
        file_path: str,
        source_code: str,
    ) -> tuple[list[Symbol], list[ImportStatement], list[str], list[CodeChunk], str | None]:
        symbols: list[Symbol] = []
        imports: list[ImportStatement] = []
        references: set[str] = set()
        chunks: list[CodeChunk] = []
        lines = source_code.splitlines()

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as err:
            logger.warning("Syntax error parsing %s: %s", file_path, err)
            # Create a fallback chunk of the entire raw text so keyword search still works
            fallback_chunk = CodeChunk(
                chunk_id=f"{file_path}:1:{len(lines)}",
                file_path=file_path,
                start_line=1,
                end_line=max(1, len(lines)),
                content=source_code[:4000],
                tokens=tokenize_code(source_code[:4000]),
            )
            return symbols, imports, list(references), [fallback_chunk], str(err)
        except Exception as err:
            logger.warning("Unexpected error parsing %s: %s", file_path, err)
            return symbols, imports, list(references), [], str(err)

        # 1. Extract Symbols and Imports
        class SymbolVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.current_class: str | None = None

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                docstring = ast.get_docstring(node)
                start = node.lineno
                end = node.end_lineno or start
                symbols.append(
                    Symbol(
                        name=node.name,
                        kind=SymbolKind.CLASS,
                        file_path=file_path,
                        start_line=start,
                        end_line=end,
                        docstring=docstring,
                        parent_name=self.current_class,
                    )
                )

                # Create code chunk for class header / docstring
                chunk_content = "\n".join(lines[start - 1 : min(end, start + 25)])
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file_path}:{node.name}:{start}",
                        file_path=file_path,
                        start_line=start,
                        end_line=end,
                        content=chunk_content,
                        symbol_name=node.name,
                        tokens=tokenize_code(chunk_content),
                    )
                )

                prev_class = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev_class

            def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
                docstring = ast.get_docstring(node)
                start = node.lineno
                end = node.end_lineno or start
                kind = SymbolKind.METHOD if self.current_class else SymbolKind.FUNCTION

                # Build argument signature
                args_list = [a.arg for a in node.args.args]
                sig = f"({', '.join(args_list)})"

                symbols.append(
                    Symbol(
                        name=node.name,
                        kind=kind,
                        file_path=file_path,
                        start_line=start,
                        end_line=end,
                        docstring=docstring,
                        signature=sig,
                        parent_name=self.current_class,
                    )
                )

                # Create code chunk for function
                chunk_content = "\n".join(lines[start - 1 : end])
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file_path}:{node.name}:{start}",
                        file_path=file_path,
                        start_line=start,
                        end_line=end,
                        content=chunk_content,
                        symbol_name=node.name,
                        tokens=tokenize_code(chunk_content),
                    )
                )

                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self.visit_FunctionDef(node)

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    imports.append(
                        ImportStatement(
                            source_module=alias.name,
                            imported_names=[alias.name],
                            alias=alias.asname,
                            is_from_import=False,
                            line_number=node.lineno,
                        )
                    )
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                mod = node.module or ""
                names = [alias.name for alias in node.names]
                imports.append(
                    ImportStatement(
                        source_module=mod,
                        imported_names=names,
                        is_from_import=True,
                        line_number=node.lineno,
                    )
                )
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call) -> None:
                # Capture function call references
                if isinstance(node.func, ast.Name):
                    references.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    references.add(node.func.attr)
                self.generic_visit(node)

            def visit_Attribute(self, node: ast.Attribute) -> None:
                references.add(node.attr)
                self.generic_visit(node)

        visitor = SymbolVisitor()
        visitor.visit(tree)

        # If no function/class chunks were created (e.g. script or module-level declarations),
        # create sliding chunks over the file
        if not chunks:
            chunk_size = 50
            for i in range(0, max(1, len(lines)), chunk_size):
                chunk_lines = lines[i : i + chunk_size]
                chunk_text = "\n".join(chunk_lines)
                chunks.append(
                    CodeChunk(
                        chunk_id=f"{file_path}:{i+1}:{i+len(chunk_lines)}",
                        file_path=file_path,
                        start_line=i + 1,
                        end_line=i + len(chunk_lines),
                        content=chunk_text,
                        tokens=tokenize_code(chunk_text),
                    )
                )

        return symbols, imports, list(references), chunks, None


class GenericTextAdapter(BaseLanguageAdapter):
    """Fallback text adapter for generic files, Markdown, or unsupported code."""

    def __init__(self, language: str = "text", extensions: set[str] | None = None) -> None:
        self._language = language
        self._extensions = frozenset(extensions or {".txt", ".md", ".json", ".yaml", ".yml"})

    @property
    def language_name(self) -> str:
        return self._language

    @property
    def supported_extensions(self) -> frozenset[str]:
        return self._extensions

    def parse_source(
        self,
        file_path: str,
        source_code: str,
    ) -> tuple[list[Symbol], list[ImportStatement], list[str], list[CodeChunk], str | None]:
        lines = source_code.splitlines()
        chunks: list[CodeChunk] = []
        chunk_size = 50

        for i in range(0, max(1, len(lines)), chunk_size):
            chunk_lines = lines[i : i + chunk_size]
            chunk_text = "\n".join(chunk_lines)
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file_path}:{i+1}:{i+len(chunk_lines)}",
                    file_path=file_path,
                    start_line=i + 1,
                    end_line=i + len(chunk_lines),
                    content=chunk_text,
                    tokens=tokenize_code(chunk_text),
                )
            )

        return [], [], [], chunks, None


class LanguageRegistry:
    """Registry routing file extensions to their corresponding LanguageAdapter."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseLanguageAdapter] = {}
        self._default_adapter = GenericTextAdapter()

        # Register default Python adapter
        self.register(PythonAstAdapter())

    def register(self, adapter: BaseLanguageAdapter) -> None:
        """Register a language adapter for its supported file extensions."""
        for ext in adapter.supported_extensions:
            self._adapters[ext.lower()] = adapter

    def get_adapter(self, file_path: str | Path) -> BaseLanguageAdapter:
        """Retrieve the appropriate adapter for a file path, or default fallback."""
        ext = Path(file_path).suffix.lower()
        return self._adapters.get(ext, self._default_adapter)
