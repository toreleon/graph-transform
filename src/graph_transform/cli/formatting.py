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

from graph_transform.core.typed_graph import EdgeType, NodeType, TypedGraph
from graph_transform.operators.primitive_operators import OperatorType
from graph_transform.rewriting.invariants import InvariantViolation
from graph_transform.rewriting.production_rule import RewriteResult

console = Console()
err_console = Console(stderr=True)


# =============================================================================
# Operator listing
# =============================================================================


def print_operator_table(
    operators: list[OperatorType],
    descriptions: dict[OperatorType, str],
    category: str = "",
) -> None:
    """Print a Rich table of operators."""
    table = Table(
        title=f"Operators: {category}" if category else "All Operators",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Operator", style="bold white", min_width=25)
    table.add_column("Category", style="yellow", min_width=12)
    table.add_column("Description", style="white")

    for op in operators:
        cat = _operator_category(op)
        desc = descriptions.get(op, "")
        table.add_row(op.value, cat, desc)

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
# Rewrite result
# =============================================================================


def print_rewrite_result(result: RewriteResult, verbose: bool = False) -> None:
    """Print the result of an apply/dry-run operation."""
    if result.success:
        print_success(f"Rule '{result.rule_name}' applied successfully.")
        if result.result_graph and verbose:
            print_graph_summary(result.result_graph, title="Result Graph")
    else:
        print_error(f"Rule '{result.rule_name}' failed.")
        for err in result.errors:
            err_console.print(f"  [red]{err}[/red]")

    if result.pre_violations and verbose:
        console.print("\n[bold]Pre-condition violations:[/bold]")
        print_violations(result.pre_violations)

    if result.post_violations and verbose:
        console.print("\n[bold]Post-condition violations:[/bold]")
        print_violations(result.post_violations)


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
    table.add_column("Invariant", style="yellow", min_width=20)
    table.add_column("Message", style="white")
    table.add_column("Node", style="dim")

    for v in violations:
        sev_style = "red" if v.severity == "error" else "yellow"
        table.add_row(
            Text(v.severity.upper(), style=sev_style),
            v.invariant_name,
            v.message,
            v.node_id or "",
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


# =============================================================================
# Helpers
# =============================================================================


def _operator_category(op: OperatorType) -> str:
    """Return the category string for an operator."""
    if op in OperatorType.method_operators():
        return "method"
    if op in OperatorType.field_operators():
        return "field"
    if op in OperatorType.class_operators():
        return "class"
    if op in OperatorType.param_operators():
        return "param"
    if op in OperatorType.module_operators():
        return "module"
    if op in OperatorType.reference_operators():
        return "reference"
    if op in OperatorType.call_site_operators():
        return "call_site"
    return "other"
