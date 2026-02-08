"""
apply -- Apply a primitive or composition to a graph.
"""

from __future__ import annotations

import json
import sys

import click

from graph_transform.cli.formatting import (
    err_console,
    format_composition_result_json,
    format_primitive_result_json,
    print_composition_result,
    print_error,
    print_graph_summary,
    print_primitive_result,
    print_success,
)
from graph_transform.cli.primitive_metadata import (
    resolve_composition,
    resolve_primitive,
)
from graph_transform.core.primitives import (
    CompositionRegistry,
    primitive_from_dict,
)
from graph_transform.io.serialization import load_graph, save_graph


@click.command("apply")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--primitive", "-prim",
    default=None,
    help="Primitive to apply: insert_node, insert_edge, delete_node, delete_edge, update.",
)
@click.option(
    "--composition", "-comp",
    default=None,
    help="Composition to apply: RENAME, MOVE, EXTRACT, INLINE, ADD_GUARD, CHANGE_SIGNATURE, WRAP.",
)
@click.option(
    "--params", "-p",
    required=True,
    help="JSON string of parameters.",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file for result graph (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "as_json", is_flag=True, help="Output full result as JSON.")
def apply_operator(
    graph_file: str,
    primitive: str | None,
    composition: str | None,
    params: str,
    output: str | None,
    verbose: bool,
    as_json: bool,
) -> None:
    """Apply a primitive or composition to a graph.

    Examples:

        # Apply a primitive
        graph-transform apply graph.json --primitive insert_node \\
            -p '{"node_id": "func:new", "node_kind": "callable", "attrs": {"name": "new"}}'

        # Apply a composition
        graph-transform apply graph.json --composition RENAME \\
            -p '{"target": "func:old", "new_name": "new_name"}'
    """
    # Validate that exactly one of --primitive or --composition is specified
    if primitive and composition:
        print_error("Specify either --primitive or --composition, not both.")
        sys.exit(2)

    if not primitive and not composition:
        print_error("Must specify either --primitive or --composition.")
        sys.exit(2)

    # Parse parameters
    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError as e:
        print_error(f"Invalid --params JSON: {e}")
        sys.exit(2)

    # Load graph
    try:
        graph = load_graph(graph_file)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    if primitive:
        _apply_primitive(
            graph, primitive, params_dict, output, verbose, as_json
        )
    else:
        _apply_composition(
            graph, composition, params_dict, output, verbose, as_json
        )


def _apply_primitive(
    graph,
    primitive_name: str,
    params: dict,
    output: str | None,
    verbose: bool,
    as_json: bool,
) -> None:
    """Execute a primitive operation."""
    try:
        prim_type = resolve_primitive(primitive_name)
    except ValueError as e:
        print_error(str(e))
        sys.exit(2)

    # Build primitive dict for deserialization
    prim_dict = {"primitive": prim_type, **params}

    try:
        prim = primitive_from_dict(prim_dict)
    except (KeyError, ValueError) as e:
        print_error(f"Invalid primitive parameters: {e}")
        sys.exit(2)

    # Execute
    result = prim.execute(graph)

    # Output
    if as_json:
        sys.stdout.write(
            json.dumps(format_primitive_result_json(result), indent=2) + "\n"
        )
        sys.exit(0 if result.success else 1)

    print_primitive_result(result, verbose=verbose)

    if result.success:
        if verbose:
            print_graph_summary(graph, title="Result Graph")
        save_graph(graph, output)
        if output:
            print_success(f"Result graph written to {output}")
    else:
        sys.exit(1)


def _apply_composition(
    graph,
    composition_name: str,
    params: dict,
    output: str | None,
    verbose: bool,
    as_json: bool,
) -> None:
    """Execute a composition operation."""
    try:
        comp_type = resolve_composition(composition_name)
    except ValueError as e:
        print_error(str(e))
        sys.exit(2)

    # Create composition instance
    comp = CompositionRegistry.create(comp_type, **params)
    if comp is None:
        print_error(f"Failed to create composition '{comp_type}'.")
        sys.exit(2)

    # Execute
    result = comp.execute(graph)

    # Output
    if as_json:
        sys.stdout.write(
            json.dumps(format_composition_result_json(result), indent=2) + "\n"
        )
        sys.exit(0 if result.success else 1)

    print_composition_result(result, verbose=verbose)

    if result.success:
        if verbose:
            print_graph_summary(graph, title="Result Graph")
        save_graph(graph, output)
        if output:
            print_success(f"Result graph written to {output}")
    else:
        sys.exit(1)
