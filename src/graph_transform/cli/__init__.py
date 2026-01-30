"""
graph-transform CLI

Algebraic graph rewriting engine for code refactoring.
"""

from __future__ import annotations

import click

from .commands.apply_cmd import apply_operator
from .commands.batch_cmd import batch_operators
from .commands.build_cmd import build
from .commands.codegen_cmd import codegen
from .commands.dry_run_cmd import dry_run
from .commands.list_cmd import list_operators
from .commands.verify_cmd import verify_graph
from .commands.visualize_cmd import visualize


@click.group()
@click.version_option(version="0.1.0", prog_name="graph-transform")
def cli() -> None:
    """Algebraic graph rewriting engine for code refactoring.

    Build, transform, verify, and visualize code graphs using
    41 primitive refactoring operators with DPO/SPO semantics.

    \b
    Quick start:
      graph-transform list                  # see all operators
      graph-transform build src/ -o g.json  # build graph from source
      graph-transform verify g.json         # check invariants
      graph-transform apply g.json -op add_method -p '{"class_name":"Foo","method_name":"bar"}'
      graph-transform batch g.json -op add_param -p '...' -op add_arg -p '...'
      graph-transform codegen g.json g2.json -o plan.json  # generate edit plan
      graph-transform visualize g.json -o out
    """


cli.add_command(list_operators, name="list")
cli.add_command(apply_operator, name="apply")
cli.add_command(batch_operators, name="batch")
cli.add_command(codegen, name="codegen")
cli.add_command(verify_graph, name="verify")
cli.add_command(dry_run, name="dry-run")
cli.add_command(visualize, name="visualize")
cli.add_command(build, name="build")


def main() -> None:
    """Entry point for the graph-transform CLI."""
    cli()
