"""
list -- List available primitives and compositions.
"""

from __future__ import annotations

import json
import sys

import click

from graph_transform.cli.formatting import (
    console,
    print_compositions_table,
    print_composition_params,
    print_primitives_table,
    print_primitive_params,
)
from graph_transform.cli.primitive_metadata import (
    COMPOSITION_DESCRIPTIONS,
    COMPOSITION_EXAMPLES,
    COMPOSITION_PARAMS,
    COMPOSITION_TYPES,
    PRIMITIVE_DESCRIPTIONS,
    PRIMITIVE_EXAMPLES,
    PRIMITIVE_PARAMS,
    PRIMITIVE_TYPES,
)


@click.command("list")
@click.option(
    "--primitives", "-prim",
    is_flag=True,
    help="List primitives (insert_node, delete_node, etc.).",
)
@click.option(
    "--compositions", "-comp",
    is_flag=True,
    help="List compositions (RENAME, MOVE, EXTRACT, etc.).",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--verbose", "-v", is_flag=True, help="Show parameter schemas and examples.")
def list_operators(
    primitives: bool,
    compositions: bool,
    as_json: bool,
    verbose: bool,
) -> None:
    """List available primitives and compositions.

    By default, lists both primitives and compositions.

    Examples:

        graph-transform list                    # List all
        graph-transform list --primitives       # List primitives only
        graph-transform list --compositions     # List compositions only
        graph-transform list -v                 # Include parameter details
    """
    # Default: list both if neither specified
    if not primitives and not compositions:
        primitives = True
        compositions = True

    if as_json:
        _output_json(primitives, compositions, verbose)
        return

    if primitives:
        _print_primitives(verbose)

    if compositions:
        if primitives:
            console.print()  # Separator
        _print_compositions(verbose)


def _print_primitives(verbose: bool) -> None:
    """Print primitives table and optionally parameters."""
    print_primitives_table(PRIMITIVE_TYPES, PRIMITIVE_DESCRIPTIONS)

    if verbose:
        console.print()
        for prim in PRIMITIVE_TYPES:
            params = PRIMITIVE_PARAMS.get(prim, {})
            if params:
                print_primitive_params(prim, params)
                example = PRIMITIVE_EXAMPLES.get(prim)
                if example:
                    console.print(f"  [dim]Example: -p '{json.dumps(example)}'[/dim]")
                console.print()


def _print_compositions(verbose: bool) -> None:
    """Print compositions table and optionally parameters."""
    print_compositions_table(COMPOSITION_TYPES, COMPOSITION_DESCRIPTIONS)

    if verbose:
        console.print()
        for comp in COMPOSITION_TYPES:
            params = COMPOSITION_PARAMS.get(comp, {})
            if params:
                print_composition_params(comp, params)
                example = COMPOSITION_EXAMPLES.get(comp)
                if example:
                    console.print(f"  [dim]Example: -p '{json.dumps(example)}'[/dim]")
                console.print()


def _output_json(primitives: bool, compositions: bool, verbose: bool) -> None:
    """Output as JSON."""
    data: dict = {}

    if primitives:
        prim_list = []
        for prim in PRIMITIVE_TYPES:
            entry: dict = {
                "name": prim,
                "description": PRIMITIVE_DESCRIPTIONS.get(prim, ""),
            }
            if verbose:
                entry["params"] = PRIMITIVE_PARAMS.get(prim, {})
                if prim in PRIMITIVE_EXAMPLES:
                    entry["example"] = PRIMITIVE_EXAMPLES[prim]
            prim_list.append(entry)
        data["primitives"] = prim_list

    if compositions:
        comp_list = []
        for comp in COMPOSITION_TYPES:
            entry = {
                "name": comp,
                "description": COMPOSITION_DESCRIPTIONS.get(comp, ""),
            }
            if verbose:
                entry["params"] = COMPOSITION_PARAMS.get(comp, {})
                if comp in COMPOSITION_EXAMPLES:
                    entry["example"] = COMPOSITION_EXAMPLES[comp]
            comp_list.append(entry)
        data["compositions"] = comp_list

    sys.stdout.write(json.dumps(data, indent=2) + "\n")
