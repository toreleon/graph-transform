"""
MCP Server Entry Point with StreamableHttp

Story 1.1: AI agents can connect via StreamableHttp transport
and invoke transformation tools.

The server is stateless per-call (FR6) and returns JSON responses (FR5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from graph_transform.mcp.tools.spec import spec_tool
from graph_transform.mcp.tools.query import query_tool
from graph_transform.mcp.tools.plan import plan_tool
from graph_transform.mcp.tools.verify import verify_tool


@dataclass
class Tool:
    """MCP tool definition."""
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class MCPApp:
    """MCP Application with registered tools."""
    tools: dict[str, Tool]

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self.tools.values())

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool by name with arguments."""
        if name not in self.tools:
            return {
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {name}"
                }
            }
        tool = self.tools[name]
        try:
            result = tool.handler(arguments)
            return result
        except Exception as e:
            return {
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }


def create_app() -> MCPApp:
    """Create the MCP application with all tools registered.

    Returns an MCPApp instance with spec, query, plan, and verify tools.
    """
    tools = {
        "spec": Tool(
            name="spec",
            description="Discover available transformation operators and their parameters",
            input_schema={
                "type": "object",
                "properties": {
                    "operator": {
                        "type": "string",
                        "description": "Optional: specific operator to get details for"
                    }
                },
                "required": []
            },
            handler=spec_tool
        ),
        "query": Tool(
            name="query",
            description="Query for nodes in the code graph by pattern, kind, or file path",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory path to query"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Name pattern to match (glob or re: prefix for regex)"
                    },
                    "kind": {
                        "type": "string",
                        "description": "Node kind filter (function, class, etc.)"
                    },
                    "file": {
                        "type": "string",
                        "description": "File path filter (glob pattern)"
                    }
                },
                "required": ["path"]
            },
            handler=query_tool
        ),
        "plan": Tool(
            name="plan",
            description="Create a transformation plan for a refactoring operation",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory path to transform"
                    },
                    "operator": {
                        "type": "string",
                        "description": "Operator name (RENAME, MOVE, etc.)"
                    },
                    "params": {
                        "type": "object",
                        "description": "Operator parameters"
                    }
                },
                "required": ["path", "operator", "params"]
            },
            handler=plan_tool
        ),
        "verify": Tool(
            name="verify",
            description="Verify graph state and validate transformations",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory path to verify"
                    },
                    "graph": {
                        "type": "string",
                        "description": "Path to graph JSON file to verify"
                    }
                },
                "required": []
            },
            handler=verify_tool
        ),
    }

    return MCPApp(tools=tools)


def _create_mcp_server():
    """Create and configure the MCP server with all tools.

    Returns:
        Configured FastMCP server instance.

    Raises:
        ImportError: If MCP SDK is not installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise ImportError(
            "MCP SDK not installed. Install with: pip install graph-transform[mcp]"
        )

    mcp = FastMCP("graph-transform")

    # Register spec tool
    @mcp.tool()
    def spec(operator: str | None = None) -> dict:
        """Discover available transformation operators and their parameters.

        Args:
            operator: Optional specific operator to get details for

        Returns:
            JSON with operator specifications including names, descriptions,
            parameters, preconditions, and examples.
        """
        return spec_tool({"operator": operator} if operator else {})

    # Register query tool
    @mcp.tool()
    def query(
        path: str,
        pattern: str | None = None,
        kind: str | None = None,
        file: str | None = None,
    ) -> dict:
        """Query for nodes in the code graph by pattern, kind, or file path.

        Args:
            path: File or directory path to query
            pattern: Name pattern to match (glob or re: prefix for regex)
            kind: Node kind filter (function, class, etc.)
            file: File path filter (glob pattern)

        Returns:
            JSON with matching nodes including id, kind, name, file, line.
        """
        return query_tool({
            "path": path,
            "pattern": pattern,
            "kind": kind,
            "file": file,
        })

    # Register plan tool
    @mcp.tool()
    def plan(path: str, operator: str, params: dict) -> dict:
        """Create a transformation plan for a refactoring operation.

        Args:
            path: File or directory path to transform
            operator: Operator name (RENAME, MOVE, EXTRACT, etc.)
            params: Operator parameters

        Returns:
            JSON with transformation plan including primitives and affected files.
        """
        return plan_tool({
            "path": path,
            "operator": operator,
            "params": params,
        })

    # Register verify tool
    @mcp.tool()
    def verify(path: str | None = None, graph: str | None = None) -> dict:
        """Verify graph state and validate transformations.

        Args:
            path: File or directory path to verify
            graph: Path to graph JSON file to verify

        Returns:
            JSON with verification status and any violations.
        """
        return verify_tool({"path": path, "graph": graph})

    return mcp


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Start the MCP server with StreamableHttp transport.

    Args:
        host: Host to bind to
        port: Port to bind to
    """
    mcp = _create_mcp_server()
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    serve()
