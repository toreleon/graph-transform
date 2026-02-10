# Agent Integration Guide

This guide explains how AI agents integrate with graph-transform for verified code refactoring via the MCP (Model Context Protocol) server.

## Quick Start

Configure the MCP server in your Claude Code settings:

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

## Workflow Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    spec     │ ──► │    query    │ ──► │    plan     │ ──► │   verify    │
│  discover   │     │  find nodes │     │  transform  │     │   check     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

## MCP Tools

### 1. `spec` - Discover Operators

Get available operators and their parameters.

**Request:**
```json
{"operator": null}
```

**Response:**
```json
{
  "status": "ok",
  "primitives": [
    {
      "name": "insert_node",
      "description": "Insert a new node into the graph",
      "params": {
        "node_id": {"type": "string", "required": true},
        "node_kind": {"type": "string", "required": true},
        "attrs": {"type": "object", "required": false}
      },
      "preconditions": ["node_id must not exist in graph"],
      "example": {"node_id": "func:helper", "node_kind": "callable", "attrs": {"name": "helper"}}
    }
  ],
  "compositions": [
    {
      "name": "RENAME",
      "description": "Rename an entity and update all references",
      "params": {
        "target": {"type": "string", "required": true},
        "new_name": {"type": "string", "required": true}
      },
      "preconditions": ["target must exist", "new_name must not conflict in scope"]
    }
  ]
}
```

### 2. `query` - Find Nodes

Locate nodes by pattern, kind, or file path.

**Request:**
```json
{
  "path": "src/",
  "pattern": "*Service",
  "kind": "class",
  "file": "models/*.py"
}
```

**Response:**
```json
{
  "status": "ok",
  "count": 3,
  "nodes": [
    {"id": "class:UserService", "kind": "CLASS", "name": "UserService", "file": "models/user.py", "line": 10},
    {"id": "class:OrderService", "kind": "CLASS", "name": "OrderService", "file": "models/order.py", "line": 15},
    {"id": "class:PaymentService", "kind": "CLASS", "name": "PaymentService", "file": "models/payment.py", "line": 8}
  ]
}
```

**Pattern types:**
- Glob: `*Service`, `get_*`, `*Helper*`
- Regex: `re:^test_`, `re:.*Service$`

**Kind aliases:**
- `function` → `callable`
- `class` → `type`
- `variable` → `binding`
- `module` → `container`

### 3. `plan` - Create Transformation

Plan a refactoring operation with automatic verification.

**Request:**
```json
{
  "path": "src/",
  "operator": "RENAME",
  "params": {
    "target": "class:UserService",
    "new_name": "AccountService"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "operator": "RENAME",
  "params": {"target": "class:UserService", "new_name": "AccountService"},
  "plan": {
    "primitives": [
      {"type": "Update", "params": {"node_id": "class:UserService", "prop": "name", "value": "AccountService"}}
    ],
    "affected_files": ["models/user.py", "services/auth.py"],
    "summary": {"primitive_count": 1, "file_count": 2}
  },
  "verification": {
    "valid": true,
    "error_count": 0,
    "violations": []
  }
}
```

### 4. `verify` - Check Invariants

Validate graph state by layer.

**Request:**
```json
{
  "path": "src/",
  "layer": "scope",
  "min_severity": "error"
}
```

**Response:**
```json
{
  "status": "ok",
  "valid": false,
  "violations": [
    {
      "rule": "unique_function_names_in_class",
      "message": "Duplicate function name 'process' in class 'Handler'",
      "node": "func:Handler.process:2",
      "severity": "error",
      "layer": "scope",
      "fix_hint": "Rename one of the functions or remove the duplicate"
    }
  ]
}
```

**Layers (in order):**
| Layer | Purpose |
|-------|---------|
| `schema` | Edge types, multiplicity, required attributes |
| `structure` | Containment acyclicity, orphan detection |
| `scope` | Name uniqueness within scopes |
| `reference` | Symbol resolution and consistency |
| `type_system` | Inheritance DAG, override compatibility |
| `semantic` | Argument/parameter matching |
| `quality` | Unused imports, empty containers |

## Error Handling

All errors follow a structured format with actionable suggestions:

```json
{
  "status": "error",
  "error": {
    "code": "TARGET_NOT_FOUND",
    "message": "Node 'func:unknown' not found",
    "phase": "precondition",
    "details": {
      "node_id": "func:unknown"
    },
    "suggestions": [
      {
        "action": "verify_target",
        "description": "Use the query tool to find the correct target ID",
        "example": "query pattern='*' to list all nodes"
      },
      {
        "action": "similar_targets",
        "description": "Did you mean one of these?",
        "example": "func:unknownHelper, func:unknownUtil"
      }
    ]
  }
}
```

### Error Codes

| Code | Category | Self-Correction Strategy |
|------|----------|--------------------------|
| `MISSING_PATH` | Input | Provide the required path parameter |
| `PATH_NOT_FOUND` | Input | Check file/directory exists |
| `UNKNOWN_OPERATOR` | Input | Use `spec` to get valid operators |
| `PARSE_ERROR` | Parse | Fix syntax errors in source file |
| `TARGET_NOT_FOUND` | Precondition | Use `query` to find correct node ID |
| `NAME_CONFLICT` | Conflict | Choose different name or rename existing |
| `SCOPE_VIOLATION` | Conflict | Change visibility or choose different scope |
| `PRECONDITION_FAILED` | Verification | Address the stated precondition |
| `GLUING_VIOLATION` | DPO | Handle dangling edges before delete |

### Self-Correction Loop

The error response is designed for agents to self-correct:

```python
def refactor_with_retry(path, operator, params, max_attempts=3):
    for attempt in range(max_attempts):
        result = plan(path=path, operator=operator, params=params)

        if result["status"] == "ok":
            if result["verification"]["valid"]:
                return result  # Success
            else:
                # Handle verification violations
                violations = result["verification"]["violations"]
                params = apply_fix_hints(params, violations)
        else:
            # Handle error with suggestions
            error = result["error"]
            suggestions = error.get("suggestions", [])
            params = apply_suggestions(params, suggestions)

    return {"status": "error", "message": "Max attempts exceeded"}
```

## Complete Example

### Rename a Class

```python
# Step 1: Find the class
query_result = query(path="src/", pattern="UserService", kind="class")
# Returns: {"nodes": [{"id": "class:UserService", ...}]}

target_id = query_result["nodes"][0]["id"]

# Step 2: Plan the rename
plan_result = plan(
    path="src/",
    operator="RENAME",
    params={"target": target_id, "new_name": "AccountService"}
)

if plan_result["status"] == "error":
    # Follow suggestions in plan_result["error"]["suggestions"]
    print(f"Error: {plan_result['error']['message']}")
    for s in plan_result["error"]["suggestions"]:
        print(f"  Try: {s['action']} - {s['description']}")
elif not plan_result["verification"]["valid"]:
    # Handle violations
    for v in plan_result["verification"]["violations"]:
        print(f"Violation: {v['message']}")
        print(f"Fix: {v['fix_hint']}")
else:
    # Transformation is valid
    print(f"Plan valid. Affects {plan_result['plan']['summary']['file_count']} files")
```

### Add a Parameter

```python
# Step 1: Find the function
query_result = query(path="src/", pattern="process_data", kind="function")
target_id = query_result["nodes"][0]["id"]

# Step 2: Plan signature change
plan_result = plan(
    path="src/",
    operator="CHANGE_SIGNATURE",
    params={
        "target": target_id,
        "add_params": [{"name": "timeout", "default": "30"}]
    }
)

if plan_result["status"] == "ok" and plan_result["verification"]["valid"]:
    print(f"Will update {len(plan_result['plan']['primitives'])} locations")
```

### Move a Function

```python
# Step 1: Find source and destination
func = query(path="src/", pattern="helper_func", kind="function")["nodes"][0]
module = query(path="src/", pattern="utils", kind="module")["nodes"][0]

# Step 2: Plan the move
plan_result = plan(
    path="src/",
    operator="MOVE",
    params={
        "target": func["id"],
        "destination": module["id"]
    }
)
```

## Available Operators

### Primitives

| Primitive | Purpose | Key Parameters |
|-----------|---------|----------------|
| `insert_node` | Add a node | `node_id`, `node_kind`, `attrs` |
| `insert_edge` | Add an edge | `source`, `target`, `edge_kind` |
| `delete_node` | Remove a node | `node_id`, `cascade` |
| `delete_edge` | Remove an edge | `source`, `target`, `edge_kind` |
| `update` | Modify property | `node_id`, `prop`, `value` |

### Compositions

| Composition | Purpose | Key Parameters |
|-------------|---------|----------------|
| `RENAME` | Rename entity and references | `target`, `new_name` |
| `MOVE` | Move to different scope | `target`, `destination` |
| `EXTRACT` | Extract code to new entity | `source_range`, `name`, `entity_type` |
| `INLINE` | Inline into call sites | `target` |
| `ADD_GUARD` | Add guard check | `target`, `guard_type`, `condition` |
| `CHANGE_SIGNATURE` | Modify callable signature | `target`, `add_params`, `remove_params` |
| `WRAP` | Wrap in construct | `target`, `wrapper_type` |

## Best Practices

1. **Always query first**: Use `query` to find correct node IDs before planning
2. **Check verification**: Always check `verification.valid` in plan responses
3. **Follow suggestions**: Error responses include actionable suggestions
4. **Use fix hints**: Violation objects include `fix_hint` for resolution
5. **Retry with corrections**: The system is designed for iterative correction
6. **Filter by layer**: Use `layer` parameter in verify for focused checks
7. **Check affected files**: Review `plan.affected_files` before applying

## Troubleshooting

### Common Issues

**"Node not found"**
- Use `query(path="src/", pattern="*")` to list all nodes
- Check the exact node ID format (e.g., `class:Name`, `func:Name`)

**"Name conflict"**
- Query the scope for existing names
- Choose a unique name or rename the existing entity first

**"Parse error"**
- The source file has syntax errors
- Fix the Python syntax before running transformations

**"Gluing violation"**
- DPO mode prevents dangling edges
- Delete or redirect edges before deleting nodes
