"""
dry-run -- Check if an operator is applicable without modifying the graph.
"""

from __future__ import annotations

import json
import sys

import click

from graph_transform.cli.formatting import (
    err_console,
    print_error,
    print_rewrite_result,
    print_success,
)
from graph_transform.cli.operator_metadata import resolve_operator
from graph_transform.engine.core import create_engine
from graph_transform.io.serialization import format_result_json, load_graph


@click.command("dry-run")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--operator", "-op",
    required=True,
    help="Operator name (e.g. add_method, rename_class).",
)
@click.option(
    "--params", "-p",
    required=True,
    help="JSON string of operator parameters.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["dpo", "spo"]),
    default="dpo",
    help="Rewriting mode (default: dpo).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON.")
def dry_run(
    graph_file: str,
    operator: str,
    params: str,
    mode: str,
    verbose: bool,
    as_json: bool,
) -> None:
    """Check if an operator is applicable without modifying the graph."""
    try:
        op_type = resolve_operator(operator)
    except ValueError as e:
        print_error(str(e))
        sys.exit(2)

    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError as e:
        print_error(f"Invalid --params JSON: {e}")
        sys.exit(2)

    try:
        graph = load_graph(graph_file)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    engine = create_engine(mode=mode, check_invariants=True)
    rule = engine.catalog.create_rule(op_type, params_dict)
    result = engine.dry_run(rule, graph)

    if as_json:
        sys.stdout.write(json.dumps(format_result_json(result), indent=2) + "\n")
        sys.exit(0 if result.success else 1)

    if result.success:
        print_success(f"Operator '{operator}' is applicable.")
        if verbose:
            err_console.print(f"  Rule: {result.rule_name}")
            if result.result_graph:
                err_console.print(
                    f"  Result would have: "
                    f"{result.result_graph.node_count} nodes, "
                    f"{result.result_graph.edge_count} edges"
                )
    else:
        print_error(f"Operator '{operator}' is NOT applicable.")
        for err in result.errors:
            err_console.print(f"  [red]{err}[/red]")
        sys.exit(1)
