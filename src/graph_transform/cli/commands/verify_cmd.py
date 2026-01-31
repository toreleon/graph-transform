"""
verify -- Run invariant checks on a graph.
"""

from __future__ import annotations

import json
import sys

import click

from graph_transform.cli.formatting import (
    print_error,
    print_success,
    print_violations,
    print_warning,
)
from graph_transform.engine.core import verify_graph_invariants
from graph_transform.io.serialization import load_graph
from graph_transform.rewriting.invariants import InvariantLayer, InvariantSeverity

_LAYER_CHOICES = [layer.name.lower() for layer in InvariantLayer]


@click.command("verify")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors (exit 1).",
)
@click.option("--json", "as_json", is_flag=True, help="Output violations as JSON.")
@click.option(
    "--layer",
    "layer_names",
    multiple=True,
    type=click.Choice(_LAYER_CHOICES, case_sensitive=False),
    help="Only check specific layers (can be repeated).",
)
def verify_graph(
    graph_file: str, strict: bool, as_json: bool, layer_names: tuple[str, ...]
) -> None:
    """Run all invariant checks on a graph."""
    try:
        graph = load_graph(graph_file)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    layers: set[InvariantLayer] | None = None
    if layer_names:
        layers = {InvariantLayer[name.upper()] for name in layer_names}

    violations = verify_graph_invariants(graph, layers=layers)

    if as_json:
        data = [v.to_dict() for v in violations]
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    else:
        if violations:
            print_violations(violations)
        else:
            print_success("All invariants satisfied.")

    errors = [v for v in violations if v.severity == InvariantSeverity.ERROR]
    warnings = [v for v in violations if v.severity == InvariantSeverity.WARNING]

    if errors:
        print_error(f"{len(errors)} error(s) found.")
        sys.exit(1)
    elif warnings and strict:
        print_warning(f"{len(warnings)} warning(s) found (--strict mode).")
        sys.exit(1)
    else:
        if warnings and not as_json:
            print_warning(f"{len(warnings)} warning(s).")
