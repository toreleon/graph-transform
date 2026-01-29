# Graph Transformation Engine

Algebraic graph rewriting (DPO/SPO) with pre/post invariant checking for verifying and applying refactoring operators on code graphs.

## Overview

This package implements a formal graph transformation engine based on the **Double Pushout (DPO)** and **Single Pushout (SPO)** approaches from algebraic graph rewriting theory. Each of the 40+ refactoring operators (from Fowler's catalog and Opdyke's thesis) is defined as a production rule `L <- K -> R`, where:

- **L** (left-hand side) is the pattern to match in the host graph
- **K** (interface/gluing) is the structure preserved by the rewrite
- **R** (right-hand side) is the replacement

The engine finds subgraph matches via VF2 backtracking, verifies pre/post invariants, and computes pushouts to produce new graph states.

## Quick Start

```python
from graph_transform import (
    TypedGraph, GraphNode, GraphEdge,
    NodeType, EdgeType, OperatorType,
    create_engine,
)

# Build a typed graph
graph = TypedGraph()
graph.add_node(GraphNode("cls:MyClass", NodeType.CLASS, {"name": "MyClass"}))
graph.add_node(GraphNode("func:do_work", NodeType.FUNCTION, {"name": "do_work", "is_method": True}))
graph.add_edge(GraphEdge("cls:MyClass", "func:do_work", EdgeType.CONTAINS_METHOD))

# Create engine and a production rule
engine = create_engine(mode="dpo", check_invariants=True)
rule = engine.catalog.create_rule(OperatorType.ADD_METHOD, {
    "class_name": "MyClass",
    "method_name": "new_helper",
})

# Apply the rule
result = engine.apply_rule(rule, graph)
assert result.success
print(f"Graph now has {len(result.result_graph.nodes)} nodes")
```

### One-Shot Convenience

```python
from graph_transform import apply_operator, OperatorType

result = apply_operator(
    OperatorType.ADD_PARAM,
    {"function_name": "get_data", "param_name": "log", "default_value": "True"},
    graph,
)
```

### Multi-Step Transformation Path

```python
from graph_transform import create_engine, OperatorType, TransformationPath, RuleApplication

engine = create_engine()
catalog = engine.catalog

path = TransformationPath()
path.steps = [
    RuleApplication(rule=catalog.create_rule(OperatorType.ADD_PARAM, {
        "function_name": "get_data", "param_name": "log", "default_value": "True",
    })),
    RuleApplication(rule=catalog.create_rule(OperatorType.ADD_ARG, {
        "callee": "get_data", "arg_name": "log", "arg_value": "False",
    })),
]

result_path = engine.apply_path(path, graph)
print(f"Steps succeeded: {result_path.success_count}/{result_path.length}")
```

## Architecture

```
                    +---------------------------+
                    | GraphTransformationEngine |
                    +---------------------------+
                      |    |    |    |    |
          +-----------+    |    |    |    +-----------+
          v                v    v    v                v
   MatchFinder    PushoutEngine  |  InvariantRegistry  ProductionRuleCatalog
   (VF2 match)    (DPO / SPO)   |  (6 built-in        (40+ operator
                                |   invariants)         rule factories)
                                v
                       TransformationPath
                       (sequenced steps)
```

### Module Dependency Layers

| Layer | Module | Purpose |
|-------|--------|---------|
| 1 | `primitive_operators.py` | OperatorType enum (40+ ops), OperatorAlgebra, RefactorPlan |
| 1 | `nodes.py` | ClassNode, FieldNode, ImportNode, ModuleNode |
| 2 | `typed_graph.py` | NodeType, EdgeType, GraphNode, GraphEdge, TypedGraph |
| 3 | `morphism.py` | GraphMorphism (validity, injectivity, composition) |
| 4 | `production_rule.py` | ProductionRule (L <- K -> R), RewriteMode, RewriteResult |
| 5 | `match_finder.py` | VF2-style subgraph isomorphism |
| 5 | `pushout_engine.py` | DPO/SPO pushout construction |
| 5 | `invariants.py` | Invariant, InvariantRegistry, 6 built-in checks |
| 6 | `rule_catalog.py` | ProductionRuleCatalog (factory for all 40+ operators) |
| 6 | `transformation_path.py` | RuleApplication, TransformationPath |
| 7 | `engine.py` | GraphTransformationEngine + convenience functions |

## Core Concepts

### Typed Graph

A uniform representation where all code elements (functions, classes, parameters, etc.) are stored as `GraphNode` objects with a `NodeType` and an attribute dictionary. Edges are `GraphEdge` objects typed by `EdgeType`.

```python
# 8 node types
NodeType: FUNCTION, CLASS, FIELD, PARAMETER, CALL, ARGUMENT, IMPORT, MODULE

# 10 edge types
EdgeType: CONTAINS_METHOD, CONTAINS_FIELD, HAS_PARAMETER, HAS_ARGUMENT,
          CALLS, INHERITS, IMPORTS, DEFINED_IN, CALLER_OF, REFERENCES
```

Convert from the existing `CodeGraph` representation:

```python
typed_graph = TypedGraph.from_code_graph(code_graph, classes, fields, imports, modules)
```

### Production Rules (L <- K -> R)

Each operator is encoded as a production rule with three graphs and two inclusion morphisms:

```
L  <--l--  K  --r-->  R
(pattern)  (glue)   (replacement)
```

- **Deleted**: nodes in L but not in K
- **Preserved**: nodes in K (present in both L and R)
- **Created**: nodes in R but not in K

Example -- `ADD_PARAM` rule:
- L: `{func_node}` -- K: `{func_node}` -- R: `{func_node, param_node, HAS_PARAMETER edge}`
- Deleted: nothing. Created: param_node + edge. Preserved: func_node.

### DPO vs SPO

| Mode | Behavior | Use When |
|------|----------|----------|
| **DPO** (default) | Checks gluing condition; fails if deleting a node would leave dangling edges | Safe structural refactorings (add/rename/move) |
| **SPO** | Auto-removes dangling edges on deletion | Cascade-delete operators (REMOVE_CLASS, DELETE_MODULE) |

DPO gluing condition has two parts:
1. **Dangling condition**: no edge outside the match is incident to a deleted node
2. **Identification condition**: match is injective on deleted nodes

### Invariant System

Six built-in graph-level invariants checked before and after each rewrite:

| Invariant | Severity | Description |
|-----------|----------|-------------|
| `no_dangling_edges` | error | All edge endpoints must exist as nodes |
| `unique_function_names_in_class` | error | No duplicate method names within a class |
| `unique_class_names_in_module` | error | No duplicate class names within a module |
| `unique_field_names_in_class` | error | No duplicate field names within a class |
| `valid_inheritance` | error | No circular inheritance, no self-inheritance |
| `parameter_positions_consecutive` | warning | Parameter positions should be 0..n-1 |

Register custom invariants:

```python
from graph_transform import Invariant, InvariantViolation

def check_max_params(graph):
    violations = []
    for func in graph.get_nodes_by_type(NodeType.FUNCTION):
        params = [e for e in graph.get_edges_from(func.id) if e.edge_type == EdgeType.HAS_PARAMETER]
        if len(params) > 5:
            violations.append(InvariantViolation("max_params", f"{func.id} has too many params"))
    return violations

engine.invariants.add_invariant(Invariant("max_params", "Max 5 params per function", check_max_params))
```

## Supported Operators (41)

### Method-Level (9)
`ADD_METHOD`, `REMOVE_METHOD`, `RENAME_METHOD`, `MOVE_METHOD`, `EXTRACT_METHOD`, `INLINE_METHOD`, `PULL_UP_METHOD`, `PUSH_DOWN_METHOD`, `CHANGE_SIGNATURE`

### Field-Level (7)
`ADD_FIELD`, `REMOVE_FIELD`, `RENAME_FIELD`, `MOVE_FIELD`, `PULL_UP_FIELD`, `PUSH_DOWN_FIELD`, `ENCAPSULATE_FIELD`

### Class-Level (7)
`ADD_CLASS`, `REMOVE_CLASS`, `RENAME_CLASS`, `MOVE_CLASS`, `EXTRACT_CLASS`, `INLINE_CLASS`, `EXTRACT_SUPERCLASS`

### Parameter-Level (4)
`ADD_PARAM`, `REMOVE_PARAM`, `RENAME_PARAM`, `INTRODUCE_PARAM_OBJECT`

### Module-Level (5)
`CREATE_MODULE`, `DELETE_MODULE`, `RENAME_MODULE`, `MOVE_TO_MODULE`, `MERGE_MODULES`

### Reference-Level (5)
`ADD_IMPORT`, `REMOVE_IMPORT`, `UPDATE_IMPORT`, `UPDATE_CALL`, `UPDATE_REFERENCE`

### Call-Site Level (3)
`ADD_ARG`, `REMOVE_ARG`, `UPDATE_ARG`

### Meta
`RENAME_FUNC` (alias for RENAME_METHOD at function level)

## Engine API

### `GraphTransformationEngine`

| Method | Description |
|--------|-------------|
| `apply_rule(rule, graph, match=None)` | Apply a single production rule with full invariant pipeline |
| `apply_all_matches(rule, graph, max=100)` | Apply rule at all non-overlapping match sites |
| `apply_path(path, graph, stop_on_failure=True)` | Apply an ordered sequence of rules |
| `find_matches(rule, graph, max=100)` | Find all matches of rule's LHS in graph |
| `dry_run(rule, graph)` | Check applicability without modifying the graph |
| `verify_graph(graph)` | Run all graph-level invariants |

### Convenience Functions

```python
# Create engine with mode and invariant settings
engine = create_engine(mode="dpo", check_invariants=True)

# One-shot apply
result = apply_operator(OperatorType.RENAME_METHOD, {"old_name": "foo", "new_name": "bar"}, graph)

# Quick invariant check
violations = verify_graph_invariants(graph)
```

### `RewriteResult`

Returned by all apply methods:

```python
@dataclass
class RewriteResult:
    success: bool                              # Did the rewrite succeed?
    result_graph: TypedGraph | None            # The rewritten graph (None on failure)
    match: GraphMorphism | None                # The match used
    errors: list[str]                          # Error messages
    pre_violations: list[InvariantViolation]   # Precondition violations
    post_violations: list[InvariantViolation]  # Postcondition violations
    rule_name: str                             # Name of the rule applied
```

## Apply Rule Pipeline

When `engine.apply_rule(rule, graph)` is called:

1. **Find match** `m: L -> G` via VF2 backtracking (if not provided)
2. **Verify preconditions** on the host graph G
3. **Verify graph invariants** on G (optional)
4. **Compute pushout** via DPO or SPO to produce G'
5. **Verify postconditions** on the result graph G'
6. **Verify graph invariants** on G' (optional)

If any step fails, a `RewriteResult` with `success=False` is returned immediately.

## Tests

```bash
python -m pytest tests/test_graph_transformation_engine.py -v
```

73 tests covering:
- Extended node types (creation, serialization roundtrips)
- TypedGraph (CRUD, dangling edges, subgraph, copy)
- GraphMorphism (validity, injectivity, composition)
- MatchFinder (single/multi match, wildcards, edge patterns)
- ProductionRule (deleted/created/preserved nodes, validation)
- DPO rewriting (add/delete node, gluing condition, attr update)
- SPO rewriting (auto-removal of dangling edges)
- Invariants (all 6 built-in + custom)
- ProductionRuleCatalog (one test per category + full coverage check)
- TransformationPath (sequencing, serialization)
- GraphTransformationEngine (end-to-end: apply, dry_run, find_matches, paths)
- Real-world scenarios (add_param + update_call_sites, move_method, sequential paths)
