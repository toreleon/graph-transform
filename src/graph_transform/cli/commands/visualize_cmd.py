"""
visualize -- Render a graph as SVG/PNG/PDF.
"""

from __future__ import annotations

import sys

import click

from graph_transform.cli.formatting import print_error, print_success
from graph_transform.io.serialization import load_graph


@click.command("visualize")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    required=True,
    type=click.Path(),
    help="Output file path (without extension, e.g. output/graph).",
)
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["svg", "png", "pdf"]),
    default="svg",
    help="Output format (default: svg).",
)
@click.option("--title", "-t", default="", help="Title displayed on the graph.")
def visualize(graph_file: str, output: str, fmt: str, title: str) -> None:
    """Render a graph as SVG, PNG, or PDF."""
    try:
        graph = load_graph(graph_file)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    try:
        from graph_transform.io.visualization import render_graph
    except ImportError as e:
        print_error(str(e))
        sys.exit(1)

    try:
        path = render_graph(graph, title=title, output_path=output, fmt=fmt)
        print_success(f"Graph rendered to {path}")
    except Exception as e:
        print_error(f"Visualization failed: {e}")
        sys.exit(1)
