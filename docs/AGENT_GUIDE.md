# Agent Integration Guide

This guide explains how to integrate `graph-transform` into a coding agent for verified refactoring.

## Workflow Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    grep     │ ──► │    build    │ ──► │    batch    │ ──► │   codegen   │
│ find files  │     │  subgraph   │     │   refactor  │     │  edit plan  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

## Step 1: Discover Relevant Files

Use grep to find files containing the target symbol:

```bash
grep -rl "target_function" src/ > files.txt
```

## Step 2: Build Subgraph

Build a graph from only the relevant files:

```bash
# From grep pipe
grep -rl "target_function" src/ | graph-transform build --stdin -o subgraph.json

# Or explicit files
graph-transform build --files a.py --files b.py -o subgraph.json
```

## Step 3: Create Refactor Plan (YAML)

Generate a YAML file describing the transformation:

```yaml
description: "Add logging parameter to target_function"
steps:
  - op: add_param
    params:
      function_name: target_function
      param_name: logging
      default_value: "True"
      
  - op: add_arg
    params:
      callee: target_function
      arg_name: logging
      arg_value: "True"
    repeat: all  # Apply to all call sites
```

## Step 4: Apply with Verification

Apply the transformation with invariant checking:

```bash
graph-transform batch subgraph.json -f refactor.yaml -o result.json -v
```

If invariants fail, the transformation is rejected. Fix the plan and retry.

## Step 5: Generate Edit Plan

Convert the graph diff to structured code edits:

```bash
graph-transform codegen subgraph.json result.json -o plan.json
```

**Output format:**
```json
{
  "edits": [
    {
      "type": "add_parameter",
      "file": "helpers.py",
      "line": 28,
      "function": "target_function",
      "parameter": {"name": "logging", "default": "True"}
    },
    {
      "type": "add_argument",
      "file": "manager.py",
      "line": 240,
      "call": "target_function",
      "argument": {"name": "logging", "value": "True"}
    }
  ]
}
```

## Step 6: Apply Code Edits

Your agent reads `plan.json` and applies edits using AST tools (e.g., libcst, rope).

---

## Available Operators

| Category | Operators |
|----------|-----------|
| **Method** | `add_method`, `remove_method`, `rename_method`, `move_method`, `extract_method`, `inline_method` |
| **Field** | `add_field`, `remove_field`, `rename_field`, `move_field`, `encapsulate_field` |
| **Class** | `add_class`, `remove_class`, `rename_class`, `move_class`, `extract_class` |
| **Param** | `add_param`, `remove_param`, `rename_param` |
| **Call** | `add_arg`, `remove_arg`, `update_arg` |

Run `graph-transform list` for the full list.

---

## Edit Types in `plan.json`

| Type | Description |
|------|-------------|
| `add_parameter` | Add parameter to function definition |
| `add_argument` | Add argument to call site |
| `add_method` | Add new method to class |
| `add_field` | Add new field to class |
| `rename` | Rename any symbol |
| `remove_*` | Remove corresponding element |

---

## Error Handling

Invariant failures indicate semantic issues:

| Invariant | Meaning |
|-----------|---------|
| `call_argument_count_match` | Call sites don't match function signature |
| `symbol_resolution` | Dangling references to undefined symbols |
| `no_global_name_clashes` | Duplicate names in same scope |

Fix your refactor plan to resolve violations before proceeding.
