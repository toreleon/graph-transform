"""
batch -- Apply multiple refactoring operators in sequence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml

from graph_transform.cli.formatting import (
    err_console,
    print_error,
    print_graph_summary,
    print_success,
)
from graph_transform.cli.operator_metadata import resolve_operator
from graph_transform.engine.core import create_engine
from graph_transform.engine.transformation_path import RuleApplication, TransformationPath
from graph_transform.io.serialization import load_graph, save_graph


class OperatorStep:
    """A single operator step in a batch."""
    
    def __init__(self, operator: str, params: dict, repeat: str = "once"):
        self.operator = operator
        self.params = params
        self.repeat = repeat  # "once" or "all"


def parse_yaml_file(filepath: str) -> tuple[str, list[OperatorStep]]:
    """Parse a YAML batch file.
    
    Format:
    description: "Add logging parameter"
    steps:
      - op: add_param
        params:
          function_name: foo
          param_name: bar
    """
    with open(filepath) as f:
        data = yaml.safe_load(f)
    
    description = data.get("description", "Batch refactoring")
    steps = []
    for step in data.get("steps", []):
        steps.append(OperatorStep(
            operator=step["op"],
            params=step.get("params", {}),
            repeat=step.get("repeat", "once"),
        ))
    return description, steps


def parse_inline_operators(operators: tuple, params: tuple) -> list[OperatorStep]:
    """Parse inline -op/-p pairs."""
    if len(operators) != len(params):
        raise ValueError(f"Mismatch: {len(operators)} operators but {len(params)} param sets")
    
    steps = []
    for op, p in zip(operators, params):
        try:
            params_dict = json.loads(p)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for operator '{op}': {e}")
        steps.append(OperatorStep(operator=op, params=params_dict))
    return steps


@click.command("batch")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--file", "-f",
    type=click.Path(exists=True),
    help="YAML file defining the batch steps.",
)
@click.option(
    "--operator", "-op",
    multiple=True,
    help="Operator name (can be repeated).",
)
@click.option(
    "--params", "-p",
    multiple=True,
    help="JSON params for each operator (must match -op count).",
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
    "--check-per-step",
    is_flag=True,
    help="Run invariants after each step (default: only at end).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
def batch_operators(
    graph_file: str,
    file: str | None,
    operator: tuple[str, ...],
    params: tuple[str, ...],
    mode: str,
    output: str | None,
    check_per_step: bool,
    verbose: bool,
) -> None:
    """Apply multiple refactoring operators in sequence.
    
    Use either a YAML file (-f) or inline operators (-op/-p pairs).
    
    Examples:
    
        # YAML file
        graph-transform batch graph.json -f refactor.yaml -o result.json
        
        # Inline operators
        graph-transform batch graph.json \\
          -op add_param -p '{"function_name":"foo","param_name":"bar"}' \\
          -op add_arg -p '{"callee":"foo","arg_name":"bar","arg_value":"True"}' \\
          -o result.json
    """
    # Parse steps from either YAML or inline
    if file:
        if operator or params:
            print_error("Cannot use both --file and inline --operator/--params")
            sys.exit(2)
        try:
            description, steps = parse_yaml_file(file)
        except Exception as e:
            print_error(f"Failed to parse YAML file: {e}")
            sys.exit(2)
    elif operator:
        try:
            steps = parse_inline_operators(operator, params)
            description = f"Batch of {len(steps)} operators"
        except ValueError as e:
            print_error(str(e))
            sys.exit(2)
    else:
        print_error("Must provide either --file or --operator/--params pairs")
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
    
    # Create engine and path
    # For per-step checking, enable invariants; otherwise disable until end
    engine = create_engine(mode=mode, check_invariants=check_per_step)
    path = TransformationPath(initial_graph=graph, current_graph=graph)
    path.metadata["description"] = description
    
    current = graph
    failed = False
    
    for i, step in enumerate(steps):
        if verbose:
            err_console.print(f"[dim]Step {i+1}/{len(steps)}: {step.operator}" + 
                              (" (all matches)" if step.repeat == "all" else "") + "[/dim]")
        
        try:
            op_type = resolve_operator(step.operator)
        except ValueError as e:
            print_error(f"Step {i+1}: {e}")
            failed = True
            break
        
        rule = engine.catalog.create_rule(op_type, step.params)
        
        # Apply to all matches or just one
        if step.repeat == "all":
            results = engine.apply_all_matches(rule, current)
            if not results:
                print_error(f"Step {i+1} ({step.operator}) failed: No matches found")
                failed = True
                break
            # Get the final result after all applications
            result = results[-1]
            if verbose and len(results) > 1:
                err_console.print(f"  [dim]Applied to {len(results)} matches[/dim]")
        else:
            result = engine.apply_rule(rule, current)
        
        app = RuleApplication(rule=rule, result=result)
        path.add_step(app)
        
        if not result.success:
            print_error(f"Step {i+1} ({step.operator}) failed: {result.errors[0] if result.errors else 'Unknown error'}")
            failed = True
            break
        
        current = result.result_graph
    
    # Final invariant check if not checking per-step
    if not failed and not check_per_step and current:
        final_engine = create_engine(mode=mode, check_invariants=True)
        violations = final_engine.verify_graph(current)
        errors = [v for v in violations if v.severity == "error"]
        if errors:
            print_error(f"Final invariant check failed with {len(errors)} error(s):")
            for v in errors[:5]:  # Show first 5
                err_console.print(f"  [red]•[/red] {v.invariant_name}: {v.message}")
            if len(errors) > 5:
                err_console.print(f"  [dim]... and {len(errors) - 5} more[/dim]")
            failed = True
    
    # Output results
    if failed:
        err_console.print(f"\n[red]Batch failed at step {path.length}[/red]")
        sys.exit(1)
    
    if verbose:
        print_graph_summary(current, title="Result Graph")
    
    print_success(f"Batch completed: {path.success_count}/{path.length} steps succeeded")
    
    if current:
        save_graph(current, output)
        if output:
            print_success(f"Result graph written to {output}")
