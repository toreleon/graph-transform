"""
Verify Tool - Validate graph state and transformations.

FR4: Agents can verify graph state via `verify` tool
FR26: System validates DPO gluing conditions before plan approval
FR27: System checks for name conflicts in target scope
FR28: System verifies all references are resolvable after transformation
FR29: System detects scope violations
FR30: System validates preconditions for each operator
FR31: System validates postconditions after transformation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_transform.io.builder import build_graph_from_source as build_graph
from graph_transform.io.serialization import load_graph
from graph_transform.rewriting.invariants import (
    InvariantRegistry,
    InvariantLayer,
    InvariantSeverity,
)


def verify_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Handle verify tool calls.

    Args:
        args: Tool arguments including:
            - path: File or directory path to verify (optional)
            - graph: Path to graph JSON file to verify (optional)
            - layer: Specific layer to check (optional)
            - min_severity: Minimum severity to report (optional, default: info)
            - stop_on_error: Stop checking on first layer with errors (optional)

    Returns:
        JSON response with verification status and any violations
    """
    path = args.get("path")
    graph_file = args.get("graph")
    layer_filter = args.get("layer")
    min_severity_str = args.get("min_severity", "info")
    stop_on_error = args.get("stop_on_error", False)

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

    # Parse layer filter if provided
    layers = None
    if layer_filter:
        try:
            layers = {InvariantLayer[layer_filter.upper()]}
        except KeyError:
            return {
                "status": "error",
                "error": {
                    "code": "INVALID_LAYER",
                    "message": f"Unknown layer: {layer_filter}. Valid layers: "
                               f"{', '.join(l.name.lower() for l in InvariantLayer)}"
                }
            }

    # Parse minimum severity
    try:
        min_severity = InvariantSeverity(min_severity_str.lower())
    except ValueError:
        min_severity = InvariantSeverity.INFO

    # Run invariant checks
    registry = InvariantRegistry()
    violations = registry.verify_graph(
        graph,
        layers=layers,
        min_severity=min_severity,
        stop_on_layer_error=stop_on_error,
    )

    if not violations:
        return {
            "status": "ok",
            "valid": True,
            "violations": []
        }

    violation_list = []
    for v in violations:
        violation_list.append({
            "rule": v.invariant_name,
            "message": v.message,
            "node": v.node_id,
            "severity": v.severity.value,
            "layer": v.layer.name.lower() if v.layer else None,
            "fix_hint": v.fix_hint,
        })

    return {
        "status": "ok",
        "valid": False,
        "violations": violation_list
    }
