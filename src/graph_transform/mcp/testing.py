"""
Testing utilities for the MCP server.

Provides MCPTestClient for testing MCP tools without a network connection.
"""

from __future__ import annotations

from typing import Any


class MCPTestClient:
    """Test client for MCP server tools.

    Allows calling tools directly without HTTP transport.
    """

    def __init__(self, app: "MCPApp") -> None:
        """Initialize with an MCPApp instance."""
        self.app = app

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool by name with arguments.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result as dict
        """
        return self.app.call_tool(name, arguments)

    def list_tools(self) -> list[str]:
        """List available tool names."""
        return [t.name for t in self.app.list_tools()]
