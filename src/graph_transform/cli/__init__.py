"""
graph-transform CLI

Algebraic graph rewriting engine for code refactoring.
Uses the three-primitive system (INSERT, DELETE, UPDATE)
with compositions (RENAME, MOVE, EXTRACT, INLINE, etc.).
"""

from __future__ import annotations

import click

from .commands.apply_cmd import apply_operator
from .commands.batch_cmd import batch_operators
from .commands.build_cmd import build
from .commands.dry_run_cmd import dry_run
from .commands.emit_cmd import emit
from .commands.list_cmd import list_operators
from .commands.migrate_cmd import migrate
from .commands.plan_cmd import plan
from .commands.verify_cmd import verify_graph
from .commands.visualize_cmd import visualize


@click.group()
@click.version_option(version="0.1.0", prog_name="graph-transform")
def cli() -> None:
    """Algebraic graph rewriting engine for code refactoring.

    Build, transform, verify, and visualize code graphs using
    the three-primitive system (INSERT, DELETE, UPDATE) and
    compositions (RENAME, MOVE, EXTRACT, INLINE, etc.).

    \b
    Quick start:
      graph-transform list                     # see primitives and compositions
      graph-transform build src/ -o g.json     # build graph from source
      graph-transform verify g.json            # check invariants
      graph-transform apply g.json --primitive insert_node -p '{"node_id":"...", ...}'
      graph-transform apply g.json --composition RENAME -p '{"target":"...", "new_name":"..."}'
      graph-transform batch g.json -f steps.yaml  # apply multiple operations
      graph-transform plan src/ -F recipe.yaml -o plan.json  # generate edit plan
      graph-transform visualize g.json -o out
    """


cli.add_command(list_operators, name="list")
cli.add_command(apply_operator, name="apply")
cli.add_command(batch_operators, name="batch")
cli.add_command(plan, name="plan")
cli.add_command(verify_graph, name="verify")
cli.add_command(dry_run, name="dry-run")
cli.add_command(visualize, name="visualize")
cli.add_command(build, name="build")
cli.add_command(emit, name="emit")
cli.add_command(migrate, name="migrate")


def main() -> None:
    """Entry point for the graph-transform CLI."""
    cli()
