"""MCP Tools for graph-transform.

Provides:
- spec: Discover operators
- query: Find nodes
- plan: Create transformation plans
- verify: Validate transformations
"""

from graph_transform.mcp.tools.spec import spec_tool
from graph_transform.mcp.tools.query import query_tool
from graph_transform.mcp.tools.plan import plan_tool
from graph_transform.mcp.tools.verify import verify_tool

__all__ = ["spec_tool", "query_tool", "plan_tool", "verify_tool"]
