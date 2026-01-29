"""
Graph Serialization

JSON I/O for TypedGraph and operation results.
Supports file paths and stdin/stdout for CLI integration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .typed_graph import TypedGraph
from .production_rule import RewriteResult


def load_graph(source: str) -> TypedGraph:
    """Load a TypedGraph from a JSON file path or stdin ('-').

    Args:
        source: File path to a JSON file, or '-' for stdin.

    Returns:
        A TypedGraph instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is malformed or missing required fields.
    """
    data = load_json(source)
    errors = validate_graph_json(data)
    if errors:
        raise ValueError(f"Invalid graph JSON: {'; '.join(errors)}")
    return TypedGraph.from_dict(data)


def save_graph(graph: TypedGraph, destination: str | None = None) -> None:
    """Save a TypedGraph as JSON to a file or stdout.

    Args:
        graph: The TypedGraph to serialize.
        destination: File path, or None for stdout.
    """
    data = graph.to_dict()
    text = json.dumps(data, indent=2)

    if destination is None:
        sys.stdout.write(text + "\n")
    else:
        Path(destination).write_text(text + "\n")


def load_json(source: str) -> dict[str, Any]:
    """Load raw JSON from a file path or stdin ('-').

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the content is not valid JSON.
    """
    if source == "-":
        raw = sys.stdin.read()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {source}")
        raw = path.read_text()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at top level")
    return data


def format_result_json(result: RewriteResult) -> dict[str, Any]:
    """Format a RewriteResult as a JSON-serializable dict.

    Includes the result graph (if present) alongside metadata.
    """
    out: dict[str, Any] = {
        "success": result.success,
        "rule_name": result.rule_name,
        "errors": result.errors,
    }
    if result.result_graph is not None:
        out["result_graph"] = result.result_graph.to_dict()
    if result.pre_violations:
        out["pre_violations"] = [v.to_dict() for v in result.pre_violations]
    if result.post_violations:
        out["post_violations"] = [v.to_dict() for v in result.post_violations]
    return out


def validate_graph_json(data: dict[str, Any]) -> list[str]:
    """Validate structure of graph JSON. Returns list of error strings.

    Checks:
    - 'nodes' key exists and is a dict
    - 'edges' key exists and is a list
    - Each node has 'id', 'node_type', 'attrs'
    - Each edge has 'source', 'target', 'edge_type'
    """
    errors: list[str] = []

    if "nodes" not in data:
        errors.append("Missing 'nodes' key")
    elif not isinstance(data["nodes"], dict):
        errors.append("'nodes' must be a JSON object")
    else:
        for nid, ndata in data["nodes"].items():
            if not isinstance(ndata, dict):
                errors.append(f"Node '{nid}' must be a JSON object")
                continue
            for required in ("id", "node_type"):
                if required not in ndata:
                    errors.append(f"Node '{nid}' missing required field '{required}'")

    if "edges" not in data:
        errors.append("Missing 'edges' key")
    elif not isinstance(data["edges"], list):
        errors.append("'edges' must be a JSON array")
    else:
        for i, edata in enumerate(data["edges"]):
            if not isinstance(edata, dict):
                errors.append(f"Edge at index {i} must be a JSON object")
                continue
            for required in ("source", "target", "edge_type"):
                if required not in edata:
                    errors.append(f"Edge at index {i} missing required field '{required}'")

    return errors
