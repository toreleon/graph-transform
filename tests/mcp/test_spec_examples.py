"""
Tests for Story 1.4: Spec Tool with Examples and LLM Documentation

Acceptance Criteria:
- FR47: Operators are self-describing for LLM consumption
- FR48: Documentation examples included in `spec` output
- Includes at least one usage example with input/output
- Descriptions are formatted for LLM consumption
- Edge cases and common errors are documented
- Agent can construct valid tool calls from documentation alone
"""

from __future__ import annotations

import json
import pytest


@pytest.fixture
def mcp_client():
    """Create MCP test client."""
    from graph_transform.mcp.server import create_app
    from graph_transform.mcp.testing import MCPTestClient
    return MCPTestClient(create_app())


def test_spec_includes_examples(mcp_client):
    """Spec includes usage examples (FR48)."""
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    assert result["status"] == "ok"
    op = result["operator"]

    # Should have example
    assert "example" in op
    example = op["example"]

    # Example should have required params
    assert "target" in example
    assert "new_name" in example


def test_all_operators_have_examples(mcp_client):
    """All operators include at least one example (FR48)."""
    result = mcp_client.call_tool("spec", {})

    for op in result["primitives"] + result["compositions"]:
        assert "example" in op, f"Missing example for {op['name']}"
        assert len(op["example"]) > 0, f"Empty example for {op['name']}"


def test_descriptions_are_llm_friendly(mcp_client):
    """Descriptions are formatted for LLM consumption (FR47)."""
    result = mcp_client.call_tool("spec", {})

    for op in result["primitives"] + result["compositions"]:
        desc = op["description"]

        # Description should be substantial
        assert len(desc) >= 10, f"Description too short for {op['name']}: {desc}"

        # Description should not be code or JSON
        assert not desc.startswith("{"), f"Description looks like JSON for {op['name']}"
        assert not desc.startswith("["), f"Description looks like JSON for {op['name']}"

        # Description should be plain English
        assert any(c.isalpha() for c in desc), f"Description has no letters for {op['name']}"


def test_param_descriptions_are_llm_friendly(mcp_client):
    """Parameter descriptions are formatted for LLM consumption (FR47)."""
    result = mcp_client.call_tool("spec", {"operator": "MOVE"})

    op = result["operator"]
    all_params = op["required_params"] + op["optional_params"]

    for param in all_params:
        # Each param should have description
        assert "description" in param
        desc = param["description"]
        assert len(desc) >= 5, f"Description too short for param {param['name']}"


def test_precondition_descriptions_are_clear(mcp_client):
    """Precondition descriptions are clear for LLMs."""
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    op = result["operator"]

    for pre in op["preconditions"]:
        assert "description" in pre
        desc = pre["description"]
        # Description should explain what must be true
        assert len(desc) >= 10, f"Precondition description too short: {desc}"


def test_example_has_valid_structure(mcp_client):
    """Examples have valid structure matching required params."""
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    op = result["operator"]
    example = op["example"]
    required_names = {p["name"] for p in op["required_params"]}

    # Example should include all required params
    for name in required_names:
        assert name in example, f"Example missing required param: {name}"


def test_agent_can_construct_tool_call(mcp_client):
    """Agent can construct valid tool calls from documentation (FR47)."""
    # Get RENAME spec
    result = mcp_client.call_tool("spec", {"operator": "RENAME"})

    op = result["operator"]
    example = op["example"]

    # Simulate agent constructing a tool call from the example
    # The example should be usable as params directly
    assert "target" in example
    assert "new_name" in example

    # Example values should be valid types
    assert isinstance(example["target"], str)
    assert isinstance(example["new_name"], str)


def test_spec_complete_for_all_compositions(mcp_client):
    """All compositions have complete LLM-friendly documentation."""
    result = mcp_client.call_tool("spec", {})

    compositions = ["RENAME", "MOVE", "EXTRACT", "INLINE", "ADD_GUARD", "CHANGE_SIGNATURE", "WRAP"]

    for name in compositions:
        op_result = mcp_client.call_tool("spec", {"operator": name})
        assert op_result["status"] == "ok", f"Failed to get spec for {name}"

        op = op_result["operator"]

        # Must have all required fields
        assert "description" in op
        assert "required_params" in op
        assert "optional_params" in op
        assert "preconditions" in op
        assert "example" in op

        # Description must be meaningful
        assert len(op["description"]) >= 20, f"Description too short for {name}"

        # Must have at least one required param
        assert len(op["required_params"]) > 0, f"No required params for {name}"

        # Must have at least one precondition
        assert len(op["preconditions"]) > 0, f"No preconditions for {name}"


def test_spec_complete_for_all_primitives(mcp_client):
    """All primitives have complete LLM-friendly documentation."""
    primitives = ["insert_node", "insert_edge", "delete_node", "delete_edge", "update"]

    for name in primitives:
        op_result = mcp_client.call_tool("spec", {"operator": name})
        assert op_result["status"] == "ok", f"Failed to get spec for {name}"

        op = op_result["operator"]

        # Must have all required fields
        assert "description" in op
        assert "required_params" in op
        assert "example" in op

        # Description must be meaningful
        assert len(op["description"]) >= 20, f"Description too short for {name}"
