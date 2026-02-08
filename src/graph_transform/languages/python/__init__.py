"""
Python Language Adapter

Provides parsing and code generation for Python source files.
"""

from __future__ import annotations

from pathlib import Path

from graph_transform.core.typed_graph import TypedGraph
from graph_transform.languages.base import EditInstruction, LanguageAdapter

from .emitter import PythonEmitter
from .parser import PythonParser


class PythonAdapter(LanguageAdapter):
    """Language adapter for Python source files.

    Uses the stdlib ast module for parsing and provides code generation
    and edit application capabilities.

    Example:
        adapter = PythonAdapter()
        graph = adapter.parse("def hello(): pass", "example.py")
        source = adapter.emit(graph)
    """

    def __init__(self) -> None:
        self._parser = PythonParser()
        self._emitter = PythonEmitter()

    @property
    def name(self) -> str:
        return "python"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyw"]

    def parse(self, source: str, filename: str = "<source>") -> TypedGraph:
        """Parse Python source code into a TypedGraph.

        Args:
            source: The Python source code as a string.
            filename: The filename for error messages and node metadata.

        Returns:
            A TypedGraph representing the code structure.

        Raises:
            SyntaxError: If the source code cannot be parsed.
        """
        return self._parser.parse(source, filename)

    def parse_file(self, file_path: str | Path) -> TypedGraph:
        """Parse a Python file into a TypedGraph.

        Args:
            file_path: Path to the Python file.

        Returns:
            A TypedGraph representing the code structure.

        Raises:
            FileNotFoundError: If the file does not exist.
            SyntaxError: If the source code cannot be parsed.
        """
        return self._parser.parse_file(file_path)

    def emit(self, graph: TypedGraph, original_source: str | None = None) -> str:
        """Generate Python source code from a TypedGraph.

        Args:
            graph: The TypedGraph to convert to source code.
            original_source: Optional original source for formatting hints.

        Returns:
            Generated Python source code.
        """
        return self._emitter.emit(graph, original_source)

    def apply_edit(self, source: str, edit: EditInstruction) -> str:
        """Apply a single edit instruction to Python source code.

        Args:
            source: The original Python source code.
            edit: The edit instruction to apply.

        Returns:
            The modified source code.
        """
        return self._emitter.apply_edit(source, edit)

    def apply_edits(self, source: str, edits: list[EditInstruction]) -> str:
        """Apply multiple edit instructions to source code.

        Args:
            source: The original source code.
            edits: List of edit instructions to apply.

        Returns:
            The modified source code.
        """
        return self._emitter.apply_edits(source, edits)


__all__ = [
    "PythonAdapter",
    "PythonParser",
    "PythonEmitter",
]
