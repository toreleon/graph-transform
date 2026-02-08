"""
spec -- Output detailed specification of operators and commands.

Designed for LLM agents to query exact parameter names and usage.
"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import Any, get_type_hints

import click

from graph_transform.core.primitives import CompositionRegistry
from graph_transform.core.primitives.base import (
    DeleteEdge,
    DeleteNode,
    InsertEdge,
    InsertNode,
    Update,
)
from graph_transform.core.primitives.compositions import (
    AddGuard,
    ChangeSignature,
    Extract,
    Inline,
    Move,
    Rename,
    UpdateImport,
    Wrap,
)


PRIMITIVES = {
    "insert_node": InsertNode,
    "delete_node": DeleteNode,
    "insert_edge": InsertEdge,
    "delete_edge": DeleteEdge,
    "update": Update,
}

COMPOSITIONS = {
    "RENAME": Rename,
    "MOVE": Move,
    "EXTRACT": Extract,
    "INLINE": Inline,
    "ADD_GUARD": AddGuard,
    "CHANGE_SIGNATURE": ChangeSignature,
    "WRAP": Wrap,
    "UPDATE_IMPORT": UpdateImport,
}


def _get_field_info(cls: type) -> list[dict[str, Any]]:
    """Extract field info from a dataclass."""
    result = []
    hints = get_type_hints(cls) if hasattr(cls, "__annotations__") else {}

    for f in fields(cls):
        field_info: dict[str, Any] = {
            "name": f.name,
            "type": str(hints.get(f.name, "Any")),
            "required": f.default is f.default_factory if hasattr(f, "default_factory") else f.default is f.default,
        }

        # Check for default
        if f.default is not f.default_factory:
            if f.default is not None and not callable(f.default):
                field_info["default"] = str(f.default)
                field_info["required"] = False

        result.append(field_info)

    return result


def _format_params_compact(cls: type) -> str:
    """Format params in a compact inline format."""
    params = []
    for f in fields(cls):
        required = f.default is f.default_factory if hasattr(f, "default_factory") else True
        if f.default is not f.default_factory and f.default is not None:
            required = False

        if required:
            params.append(f.name)
        else:
            params.append(f"[{f.name}]")

    return ", ".join(params)


@click.command("spec")
@click.argument("operator", required=False)
@click.option("--compact", is_flag=True, help="Compact output for quick reference")
@click.option("--json", "json_output", is_flag=True, help="JSON output format")
def spec(operator: str | None, compact: bool, json_output: bool) -> None:
    """Output specification of operators and their parameters.

    Query the exact parameter names and types for primitives and compositions.
    Designed for LLM agents to avoid guessing CLI syntax.

    Examples:

        graph-transform spec --compact     # Quick overview of all operators
        graph-transform spec MOVE          # Full details for MOVE composition
        graph-transform spec insert_node   # Full details for insert_node primitive
    """
    if operator:
        # Show detailed spec for one operator
        operator_upper = operator.upper()
        operator_lower = operator.lower()

        if operator_lower in PRIMITIVES:
            cls = PRIMITIVES[operator_lower]
            _print_operator_spec(operator_lower, cls, "primitive", json_output)
        elif operator_upper in COMPOSITIONS:
            cls = COMPOSITIONS[operator_upper]
            _print_operator_spec(operator_upper, cls, "composition", json_output)
        else:
            click.echo(f"Unknown operator: {operator}", err=True)
            click.echo(f"Available primitives: {', '.join(PRIMITIVES.keys())}", err=True)
            click.echo(f"Available compositions: {', '.join(COMPOSITIONS.keys())}", err=True)
            raise SystemExit(2)
    else:
        # Show all operators
        if json_output or not compact:
            _print_full_spec(json_output)
        else:
            _print_compact_spec()


def _print_operator_spec(name: str, cls: type, op_type: str, json_output: bool) -> None:
    """Print detailed spec for a single operator."""
    info = {
        "name": name,
        "type": op_type,
        "parameters": _get_field_info(cls),
        "docstring": cls.__doc__ or "",
    }

    if json_output:
        click.echo(json.dumps(info, indent=2))
    else:
        click.echo(f"=== {name} ({op_type}) ===\n")
        if cls.__doc__:
            click.echo(cls.__doc__.strip())
            click.echo()

        click.echo("Parameters:")
        for p in info["parameters"]:
            req = "REQUIRED" if p.get("required", True) else f"optional, default={p.get('default', 'None')}"
            click.echo(f"  {p['name']}: {p['type']} ({req})")

        click.echo(f"\nYAML recipe example:")
        click.echo(f"  - composition: {name}" if op_type == "composition" else f"  - primitive: {name}")
        click.echo("    params:")
        for p in info["parameters"]:
            if p.get("required", True):
                click.echo(f"      {p['name']}: <value>")


def _print_compact_spec() -> None:
    """Print compact overview of all operators."""
    click.echo("=== PRIMITIVES ===")
    for name, cls in PRIMITIVES.items():
        params = _format_params_compact(cls)
        click.echo(f"  {name}({params})")

    click.echo("\n=== COMPOSITIONS ===")
    for name, cls in COMPOSITIONS.items():
        params = _format_params_compact(cls)
        click.echo(f"  {name}({params})")

    click.echo("\n=== YAML RECIPE FORMAT (recipe.yaml) ===")
    click.echo("""
description: "Refactoring description"
steps:
  - composition: MOVE
    params:
      target: "func:my_func"
      from_scope: "module:old"
      to_scope: "module:new"

  - composition: UPDATE_IMPORT
    params:
      symbol: "my_func"
      old_module: "old_module"
      new_module: "new_module"

  - composition: RENAME
    params:
      target: "func:old_name"
      new_name: "new_name"

Usage: graph-transform plan src/ -F recipe.yaml -o plan.json

=== DISCOVERING NODE IDs ===

IMPORTANT: Node IDs include the full file path. Use `query` to discover them:

  graph-transform query path/to/file.py --modules    # list module IDs
  graph-transform query path/to/file.py --functions  # list function IDs
  graph-transform query path/to/file.py --find name  # search for nodes

Example output:
  module:workspace.myproject.src.utils  (NOT module:utils)
  func:my_function                       (from file attrs)

Always query before using MOVE/RENAME to get correct IDs!
""")


def _print_full_spec(json_output: bool) -> None:
    """Print full spec for all operators."""
    data = {
        "primitives": {},
        "compositions": {},
        "recipe_format": {
            "description": "YAML with description + steps list. Each step has composition/primitive + params dict",
            "example": {
                "description": "Refactoring task",
                "steps": [
                    {
                        "composition": "MOVE",
                        "params": {
                            "target": "func:symbol_name",
                            "from_scope": "module:source",
                            "to_scope": "module:dest",
                        },
                    },
                    {
                        "composition": "UPDATE_IMPORT",
                        "params": {
                            "symbol": "symbol_name",
                            "old_module": "source",
                            "new_module": "dest",
                        },
                    },
                ],
            },
        },
    }

    for name, cls in PRIMITIVES.items():
        data["primitives"][name] = {
            "parameters": _get_field_info(cls),
            "docstring": (cls.__doc__ or "").strip(),
        }

    for name, cls in COMPOSITIONS.items():
        data["compositions"][name] = {
            "parameters": _get_field_info(cls),
            "docstring": (cls.__doc__ or "").strip(),
        }

    if json_output:
        click.echo(json.dumps(data, indent=2))
    else:
        # Pretty print
        click.echo("=== PRIMITIVES ===\n")
        for name, info in data["primitives"].items():
            click.echo(f"{name}:")
            for p in info["parameters"]:
                req = "required" if p.get("required", True) else "optional"
                click.echo(f"  - {p['name']}: {p['type']} ({req})")
            click.echo()

        click.echo("=== COMPOSITIONS ===\n")
        for name, info in data["compositions"].items():
            click.echo(f"{name}:")
            for p in info["parameters"]:
                req = "required" if p.get("required", True) else "optional"
                click.echo(f"  - {p['name']}: {p['type']} ({req})")
            click.echo()
