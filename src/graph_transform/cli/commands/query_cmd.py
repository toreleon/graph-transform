"""
query -- Query the graph for node IDs and structure.

Helps agents discover correct node IDs before using compositions like MOVE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from graph_transform.io.builder import build_graph_from_files, build_graph_from_source


@click.command("query")
@click.argument("source_path", required=False)
@click.option("--stdin", "stdin_flag", is_flag=True, help="Read file paths from stdin")
@click.option("--files", "-f", multiple=True, help="Specific files to include")
@click.option("--modules", is_flag=True, help="List all module node IDs")
@click.option("--functions", is_flag=True, help="List all function node IDs")
@click.option("--classes", is_flag=True, help="List all class node IDs")
@click.option("--find", "-F", help="Find nodes matching a pattern (e.g., 'resolve_all')")
@click.option("--edges-for", "-e", help="Show edges for a specific node ID")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def query_cmd(
    source_path: str | None,
    stdin_flag: bool,
    files: tuple[str, ...],
    modules: bool,
    functions: bool,
    classes: bool,
    find: str | None,
    edges_for: str | None,
    json_output: bool,
) -> None:
    """Query the graph for node IDs and structure.

    Examples:

    \b
    # List all modules in a directory
    graph-transform query . --modules

    \b
    # Find nodes containing 'resolve_all'
    graph-transform query . --find resolve_all

    \b
    # Show edges for a specific node
    graph-transform query . --edges-for "func:resolve_all"

    \b
    # Query files from grep results
    grep -rl 'resolve_all' . | graph-transform query --stdin --find resolve_all
    """
    # Build graph
    graph = _build_graph(source_path, files, stdin_flag)

    results: dict = {}

    # List modules
    if modules:
        mod_ids = [
            {"id": node_id, "file": node.attrs.get("file", ""), "name": node.attrs.get("name", "")}
            for node_id, node in graph.nodes.items()
            if node_id.startswith("module:")
        ]
        results["modules"] = mod_ids
        if not json_output:
            click.echo("=== MODULES ===")
            for m in mod_ids:
                click.echo(f"  {m['id']}")
                click.echo(f"    file: {m['file']}")

    # List functions
    if functions:
        func_ids = [
            {"id": node_id, "file": node.attrs.get("file", ""), "line": node.attrs.get("line")}
            for node_id, node in graph.nodes.items()
            if node_id.startswith("func:")
        ]
        results["functions"] = func_ids
        if not json_output:
            click.echo("=== FUNCTIONS ===")
            for f in func_ids:
                click.echo(f"  {f['id']} ({f['file']}:{f['line']})")

    # List classes
    if classes:
        cls_ids = [
            {"id": node_id, "file": node.attrs.get("file", ""), "line": node.attrs.get("line")}
            for node_id, node in graph.nodes.items()
            if node_id.startswith("class:")
        ]
        results["classes"] = cls_ids
        if not json_output:
            click.echo("=== CLASSES ===")
            for c in cls_ids:
                click.echo(f"  {c['id']} ({c['file']}:{c['line']})")

    # Find nodes matching pattern
    if find:
        matching = []
        for node_id, node in graph.nodes.items():
            name = node.attrs.get("name") or ""
            if find.lower() in node_id.lower() or find.lower() in name.lower():
                matching.append({
                    "id": node_id,
                    "type": node.node_type.value,
                    "file": node.attrs.get("file", ""),
                    "line": node.attrs.get("line"),
                    "name": name,
                })
        results["matching"] = matching
        if not json_output:
            click.echo(f"=== NODES MATCHING '{find}' ===")
            for m in matching:
                loc = f"{m['file']}:{m['line']}" if m['line'] else m['file']
                click.echo(f"  {m['id']} ({m['type']}) - {loc}")

    # Show edges for a node
    if edges_for:
        node = graph.get_node(edges_for)
        if not node:
            click.echo(f"Node not found: {edges_for}", err=True)
            sys.exit(1)

        incoming = [
            {"source": e.source, "type": e.edge_type.value}
            for e in graph.get_edges_to(edges_for)
        ]
        outgoing = [
            {"target": e.target, "type": e.edge_type.value}
            for e in graph.get_edges_from(edges_for)
        ]

        results["node"] = {
            "id": edges_for,
            "attrs": node.attrs,
            "incoming_edges": incoming,
            "outgoing_edges": outgoing,
        }

        if not json_output:
            click.echo(f"=== NODE: {edges_for} ===")
            click.echo(f"  attrs: {node.attrs}")
            click.echo("  incoming edges:")
            for e in incoming:
                click.echo(f"    {e['type']}: {e['source']} -> {edges_for}")
            click.echo("  outgoing edges:")
            for e in outgoing:
                click.echo(f"    {e['type']}: {edges_for} -> {e['target']}")

    # Default: show summary
    if not any([modules, functions, classes, find, edges_for]):
        summary = {
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "modules": len([n for n in graph.nodes if n.startswith("module:")]),
            "functions": len([n for n in graph.nodes if n.startswith("func:")]),
            "classes": len([n for n in graph.nodes if n.startswith("class:")]),
        }
        results["summary"] = summary
        if not json_output:
            click.echo("=== GRAPH SUMMARY ===")
            click.echo(f"  Total nodes: {summary['total_nodes']}")
            click.echo(f"  Total edges: {summary['total_edges']}")
            click.echo(f"  Modules: {summary['modules']}")
            click.echo(f"  Functions: {summary['functions']}")
            click.echo(f"  Classes: {summary['classes']}")
            click.echo("\nUse --modules, --functions, --classes, --find, or --edges-for for details")

    if json_output:
        click.echo(json.dumps(results, indent=2))


def _build_graph(
    source_path: str | None,
    files: tuple[str, ...],
    stdin_flag: bool,
):
    """Build graph from source."""
    file_list: list[str] = []

    if stdin_flag:
        if source_path or files:
            click.echo("Cannot use --stdin with SOURCE_PATH or --files", err=True)
            sys.exit(2)
        for line in sys.stdin:
            line = line.strip()
            if line and line.endswith(".py"):
                file_list.append(line)
        if not file_list:
            click.echo("No Python files provided via stdin", err=True)
            sys.exit(2)
    elif files:
        if source_path:
            click.echo("Cannot use SOURCE_PATH with --files", err=True)
            sys.exit(2)
        file_list = list(files)
    elif source_path:
        pass
    else:
        click.echo("Must provide SOURCE_PATH, --files, or --stdin", err=True)
        sys.exit(2)

    try:
        if file_list:
            return build_graph_from_files(file_list)
        else:
            return build_graph_from_source(source_path)
    except (FileNotFoundError, SyntaxError, ValueError) as e:
        click.echo(f"ERROR {e}", err=True)
        sys.exit(1)
