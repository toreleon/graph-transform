"""
graph-transform MCP Server

Provides MCP (Model Context Protocol) server for AI agents to perform
verified code transformations.

Tools:
- spec: Discover available operators and their parameters
- query: Find nodes in the code graph by pattern/kind/file
- plan: Create transformation plans
- verify: Validate graph state and transformations
"""

from graph_transform.mcp.server import create_app, serve

__all__ = ["create_app", "serve"]
