"""
Verify Tool - Validate graph state and transformations.

FR4: Agents can verify graph state via `verify` tool
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_transform.io.builder import build_graph_from_source as build_graph
from graph_transform.io.serialization import load_graph
from graph_transform.rewriting.invariants import InvariantRegistry


def verify_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Handle verify tool calls.

    Args:
        args: Tool arguments including:
            - path: File or directory path to verify (optional)
            - graph: Path to graph JSON file to verify (optional)

    Returns:
        JSON response with verification status and any violations
    """
    path = args.get("path")
    graph_file = args.get("graph")

    if not path and not graph_file:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_INPUT",
                "message": "Either 'path' or 'graph' is required"
            }
        }

    try:
        if graph_file:
            graph_path = Path(graph_file)
            if not graph_path.exists():
                return {
                    "status": "error",
                    "error": {
                        "code": "GRAPH_NOT_FOUND",
                        "message": f"Graph file not found: {graph_file}"
                    }
                }
            graph = load_graph(graph_path)
        else:
            path_obj = Path(path)
            if not path_obj.exists():
                return {
                    "status": "error",
                    "error": {
                        "code": "PATH_NOT_FOUND",
                        "message": f"Path not found: {path}"
                    }
                }
            graph = build_graph(path_obj)
    except Exception as e:
        return {
            "status": "error",
            "error": {
                "code": "LOAD_ERROR",
                "message": str(e)
            }
        }

    # Run invariant checks
    registry = InvariantRegistry()
    violations = registry.verify_graph(graph)

    if not violations:
        return {
            "status": "ok",
            "valid": True,
            "violations": []
        }

    violation_list = []
    for v in violations:
        violation_list.append({
            "rule": v.rule_name if hasattr(v, "rule_name") else str(v),
            "message": v.message if hasattr(v, "message") else str(v),
            "node": v.node_id if hasattr(v, "node_id") else None,
            "severity": v.severity.value if hasattr(v, "severity") and hasattr(v.severity, "value") else "error",
        })

    return {
        "status": "ok",
        "valid": False,
        "violations": violation_list
    }
