"""
build -- Build a TypedGraph from Python source code.
"""

from __future__ import annotations

import sys

import click

from graph_transform.builder import build_graph_from_source
from graph_transform.cli.formatting import print_error, print_graph_summary, print_success
from graph_transform.serialization import save_graph


@click.command("build")
@click.argument("source_path", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output JSON file (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show graph summary after building.")
def build(source_path: str, output: str | None, verbose: bool) -> None:
    """Build a TypedGraph from Python source code."""
    try:
        graph = build_graph_from_source(source_path)
    except (FileNotFoundError, SyntaxError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    if verbose:
        print_graph_summary(graph, title=f"Built from {source_path}")

    save_graph(graph, output)

    if output:
        print_success(f"Graph written to {output}")
