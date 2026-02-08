"""
dry-run -- Check if a primitive/composition is applicable without modifying the graph.
"""

from __future__ import annotations

import copy
import json
import sys

import click

from graph_transform.cli.formatting import (
    err_console,
    format_composition_result_json,
    format_primitive_result_json,
    print_error,
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
from graph_transform.io.serialization import load_graph


@click.command("dry-run")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--primitive", "-prim",
    default=None,
    help="Primitive to test: insert_node, insert_edge, delete_node, delete_edge, update.",
)
@click.option(
    "--composition", "-comp",
    default=None,
    help="Composition to test: RENAME, MOVE, EXTRACT, INLINE, ADD_GUARD, CHANGE_SIGNATURE, WRAP.",
)
@click.option(
    "--params", "-p",
    required=True,
    help="JSON string of parameters.",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON.")
def dry_run(
    graph_file: str,
    primitive: str | None,
    composition: str | None,
    params: str,
    verbose: bool,
    as_json: bool,
) -> None:
    """Check if a primitive/composition is applicable without modifying the graph.

    Examples:

        graph-transform dry-run graph.json --primitive insert_node \\
            -p '{"node_id": "func:new", "node_kind": "callable", "attrs": {"name": "new"}}'

        graph-transform dry-run graph.json --composition RENAME \\
            -p '{"target": "func:old", "new_name": "new_name"}'
    """
    # Validate that exactly one is specified
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

    # Make a copy for dry-run
    graph_copy = copy.deepcopy(graph)

    if primitive:
        _dry_run_primitive(graph_copy, primitive, params_dict, verbose, as_json)
    else:
        _dry_run_composition(graph_copy, composition, params_dict, verbose, as_json)


def _dry_run_primitive(
    graph,
    primitive_name: str,
    params: dict,
    verbose: bool,
    as_json: bool,
) -> None:
    """Dry-run a primitive operation."""
    try:
        prim_type = resolve_primitive(primitive_name)
    except ValueError as e:
        print_error(str(e))
        sys.exit(2)

    prim_dict = {"primitive": prim_type, **params}

    try:
        prim = primitive_from_dict(prim_dict)
    except (KeyError, ValueError) as e:
        print_error(f"Invalid primitive parameters: {e}")
        sys.exit(2)

    result = prim.execute(graph)

    if as_json:
        sys.stdout.write(
            json.dumps(format_primitive_result_json(result), indent=2) + "\n"
        )
        sys.exit(0 if result.success else 1)

    if result.success:
        print_success(f"Primitive '{primitive_name}' is applicable.")
        if verbose:
            err_console.print(f"  Affected IDs: {', '.join(result.affected_ids)}")
            err_console.print(
                f"  Result would have: "
                f"{graph.node_count} nodes, "
                f"{graph.edge_count} edges"
            )
    else:
        print_error(f"Primitive '{primitive_name}' is NOT applicable.")
        if result.error:
            err_console.print(f"  [red]{result.error}[/red]")
        sys.exit(1)


def _dry_run_composition(
    graph,
    composition_name: str,
    params: dict,
    verbose: bool,
    as_json: bool,
) -> None:
    """Dry-run a composition operation."""
    try:
        comp_type = resolve_composition(composition_name)
    except ValueError as e:
        print_error(str(e))
        sys.exit(2)

    comp = CompositionRegistry.create(comp_type, **params)
    if comp is None:
        print_error(f"Failed to create composition '{comp_type}'.")
        sys.exit(2)

    result = comp.execute(graph)

    if as_json:
        sys.stdout.write(
            json.dumps(format_composition_result_json(result), indent=2) + "\n"
        )
        sys.exit(0 if result.success else 1)

    if result.success:
        print_success(f"Composition '{composition_name}' is applicable.")
        if verbose:
            err_console.print(f"  Primitives executed: {len(result.primitive_results)}")
            if result.affected_ids:
                err_console.print(f"  Affected IDs: {', '.join(result.affected_ids)}")
            err_console.print(
                f"  Result would have: "
                f"{graph.node_count} nodes, "
                f"{graph.edge_count} edges"
            )
    else:
        print_error(f"Composition '{composition_name}' is NOT applicable.")
        if result.error:
            err_console.print(f"  [red]{result.error}[/red]")
        sys.exit(1)
