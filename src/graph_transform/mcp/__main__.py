"""
MCP Server Entry Point

Run with: python -m graph_transform.mcp

Configure in Claude Code with:
{
  "mcpServers": {
    "graph-transform": {
      "command": "python",
      "args": ["-m", "graph_transform.mcp"]
    }
  }
}
"""

from __future__ import annotations

import sys


def main() -> None:
    """Main entry point for MCP server."""
    # Check for MCP SDK
    try:
        from graph_transform.mcp.server import serve
        serve()
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Install with: pip install graph-transform[mcp]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
