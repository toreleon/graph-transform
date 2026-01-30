"""
apply -- Apply a refactoring operator to a graph.
"""

from __future__ import annotations

import json
import sys

import click

from graph_transform.cli.formatting import (
    err_console,
    print_error,
    print_graph_summary,
    print_rewrite_result,
    print_success,
)
from graph_transform.cli.operator_metadata import resolve_operator
from graph_transform.engine.core import create_engine
from graph_transform.io.serialization import format_result_json, load_graph, save_graph


@click.command("apply")
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
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file for result graph (default: stdout).",
)
@click.option(
    "--no-invariants",
    is_flag=True,
    help="Skip invariant checking.",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
@click.option("--json", "as_json", is_flag=True, help="Output full result as JSON.")
def apply_operator(
    graph_file: str,
    operator: str,
    params: str,
    mode: str,
    output: str | None,
    no_invariants: bool,
    verbose: bool,
    as_json: bool,
) -> None:
    """Apply a refactoring operator to a graph."""
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

    engine = create_engine(mode=mode, check_invariants=not no_invariants)
    rule = engine.catalog.create_rule(op_type, params_dict)
    result = engine.apply_rule(rule, graph)

    if as_json:
        sys.stdout.write(json.dumps(format_result_json(result), indent=2) + "\n")
        sys.exit(0 if result.success else 1)

    print_rewrite_result(result, verbose=verbose)

    if result.success and result.result_graph:
        if verbose:
            print_graph_summary(result.result_graph, title="Result Graph")
        save_graph(result.result_graph, output)
        if output:
            print_success(f"Result graph written to {output}")
    else:
        sys.exit(1)
