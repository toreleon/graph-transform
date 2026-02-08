"""
plan -- Generate a refactoring edit plan from source code and primitives/compositions.

Combines build + transform + edit generation in one command.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml

from graph_transform.cli.commands.batch_cmd import (
    TransformStep,
    parse_yaml_file,
)
from graph_transform.cli.formatting import err_console, print_error, print_success
from graph_transform.cli.primitive_metadata import (
    resolve_composition,
    resolve_primitive,
)
from graph_transform.core.primitives import (
    CompositionRegistry,
    primitive_from_dict,
)
from graph_transform.core.typed_graph import TypedGraph
from graph_transform.io.builder import build_graph_from_files, build_graph_from_source


# =============================================================================
# EditInstruction
# =============================================================================


@dataclass
class EditInstruction:
    """A structured edit instruction for the coding agent."""

    edit_type: str
    file: str
    line: int | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = {
            "type": self.edit_type,
            "file": self.file,
        }
        if self.line is not None:
            result["line"] = self.line
        result.update(self.details)
        return result


# =============================================================================
# Edit generation from primitive/composition results
# =============================================================================


def edits_from_primitive_result(
    result: Any,  # PrimitiveResult
    primitive_name: str,
    params: dict[str, Any],
) -> list[EditInstruction]:
    """Generate edit instructions from a PrimitiveResult."""
    edits: list[EditInstruction] = []

    if not result.success:
        return edits

    # Extract file/line from params or metadata
    file = params.get("file", params.get("attrs", {}).get("file", "unknown"))
    line = params.get("line", params.get("attrs", {}).get("line"))

    for node_id in result.affected_ids:
        if primitive_name == "insert_node":
            node_kind = params.get("node_kind", "unknown")
            name = params.get("attrs", {}).get("name", node_id)
            edits.append(EditInstruction(
                edit_type=f"add_{node_kind}",
                file=file,
                line=line,
                details={"name": name, "node_id": node_id},
            ))

        elif primitive_name == "delete_node":
            edits.append(EditInstruction(
                edit_type="delete_node",
                file=file,
                line=line,
                details={"node_id": node_id},
            ))

        elif primitive_name == "update":
            prop = params.get("prop")
            value = params.get("value")
            edits.append(EditInstruction(
                edit_type="update",
                file=file,
                line=line,
                details={
                    "target": params.get("target"),
                    "property": prop,
                    "value": value,
                },
            ))

        elif primitive_name == "insert_edge":
            edits.append(EditInstruction(
                edit_type="add_edge",
                file=file,
                line=line,
                details={
                    "source": params.get("source"),
                    "target": params.get("target"),
                    "edge_kind": params.get("edge_kind"),
                },
            ))

        elif primitive_name == "delete_edge":
            edits.append(EditInstruction(
                edit_type="delete_edge",
                file=file,
                line=line,
                details={
                    "source": params.get("source"),
                    "target": params.get("target"),
                },
            ))

    return edits


def edits_from_composition_result(
    result: Any,  # CompositionResult
    composition_name: str,
    params: dict[str, Any],
) -> list[EditInstruction]:
    """Generate edit instructions from a CompositionResult."""
    edits: list[EditInstruction] = []

    if not result.success:
        return edits

    # Map composition to edit type
    file = params.get("file", "unknown")
    line = params.get("line")

    if composition_name == "RENAME":
        target = params.get("target", "")
        new_name = params.get("new_name", "")
        edits.append(EditInstruction(
            edit_type="rename",
            file=file,
            line=line,
            details={
                "target": target,
                "new_name": new_name,
                "affected_ids": result.affected_ids,
            },
        ))

    elif composition_name == "MOVE":
        edits.append(EditInstruction(
            edit_type="move",
            file=file,
            line=line,
            details={
                "target": params.get("target"),
                "from_scope": params.get("from_scope"),
                "to_scope": params.get("to_scope"),
            },
        ))

    elif composition_name == "EXTRACT":
        edits.append(EditInstruction(
            edit_type="extract",
            file=file,
            line=line,
            details={
                "new_id": params.get("new_id"),
                "new_name": params.get("new_name"),
                "node_kind": params.get("node_kind"),
                "scope": params.get("scope"),
            },
        ))

    elif composition_name == "INLINE":
        edits.append(EditInstruction(
            edit_type="inline",
            file=file,
            line=line,
            details={
                "target": params.get("target"),
            },
        ))

    elif composition_name == "ADD_GUARD":
        edits.append(EditInstruction(
            edit_type="add_guard",
            file=file,
            line=line,
            details={
                "target": params.get("target"),
                "guard_type": params.get("guard_type"),
                "guard_condition": params.get("guard_condition"),
            },
        ))

    elif composition_name == "CHANGE_SIGNATURE":
        edits.append(EditInstruction(
            edit_type="change_signature",
            file=file,
            line=line,
            details={
                "target": params.get("target"),
                "changes": params.get("changes"),
            },
        ))

    elif composition_name == "WRAP":
        edits.append(EditInstruction(
            edit_type="wrap",
            file=file,
            line=line,
            details={
                "target": params.get("target"),
                "wrapper_kind": params.get("wrapper_kind"),
            },
        ))

    return edits


# =============================================================================
# Build and parse helpers
# =============================================================================


def _build_graph(
    source_path: str | None,
    files: tuple[str, ...],
    stdin_flag: bool,
) -> TypedGraph:
    """Build graph from source."""
    file_list: list[str] = []

    if stdin_flag:
        if source_path or files:
            print_error("Cannot use --stdin with SOURCE_PATH or --files")
            sys.exit(2)
        for line in sys.stdin:
            line = line.strip()
            if line and line.endswith(".py"):
                file_list.append(line)
        if not file_list:
            print_error("No Python files provided via stdin")
            sys.exit(2)
    elif files:
        if source_path:
            print_error("Cannot use SOURCE_PATH with --files")
            sys.exit(2)
        file_list = list(files)
    elif source_path:
        pass
    else:
        print_error("Must provide SOURCE_PATH, --files, or --stdin")
        sys.exit(2)

    try:
        if file_list:
            return build_graph_from_files(file_list)
        else:
            return build_graph_from_source(source_path)
    except (FileNotFoundError, SyntaxError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)


def _parse_steps_inline(
    primitives: tuple[str, ...],
    compositions: tuple[str, ...],
    params: tuple[str, ...],
) -> list[TransformStep]:
    """Parse inline steps from CLI options."""
    total_ops = len(primitives) + len(compositions)
    if total_ops != len(params):
        print_error(
            f"Mismatch: {total_ops} operations but {len(params)} param sets"
        )
        sys.exit(2)

    steps = []
    param_idx = 0

    for prim in primitives:
        try:
            params_dict = json.loads(params[param_idx])
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON for primitive '{prim}': {e}")
            sys.exit(2)
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
            print_error(f"Invalid JSON for composition '{comp}': {e}")
            sys.exit(2)
        steps.append(TransformStep(
            step_type="composition",
            name=comp,
            params=params_dict,
        ))
        param_idx += 1

    return steps


# =============================================================================
# CLI Command
# =============================================================================


@click.command("plan")
@click.argument("source_path", type=click.Path(exists=True), required=False)
@click.option(
    "--files", "-f",
    multiple=True,
    type=click.Path(exists=True),
    help="Specific Python files to include (can be repeated).",
)
@click.option(
    "--stdin",
    is_flag=True,
    help="Read file list from stdin (one file per line).",
)
@click.option(
    "--recipe", "-F",
    "yaml_file",
    type=click.Path(exists=True),
    help="YAML file defining the transformation steps.",
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
    help="Output file for edit plan (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
def plan(
    source_path: str | None,
    files: tuple[str, ...],
    stdin: bool,
    yaml_file: str | None,
    primitive: tuple[str, ...],
    composition: tuple[str, ...],
    params: tuple[str, ...],
    output: str | None,
    verbose: bool,
) -> None:
    """Generate a refactoring edit plan from source code and transformations.

    Builds a graph from source, applies transformations, and outputs
    structured edit instructions.

    Examples:

        # From source directory + YAML recipe
        graph-transform plan src/ -F refactor.yaml -o plan.json

        # From source + inline operations
        graph-transform plan src/ \\
            --primitive insert_node -p '{"node_id":"func:new","node_kind":"callable","attrs":{"name":"new"}}' \\
            --composition RENAME -p '{"target":"func:old","new_name":"new_name"}' \\
            -o plan.json
    """
    # Phase 1: Build graph from source
    graph = _build_graph(source_path, files, stdin)
    if verbose:
        err_console.print(
            f"[dim]Built graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges[/dim]"
        )

    # Phase 2: Parse transformation steps
    if yaml_file:
        if primitive or composition or params:
            print_error("Cannot use both -F and inline operations")
            sys.exit(2)
        try:
            _, steps = parse_yaml_file(yaml_file)
        except Exception as e:
            print_error(f"Failed to parse YAML file: {e}")
            sys.exit(2)
    elif primitive or composition:
        steps = _parse_steps_inline(primitive, composition, params)
    else:
        print_error("Must provide either -F (YAML file) or inline operations")
        sys.exit(2)

    if not steps:
        print_error("No steps defined")
        sys.exit(2)

    if verbose:
        err_console.print(f"[dim]Parsed {len(steps)} transformation steps[/dim]")

    # Phase 3: Apply transformations and collect edits
    current = graph
    step_results: list[dict[str, Any]] = []
    pipeline_error: str | None = None

    for i, step in enumerate(steps):
        step_desc = f"{step.step_type}:{step.name}"
        all_edits: list[EditInstruction] = []

        try:
            if step.step_type == "primitive":
                prim_type = resolve_primitive(step.name)
                prim_dict = {"primitive": prim_type, **step.params}
                prim = primitive_from_dict(prim_dict)
                result = prim.execute(current)

                if not result.success:
                    pipeline_error = f"Step {i+1} ({step_desc}): {result.error}"
                    print_error(pipeline_error)
                    break

                all_edits = edits_from_primitive_result(result, step.name, step.params)

            else:  # composition
                comp_type = resolve_composition(step.name)
                comp = CompositionRegistry.create(comp_type, **step.params)
                if comp is None:
                    pipeline_error = f"Step {i+1}: Failed to create composition '{comp_type}'"
                    print_error(pipeline_error)
                    break

                result = comp.execute(current)

                if not result.success:
                    pipeline_error = f"Step {i+1} ({step_desc}): {result.error}"
                    print_error(pipeline_error)
                    break

                all_edits = edits_from_composition_result(result, step.name, step.params)

        except Exception as e:
            pipeline_error = f"Step {i+1} ({step_desc}): {e}"
            print_error(pipeline_error)
            break

        # Record step result
        step_result: dict[str, Any] = {
            "step": i + 1,
            "type": step.step_type,
            "name": step.name,
            "params": step.params,
            "edits": [e.to_dict() for e in all_edits],
        }
        step_results.append(step_result)

        if verbose:
            err_console.print(
                f"  [dim]Step {i+1}/{len(steps)}: {step_desc} -> {len(all_edits)} edits[/dim]"
            )

    # Phase 4: Output
    total_edits = sum(len(s["edits"]) for s in step_results)

    output_data: dict[str, Any] = {
        "steps": step_results,
        "summary": {
            "total_steps": len(step_results),
            "total_edits": total_edits,
        },
    }

    if pipeline_error:
        output_data["error"] = pipeline_error
        output_data["partial"] = True

    json_output = json.dumps(output_data, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(json_output)
        if pipeline_error:
            print_error(
                f"Partial plan written to {output} "
                f"({total_edits} edits from {len(step_results)} completed steps)"
            )
        else:
            print_success(
                f"Edit plan written to {output} ({total_edits} edits in {len(step_results)} steps)"
            )
    else:
        sys.stdout.write(json_output + "\n")

    if pipeline_error:
        sys.exit(1)
