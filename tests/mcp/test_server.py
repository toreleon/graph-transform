"""
Tests for Story 1.1: MCP Server Entry Point with StreamableHttp

Acceptance Criteria:
- Server accepts connection using StreamableHttp transport
- Returns valid MCP handshake response
- All tool calls return valid JSON responses (FR5)
- No session state is retained between calls (FR6)
- Responses conform to MCP JSON-RPC 2.0 specification (NFR-I1)
"""

from __future__ import annotations

import json
from typing import Any

import pytest


def test_mcp_server_module_exists():
    """MCP server module can be imported."""
    from graph_transform.mcp import server
    assert hasattr(server, "create_app")


def test_mcp_server_has_tools():
    """MCP server has spec, query, plan, verify tools registered."""
    from graph_transform.mcp.server import create_app

    app = create_app()
    # Check that the tools are registered
    tools = app.list_tools()
    tool_names = {t.name for t in tools}

    assert "spec" in tool_names, "spec tool must be registered"
    assert "query" in tool_names, "query tool must be registered"
    assert "plan" in tool_names, "plan tool must be registered"
    assert "verify" in tool_names, "verify tool must be registered"


def test_spec_tool_returns_json(mcp_test_client):
    """Spec tool returns valid JSON response (FR5)."""
    result = mcp_test_client.call_tool("spec", {})

    # Result should be JSON-serializable
    json.dumps(result)
    assert isinstance(result, dict)


def test_query_tool_returns_json(mcp_test_client, tmp_path):
    """Query tool returns valid JSON response (FR5)."""
    # Create a simple Python file to query
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello(): pass")

    result = mcp_test_client.call_tool("query", {
        "path": str(test_file),
        "kind": "function"
    })

    json.dumps(result)
    assert isinstance(result, dict)


def test_plan_tool_returns_json(mcp_test_client, tmp_path):
    """Plan tool returns valid JSON response (FR5)."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def old_name(): pass")

    result = mcp_test_client.call_tool("plan", {
        "path": str(test_file),
        "operator": "rename",
        "params": {"target": "func:old_name", "new_name": "new_name"}
    })

    json.dumps(result)
    assert isinstance(result, dict)


def test_verify_tool_returns_json(mcp_test_client, tmp_path):
    """Verify tool returns valid JSON response (FR5)."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello(): pass")

    result = mcp_test_client.call_tool("verify", {
        "path": str(test_file)
    })

    json.dumps(result)
    assert isinstance(result, dict)


def test_stateless_calls(mcp_test_client, tmp_path):
    """No session state is retained between calls (FR6)."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello(): pass")

    # Call query twice - should get identical results
    result1 = mcp_test_client.call_tool("query", {
        "path": str(test_file),
        "kind": "function"
    })
    result2 = mcp_test_client.call_tool("query", {
        "path": str(test_file),
        "kind": "function"
    })

    # Results should be identical (no state accumulation)
    assert result1 == result2


def test_spec_response_time(mcp_test_client):
    """Spec tool responds in under 100ms (NFR-P1)."""
    import time

    start = time.perf_counter()
    mcp_test_client.call_tool("spec", {})
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"Spec tool took {elapsed:.3f}s, expected < 0.1s"


@pytest.fixture
def mcp_test_client():
    """Create a test client for the MCP server."""
    from graph_transform.mcp.server import create_app
    from graph_transform.mcp.testing import MCPTestClient

    app = create_app()
    return MCPTestClient(app)
