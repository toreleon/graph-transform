"""
Plan Tool - Create transformation plans.

FR3: Agents can create transformation plans via `plan` tool
FR24: Plans include all affected files and edit locations
FR25: Plans include summary of changes
FR32: Verification runs automatically during plan creation
FR33-38: Structured error responses with actionable suggestions
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_transform.io.builder import build_graph_from_source as build_graph
from graph_transform.core.primitives import CompositionRegistry
from graph_transform.core.errors import (
    ErrorCode,
    ViolationType,
    ErrorDetails,
    SuggestionFactory,
    create_error_response,
)
from graph_transform.rewriting.invariants import (
    InvariantRegistry,
    InvariantSeverity,
)


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
        return create_error_response(
            ErrorCode.MISSING_PATH,
            "path is required",
            phase=ViolationType.INPUT_VALIDATION,
            suggestions=SuggestionFactory.for_target_not_found("path"),
        )

    if not operator:
        available = list(CompositionRegistry.list_compositions())
        return create_error_response(
            ErrorCode.MISSING_OPERATOR,
            "operator is required",
            phase=ViolationType.INPUT_VALIDATION,
            suggestions=SuggestionFactory.for_unknown_operator("", available),
        )

    path_obj = Path(path)
    if not path_obj.exists():
        return create_error_response(
            ErrorCode.PATH_NOT_FOUND,
            f"Path not found: {path}",
            phase=ViolationType.INPUT_VALIDATION,
            details=ErrorDetails(file=path),
            suggestions=SuggestionFactory.for_target_not_found(path),
        )

    try:
        graph = build_graph(path_obj)
    except SyntaxError as e:
        return create_error_response(
            ErrorCode.PARSE_ERROR,
            str(e),
            phase=ViolationType.PARSE,
            details=ErrorDetails(
                file=str(path_obj),
                line=getattr(e, "lineno", None),
                column=getattr(e, "offset", None),
                source_line=getattr(e, "text", None),
            ),
            suggestions=SuggestionFactory.for_parse_error(
                str(path_obj),
                getattr(e, "lineno", None),
            ),
        )
    except Exception as e:
        return create_error_response(
            ErrorCode.PARSE_ERROR,
            str(e),
            phase=ViolationType.PARSE,
            details=ErrorDetails(file=str(path_obj)),
            suggestions=SuggestionFactory.for_parse_error(str(path_obj)),
        )

    # Get the composition
    operator_upper = operator.upper()
    composition_cls = CompositionRegistry.get(operator_upper)
    available = list(CompositionRegistry.list_compositions())

    if composition_cls is None:
        return create_error_response(
            ErrorCode.UNKNOWN_OPERATOR,
            f"Unknown operator: {operator}",
            phase=ViolationType.INPUT_VALIDATION,
            suggestions=SuggestionFactory.for_unknown_operator(operator, available),
            available=available,  # Keep for backwards compat
        )

    try:
        composition = CompositionRegistry.create(operator_upper, **params)
        primitives = list(composition.primitives(graph))
        edit_instructions = composition.edit_instructions(graph)
    except ValueError as e:
        # Precondition-type errors (missing target, etc.)
        return create_error_response(
            ErrorCode.PRECONDITION_FAILED,
            str(e),
            phase=ViolationType.PRECONDITION,
            suggestions=SuggestionFactory.for_target_not_found(
                params.get("target", "unknown")
            ),
        )
    except Exception as e:
        return create_error_response(
            ErrorCode.PLAN_ERROR,
            str(e),
            phase=ViolationType.INTERNAL,
        )

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

    # FR32: Run automatic verification during planning
    verify = args.get("verify", True)  # Default to True
    verification_result = None

    if verify:
        registry = InvariantRegistry()
        violations = registry.verify_graph(
            graph,
            min_severity=InvariantSeverity.ERROR,  # Only report errors
        )

        if violations:
            verification_result = {
                "valid": False,
                "error_count": len(violations),
                "violations": [
                    {
                        "rule": v.invariant_name,
                        "message": v.message,
                        "node": v.node_id,
                        "layer": v.layer.name.lower() if v.layer else None,
                        "fix_hint": v.fix_hint,
                    }
                    for v in violations
                ],
            }
        else:
            verification_result = {
                "valid": True,
                "error_count": 0,
                "violations": [],
            }

    # Add files from edit instructions to affected_files
    for edit in edit_instructions:
        if "file" in edit:
            affected_files.add(edit["file"])
        if "old_path" in edit:
            affected_files.add(edit["old_path"])
        if "new_path" in edit:
            affected_files.add(edit["new_path"])

    result = {
        "status": "ok",
        "operator": operator_upper,
        "params": params,
        "plan": {
            "primitives": edits,
            "edits": edit_instructions,
            "affected_files": sorted(affected_files),
            "summary": {
                "primitive_count": len(primitives),
                "edit_count": len(edit_instructions),
                "file_count": len(affected_files),
            },
        },
    }

    if verification_result is not None:
        result["verification"] = verification_result

    return result


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
