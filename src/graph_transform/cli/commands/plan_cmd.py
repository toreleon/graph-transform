"""
plan -- Generate a refactoring edit plan from source code and operators.

Combines build + transform + edit generation in one command.
Replaces the old codegen workflow (build -> batch -> codegen).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
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
from graph_transform.engine.core import create_engine, verify_graph_invariants
from graph_transform.rewriting.invariants import InvariantSeverity
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
            func_name = parent.get("name") or parameters.get("function_name", "unknown")
            param_name = nc.attrs.get("name")
            default_val = nc.attrs.get("default_value")
            has_default = nc.attrs.get("has_default", False)
            param_file = parent.get("file") or file or "unknown"
            param_line = parent.get("line") or line

            # Build parameter string for sed
            if has_default and default_val is not None:
                param_str = f"{param_name}={default_val}"
            else:
                param_str = str(param_name)

            details: dict[str, Any] = {
                "function": func_name,
                "parameter": {
                    "name": param_name,
                    "default": default_val,
                    "has_default": has_default,
                },
            }
            # Generate sed command for single-line function defs:
            # Pattern 1: def func() → def func(param=default) (empty params)
            # Pattern 2: def func(...) → def func(..., param=default) (existing params)
            if param_line and param_name and func_name != "unknown":
                details["command"] = (
                    f"sed -i "
                    f"'{param_line}s/\\(def {func_name}\\)()/\\1({param_str})/; "
                    f"t; "
                    f"{param_line}s/\\(def {func_name}(.*\\))/\\1, {param_str})/' "
                    f"{param_file}"
                )

            edits.append(EditInstruction(
                edit_type="add_parameter",
                file=param_file,
                line=param_line,
                details=details,
            ))

        elif nc.node_type == NodeType.ARGUMENT:
            parent = _find_parent_from_edges(
                nc.host_node_id or "", added_edges, EdgeType.HAS_ARGUMENT, result_graph
            )
            callee = parent.get("name") or parameters.get("callee", "unknown")
            arg_name = nc.attrs.get("name")
            arg_value = nc.attrs.get("value")
            is_keyword = nc.attrs.get("is_keyword", True)
            arg_file = parent.get("file") or file or "unknown"
            arg_line = parent.get("line") or line

            # Build argument string for sed
            if is_keyword and arg_name:
                arg_str = f"{arg_name}={arg_value}"
            else:
                arg_str = str(arg_value) if arg_value is not None else str(arg_name)

            details = {
                "call": callee,
                "argument": {
                    "name": arg_name,
                    "value": arg_value,
                    "is_keyword": is_keyword,
                },
            }
            # Generate sed command for single-line calls:
            # Pattern 1: callee() → callee(arg) (empty args)
            # Pattern 2: callee(...) → callee(..., arg) (existing args)
            if arg_line and callee != "unknown":
                details["command"] = (
                    f"sed -i "
                    f"'{arg_line}s/\\(\\<{callee}\\>\\)()/\\1({arg_str})/; "
                    f"t; "
                    f"{arg_line}s/\\(\\<{callee}\\>(.*\\))/\\1, {arg_str})/' "
                    f"{arg_file}"
                )

            edits.append(EditInstruction(
                edit_type="add_argument",
                file=arg_file,
                line=arg_line,
                details=details,
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

    # --- Attribute updates (renames, call target changes, import changes) ---
    for nc in changes.updated_nodes():
        if not nc.old_attrs:
            continue
        file, line = _extract_location(nc.host_node_id, nc.attrs)
        resolved_file = nc.attrs.get("file") or file or "unknown"
        resolved_line = nc.attrs.get("line") or line

        # Import changes — handle before generic rename so IMPORT name
        # changes (submodule pattern) produce update_import edits.
        if nc.node_type == NodeType.IMPORT:
            old_mod = nc.old_attrs.get("module", "")
            new_mod = nc.attrs.get("module", "")
            old_name = nc.old_attrs.get("name")
            new_name = nc.attrs.get("name")

            # Case 1: module path changed (from X.old import Y → from X.new import Y)
            if old_mod and new_mod and old_mod != new_mod:
                # Selective move (names filter): generate split edits so the
                # agent removes just this name from the old import block and
                # adds a new import statement instead of changing the module
                # on the entire import line.
                names_filter = parameters.get("names")
                import_name = nc.attrs.get("name")
                if names_filter and import_name:
                    # Escape dots for sed regex patterns
                    escaped_old = old_mod.replace(".", "\\.")
                    # Remove NAME from old import line:
                    #  1. Sole import: `from MOD import NAME` → delete line
                    #  2. First in list: `from MOD import NAME, REST` → keep REST
                    #  3. Middle/last: `from MOD import REST, NAME` → keep REST
                    #  4. Multi-line block: line containing only `NAME,` → delete
                    edits.append(EditInstruction(
                        edit_type="remove_from_import",
                        file=resolved_file,
                        line=resolved_line,
                        details={
                            "module": old_mod,
                            "name": import_name,
                            "command": (
                                f"sed -i "
                                f"'/^[[:space:]]*from {escaped_old} import {import_name}[[:space:]]*$/d; "
                                f"s/\\(from {escaped_old} import \\){import_name}, /\\1/; "
                                f"s/, {import_name}\\b//; "
                                f"/^[[:space:]]*{import_name}[[:space:]]*,\\?[[:space:]]*$/d' "
                                f"{resolved_file}"
                            ),
                        },
                    ))
                    # Add new import, preserving indentation of the old import.
                    # Uses h;s;p;x to: save line → replace with new import
                    # (keeping leading whitespace) → print → restore original.
                    edits.append(EditInstruction(
                        edit_type="add_import",
                        file=resolved_file,
                        line=resolved_line,
                        details={
                            "module": new_mod,
                            "name": import_name,
                            "command": (
                                f"sed -i "
                                f"'/^[[:space:]]*from {escaped_old} import/"
                                f"{{h;s/^\\([[:space:]]*\\)from .*/\\1from {new_mod} import {import_name}/;"
                                f"p;x;}}' "
                                f"{resolved_file}"
                            ),
                        },
                    ))
                else:
                    escaped_old = old_mod.replace(".", "\\.")
                    edits.append(EditInstruction(
                        edit_type="update_import",
                        file=resolved_file,
                        line=resolved_line,
                        details={
                            "old_module": old_mod,
                            "new_module": new_mod,
                            "command": (
                                f"sed -i 's/from {escaped_old} import/"
                                f"from {new_mod} import/g' {resolved_file}"
                            ),
                        },
                    ))
                continue

            # Case 2: imported name changed (from X import old → from X import new)
            # This is the submodule import pattern.
            if old_name and new_name and old_name != new_name:
                old_full = f"{old_mod}.{old_name}" if old_mod else old_name
                new_full = f"{new_mod}.{new_name}" if new_mod else new_name
                edits.append(EditInstruction(
                    edit_type="update_import",
                    file=resolved_file,
                    line=resolved_line,
                    details={
                        "old_module": old_full,
                        "new_module": new_full,
                        "command": (
                            f"sed -i "
                            f"'s/import \\<{old_name}\\>/import {new_name}/g; "
                            f"s/\\<{old_name}\\>\\./{new_name}./g' "
                            f"{resolved_file}"
                        ),
                    },
                ))
                continue

            continue  # IMPORT node with no meaningful change

        # Name changes → rename edit (FUNCTION, CLASS, FIELD, PARAMETER, etc.)
        old_name = nc.old_attrs.get("name")
        new_name = nc.attrs.get("name")
        if old_name and new_name and old_name != new_name:
            details: dict[str, Any] = {
                "old_name": old_name,
                "new_name": new_name,
                "node_type": nc.node_type.value,
            }
            if resolved_line and resolved_file != "unknown":
                details["command"] = (
                    f"sed -i "
                    f"'{resolved_line}s/\\<{old_name}\\>/{new_name}/g' "
                    f"{resolved_file}"
                )
            edits.append(EditInstruction(
                edit_type="rename",
                file=resolved_file,
                line=resolved_line,
                details=details,
            ))
            continue

        # Callee changes → update_call edit (CALL nodes)
        old_callee = nc.old_attrs.get("callee")
        new_callee = nc.attrs.get("callee")
        if old_callee and new_callee and old_callee != new_callee:
            details = {
                "old_callee": old_callee,
                "new_callee": new_callee,
            }
            if resolved_line and resolved_file != "unknown":
                details["command"] = (
                    f"sed -i "
                    f"'{resolved_line}s/\\<{old_callee}\\>/{new_callee}/g' "
                    f"{resolved_file}"
                )
            edits.append(EditInstruction(
                edit_type="update_call",
                file=resolved_file,
                line=resolved_line,
                details=details,
            ))
            continue

    # --- Edge additions: move_class/move_function (DEFINED_IN edges) ---
    for ec in changes.added_edges():
        if ec.edge_type != EdgeType.DEFINED_IN or not result_graph:
            continue

        source_node = result_graph.get_node(ec.source)
        target_node = result_graph.get_node(ec.target)

        if not source_node or source_node.node_type not in (NodeType.CLASS, NodeType.FUNCTION):
            continue
        if not target_node or target_node.node_type != NodeType.MODULE:
            continue

        item_name = source_node.attrs.get("name", "unknown")
        source_file = source_node.attrs.get("file")
        start_line = source_node.attrs.get("line")
        end_line = source_node.attrs.get("end_line")
        target_file = target_node.attrs.get("file")

        # Infer target file from source directory if not available
        if not target_file or target_file == "unknown":
            if source_file:
                source_dir = str(Path(source_file).parent)
                target_mod_name = target_node.attrs.get("name", "unknown")
                target_file = f"{source_dir}/{target_mod_name}.py"

        if not (source_file and start_line and end_line and target_file):
            continue

        # Skip if item is already in the target file
        if source_file == target_file:
            continue

        is_class = source_node.node_type == NodeType.CLASS
        edit_type = "move_class" if is_class else "move_function"
        name_key = "class_name" if is_class else "function_name"

        edits.append(EditInstruction(
            edit_type=edit_type,
            file=source_file,
            line=start_line,
            details={
                name_key: item_name,
                "source_file": source_file,
                "target_file": target_file,
                "start_line": start_line,
                "end_line": end_line,
                "copy_command": (
                    f"echo '' >> {target_file} && "
                    f"sed -n '{start_line},{end_line}p' "
                    f"{source_file} >> {target_file}"
                ),
                "delete_command": (
                    f"sed -i '{start_line},{end_line}d' {source_file}"
                ),
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
    pipeline_error: str | None = None  # set on first step failure

    for i, step in enumerate(steps):
        try:
            op_type = resolve_operator(step.operator)
        except ValueError as e:
            pipeline_error = f"Step {i + 1}: {e}"
            print_error(pipeline_error)
            break

        rules = engine.catalog.create_rules(op_type, step.params)

        all_edits: list[EditInstruction] = []
        total_applications = 0
        all_results: list[Any] = []
        any_graph_changes = False
        step_failed = False

        for rule in rules:
            if step.repeat == "all":
                results = engine.apply_all_matches(rule, current)
                if not results:
                    continue  # this sub-rule had no matches, try next

                for r in results:
                    if not r.success:
                        msg = r.errors[0] if r.errors else "Unknown error"
                        pipeline_error = f"Step {i + 1} ({step.operator}): {msg}"
                        print_error(pipeline_error)
                        step_failed = True
                        break
                    if r.changes:
                        all_edits.extend(
                            edits_from_changes(r.changes, r.result_graph, rule.name, rule.parameters)
                        )
                        if r.changes.node_changes or r.changes.edge_changes:
                            any_graph_changes = True
                    current = r.result_graph
                if step_failed:
                    break
                total_applications += len(results)
                all_results.extend(results)
            else:
                result = engine.apply_rule(rule, current)
                if not result.success:
                    if len(rules) > 1:
                        continue  # this sub-rule didn't match, try next
                    # update_import with 'names' creates one rule per name;
                    # if a name has no imports, skip it instead of failing.
                    if step.operator == "update_import" and step.params.get("names"):
                        continue
                    msg = result.errors[0] if result.errors else "Unknown error"
                    pipeline_error = f"Step {i + 1} ({step.operator}): {msg}"
                    print_error(pipeline_error)
                    step_failed = True
                    break

                if result.changes:
                    step_edits = edits_from_changes(
                        result.changes, result.result_graph, rule.name, rule.parameters
                    )
                    all_edits.extend(step_edits)
                    if result.changes.node_changes or result.changes.edge_changes:
                        any_graph_changes = True
                current = result.result_graph
                total_applications += 1
                all_results.append(result)

        if step_failed:
            break

        if total_applications == 0:
            # update_import with 'names' is best-effort: if no imports match
            # the specified names, that's fine — the moved items may not have
            # been imported by any other file.  Warn instead of failing so the
            # pipeline's earlier move commands are still usable.
            if step.operator == "update_import" and step.params.get("names"):
                err_console.print(
                    f"  [yellow]Warning: Step {i + 1} ({step.operator}) "
                    f"found no imports to update for "
                    f"names={step.params['names']}[/yellow]"
                )
            else:
                pipeline_error = f"Step {i + 1} ({step.operator}): No matches found"
                print_error(pipeline_error)
                break

        # Deduplicate edits: multiple IMPORT nodes on the same line produce
        # identical edit instructions (e.g., 10 names in one multi-line import).
        seen: set[tuple] = set()
        unique_edits: list[dict[str, Any]] = []
        for e in all_edits:
            d = e.to_dict()
            key = (d.get("type"), d.get("file"), d.get("line"), json.dumps(d, sort_keys=True))
            if key not in seen:
                seen.add(key)
                unique_edits.append(d)

        step_result: dict[str, Any] = {
            "step": i + 1,
            "operator": step.operator,
            "params": step.params,
            "edits": unique_edits,
        }
        if step.repeat == "all":
            step_result["applications"] = total_applications
        step_results.append(step_result)

        n_edits = len(step_result["edits"])
        if verbose:
            err_console.print(
                f"  [dim]Step {i + 1}/{len(steps)}: {step.operator} -> {n_edits} edits[/dim]"
            )
        if n_edits == 0:
            if any_graph_changes:
                pipeline_error = (
                    f"Step {i + 1} ({step.operator}): Graph was modified but "
                    f"produced 0 file edits — this operator is not yet supported "
                    f"for edit generation"
                )
                print_error(pipeline_error)
                break
            err_console.print(
                f"  [yellow]Warning: Step {i + 1} ({step.operator}) "
                f"produced 0 edits — verify operator targets exist in the graph[/yellow]"
            )

    # Phase 4: Post-pipeline invariant verification (differential)
    # Only report violations INTRODUCED by the transformation, not pre-existing ones.
    # Skip verification if the pipeline already failed (partial transform).
    new_errors: list[Any] = []
    new_warnings: list[Any] = []

    if not pipeline_error:
        original_violations = verify_graph_invariants(graph)
        original_keys = {(v.invariant_name, v.node_id, v.message) for v in original_violations}

        final_violations = verify_graph_invariants(current)
        new_violations = [
            v for v in final_violations
            if (v.invariant_name, v.node_id, v.message) not in original_keys
        ]

        new_errors = [v for v in new_violations if v.severity == InvariantSeverity.ERROR]
        new_warnings = [v for v in new_violations if v.severity == InvariantSeverity.WARNING]

        if verbose and new_violations:
            for v in new_violations:
                tag = "red" if v.severity == InvariantSeverity.ERROR else "yellow"
                err_console.print(f"  [{tag}]{v.severity.value}: {v.message}[/{tag}]")
                if v.fix_hint:
                    err_console.print(f"    [dim]Hint: {v.fix_hint}[/dim]")

        if new_errors:
            err_console.print(
                f"\n[red bold]Plan verification failed: "
                f"{len(new_errors)} new error(s) introduced by this transformation[/red bold]"
            )
            for v in new_errors:
                err_console.print(f"  [red]- {v.invariant_name}: {v.message}[/red]")
                if v.fix_hint:
                    err_console.print(f"    [dim]Hint: {v.fix_hint}[/dim]")
            sys.exit(1)

    # Phase 5: Output
    total_edits = sum(len(s["edits"]) for s in step_results)

    # Collect all concrete commands into a flat list for easy agent consumption.
    # Ordering: copy commands (move_class) → import/other commands → delete
    # commands (move_class, reverse line order to preserve line numbers).
    copy_commands: list[str] = []
    other_commands: list[str] = []
    delete_commands: list[tuple[int, str]] = []  # (start_line, command)

    for sr in step_results:
        for ed in sr["edits"]:
            if ed.get("type") in ("move_class", "move_function"):
                copy_cmd = ed.get("copy_command")
                del_cmd = ed.get("delete_command")
                if copy_cmd:
                    copy_commands.append(copy_cmd)
                if del_cmd:
                    delete_commands.append((ed.get("start_line", 0), del_cmd))
            else:
                cmd = ed.get("command")
                if cmd:
                    other_commands.append(cmd)

    all_commands: list[str] = copy_commands + other_commands
    # Delete commands in reverse line order (highest first) so line numbers
    # stay valid as we delete from bottom to top.
    for _, cmd in sorted(delete_commands, key=lambda x: -x[0]):
        all_commands.append(cmd)

    # Detect stdlib module shadowing: warn if any move_class targets a
    # module name that matches a Python stdlib module.
    hints: list[str] = []
    try:
        _stdlib_names = sys.stdlib_module_names  # Python 3.10+
    except AttributeError:
        _stdlib_names = {
            "warnings", "logging", "types", "collections", "io", "os", "sys",
            "json", "re", "abc", "typing", "copy", "csv", "email", "html",
            "http", "test", "time", "code", "string", "signal", "secrets",
        }
    _seen_shadow_modules: set[str] = set()
    for sr in step_results:
        for ed in sr["edits"]:
            if ed.get("type") in ("move_class", "move_function"):
                target_file = ed.get("target_file", "")
                mod_name = Path(target_file).stem if target_file else ""
                if mod_name in _stdlib_names and mod_name not in _seen_shadow_modules:
                    _seen_shadow_modules.add(mod_name)
                    hints.append(
                        f"Module '{mod_name}' shadows Python stdlib '{mod_name}'. "
                        f"Files in the same package that use 'import {mod_name}' "
                        f"for the stdlib module must alias it: "
                        f"'import {mod_name} as _stdlib_{mod_name}' and update "
                        f"stdlib usages to use the alias."
                    )

    output_data: dict[str, Any] = {
        "steps": step_results,
        "summary": {
            "total_steps": len(step_results),
            "total_edits": total_edits,
        },
    }
    if all_commands:
        output_data["commands"] = all_commands
    if hints:
        output_data["hints"] = hints

    if new_warnings:
        output_data["warnings"] = [v.to_dict() for v in new_warnings]

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
