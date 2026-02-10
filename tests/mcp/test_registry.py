"""
Tests for Story 1.2: Operator Registry with Metadata

Acceptance Criteria:
- Operators are registered with full metadata
- Includes: name, description, required parameters, optional parameters
- Parameter definitions include type and description
- Can query by operator name
- Returns None for unknown operators
"""

from __future__ import annotations

import pytest


def test_operator_registry_exists():
    """Operator registry module can be imported."""
    from graph_transform.mcp.registry import OperatorRegistry
    assert OperatorRegistry is not None


def test_registry_has_operators():
    """Registry has operators registered."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()
    operators = registry.list_operators()

    assert len(operators) > 0


def test_operator_has_metadata():
    """Registered operators have full metadata."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()
    rename = registry.get("RENAME")

    assert rename is not None
    assert rename.name == "RENAME"
    assert rename.description != ""
    assert isinstance(rename.required_params, list)
    assert isinstance(rename.optional_params, list)


def test_parameter_has_type_and_description():
    """Parameter definitions include type and description."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()
    rename = registry.get("RENAME")

    # Should have target parameter
    target_param = next((p for p in rename.required_params if p.name == "target"), None)
    assert target_param is not None
    assert target_param.param_type != ""
    assert target_param.description != ""

    # Should have new_name parameter
    new_name_param = next((p for p in rename.required_params if p.name == "new_name"), None)
    assert new_name_param is not None
    assert new_name_param.param_type != ""
    assert new_name_param.description != ""


def test_query_by_name():
    """Can query operator by name."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()

    # Query various operators
    assert registry.get("RENAME") is not None
    assert registry.get("MOVE") is not None
    assert registry.get("EXTRACT") is not None
    assert registry.get("INSERT_NODE") is not None  # Primitive

    # Case-insensitive
    assert registry.get("rename") is not None
    assert registry.get("Rename") is not None


def test_unknown_operator_returns_none():
    """Returns None for unknown operators."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()

    assert registry.get("UNKNOWN_OPERATOR") is None
    assert registry.get("") is None
    assert registry.get("foobar123") is None


def test_registry_has_primitives():
    """Registry includes primitive operators."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()

    primitives = ["insert_node", "insert_edge", "delete_node", "delete_edge", "update"]
    for name in primitives:
        op = registry.get(name)
        assert op is not None, f"Missing primitive: {name}"
        assert op.operator_type == "primitive"


def test_registry_has_compositions():
    """Registry includes composition operators."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()

    compositions = ["RENAME", "MOVE", "EXTRACT", "INLINE", "ADD_GUARD", "CHANGE_SIGNATURE", "WRAP"]
    for name in compositions:
        op = registry.get(name)
        assert op is not None, f"Missing composition: {name}"
        assert op.operator_type == "composition"


def test_operator_has_preconditions():
    """Operators include preconditions."""
    from graph_transform.mcp.registry import OperatorRegistry

    registry = OperatorRegistry()
    rename = registry.get("RENAME")

    # RENAME should have precondition that target exists
    assert rename.preconditions is not None
    assert len(rename.preconditions) > 0
