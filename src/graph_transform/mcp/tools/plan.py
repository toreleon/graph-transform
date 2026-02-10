"""
Plan Tool - Create transformation plans.

FR3: Agents can create transformation plans via `plan` tool
FR24: Plans include all affected files and edit locations
FR25: Plans include summary of changes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_transform.io.builder import build_graph_from_source as build_graph
from graph_transform.core.primitives import CompositionRegistry


def plan_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Handle plan tool calls.

    Args:
        args: Tool arguments including:
            - path: File or directory to transform (required)
            - operator: Operator name (required)
            - params: Operator parameters (required)

    Returns:
        JSON response with transformation plan
    """
    path = args.get("path")
    operator = args.get("operator")
    params = args.get("params", {})

    if not path:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_PATH",
                "message": "path is required"
            }
        }

    if not operator:
        return {
            "status": "error",
            "error": {
                "code": "MISSING_OPERATOR",
                "message": "operator is required"
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

    # Get the composition
    operator_upper = operator.upper()
    composition_cls = CompositionRegistry.get(operator_upper)

    if composition_cls is None:
        return {
            "status": "error",
            "error": {
                "code": "UNKNOWN_OPERATOR",
                "message": f"Unknown operator: {operator}",
                "available": list(CompositionRegistry.list_names())
            }
        }

    try:
        composition = CompositionRegistry.create(operator_upper, **params)
        primitives = composition.to_primitives(graph)
    except Exception as e:
        return {
            "status": "error",
            "error": {
                "code": "PLAN_ERROR",
                "message": str(e)
            }
        }

    # Collect affected files and generate plan
    affected_files = set()
    edits = []

    for primitive in primitives:
        prim_type = type(primitive).__name__
        prim_dict = _primitive_to_dict(primitive)

        # Track affected files from node attributes
        if hasattr(primitive, "attrs") and primitive.attrs:
            if "file" in primitive.attrs:
                affected_files.add(primitive.attrs["file"])

        edits.append({
            "type": prim_type,
            "params": prim_dict
        })

    return {
        "status": "ok",
        "operator": operator_upper,
        "params": params,
        "plan": {
            "primitives": edits,
            "affected_files": sorted(affected_files),
            "summary": {
                "primitive_count": len(primitives),
                "file_count": len(affected_files),
            }
        }
    }


def _primitive_to_dict(primitive: Any) -> dict[str, Any]:
    """Convert a primitive to a JSON-serializable dict."""
    result = {}
    for field in ["node_id", "node_kind", "attrs", "source", "target",
                  "edge_kind", "cascade", "prop", "value", "properties"]:
        if hasattr(primitive, field):
            val = getattr(primitive, field)
            if val is not None:
                if hasattr(val, "value"):
                    result[field] = val.value
                else:
                    result[field] = val
    return result
