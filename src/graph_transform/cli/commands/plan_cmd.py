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
# MOVE parameter auto-detection
# =============================================================================


def _auto_detect_move_from_scope(
    graph: TypedGraph,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Auto-detect from_scope for MOVE composition if not provided.

    Finds the module that contains the target node by looking at CONTAINS edges.
    """
    if "from_scope" in params and params["from_scope"]:
        return params  # Already specified

    target = params.get("target", "")
    if not target:
        return params

    # Find the containing module by looking at incoming CONTAINS edges
    for edge in graph.get_edges_to(target):
        if edge.edge_type.value == "contains":
            source_node = graph.get_node(edge.source)
            if source_node and source_node.node_type.value == "module":
                result = params.copy()
                result["from_scope"] = edge.source
                return result

    # Fallback: try to infer from target's file attribute
    target_node = graph.get_node(target)
    if target_node:
        file_path = target_node.attrs.get("file", "")
        if file_path:
            # Find module with matching file
            for node_id, node in graph.nodes.items():
                if node_id.startswith("module:") and node.attrs.get("file") == file_path:
                    result = params.copy()
                    result["from_scope"] = node_id
                    return result

    return params


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
    graph: TypedGraph | None = None,
) -> tuple[list[EditInstruction], list[dict[str, Any]]]:
    """Generate edit instructions and hints from a CompositionResult.

    Returns:
        Tuple of (edits, hints) where hints are actionable suggestions
        for the agent about imports, __all__ updates, etc.
    """
    edits: list[EditInstruction] = []
    hints: list[dict[str, Any]] = []

    if not result.success:
        return edits, hints

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
        target = params.get("target", "")
        from_scope = params.get("from_scope", "")
        to_scope = params.get("to_scope", "")

        # Get the node details for generating actionable commands
        source_file = "unknown"
        target_file = "unknown"
        symbol_name = target.split(":")[-1] if ":" in target else target
        start_line = None
        end_line = None
        from_module = ""
        to_module = ""

        if graph:
            # Get source file from from_scope module
            from_node = graph.get_node(from_scope)
            if from_node:
                source_file = from_node.attrs.get("file", "unknown")
                from_module = from_node.attrs.get("name", "")

            # Get target file from to_scope module
            to_node = graph.get_node(to_scope)
            if to_node:
                target_file = to_node.attrs.get("file", "unknown")
                to_module = to_node.attrs.get("name", "")

            # Get the actual symbol name and line numbers
            target_node = graph.get_node(target)
            if target_node:
                symbol_name = target_node.attrs.get("name", symbol_name)
                start_line = target_node.attrs.get("line")
                end_line = target_node.attrs.get("end_line")

        # Generate commands list for this MOVE
        move_commands = []
        if source_file != "unknown" and target_file != "unknown" and start_line:
            # Command 1: Extract the function definition and append to target
            if end_line:
                move_commands.append(
                    f"sed -n '{start_line},{end_line}p' {source_file} >> {target_file}"
                )
                # Command 2: Delete the function from source
                move_commands.append(
                    f"sed -i '{start_line},{end_line}d' {source_file}"
                )
            else:
                # Fallback: just provide line info for manual extraction
                move_commands.append(
                    f"# Extract function '{symbol_name}' starting at line {start_line} from {source_file} to {target_file}"
                )

        # Command 3: Update imports
        if from_module and to_module:
            move_commands.append(
                f"find . -name '*.py' -exec sed -i 's/from {from_module} import {symbol_name}/from {to_module} import {symbol_name}/g' {{}} \\;"
            )

        # Command 4: Add to __all__ in target file (for Python exports)
        # Check if the symbol was exported (in __all__) in the source module
        # We check the module's __all__ attribute instead of edges since edges may have changed after MOVE
        is_exported = False
        if graph:
            from_node = graph.get_node(from_scope)
            if from_node:
                all_exports = from_node.attrs.get("__all__", [])
                is_exported = symbol_name in all_exports

        if is_exported and target_file != "unknown":
            # Add __all__ declaration with the symbol to target file
            # First check if file exists and has __all__, if not prepend it
            move_commands.append(
                f"grep -q '^__all__' {target_file} 2>/dev/null || sed -i \"1i\\\\__all__ = ('{symbol_name}')\" {target_file}"
            )

        edits.append(EditInstruction(
            edit_type="move",
            file=source_file,
            line=start_line,
            details={
                "target": target,
                "symbol_name": symbol_name,
                "from_scope": from_scope,
                "to_scope": to_scope,
                "source_file": source_file,
                "target_file": target_file,
                "start_line": start_line,
                "end_line": end_line,
                "from_module": from_module,
                "to_module": to_module,
                "command": move_commands[0] if move_commands else None,  # Primary command
                "commands": move_commands,  # All commands
            },
        ))

        # Generate hints about imports and __all__ that need updating
        if graph:
            hints.extend(_generate_move_hints(graph, target, from_scope, to_scope))

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

    elif composition_name == "UPDATE_IMPORT":
        symbol = params.get("symbol", "")
        old_module = params.get("old_module", "")
        new_module = params.get("new_module", "")

        # Generate sed command to update imports in all files
        # Handles both: from X.Y import Z  and  from X import Y
        edits.append(EditInstruction(
            edit_type="update_import",
            file="*",  # All files
            line=None,
            details={
                "symbol": symbol,
                "old_module": old_module,
                "new_module": new_module,
                "command": f"find . -name '*.py' -exec sed -i 's/from {old_module} import {symbol}/from {new_module} import {symbol}/g' {{}} \\;",
            },
        ))

    return edits, hints


def _generate_move_hints(
    graph: TypedGraph,
    target: str,
    from_scope: str,
    to_scope: str,
) -> list[dict[str, Any]]:
    """Generate hints about imports and __all__ updates needed for a MOVE.

    When moving a symbol from one module to another, this function identifies:
    1. All files that import the symbol (need import path updates)
    2. __all__ declarations that need updating
    """
    hints: list[dict[str, Any]] = []

    # Get the moved node's name
    node = graph.get_node(target)
    if not node:
        return hints

    symbol_name = node.attrs.get("name", "")
    if not symbol_name:
        return hints

    # Get source and target module info
    from_node = graph.get_node(from_scope)
    to_node = graph.get_node(to_scope)

    from_module = from_node.attrs.get("name", "") if from_node else ""
    to_module = to_node.attrs.get("name", "") if to_node else ""
    from_file = from_node.attrs.get("file", "") if from_node else ""
    to_file = to_node.attrs.get("file", "") if to_node else ""

    # Find all import nodes that reference this symbol
    import_files: list[dict[str, Any]] = []
    for node_id, imp_node in graph.nodes.items():
        if not node_id.startswith("import:"):
            continue

        imp_name = imp_node.attrs.get("name", "")
        imp_module = imp_node.attrs.get("module", "")
        imp_file = imp_node.attrs.get("file", "")

        # Check if this import brings in our symbol
        if imp_name == symbol_name:
            # Check if it's from the source module
            if from_module and from_module in imp_module:
                import_files.append({
                    "file": imp_file,
                    "line": imp_node.attrs.get("line"),
                    "current_import": f"from {imp_module} import {imp_name}",
                    "new_import": f"from {to_module} import {imp_name}" if to_module else None,
                })

    if import_files:
        hints.append({
            "type": "update_imports",
            "symbol": symbol_name,
            "from_module": from_module,
            "to_module": to_module,
            "files": import_files,
            "message": f"Update imports of '{symbol_name}' from '{from_module}' to '{to_module}' in {len(import_files)} file(s)",
        })

    # Check if symbol is exported (has EXPORTS edge from source module)
    # This is language-agnostic: Python uses __all__, JS/TS uses export, Rust uses pub, etc.
    from graph_transform.core.typed_graph import EdgeType
    is_exported = False
    for edge in graph.get_edges_to(target):
        if edge.edge_type == EdgeType.EXPORTS and edge.source == from_scope:
            is_exported = True
            break

    # Hint about export declaration updates if symbol is exported
    if is_exported and (from_file or to_file):
        hints.append({
            "type": "update_exports",
            "symbol": symbol_name,
            "from_scope": from_scope,
            "to_scope": to_scope,
            "from_file": from_file,
            "to_file": to_file,
            "message": f"Update exports: remove '{symbol_name}' from {from_file} exports, add to {to_file} exports",
        })

    return hints


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
    all_hints: list[dict[str, Any]] = []
    pipeline_error: str | None = None

    for i, step in enumerate(steps):
        step_desc = f"{step.step_type}:{step.name}"
        all_edits: list[EditInstruction] = []
        step_hints: list[dict[str, Any]] = []

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
                step_params = step.params

                # Auto-detect from_scope for MOVE if not provided
                if comp_type.upper() == "MOVE":
                    step_params = _auto_detect_move_from_scope(current, step_params)

                comp = CompositionRegistry.create(comp_type, **step_params)
                if comp is None:
                    pipeline_error = f"Step {i+1}: Failed to create composition '{comp_type}'"
                    print_error(pipeline_error)
                    break

                result = comp.execute(current)

                if not result.success:
                    pipeline_error = f"Step {i+1} ({step_desc}): {result.error}"
                    print_error(pipeline_error)
                    break

                all_edits, step_hints = edits_from_composition_result(
                    result, step.name, step_params, graph=current
                )
                all_hints.extend(step_hints)

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
        if step_hints:
            step_result["hints"] = step_hints
        step_results.append(step_result)

        if verbose:
            err_console.print(
                f"  [dim]Step {i+1}/{len(steps)}: {step_desc} -> {len(all_edits)} edits[/dim]"
            )

    # Phase 4: Output
    total_edits = sum(len(s["edits"]) for s in step_results)

    # Extract all commands from edits for easy execution
    commands: list[str] = []
    for step in step_results:
        for edit in step.get("edits", []):
            # Handle single command
            if "command" in edit and edit["command"]:
                commands.append(edit["command"])
            # Handle multiple commands (e.g., from MOVE)
            if "commands" in edit:
                for cmd in edit["commands"]:
                    if cmd and not cmd.startswith("#"):  # Skip comments
                        commands.append(cmd)

    output_data: dict[str, Any] = {
        "steps": step_results,
        "commands": commands,  # Direct list of sed/find commands to execute
        "summary": {
            "total_steps": len(step_results),
            "total_edits": total_edits,
            "total_commands": len(commands),
        },
    }

    # Add hints at top level if any were generated
    if all_hints:
        output_data["hints"] = all_hints

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
