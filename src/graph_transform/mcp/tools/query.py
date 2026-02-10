"""
Query Tool - Find nodes in the code graph.

FR2: Agents can query for node IDs matching patterns via `query` tool
FR12-16: Query by pattern, kind, file with complete results
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from graph_transform.io.builder import build_graph_from_source as build_graph
from graph_transform.core.typed_graph import NodeType, TypedGraph


def query_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Handle query tool calls.

    Args:
        args: Tool arguments including:
            - path: File or directory to query (required)
            - pattern: Name pattern to match (optional)
            - kind: Node kind filter (optional)
            - file: File path filter (optional)

    Returns:
        JSON response with matching nodes
    """
    path = args.get("path")
    if not path:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_PATH",
                "message": "path is required"
            }
        }

    path_obj = Path(path)
    if not path_obj.exists():
        return {
            "status": "error",
            "error": {
                "code": "PATH_NOT_FOUND",
                "message": f"Path not found: {path}"
            }
        }

    try:
        graph = build_graph(path_obj)
    except Exception as e:
        return {
            "status": "error",
            "error": {
                "code": "PARSE_ERROR",
                "message": str(e)
            }
        }

    pattern = args.get("pattern")
    kind = args.get("kind")
    file_filter = args.get("file")

    nodes = _filter_nodes(graph, pattern, kind, file_filter)

    return {
        "status": "ok",
        "count": len(nodes),
        "nodes": nodes
    }


def _filter_nodes(
    graph: TypedGraph,
    pattern: str | None,
    kind: str | None,
    file_filter: str | None
) -> list[dict[str, Any]]:
    """Filter and format nodes based on criteria."""
    results = []

    for node_id, node in graph.nodes.items():
        # Kind filter
        if kind:
            kind_match = _match_kind(node.node_type, kind)
            if not kind_match:
                continue

        # Pattern filter
        if pattern:
            name = node.attrs.get("name", "")
            if not _match_pattern(name, pattern):
                continue

        # File filter
        if file_filter:
            file_path = node.attrs.get("file", "")
            if not fnmatch.fnmatch(file_path, file_filter):
                continue

        results.append({
            "id": node_id,
            "kind": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
            "name": node.attrs.get("name", ""),
            "file": node.attrs.get("file", ""),
            "line": node.attrs.get("line", 0),
        })

    # Sort by file, then line
    results.sort(key=lambda n: (n["file"], n["line"]))

    return results


def _match_kind(node_type: NodeType, filter_kind: str) -> bool:
    """Check if node kind matches filter."""
    kind_str = node_type.value if hasattr(node_type, "value") else str(node_type)
    filter_lower = filter_kind.lower()

    # Direct match
    if kind_str.lower() == filter_lower:
        return True

    # Map common aliases
    aliases = {
        "function": ["callable"],
        "class": ["type"],
        "method": ["callable"],
        "variable": ["binding"],
        "module": ["container"],
        "parameter": ["binding"],
    }

    for alias, kinds in aliases.items():
        if filter_lower == alias and kind_str.lower() in kinds:
            return True

    return False


def _match_pattern(name: str, pattern: str) -> bool:
    """Match name against pattern (glob or regex)."""
    if pattern.startswith("re:"):
        # Regex pattern
        regex = pattern[3:]
        try:
            return bool(re.search(regex, name))
        except re.error:
            return False
    else:
        # Glob pattern
        return fnmatch.fnmatch(name, pattern)
