"""
Spec Tool - Discover available operators and their parameters.

FR1: Agents can discover all available operators via `spec` tool
FR44: Returns operator names and descriptions
FR45: Returns required and optional parameters for each operator
FR46: Returns preconditions for each operator
"""

from __future__ import annotations

from typing import Any

from graph_transform.mcp.registry import OperatorRegistry


def spec_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Handle spec tool calls.

    Args:
        args: Tool arguments, optionally including 'operator' to get specific details

    Returns:
        JSON response with operator specifications
    """
    registry = OperatorRegistry()
    operator = args.get("operator")

    if operator:
        return _get_operator_spec(registry, operator)

    return _get_all_specs(registry)


def _get_operator_spec(registry: OperatorRegistry, name: str) -> dict[str, Any]:
    """Get specification for a specific operator."""
    op = registry.get(name)

    if op is None:
        return {
            "status": "error",
            "error": {
                "code": "UNKNOWN_OPERATOR",
                "message": f"Unknown operator: {name}",
                "available_primitives": [p.name for p in registry.list_primitives()],
                "available_compositions": [c.name for c in registry.list_compositions()],
            }
        }

    return {
        "status": "ok",
        "operator": op.to_dict(),
    }


def _get_all_specs(registry: OperatorRegistry) -> dict[str, Any]:
    """Get specifications for all operators."""
    return {
        "status": "ok",
        "primitives": [op.to_dict() for op in registry.list_primitives()],
        "compositions": [op.to_dict() for op in registry.list_compositions()],
    }
