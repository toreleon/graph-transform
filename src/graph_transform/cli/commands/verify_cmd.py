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
from graph_transform.engine import verify_graph_invariants
from graph_transform.serialization import load_graph


@click.command("verify")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors (exit 1).",
)
@click.option("--json", "as_json", is_flag=True, help="Output violations as JSON.")
def verify_graph(graph_file: str, strict: bool, as_json: bool) -> None:
    """Run all invariant checks on a graph."""
    try:
        graph = load_graph(graph_file)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    violations = verify_graph_invariants(graph)

    if as_json:
        data = [v.to_dict() for v in violations]
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    else:
        if violations:
            print_violations(violations)
        else:
            print_success("All invariants satisfied.")

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    if errors:
        print_error(f"{len(errors)} error(s) found.")
        sys.exit(1)
    elif warnings and strict:
        print_warning(f"{len(warnings)} warning(s) found (--strict mode).")
        sys.exit(1)
    else:
        if warnings and not as_json:
            print_warning(f"{len(warnings)} warning(s).")
