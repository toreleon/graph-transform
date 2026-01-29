"""
list -- List all available refactoring operators.
"""

from __future__ import annotations

import json
import sys

import click

from graph_transform.cli.formatting import console, print_operator_table
from graph_transform.cli.operator_metadata import (
    CATEGORIES,
    OPERATOR_DESCRIPTIONS,
    OPERATOR_EXAMPLES,
    OPERATOR_PARAMS,
    get_all_operators,
)


@click.command("list")
@click.option(
    "--category", "-c",
    type=click.Choice(
        ["method", "field", "class", "param", "module", "reference", "call_site", "all"],
        case_sensitive=False,
    ),
    default="all",
    help="Filter operators by category.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--verbose", "-v", is_flag=True, help="Show parameter schemas and examples.")
def list_operators(category: str, as_json: bool, verbose: bool) -> None:
    """List all available refactoring operators."""
    if category == "all":
        operators = get_all_operators()
    else:
        operators = CATEGORIES.get(category, [])

    if as_json:
        data = []
        for op in operators:
            entry: dict = {
                "name": op.value,
                "category": _cat(op),
                "description": OPERATOR_DESCRIPTIONS.get(op, ""),
            }
            if verbose:
                entry["params"] = OPERATOR_PARAMS.get(op, {})
                if op in OPERATOR_EXAMPLES:
                    entry["example"] = OPERATOR_EXAMPLES[op]
            data.append(entry)
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
        return

    print_operator_table(operators, OPERATOR_DESCRIPTIONS, category)

    if verbose:
        console.print()
        for op in operators:
            params = OPERATOR_PARAMS.get(op, {})
            if params:
                console.print(f"[bold cyan]{op.value}[/bold cyan] parameters:")
                for pname, pdesc in params.items():
                    console.print(f"  {pname}: {pdesc}")
                example = OPERATOR_EXAMPLES.get(op)
                if example:
                    console.print(f"  [dim]Example: --params '{example}'[/dim]")
                console.print()


def _cat(op):
    for cat, ops in CATEGORIES.items():
        if op in ops:
            return cat
    return "other"
