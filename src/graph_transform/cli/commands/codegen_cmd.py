"""
codegen -- Generate structured edit instructions from graph diff.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import click

from graph_transform.cli.formatting import print_error, print_success, err_console
from graph_transform.core.graph_diff import diff_graphs, NodeChange, EdgeChange, GraphDiff
from graph_transform.core.typed_graph import NodeType, EdgeType
from graph_transform.io.serialization import load_graph


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


def _find_parent_function(node_id: str, after_graph, before_graph, edge_changes: list[EdgeChange]) -> dict | None:
    """Find the parent function for a parameter/argument node."""
    # Look for HAS_PARAMETER or HAS_ARGUMENT edge pointing to this node
    for edge in edge_changes:
        if edge.change_type == "added" and edge.target == node_id:
            if edge.edge_type in (EdgeType.HAS_PARAMETER, EdgeType.HAS_ARGUMENT):
                parent = after_graph.get_node(edge.source) or before_graph.get_node(edge.source)
                if parent:
                    return {
                        "id": edge.source,
                        "name": parent.attrs.get("name") or parent.attrs.get("callee"),
                        "type": parent.node_type.value,
                        "file": parent.attrs.get("file"),
                        "line": parent.attrs.get("line"),
                    }
    return None


def _extract_location_from_node_id(node_id: str) -> tuple[str | None, int | None]:
    """Extract file and line from node ID."""
    # Pattern: type:file:line:col
    parts = node_id.split(":")
    if len(parts) >= 3:
        # Find numeric parts from the end
        try:
            for i in range(len(parts) - 1, 1, -1):
                if parts[i].isdigit():
                    file_path = ":".join(parts[1:i])
                    line = int(parts[i])
                    return file_path, line
        except (ValueError, IndexError):
            pass
    return None, None


def generate_edits(diff: GraphDiff, before_graph, after_graph) -> list[EditInstruction]:
    """Convert graph diff to structured edit instructions."""
    edits = []
    
    for change in diff.added_nodes():
        node_type = change.node_type
        
        if node_type == NodeType.PARAMETER:
            # Find parent function
            parent = _find_parent_function(change.node_id, after_graph, before_graph, diff.edge_changes)
            parent_file, parent_line = None, None
            if parent:
                parent_file = parent.get("file")
                parent_line = parent.get("line")
                if not parent_file:
                    parent_file, parent_line = _extract_location_from_node_id(parent["id"])
            
            edits.append(EditInstruction(
                edit_type="add_parameter",
                file=parent_file or change.file or "unknown",
                line=parent_line or change.line,
                details={
                    "function": parent["name"] if parent else "unknown",
                    "parameter": {
                        "name": change.attrs.get("name"),
                        "default": change.attrs.get("default_value"),
                        "has_default": change.attrs.get("has_default", False),
                    }
                }
            ))
        
        elif node_type == NodeType.ARGUMENT:
            # Find parent call
            parent = _find_parent_function(change.node_id, after_graph, before_graph, diff.edge_changes)
            parent_file, parent_line = None, None
            if parent:
                parent_file = parent.get("file")
                parent_line = parent.get("line")
                if not parent_file:
                    parent_file, parent_line = _extract_location_from_node_id(parent["id"])
            
            edits.append(EditInstruction(
                edit_type="add_argument",
                file=parent_file or change.file or "unknown",
                line=parent_line or change.line,
                details={
                    "call": parent["name"] if parent else "unknown",
                    "argument": {
                        "name": change.attrs.get("name"),
                        "value": change.attrs.get("value"),
                        "is_keyword": change.attrs.get("is_keyword", True),
                    }
                }
            ))
        
        elif node_type == NodeType.FUNCTION:
            file = change.file or change.attrs.get("file") or "unknown"
            edits.append(EditInstruction(
                edit_type="add_method" if change.attrs.get("is_method") else "add_function",
                file=file,
                line=change.line or change.attrs.get("line"),
                details={
                    "name": change.attrs.get("name"),
                    "is_async": change.attrs.get("is_async", False),
                }
            ))
        
        elif node_type == NodeType.CLASS:
            file = change.file or change.attrs.get("file") or "unknown"
            edits.append(EditInstruction(
                edit_type="add_class",
                file=file,
                line=change.line or change.attrs.get("line"),
                details={
                    "name": change.attrs.get("name"),
                }
            ))
        
        elif node_type == NodeType.FIELD:
            file = change.file or change.attrs.get("file") or "unknown"
            edits.append(EditInstruction(
                edit_type="add_field",
                file=file,
                line=change.line or change.attrs.get("line"),
                details={
                    "class": change.attrs.get("class_name"),
                    "name": change.attrs.get("name"),
                    "default": change.attrs.get("default_value"),
                }
            ))
    
    # Handle removed nodes
    for change in diff.removed_nodes():
        file = change.file or change.attrs.get("file") or "unknown"
        line = change.line or change.attrs.get("line")
        
        edit_type_map = {
            NodeType.PARAMETER: "remove_parameter",
            NodeType.ARGUMENT: "remove_argument",
            NodeType.FUNCTION: "remove_function",
            NodeType.CLASS: "remove_class",
            NodeType.FIELD: "remove_field",
        }
        
        if change.node_type in edit_type_map:
            edits.append(EditInstruction(
                edit_type=edit_type_map[change.node_type],
                file=file,
                line=line,
                details={
                    "name": change.attrs.get("name") or change.attrs.get("callee"),
                }
            ))
    
    # Handle modified nodes (e.g., renames)
    for change in diff.modified_nodes():
        old_name = change.old_attrs.get("name") if change.old_attrs else None
        new_name = change.attrs.get("name")
        
        if old_name and new_name and old_name != new_name:
            file = change.file or change.attrs.get("file") or "unknown"
            edits.append(EditInstruction(
                edit_type="rename",
                file=file,
                line=change.line or change.attrs.get("line"),
                details={
                    "old_name": old_name,
                    "new_name": new_name,
                    "node_type": change.node_type.value,
                }
            ))
    
    return edits


@click.command("codegen")
@click.argument("before_graph", type=click.Path(exists=True))
@click.argument("after_graph", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file for edit plan (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output.")
def codegen(
    before_graph: str,
    after_graph: str,
    output: str | None,
    verbose: bool,
) -> None:
    """Generate structured edit instructions from graph diff.
    
    Compares BEFORE_GRAPH and AFTER_GRAPH to produce a JSON plan
    of code edits that can be applied by a coding agent.
    
    Example:
    
        graph-transform codegen graph.json result.json -o plan.json
    """
    try:
        before = load_graph(before_graph)
        after = load_graph(after_graph)
    except (FileNotFoundError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)
    
    diff = diff_graphs(before, after)
    
    if not diff.has_changes:
        if verbose:
            err_console.print("[dim]No changes detected between graphs[/dim]")
        result = {"description": "No changes", "edits": []}
    else:
        edits = generate_edits(diff, before, after)
        
        if verbose:
            err_console.print(f"[dim]Found {len(diff.node_changes)} node changes, {len(diff.edge_changes)} edge changes[/dim]")
            err_console.print(f"[dim]Generated {len(edits)} edit instructions[/dim]")
        
        result = {
            "description": f"Code edits from graph transformation",
            "summary": {
                "added_nodes": len(diff.added_nodes()),
                "removed_nodes": len(diff.removed_nodes()),
                "modified_nodes": len(diff.modified_nodes()),
            },
            "edits": [e.to_dict() for e in edits],
        }
    
    json_output = json.dumps(result, indent=2)
    
    if output:
        with open(output, "w") as f:
            f.write(json_output)
        print_success(f"Edit plan written to {output}")
    else:
        sys.stdout.write(json_output + "\n")
