"""
Graph Builder

Build a TypedGraph from source files using language adapters.
Supports multiple languages through the LanguageRegistry.

For Python-only projects, this module provides convenience functions
that automatically use the Python adapter.
"""

from __future__ import annotations

from pathlib import Path

from graph_transform.core.typed_graph import TypedGraph
from graph_transform.languages import LanguageRegistry


def build_graph_from_source(
    source_path: str | Path,
    language: str | None = None,
) -> TypedGraph:
    """Build a TypedGraph from source files.

    If source_path is a directory, recursively processes all files
    with recognized extensions and produces a single unified TypedGraph.

    Args:
        source_path: Path to a source file or directory.
        language: Optional explicit language (e.g., 'python', 'java').
                  If not specified, auto-detects from file extensions.

    Returns:
        A TypedGraph representing the code structure.

    Raises:
        FileNotFoundError: If the path does not exist.
        SyntaxError: If a source file cannot be parsed.
        ValueError: If language cannot be detected or is not supported.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {source_path}")

    if path.is_file():
        if language:
            adapter = LanguageRegistry.get(language)
        else:
            adapter = LanguageRegistry.detect(path)
        return adapter.parse_file(path)

    elif path.is_dir():
        return _build_from_directory(path, language)

    else:
        raise ValueError(f"Path is neither a file nor a directory: {source_path}")


def build_graph_from_files(
    file_paths: list[str | Path],
    language: str | None = None,
) -> TypedGraph:
    """Build a TypedGraph from a list of source files.

    Useful for building subgraphs from grep results or specific file lists.

    Args:
        file_paths: List of paths to source files.
        language: Optional explicit language. If not specified,
                  auto-detects from each file's extension.

    Returns:
        A TypedGraph representing the code structure.

    Raises:
        FileNotFoundError: If any file does not exist.
        SyntaxError: If a source file cannot be parsed.
        ValueError: If no files provided or language cannot be detected.
    """
    if not file_paths:
        raise ValueError("No files provided")

    graph = TypedGraph()

    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        if language:
            adapter = LanguageRegistry.get(language)
        else:
            adapter = LanguageRegistry.detect(path)

        file_graph = adapter.parse_file(path)
        _merge_graph(graph, file_graph)

    return graph


def _build_from_directory(
    directory: Path,
    language: str | None = None,
) -> TypedGraph:
    """Build a TypedGraph from all source files in a directory."""
    graph = TypedGraph()
    files_found = False

    # Get all supported extensions
    if language:
        adapter = LanguageRegistry.get(language)
        extensions = adapter.extensions
    else:
        extensions = list(LanguageRegistry.supported_extensions().keys())

    # Find and parse files
    for ext in extensions:
        pattern = f"**/*{ext}"
        for source_file in sorted(directory.glob(pattern)):
            if source_file.is_file():
                files_found = True
                if language:
                    adapter = LanguageRegistry.get(language)
                else:
                    adapter = LanguageRegistry.detect(source_file)

                try:
                    file_graph = adapter.parse_file(source_file)
                    _merge_graph(graph, file_graph)
                except SyntaxError:
                    # Skip files that fail to parse
                    continue

    if not files_found:
        ext_list = ", ".join(extensions)
        raise FileNotFoundError(
            f"No source files ({ext_list}) found in: {directory}"
        )

    return graph


def _merge_graph(target: TypedGraph, source: TypedGraph) -> None:
    """Merge source graph into target graph."""
    for node_id, node in source.nodes.items():
        if not target.has_node(node_id):
            target.add_node(node)

    for edge in source.edges:
        if not target.has_edge(edge.source, edge.target):
            target.add_edge(edge)
