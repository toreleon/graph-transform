"""
batch -- Apply multiple primitives/compositions in sequence.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml

from graph_transform.cli.formatting import (
    err_console,
    print_error,
    print_graph_summary,
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


@dataclass
class TransformStep:
    """A single transformation step in a batch."""

    step_type: str  # "primitive" or "composition"
    name: str
    params: dict = field(default_factory=dict)
    repeat: str = "once"  # "once" or "all" (for compositions)


@dataclass
class BatchResult:
    """Result of a batch transformation."""

    success: bool
    steps_completed: int
    total_steps: int
    failed_step: int | None = None
    error: str | None = None


def parse_yaml_file(filepath: str) -> tuple[str, list[TransformStep]]:
    """Parse a YAML batch file.

    New format:
        description: "Add helper function"
        steps:
          - primitive: insert_node
            params:
              node_id: "func:helper"
              node_kind: callable
              attrs: {name: "helper"}

          - composition: RENAME
            params:
              target: "func:old"
              new_name: "new_name"
    """
    with open(filepath) as f:
        data = yaml.safe_load(f)

    description = data.get("description", "Batch transformation")
    steps = []

    for step in data.get("steps", []):
        if "primitive" in step:
            steps.append(TransformStep(
                step_type="primitive",
                name=step["primitive"],
                params=step.get("params", {}),
            ))
        elif "composition" in step:
            steps.append(TransformStep(
                step_type="composition",
                name=step["composition"],
                params=step.get("params", {}),
                repeat=step.get("repeat", "once"),
            ))
        else:
            raise ValueError(f"Invalid step: must have 'primitive' or 'composition' key")

    return description, steps


def parse_inline_steps(
    primitives: tuple[str, ...],
    compositions: tuple[str, ...],
    params: tuple[str, ...],
) -> list[TransformStep]:
    """Parse inline --primitive/--composition and --params pairs.

    The order of params corresponds to the order of primitives + compositions.
    """
    total_ops = len(primitives) + len(compositions)
    if total_ops != len(params):
        raise ValueError(
            f"Mismatch: {total_ops} operations but {len(params)} param sets"
        )

    steps = []
    param_idx = 0

    # Process primitives first, then compositions
    for prim in primitives:
        try:
            params_dict = json.loads(params[param_idx])
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for primitive '{prim}': {e}")
        steps.append(TransformStep(
            step_type="primitive",
            name=prim,
            params=params_dict,
        ))
        param_idx += 1

    for comp in compositions:
        try:
            params_dict = json.loads(params[param_idx])
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for composition '{comp}': {e}")
        steps.append(TransformStep(
            step_type="composition",
            name=comp,
            params=params_dict,
        ))
        param_idx += 1

    return steps


@click.command("batch")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--file", "-f",
    type=click.Path(exists=True),
    help="YAML file defining the batch steps.",
)
@click.option(
    "--primitive", "-prim",
    multiple=True,
    help="Primitive name (can be repeated).",
)
@click.option(
    "--composition", "-comp",
    multiple=True,
    help="Composition name (can be repeated).",
)
@click.option(
    "--params", "-p",
    multiple=True,
    help="JSON params for each operation (must match total operation count).",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file for result graph (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
def batch_operators(
    graph_file: str,
    file: str | None,
    primitive: tuple[str, ...],
    composition: tuple[str, ...],
    params: tuple[str, ...],
    output: str | None,
    verbose: bool,
) -> None:
    """Apply multiple primitives/compositions in sequence.

    Use either a YAML file (-f) or inline operations.

    Examples:

        # YAML file
        graph-transform batch graph.json -f refactor.yaml -o result.json

        # Inline operations
        graph-transform batch graph.json \\
          --primitive insert_node -p '{"node_id":"func:new","node_kind":"callable","attrs":{"name":"new"}}' \\
          --composition RENAME -p '{"target":"func:old","new_name":"renamed"}'
    """
    # Parse steps from either YAML or inline
    if file:
        if primitive or composition or params:
            print_error("Cannot use both --file and inline operations")
            sys.exit(2)
        try:
            description, steps = parse_yaml_file(file)
        except Exception as e:
            print_error(f"Failed to parse YAML file: {e}")
            sys.exit(2)
    elif primitive or composition:
        try:
            steps = parse_inline_steps(primitive, composition, params)
            description = f"Batch of {len(steps)} operations"
        except ValueError as e:
            print_error(str(e))
            sys.exit(2)
    else:
        print_error("Must provide either --file or inline operations")
        sys.exit(2)

    if not steps:
        print_error("No steps defined")
        sys.exit(2)

    # Load graph
    try:
        graph = load_graph(graph_file)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    # Execute steps
    current = graph
    steps_completed = 0

    for i, step in enumerate(steps):
        step_desc = f"{step.step_type}:{step.name}"
        if verbose:
            err_console.print(f"[dim]Step {i+1}/{len(steps)}: {step_desc}[/dim]")

        try:
            if step.step_type == "primitive":
                result = _execute_primitive(current, step)
            else:
                result = _execute_composition(current, step)
        except Exception as e:
            print_error(f"Step {i+1} ({step_desc}) failed: {e}")
            sys.exit(1)

        if not result.success:
            error_msg = result.error if hasattr(result, 'error') and result.error else "Unknown error"
            print_error(f"Step {i+1} ({step_desc}) failed: {error_msg}")
            sys.exit(1)

        steps_completed += 1

        if verbose and hasattr(result, 'affected_ids') and result.affected_ids:
            err_console.print(f"  [dim]Affected: {', '.join(result.affected_ids[:3])}"
                              + (f" (+{len(result.affected_ids)-3} more)" if len(result.affected_ids) > 3 else "")
                              + "[/dim]")

    # Output results
    if verbose:
        print_graph_summary(current, title="Result Graph")

    print_success(f"Batch completed: {steps_completed}/{len(steps)} steps succeeded")

    save_graph(current, output)
    if output:
        print_success(f"Result graph written to {output}")


def _execute_primitive(graph, step: TransformStep):
    """Execute a primitive step."""
    try:
        prim_type = resolve_primitive(step.name)
    except ValueError as e:
        raise ValueError(str(e))

    prim_dict = {"primitive": prim_type, **step.params}

    try:
        prim = primitive_from_dict(prim_dict)
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid primitive parameters: {e}")

    return prim.execute(graph)


def _execute_composition(graph, step: TransformStep):
    """Execute a composition step."""
    try:
        comp_type = resolve_composition(step.name)
    except ValueError as e:
        raise ValueError(str(e))

    comp = CompositionRegistry.create(comp_type, **step.params)
    if comp is None:
        raise ValueError(f"Failed to create composition '{comp_type}'")

    return comp.execute(graph)
