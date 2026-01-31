"""
plan -- Generate a refactoring edit plan from source code and operators.

Combines build + transform + edit generation in one command.
Replaces the old codegen workflow (build -> batch -> codegen).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import click

from graph_transform.cli.commands.batch_cmd import (
    OperatorStep,
    parse_inline_operators,
    parse_yaml_file,
)
from graph_transform.cli.formatting import err_console, print_error, print_success
from graph_transform.cli.operator_metadata import resolve_operator
from graph_transform.core.typed_graph import EdgeType, NodeType, TypedGraph
from graph_transform.engine.core import create_engine
from graph_transform.io.builder import build_graph_from_files, build_graph_from_source
from graph_transform.rewriting.graph_change import ChangeType, GraphChangeSet


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
# Helpers
# =============================================================================


def _extract_location(
    node_id: str | None, attrs: dict[str, Any]
) -> tuple[str | None, int | None]:
    """Extract file and line from node attributes or node ID."""
    file = attrs.get("file")
    line = attrs.get("line")
    if file:
        return file, line
    # Fallback: parse from node_id like "call:test.py:10:1"
    if node_id:
        parts = node_id.split(":")
        if len(parts) >= 3:
            try:
                for i in range(len(parts) - 1, 1, -1):
                    if parts[i].isdigit():
                        return ":".join(parts[1:i]), int(parts[i])
            except (ValueError, IndexError):
                pass
    return None, None


def _find_parent_from_edges(
    child_host_id: str,
    added_edges: list,
    edge_type: EdgeType,
    result_graph: TypedGraph | None,
) -> dict[str, Any]:
    """Find parent node info for a child from added edges."""
    for ec in added_edges:
        if ec.target == child_host_id and ec.edge_type == edge_type:
            parent_id = ec.source
            parent_info: dict[str, Any] = {"id": parent_id}
            # Look up parent attrs from result graph
            if result_graph:
                parent_node = result_graph.get_node(parent_id)
                if parent_node:
                    parent_info["name"] = parent_node.attrs.get("name") or parent_node.attrs.get("callee")
                    parent_info["file"] = parent_node.attrs.get("file")
                    parent_info["line"] = parent_node.attrs.get("line")
            if "file" not in parent_info:
                file, line = _extract_location(parent_id, {})
                parent_info.setdefault("file", file)
                parent_info.setdefault("line", line)
            return parent_info
    return {}


# =============================================================================
# Edit generation from GraphChangeSet
# =============================================================================


def edits_from_changes(
    changes: GraphChangeSet,
    result_graph: TypedGraph | None,
    rule_name: str,
    parameters: dict[str, Any],
) -> list[EditInstruction]:
    """Convert GraphChangeSet records into EditInstruction list.

    Unlike the old codegen approach (which diffed two graphs), this reads
    directly from the change records captured at rewrite time. It also has
    access to the operator parameters for richer context.
    """
    edits: list[EditInstruction] = []
    added_edges = changes.added_edges()

    # --- Added nodes ---
    for nc in changes.added_nodes():
        file, line = _extract_location(nc.host_node_id, nc.attrs)

        if nc.node_type == NodeType.PARAMETER:
            parent = _find_parent_from_edges(
                nc.host_node_id or "", added_edges, EdgeType.HAS_PARAMETER, result_graph
            )
            edits.append(EditInstruction(
                edit_type="add_parameter",
                file=parent.get("file") or file or "unknown",
                line=parent.get("line") or line,
                details={
                    "function": parent.get("name") or parameters.get("function_name", "unknown"),
                    "parameter": {
                        "name": nc.attrs.get("name"),
                        "default": nc.attrs.get("default_value"),
                        "has_default": nc.attrs.get("has_default", False),
                    },
                },
            ))

        elif nc.node_type == NodeType.ARGUMENT:
            parent = _find_parent_from_edges(
                nc.host_node_id or "", added_edges, EdgeType.HAS_ARGUMENT, result_graph
            )
            edits.append(EditInstruction(
                edit_type="add_argument",
                file=parent.get("file") or file or "unknown",
                line=parent.get("line") or line,
                details={
                    "call": parent.get("name") or parameters.get("callee", "unknown"),
                    "argument": {
                        "name": nc.attrs.get("name"),
                        "value": nc.attrs.get("value"),
                        "is_keyword": nc.attrs.get("is_keyword", True),
                    },
                },
            ))

        elif nc.node_type == NodeType.FUNCTION:
            edits.append(EditInstruction(
                edit_type="add_method" if nc.attrs.get("is_method") else "add_function",
                file=nc.attrs.get("file") or file or "unknown",
                line=nc.attrs.get("line") or line,
                details={
                    "name": nc.attrs.get("name"),
                    "is_async": nc.attrs.get("is_async", False),
                },
            ))

        elif nc.node_type == NodeType.CLASS:
            edits.append(EditInstruction(
                edit_type="add_class",
                file=nc.attrs.get("file") or file or "unknown",
                line=nc.attrs.get("line") or line,
                details={"name": nc.attrs.get("name")},
            ))

        elif nc.node_type == NodeType.FIELD:
            edits.append(EditInstruction(
                edit_type="add_field",
                file=nc.attrs.get("file") or file or "unknown",
                line=nc.attrs.get("line") or line,
                details={
                    "class": nc.attrs.get("class_name"),
                    "name": nc.attrs.get("name"),
                    "default": nc.attrs.get("default_value"),
                },
            ))

        elif nc.node_type == NodeType.IMPORT:
            edits.append(EditInstruction(
                edit_type="add_import",
                file=nc.attrs.get("file") or file or "unknown",
                line=nc.attrs.get("line") or line,
                details={
                    "module": nc.attrs.get("module"),
                    "name": nc.attrs.get("name"),
                    "alias": nc.attrs.get("alias"),
                },
            ))

        elif nc.node_type == NodeType.MODULE:
            edits.append(EditInstruction(
                edit_type="create_module",
                file=nc.attrs.get("file") or file or "unknown",
                line=None,
                details={"name": nc.attrs.get("name")},
            ))

    # --- Removed nodes ---
    edit_type_map = {
        NodeType.PARAMETER: "remove_parameter",
        NodeType.ARGUMENT: "remove_argument",
        NodeType.FUNCTION: "remove_function",
        NodeType.CLASS: "remove_class",
        NodeType.FIELD: "remove_field",
        NodeType.IMPORT: "remove_import",
        NodeType.MODULE: "delete_module",
    }
    for nc in changes.removed_nodes():
        if nc.node_type in edit_type_map:
            file, line = _extract_location(nc.host_node_id, nc.attrs)
            edits.append(EditInstruction(
                edit_type=edit_type_map[nc.node_type],
                file=nc.attrs.get("file") or file or "unknown",
                line=nc.attrs.get("line") or line,
                details={
                    "name": nc.attrs.get("name") or nc.attrs.get("callee"),
                },
            ))

    # --- Attribute updates (renames, etc.) ---
    for nc in changes.updated_nodes():
        old_name = nc.old_attrs.get("name") if nc.old_attrs else None
        new_name = nc.attrs.get("name")
        if old_name and new_name and old_name != new_name:
            file, line = _extract_location(nc.host_node_id, nc.attrs)
            edits.append(EditInstruction(
                edit_type="rename",
                file=nc.attrs.get("file") or file or "unknown",
                line=nc.attrs.get("line") or line,
                details={
                    "old_name": old_name,
                    "new_name": new_name,
                    "node_type": nc.node_type.value,
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
    """Build graph from source (mirrors build_cmd.py logic)."""
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


def _parse_steps(
    yaml_file: str | None,
    operator: tuple[str, ...],
    params: tuple[str, ...],
) -> list[OperatorStep]:
    """Parse operator steps (mirrors batch_cmd.py logic)."""
    if yaml_file:
        if operator or params:
            print_error("Cannot use both -F and inline --operator/--params")
            sys.exit(2)
        try:
            _, steps = parse_yaml_file(yaml_file)
        except Exception as e:
            print_error(f"Failed to parse YAML file: {e}")
            sys.exit(2)
    elif operator:
        try:
            steps = parse_inline_operators(operator, params)
        except ValueError as e:
            print_error(str(e))
            sys.exit(2)
    else:
        print_error("Must provide either -F (YAML file) or --operator/--params pairs")
        sys.exit(2)

    if not steps:
        print_error("No steps defined")
        sys.exit(2)

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
    help="Read file list from stdin (one file per line, pipe from grep).",
)
@click.option(
    "--recipe", "-F",
    "yaml_file",
    type=click.Path(exists=True),
    help="YAML file defining the refactoring steps.",
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
    help="Output file for edit plan (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
def plan(
    source_path: str | None,
    files: tuple[str, ...],
    stdin: bool,
    yaml_file: str | None,
    operator: tuple[str, ...],
    params: tuple[str, ...],
    mode: str,
    output: str | None,
    verbose: bool,
) -> None:
    """Generate a refactoring edit plan from source code and operators.

    Builds a graph from source, applies operators with verification,
    and outputs structured edit instructions -- all in one command.

    \b
    Examples:

      # From source directory + YAML recipe
      graph-transform plan src/ -F refactor.yaml -o plan.json

      # From source + inline operators
      graph-transform plan src/ \\
        -op add_param -p '{"function_name":"foo","param_name":"bar"}' \\
        -op add_arg -p '{"callee":"foo","arg_name":"bar","arg_value":"True"}' \\
        -o plan.json

      # From piped grep results
      grep -rl "target_fn" src/ | graph-transform plan --stdin \\
        -F refactor.yaml -o plan.json
    """
    # Phase 1: Build graph from source
    graph = _build_graph(source_path, files, stdin)
    if verbose:
        err_console.print(
            f"[dim]Built graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges[/dim]"
        )

    # Phase 2: Parse operator steps
    steps = _parse_steps(yaml_file, operator, params)
    if verbose:
        err_console.print(f"[dim]Parsed {len(steps)} operator steps[/dim]")

    # Phase 3: Apply operators and collect changes
    engine = create_engine(mode=mode, check_invariants=False)
    current = graph
    step_results: list[dict[str, Any]] = []

    for i, step in enumerate(steps):
        try:
            op_type = resolve_operator(step.operator)
        except ValueError as e:
            print_error(f"Step {i + 1}: {e}")
            sys.exit(1)

        rule = engine.catalog.create_rule(op_type, step.params)

        if step.repeat == "all":
            results = engine.apply_all_matches(rule, current)
            if not results:
                print_error(f"Step {i + 1} ({step.operator}): No matches found")
                sys.exit(1)

            all_edits: list[EditInstruction] = []
            for r in results:
                if not r.success:
                    msg = r.errors[0] if r.errors else "Unknown error"
                    print_error(f"Step {i + 1} ({step.operator}): {msg}")
                    sys.exit(1)
                if r.changes:
                    all_edits.extend(
                        edits_from_changes(r.changes, r.result_graph, rule.name, rule.parameters)
                    )
                current = r.result_graph

            step_results.append({
                "step": i + 1,
                "operator": step.operator,
                "params": step.params,
                "description": rule.description,
                "applications": len(results),
                "edits": [e.to_dict() for e in all_edits],
            })
        else:
            result = engine.apply_rule(rule, current)
            if not result.success:
                msg = result.errors[0] if result.errors else "Unknown error"
                print_error(f"Step {i + 1} ({step.operator}): {msg}")
                sys.exit(1)

            step_edits: list[EditInstruction] = []
            if result.changes:
                step_edits = edits_from_changes(
                    result.changes, result.result_graph, rule.name, rule.parameters
                )
            current = result.result_graph

            step_results.append({
                "step": i + 1,
                "operator": step.operator,
                "params": step.params,
                "description": rule.description,
                "edits": [e.to_dict() for e in step_edits],
            })

        if verbose:
            n_edits = len(step_results[-1]["edits"])
            err_console.print(
                f"  [dim]Step {i + 1}/{len(steps)}: {step.operator} -> {n_edits} edits[/dim]"
            )

    # Phase 4: Output
    total_edits = sum(len(s["edits"]) for s in step_results)
    output_data = {
        "description": "Refactoring edit plan",
        "steps": step_results,
        "summary": {
            "total_steps": len(step_results),
            "total_edits": total_edits,
        },
    }

    json_output = json.dumps(output_data, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(json_output)
        print_success(
            f"Edit plan written to {output} ({total_edits} edits in {len(step_results)} steps)"
        )
    else:
        sys.stdout.write(json_output + "\n")
