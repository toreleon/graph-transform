# Graph Transformation Engine

MCP server providing verified code transformations for AI coding agents. Built on algebraic graph rewriting (DPO/SPO) with layered invariant verification.

## Overview

Graph-transform provides:
- **MCP Server**: AI agents connect via Model Context Protocol to query code, plan transformations, and verify results
- **Python API**: Programmatic access to the three-primitive system and compositions

## The Three-Primitive System

All code transformations reduce to three atomic operations:

| Primitive | Description |
|-----------|-------------|
| **INSERT** | Add a node or edge to the graph |
| **DELETE** | Remove a node or edge from the graph |
| **UPDATE** | Modify a property of an existing element |

These primitives compose into higher-level refactoring operations:

| Composition | Description |
|-------------|-------------|
| **RENAME** | Rename an entity and update all references |
| **MOVE** | Move an entity from one scope to another |
| **EXTRACT** | Extract code into a new entity |
| **INLINE** | Inline an entity into its call sites |
| **ADD_GUARD** | Add a guard/check before an operation |
| **CHANGE_SIGNATURE** | Change a callable's signature and update call sites |
| **WRAP** | Wrap code in a construct (try/catch, with, etc.) |

## Installation

```bash
# Install from source
pip install -e .

# Or with uv (recommended)
uv sync

# Verify installation
python -m graph_transform
```

## MCP Server Configuration

Add to your Claude Code settings:

```json
{
  "mcpServers": {
    "graph-transform": {
      "command": "python",
      "args": ["-m", "graph_transform.mcp"]
    }
  }
}
```

Or with explicit Python path:

```json
{
  "mcpServers": {
    "graph-transform": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "graph_transform.mcp"]
    }
  }
}
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `spec` | Discover available operators and their parameters |
| `query` | Find nodes in the code graph by pattern, kind, or file |
| `plan` | Create a transformation plan for a refactoring operation |
| `verify` | Verify graph state and validate transformations |

### Example Agent Workflow

```python
# 1. Discover operators
spec()  # Returns all primitives and compositions with schemas

# 2. Query for nodes
query(path="src/", pattern="*Service", kind="class")
# Returns: [{"id": "class:UserService", "file": "user.py", "line": 10}, ...]

# 3. Plan a transformation
plan(
    path="src/",
    operator="RENAME",
    params={"target": "class:UserService", "new_name": "AccountService"}
)
# Returns: {"status": "ok", "plan": {...}, "verification": {"valid": true}}

# 4. Verify the result
verify(path="src/")
# Returns: {"valid": true, "violations": []}
```

### Structured Error Responses

All MCP tools return structured errors with actionable suggestions:

```json
{
  "status": "error",
  "error": {
    "code": "TARGET_NOT_FOUND",
    "message": "Node 'func:unknown' not found",
    "phase": "precondition",
    "details": {"node_id": "func:unknown"},
    "suggestions": [
      {
        "action": "verify_target",
        "description": "Use the query tool to find the correct target ID",
        "example": "query pattern='*' to list all nodes"
      }
    ]
  }
}
```

## Python API

```python
from graph_transform import (
    # Build graphs
    build_graph_from_source,
    TypedGraph, GraphNode, GraphEdge, NodeType, EdgeType,
    # Primitives
    insert_node, insert_edge, delete_node, update,
    NodeKind, EdgeKind,
    # Compositions
    CompositionRegistry, Rename, Move, Extract,
    # Invariants
    InvariantRegistry, InvariantLayer, InvariantSeverity,
    # Engine
    create_engine,
)

# Build a graph from source
graph = build_graph_from_source("src/")
print(f"Nodes: {len(graph.nodes)}, Edges: {len(graph.edges)}")

# Apply a primitive
result = insert_node(
    "func:helper",
    NodeKind.CALLABLE,
    {"name": "helper", "file": "utils.py", "line": 10},
).execute(graph)
print(f"Success: {result.success}")

# Use compositions
rename = CompositionRegistry.create("RENAME", target="func:old", new_name="new_name")
for primitive in rename.primitives(graph):
    primitive.execute(graph)

# Verify invariants
registry = InvariantRegistry()
violations = registry.verify_graph(
    graph,
    layers={InvariantLayer.SCOPE, InvariantLayer.REFERENCE},
    min_severity=InvariantSeverity.ERROR,
)
for v in violations:
    print(f"{v.layer.name}: {v.message} ({v.fix_hint})")
```

## Invariant System

Verification is organized into ordered layers:

| Layer | Purpose | Examples |
|-------|---------|----------|
| **SCHEMA** | Type graph conformance | Edge types, multiplicity, required attrs |
| **STRUCTURE** | Topological integrity | Containment acyclicity, orphan detection |
| **SCOPE** | Name uniqueness | No duplicate function names in class |
| **REFERENCE** | Symbol resolution | All references point to existing nodes |
| **TYPE_SYSTEM** | Inheritance validity | No cycles, override compatibility |
| **SEMANTIC** | Arg/param matching | Call arguments match signature |
| **QUALITY** | Code quality hints | Unused imports, empty containers |

Each violation includes:
- `layer`: Which verification layer detected the issue
- `severity`: ERROR (blocks transformation) / WARNING / INFO
- `fix_hint`: Actionable suggestion for resolution

## Error Codes

| Code | Category | Description |
|------|----------|-------------|
| `MISSING_PATH` | Input | Required path not provided |
| `PATH_NOT_FOUND` | Input | File/directory doesn't exist |
| `UNKNOWN_OPERATOR` | Input | Invalid operator name |
| `PARSE_ERROR` | Parse | Python syntax error |
| `TARGET_NOT_FOUND` | Precondition | Node ID doesn't exist |
| `NAME_CONFLICT` | Conflict | Name already exists in scope |
| `SCOPE_VIOLATION` | Conflict | Access violation |
| `PRECONDITION_FAILED` | Verification | Operator precondition not met |
| `POSTCONDITION_FAILED` | Verification | Transformation broke invariant |
| `GLUING_VIOLATION` | DPO | Dangling edges would result |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design, module dependencies, and data flow diagrams.

## Tests

```bash
# Run all tests
make test

# Or directly with pytest
uv run pytest -v

# Run specific test files
uv run pytest tests/test_epic6_emission_feedback.py -v
```

## License

MIT
