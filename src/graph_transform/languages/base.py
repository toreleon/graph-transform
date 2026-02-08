"""
Language Adapter Base Class

Abstract interface for language-specific parsing and code generation.
Each supported language implements this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph_transform.core.typed_graph import TypedGraph


@dataclass
class EditInstruction:
    """A structured edit instruction for code generation.

    This is the bridge between graph transformations and source code edits.
    Language adapters use these instructions to apply changes to source files.
    """

    edit_type: str
    file: str
    line: int | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = {
            "type": self.edit_type,
            "file": self.file,
        }
        if self.line is not None:
            result["line"] = self.line
        result.update(self.details)
        return result


class LanguageAdapter(ABC):
    """Abstract base class for language-specific parsing and code generation.

    Each supported language (Python, Java, TypeScript, Go, etc.) must provide
    an implementation of this interface. The adapter handles:

    1. Parsing: Convert source code to TypedGraph
    2. Emitting: Generate source code from TypedGraph
    3. Editing: Apply EditInstruction to source code

    Example implementation:
        class PythonAdapter(LanguageAdapter):
            @property
            def name(self) -> str:
                return "python"

            @property
            def extensions(self) -> list[str]:
                return [".py", ".pyw"]

            def parse(self, source: str, filename: str = "<source>") -> TypedGraph:
                # Use ast module to parse Python
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Language identifier (e.g., 'python', 'java', 'typescript').

        This is used for explicit language selection via CLI flags.
        """
        pass

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """File extensions for this language (e.g., ['.py'], ['.java']).

        Used for automatic language detection from file paths.
        Extensions should include the leading dot.
        """
        pass

    @abstractmethod
    def parse(self, source: str, filename: str = "<source>") -> TypedGraph:
        """Parse source code into a TypedGraph.

        Args:
            source: The source code as a string.
            filename: The filename for error messages and node metadata.

        Returns:
            A TypedGraph representing the code structure.

        Raises:
            SyntaxError: If the source code cannot be parsed.
        """
        pass

    @abstractmethod
    def parse_file(self, file_path: str | Path) -> TypedGraph:
        """Parse a source file into a TypedGraph.

        Args:
            file_path: Path to the source file.

        Returns:
            A TypedGraph representing the code structure.

        Raises:
            FileNotFoundError: If the file does not exist.
            SyntaxError: If the source code cannot be parsed.
        """
        pass

    def parse_files(self, file_paths: list[str | Path]) -> TypedGraph:
        """Parse multiple source files into a single unified TypedGraph.

        Default implementation parses each file and merges graphs.
        Subclasses may override for more efficient batch processing.

        Args:
            file_paths: List of paths to source files.

        Returns:
            A unified TypedGraph representing all files.
        """
        if not file_paths:
            raise ValueError("No files provided")

        graph = TypedGraph()
        for path in file_paths:
            file_graph = self.parse_file(path)
            # Merge nodes
            for node_id, node in file_graph.nodes.items():
                if not graph.has_node(node_id):
                    graph.add_node(node)
            # Merge edges
            for edge in file_graph.edges:
                if not graph.has_edge(edge.source, edge.target):
                    graph.add_edge(edge)
        return graph

    @abstractmethod
    def emit(self, graph: TypedGraph, original_source: str | None = None) -> str:
        """Generate source code from a TypedGraph.

        This is the inverse of parse(): given a graph representation,
        produce valid source code in this language.

        Args:
            graph: The TypedGraph to convert to source code.
            original_source: Optional original source for formatting hints.

        Returns:
            Generated source code as a string.

        Note:
            Full emission is complex and may not preserve all formatting.
            For refactoring, prefer apply_edit() which makes targeted changes.
        """
        pass

    @abstractmethod
    def apply_edit(self, source: str, edit: EditInstruction) -> str:
        """Apply a single edit instruction to source code.

        This is the primary method for applying refactoring changes.
        It takes the original source and an edit instruction, and returns
        the modified source.

        Args:
            source: The original source code.
            edit: The edit instruction to apply.

        Returns:
            The modified source code.

        Raises:
            ValueError: If the edit cannot be applied.
        """
        pass

    def apply_edits(self, source: str, edits: list[EditInstruction]) -> str:
        """Apply multiple edit instructions to source code.

        Default implementation applies edits sequentially, adjusting
        line numbers as needed. Subclasses may override for more
        sophisticated handling.

        Args:
            source: The original source code.
            edits: List of edit instructions to apply.

        Returns:
            The modified source code.
        """
        result = source
        for edit in edits:
            result = self.apply_edit(result, edit)
        return result
