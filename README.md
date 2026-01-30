# Graph Transformation Engine

Algebraic graph rewriting (DPO/SPO) with pre/post invariant checking for verifying and applying refactoring operators on code graphs.

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
# List all 41 refactoring operators
graph-transform list

# Build a graph from Python source
graph-transform build src/ -o graph.json -v

# Check invariants on a graph
graph-transform verify graph.json

# Apply a refactoring operator
graph-transform apply graph.json \
  -op add_method \
  -p '{"class_name":"MyClass","method_name":"new_helper"}' \
  -o result.json

# Preview changes without applying (dry-run)
graph-transform dry-run graph.json \
  -op rename_class \
  -p '{"old_name":"Foo","new_name":"Bar"}'

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

List all available refactoring operators.

```bash
graph-transform list [--category <cat>] [--json]

# Examples  
graph-transform list                   # Show all operators
graph-transform list --category method # Only method operators
graph-transform list --json            # Machine-readable output
```

### `graph-transform apply`

Apply a refactoring operator to a graph.

```bash
graph-transform apply <graph.json> -op <operator> -p '<params>' [options]

# Options
  -op, --operator   Operator name (e.g. add_method, rename_class)
  -p, --params      JSON string of operator parameters
  -m, --mode        Rewriting mode: dpo (default) or spo
  -o, --output      Output file (default: stdout)
  --no-invariants   Skip invariant checking
  -v, --verbose     Show detailed output
  --json            Output full result as JSON

# Examples
graph-transform apply g.json -op add_class -p '{"class_name":"Helper"}' -o g2.json
graph-transform apply g.json -op remove_class -p '{"class_name":"Old"}' -m spo
```

### `graph-transform batch`

Apply multiple operators in sequence (operator chains).

```bash
graph-transform batch <graph.json> -f <refactor.yaml> -o result.json
graph-transform batch <graph.json> -op <op1> -p '<p1>' -op <op2> -p '<p2>' -o result.json

# Options
  -f, --file         YAML file defining steps
  -op, --operator    Operator name (repeatable)
  -p, --params       JSON params for each operator
  --check-per-step   Run invariants after each step (default: only at end)
  -v, --verbose      Show detailed output
```

**YAML file format** (`refactor.yaml`):
```yaml
description: "Add logging parameter"
steps:
  - op: add_param
    params:
      function_name: get_group_vars
      param_name: logging
      default_value: "True"
      
  - op: add_arg
    params:
      callee: get_group_vars
      arg_name: logging
      arg_value: "True"
    repeat: all  # Apply to all matching call sites
```

Check if an operator is applicable without modifying the graph.

```bash
graph-transform dry-run <graph.json> -op <operator> -p '<params>'

# Example
graph-transform dry-run g.json -op rename_method \
  -p '{"old_name":"foo","new_name":"bar"}'
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

## Supported Operators (41)

| Category | Operators |
|----------|-----------|
| **Method** (9) | `add_method`, `remove_method`, `rename_method`, `move_method`, `extract_method`, `inline_method`, `pull_up_method`, `push_down_method`, `change_signature` |
| **Field** (7) | `add_field`, `remove_field`, `rename_field`, `move_field`, `pull_up_field`, `push_down_field`, `encapsulate_field` |
| **Class** (7) | `add_class`, `remove_class`, `rename_class`, `move_class`, `extract_class`, `inline_class`, `extract_superclass` |
| **Parameter** (4) | `add_param`, `remove_param`, `rename_param`, `introduce_param_object` |
| **Module** (5) | `create_module`, `delete_module`, `rename_module`, `move_to_module`, `merge_modules` |
| **Reference** (5) | `add_import`, `remove_import`, `update_import`, `update_call`, `update_reference` |
| **Call-Site** (3) | `add_arg`, `remove_arg`, `update_arg` |

## Python API

```python
from graph_transform import (
    TypedGraph, GraphNode, GraphEdge,
    NodeType, EdgeType, OperatorType,
    create_engine,
)

# Build a graph
graph = TypedGraph()
graph.add_node(GraphNode("class:MyClass", NodeType.CLASS, {"name": "MyClass"}))
graph.add_node(GraphNode("func:do_work", NodeType.FUNCTION, {"name": "do_work"}))
graph.add_edge(GraphEdge("class:MyClass", "func:do_work", EdgeType.CONTAINS_METHOD))

# Create engine and apply a rule
engine = create_engine(mode="dpo", check_invariants=True)
rule = engine.catalog.create_rule(OperatorType.ADD_METHOD, {
    "class_name": "MyClass",
    "method_name": "new_helper",
})
result = engine.apply_rule(rule, graph)
print(f"Success: {result.success}")
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
