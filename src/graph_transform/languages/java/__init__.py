"""
Java Language Adapter

Provides code generation for Java source files from TypedGraph.
Note: Parsing Java requires tree-sitter (not yet implemented).
"""

from __future__ import annotations

from pathlib import Path

from graph_transform.core.typed_graph import TypedGraph
from graph_transform.languages.base import EditInstruction, LanguageAdapter

from .emitter import JavaEmitter


class JavaAdapter(LanguageAdapter):
    """Language adapter for Java source files.

    Currently supports:
    - Emitting Java code from TypedGraph (for Python -> Java migration)

    Not yet implemented (requires tree-sitter):
    - Parsing Java source files
    """

    def __init__(self) -> None:
        self._emitter = JavaEmitter()

    @property
    def name(self) -> str:
        return "java"

    @property
    def extensions(self) -> list[str]:
        return [".java"]

    def parse(self, source: str, filename: str = "<source>") -> TypedGraph:
        """Parse Java source code into a TypedGraph.

        Not yet implemented - requires tree-sitter-java.
        """
        raise NotImplementedError(
            "Java parsing requires tree-sitter. "
            "Install with: pip install tree-sitter tree-sitter-java"
        )

    def parse_file(self, file_path: str | Path) -> TypedGraph:
        """Parse a Java file into a TypedGraph.

        Not yet implemented - requires tree-sitter-java.
        """
        raise NotImplementedError(
            "Java parsing requires tree-sitter. "
            "Install with: pip install tree-sitter tree-sitter-java"
        )

    def emit(self, graph: TypedGraph, original_source: str | None = None) -> str:
        """Generate Java source code from a TypedGraph.

        Note: This returns a single combined file. For proper Java output
        with separate files per class, use emit_files() instead.
        """
        files = self._emitter.emit(graph)
        # Combine all files into one string (for simple cases)
        return "\n\n// --- Next File ---\n\n".join(files.values())

    def emit_files(self, graph: TypedGraph, output_dir: str | Path) -> dict[str, str]:
        """Generate Java source files from a TypedGraph.

        Creates one .java file per class, following Java conventions.

        Args:
            graph: The TypedGraph to convert.
            output_dir: Directory to write the Java files.

        Returns:
            Dictionary mapping filename to generated content.
        """
        return self._emitter.emit(graph, output_dir)

    def apply_edit(self, source: str, edit: EditInstruction) -> str:
        """Apply a single edit instruction to Java source code.

        Not yet implemented.
        """
        raise NotImplementedError("Java edit application not yet implemented")


__all__ = [
    "JavaAdapter",
    "JavaEmitter",
]
