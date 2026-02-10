"""
Tests for Story 1.3: Spec Tool Returns Operator List

Acceptance Criteria:
- FR1: Agents can discover all available operators via `spec` tool
- FR44: Returns operator names and descriptions
- FR45: Returns required and optional parameters for each operator
- FR46: Returns preconditions for each operator
- NFR-P1: Response time under 100ms
"""

from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def mcp_client():
    """Create MCP test client."""
    from graph_transform.mcp.server import create_app
    from graph_transform.mcp.testing import MCPTestClient
    return MCPTestClient(create_app())


def test_spec_returns_all_operators(mcp_client):
    """Spec tool returns all operators (FR1)."""
    result = mcp_client.call_tool("spec", {})

    assert result["status"] == "ok"
    assert "primitives" in result
    assert "compositions" in result

    # Check primitives
    primitive_names = {p["name"] for p in result["primitives"]}
    assert "insert_node" in primitive_names
    assert "insert_edge" in primitive_names
    assert "delete_node" in primitive_names
    assert "delete_edge" in primitive_names
    assert "update" in primitive_names

    # Check compositions
    composition_names = {c["name"] for c in result["compositions"]}
    assert "RENAME" in composition_names
    assert "MOVE" in composition_names
    assert "EXTRACT" in composition_names
    assert "INLINE" in composition_names


def test_spec_returns_names_and_descriptions(mcp_client):
    """Spec tool returns operator names and descriptions (FR44)."""
    result = mcp_client.call_tool("spec", {})

    for op in result["primitives"] + result["compositions"]:
        assert "name" in op
        assert op["name"] != ""
        assert "description" in op
        assert op["description"] != ""


def test_spec_returns_required_params(mcp_client):
    """Spec tool returns required parameters (FR45)."""
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    assert result["status"] == "ok"
    op = result["operator"]

    # RENAME requires target and new_name
    required = op["required_params"]
    required_names = {p["name"] for p in required}

    assert "target" in required_names
    assert "new_name" in required_names


def test_spec_returns_optional_params(mcp_client):
    """Spec tool returns optional parameters (FR45)."""
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    op = result["operator"]

    # Should have optional params list
    assert "optional_params" in op

    # RENAME has update_references optional
    optional = op["optional_params"]
    optional_names = {p["name"] for p in optional}
    assert "update_references" in optional_names


def test_spec_returns_preconditions(mcp_client):
    """Spec tool returns preconditions (FR46)."""
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    op = result["operator"]

    # Should have preconditions
    assert "preconditions" in op
    assert len(op["preconditions"]) > 0

    # Check precondition structure
    for pre in op["preconditions"]:
        assert "name" in pre
        assert "description" in pre


def test_spec_unknown_operator(mcp_client):
    """Spec tool returns error for unknown operator."""
    result = mcp_client.call_tool("spec", {"operator": "UNKNOWN"})

    assert result["status"] == "error"
    assert "error" in result
    assert result["error"]["code"] == "UNKNOWN_OPERATOR"


def test_spec_response_time(mcp_client):
    """Spec tool responds in under 100ms (NFR-P1)."""
    start = time.perf_counter()
    mcp_client.call_tool("spec", {})
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"Spec took {elapsed:.3f}s, expected < 0.1s"


def test_spec_json_serializable(mcp_client):
    """Spec response is JSON serializable (FR5)."""
    result = mcp_client.call_tool("spec", {})

    # Should be able to serialize to JSON
    json_str = json.dumps(result)
    assert len(json_str) > 0

    # And parse back
    parsed = json.loads(json_str)
    assert parsed["status"] == "ok"


def test_spec_single_operator_json_serializable(mcp_client):
    """Single operator spec is JSON serializable (FR5)."""
    result = mcp_client.call_tool("spec", {"operator": "MOVE"})

    json_str = json.dumps(result)
    parsed = json.loads(json_str)

    assert parsed["status"] == "ok"
    assert parsed["operator"]["name"] == "MOVE"
