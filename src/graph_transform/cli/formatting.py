"""
Rich Output Formatting

Centralized Rich console helpers for all CLI subcommands.
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from graph_transform.core.typed_graph import NodeType, TypedGraph
from graph_transform.rewriting.invariants import InvariantSeverity, InvariantViolation

console = Console()
err_console = Console(stderr=True)


# =============================================================================
# Primitive and Composition listing
# =============================================================================


def print_primitives_table(
    primitives: list[str],
    descriptions: dict[str, str],
) -> None:
    """Print a Rich table of primitives."""
    table = Table(
        title="Primitives",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Primitive", style="bold white", min_width=15)
    table.add_column("Description", style="white")

    for prim in primitives:
        desc = descriptions.get(prim, "")
        table.add_row(prim, desc)

    console.print(table)


def print_compositions_table(
    compositions: list[str],
    descriptions: dict[str, str],
) -> None:
    """Print a Rich table of compositions."""
    table = Table(
        title="Compositions",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Composition", style="bold white", min_width=18)
    table.add_column("Description", style="white")

    for comp in compositions:
        desc = descriptions.get(comp, "")
        table.add_row(comp, desc)

    console.print(table)


def print_primitive_params(name: str, params: dict[str, str]) -> None:
    """Print parameters for a primitive."""
    table = Table(
        title=f"Parameters: {name}",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Parameter", style="bold yellow", min_width=15)
    table.add_column("Description", style="white")

    for param, desc in params.items():
        table.add_row(param, desc)

    console.print(table)


def print_composition_params(name: str, params: dict[str, str]) -> None:
    """Print parameters for a composition."""
    table = Table(
        title=f"Parameters: {name}",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Parameter", style="bold yellow", min_width=20)
    table.add_column("Description", style="white")

    for param, desc in params.items():
        table.add_row(param, desc)

    console.print(table)


# =============================================================================
# Graph summary
# =============================================================================


def print_graph_summary(graph: TypedGraph, title: str = "Graph Summary") -> None:
    """Print a panel with node/edge counts by type."""
    # Node counts by type
    node_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        key = node.node_type.value
        node_counts[key] = node_counts.get(key, 0) + 1

    # Edge counts by type
    edge_counts: dict[str, int] = {}
    for edge in graph.edges:
        key = edge.edge_type.value
        edge_counts[key] = edge_counts.get(key, 0) + 1

    lines = [
        f"[bold]Nodes:[/bold] {graph.node_count} total",
    ]
    for ntype, count in sorted(node_counts.items()):
        lines.append(f"  {ntype}: {count}")

    lines.append(f"\n[bold]Edges:[/bold] {graph.edge_count} total")
    for etype, count in sorted(edge_counts.items()):
        lines.append(f"  {etype}: {count}")

    console.print(Panel("\n".join(lines), title=title, border_style="blue"))


# =============================================================================
# Primitive and Composition results
# =============================================================================


def print_primitive_result(
    result: Any,  # PrimitiveResult
    verbose: bool = False,
) -> None:
    """Print the result of a primitive operation."""
    if result.success:
        print_success(f"Primitive '{result.primitive_kind.value}' executed successfully.")
        if result.affected_ids and verbose:
            console.print(f"  Affected IDs: {', '.join(result.affected_ids)}")
        if result.metadata and verbose:
            console.print(f"  Metadata: {json.dumps(result.metadata, indent=2)}")
    else:
        print_error(f"Primitive '{result.primitive_kind.value}' failed.")
        if result.error:
            err_console.print(f"  [red]{result.error}[/red]")


def print_composition_result(
    result: Any,  # CompositionResult
    verbose: bool = False,
) -> None:
    """Print the result of a composition operation."""
    if result.success:
        print_success(f"Composition '{result.composition_name}' executed successfully.")
        if verbose:
            console.print(f"  Primitives executed: {len(result.primitive_results)}")
            if result.affected_ids:
                console.print(f"  Affected IDs: {', '.join(result.affected_ids)}")
    else:
        print_error(f"Composition '{result.composition_name}' failed.")
        if result.error:
            err_console.print(f"  [red]{result.error}[/red]")
        if result.primitive_results and verbose:
            console.print(f"  Primitives completed: {len(result.primitive_results)}")


def format_primitive_result_json(result: Any) -> dict[str, Any]:
    """Format a PrimitiveResult as JSON-serializable dict."""
    return {
        "success": result.success,
        "primitive_kind": result.primitive_kind.value,
        "affected_ids": result.affected_ids,
        "error": result.error,
        "metadata": result.metadata,
    }


def format_composition_result_json(result: Any) -> dict[str, Any]:
    """Format a CompositionResult as JSON-serializable dict."""
    return {
        "success": result.success,
        "composition_name": result.composition_name,
        "affected_ids": result.affected_ids,
        "error": result.error,
        "primitive_count": len(result.primitive_results),
        "primitives": [
            format_primitive_result_json(pr)
            for pr in result.primitive_results
        ],
        "metadata": result.metadata,
    }


# =============================================================================
# Invariant violations
# =============================================================================


def print_violations(violations: list[InvariantViolation]) -> None:
    """Print invariant violations as a Rich table."""
    if not violations:
        print_success("No violations found.")
        return

    table = Table(
        show_header=True,
        header_style="bold red",
        border_style="red",
    )
    table.add_column("Severity", style="bold", min_width=8)
    table.add_column("Layer", style="cyan", min_width=10)
    table.add_column("Invariant", style="yellow", min_width=20)
    table.add_column("Message", style="white")
    table.add_column("Node", style="dim")
    table.add_column("Fix Hint", style="green dim")

    for v in violations:
        sev_style = {
            InvariantSeverity.ERROR: "red",
            InvariantSeverity.WARNING: "yellow",
            InvariantSeverity.INFO: "blue",
        }.get(v.severity, "white")
        table.add_row(
            Text(v.severity.value.upper(), style=sev_style),
            v.layer.name.lower() if hasattr(v, "layer") else "",
            v.invariant_name,
            v.message,
            v.node_id or "",
            v.fix_hint or "",
        )

    console.print(table)


# =============================================================================
# Graph tree
# =============================================================================


def print_graph_tree(graph: TypedGraph) -> None:
    """Print graph structure as a Rich tree."""
    tree = Tree("[bold blue]Graph[/bold blue]")

    # Group by type
    by_type: dict[NodeType, list[str]] = {}
    for node in graph.nodes.values():
        by_type.setdefault(node.node_type, []).append(
            f"{node.id} ({node.attrs.get('name', '')})"
        )

    for ntype in NodeType:
        nodes = by_type.get(ntype, [])
        if nodes:
            branch = tree.add(f"[bold]{ntype.value}[/bold] ({len(nodes)})")
            for n in nodes:
                branch.add(n)

    console.print(tree)


# =============================================================================
# Status messages
# =============================================================================


def print_success(message: str) -> None:
    err_console.print(f"[bold green]OK[/bold green] {message}")


def print_error(message: str) -> None:
    err_console.print(f"[bold red]ERROR[/bold red] {message}")


def print_warning(message: str) -> None:
    err_console.print(f"[bold yellow]WARN[/bold yellow] {message}")
