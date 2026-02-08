# Graph Transformation Engine

Algebraic graph rewriting (DPO/SPO) with pre/post invariant checking for verifying and applying refactoring operations on code graphs.

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
# Clone and install
git clone <repository-url>
cd graph-transform
pip install -e .

# Or with uv
uv sync --all-extras
```

## CLI Quick Start

```bash
# List available primitives and compositions
graph-transform list --primitives
graph-transform list --compositions

# Build a graph from Python source
graph-transform build src/ -o graph.json -v

# Check invariants on a graph
graph-transform verify graph.json

# Apply a primitive
graph-transform apply graph.json \
  --primitive insert_node \
  -p '{"node_id":"func:helper","node_kind":"callable","attrs":{"name":"helper"}}'

# Apply a composition
graph-transform apply graph.json \
  --composition RENAME \
  -p '{"target":"func:old","new_name":"new_name"}' \
  -o result.json

# Preview changes without applying (dry-run)
graph-transform dry-run graph.json \
  --composition RENAME \
  -p '{"target":"func:foo","new_name":"bar"}'

# Visualize the graph as SVG
graph-transform visualize graph.json -o diagram
```

## CLI Commands

### `graph-transform build`

Build a TypedGraph from Python source files.

```bash
graph-transform build <source> [-o output.json] [-v]

# Examples
graph-transform build src/                    # Parse directory, output to stdout
graph-transform build mymodule.py -o g.json   # Parse single file
graph-transform build . -o g.json -v          # Verbose: show summary
```

### `graph-transform list`

List available primitives and compositions.

```bash
graph-transform list [--primitives] [--compositions] [--json]

# Examples
graph-transform list --primitives     # Show all primitives
graph-transform list --compositions   # Show all compositions
graph-transform list --json           # Machine-readable output
```

### `graph-transform apply`

Apply a primitive or composition to a graph.

```bash
graph-transform apply <graph.json> [options]

# Options
  --primitive, -prim   Primitive to apply (insert_node, delete_node, update, etc.)
  --composition, -comp Composition to apply (RENAME, MOVE, EXTRACT, etc.)
  -p, --params         JSON string of parameters
  -m, --mode           Rewriting mode: dpo (default) or spo
  -o, --output         Output file (default: stdout)
  --no-invariants      Skip invariant checking
  -v, --verbose        Show detailed output
  --json               Output full result as JSON

# Examples
graph-transform apply g.json --primitive insert_node \
  -p '{"node_id":"func:helper","node_kind":"callable","attrs":{"name":"helper"}}' \
  -o g2.json

graph-transform apply g.json --composition RENAME \
  -p '{"target":"func:old","new_name":"new_name"}' \
  -o g2.json
```

### `graph-transform batch`

Apply multiple operations in sequence.

```bash
graph-transform batch <graph.json> -f <refactor.yaml> -o result.json

# Options
  -f, --file           YAML file defining steps
  --check-per-step     Run invariants after each step (default: only at end)
  -v, --verbose        Show detailed output
```

**YAML file format** (`refactor.yaml`):
```yaml
description: "Refactoring example"
steps:
  - primitive: insert_node
    params:
      node_id: "func:helper"
      node_kind: callable
      attrs:
        name: helper
        file: utils.py
        line: 10

  - composition: RENAME
    params:
      target: "func:old"
      new_name: "new_name"
```

### `graph-transform dry-run`

Check if an operation is applicable without modifying the graph.

```bash
graph-transform dry-run <graph.json> --primitive <name> -p '<params>'
graph-transform dry-run <graph.json> --composition <name> -p '<params>'

# Example
graph-transform dry-run g.json --composition RENAME \
  -p '{"target":"func:foo","new_name":"bar"}'
```

### `graph-transform plan`

Generate a refactoring edit plan from source code and transformations.

```bash
graph-transform plan <source> [options]

# Examples
graph-transform plan src/ -F refactor.yaml -o plan.json

graph-transform plan src/ \
  --primitive insert_node -p '{"node_id":"func:new","node_kind":"callable","attrs":{"name":"new"}}' \
  --composition RENAME -p '{"target":"func:old","new_name":"new_name"}' \
  -o plan.json
```

### `graph-transform verify`

Run all invariant checks on a graph.

```bash
graph-transform verify <graph.json> [-v]

# Example
graph-transform verify g.json -v   # Show all checks
```

### `graph-transform visualize`

Render a graph as SVG, PNG, or PDF (requires graphviz).

```bash
graph-transform visualize <graph.json> -o <output> [-f format]

# Examples
graph-transform visualize g.json -o diagram          # SVG (default)
graph-transform visualize g.json -o diagram -f png   # PNG
```

## Primitives

### INSERT Primitives

| Primitive | Description |
|-----------|-------------|
| `insert_node` | Add a new node (function, class, variable, etc.) |
| `insert_edge` | Add a new edge (containment, calls, inherits, etc.) |

### DELETE Primitives

| Primitive | Description |
|-----------|-------------|
| `delete_node` | Remove a node (with optional cascade) |
| `delete_edge` | Remove an edge |

### UPDATE Primitive

| Primitive | Description |
|-----------|-------------|
| `update` | Modify properties of a node or edge |

### Node Kinds

`callable`, `type`, `binding`, `container`, `reference`, `call`, `access`, `block`, `branch`, `loop`, `literal`, `expression`, `argument`, `annotation`

### Edge Kinds

`contains`, `defines`, `references`, `calls`, `accesses`, `imports`, `inherits`, `implements`, `type_of`, `flows_to`, `depends_on`, `has_parameter`, `has_argument`, `binds_to`

## Python API

```python
from graph_transform import (
    TypedGraph, GraphNode, GraphEdge,
    NodeType, EdgeType,
    insert_node, insert_edge, delete_node, update,
    NodeKind, EdgeKind,
    CompositionRegistry,
    create_engine,
)

# Build a graph
graph = TypedGraph()
graph.add_node(GraphNode("class:MyClass", NodeType.CLASS, {"name": "MyClass"}))
graph.add_node(GraphNode("func:do_work", NodeType.FUNCTION, {"name": "do_work"}))
graph.add_edge(GraphEdge("class:MyClass", "func:do_work", EdgeType.CONTAINS_METHOD))

# Use primitives directly
result = insert_node(
    "func:helper",
    NodeKind.CALLABLE,
    {"name": "helper", "file": "utils.py", "line": 10},
).execute(graph)
print(f"Success: {result.success}")

# Use compositions
rename = CompositionRegistry.create("RENAME", target="func:do_work", new_name="process")
result = rename.execute(graph)
print(f"Renamed: {result.success}")
```

### Build from Source

```python
from graph_transform.io import build_graph_from_source

graph = build_graph_from_source("src/")
print(f"Nodes: {graph.node_count}, Edges: {graph.edge_count}")
```

### SQLite Persistence

```python
from graph_transform.io import SQLiteGraphStore

store = SQLiteGraphStore("/tmp/graphs.db")
store.save_graph(graph, "my_project")
loaded = store.load_graph("my_project")
```

## Tests

```bash
# Run all tests
make test

# Or directly
uv run pytest -v
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design documentation.

## License

MIT
