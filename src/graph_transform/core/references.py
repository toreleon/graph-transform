"""
Reference Tracking Module

Provides functions for finding and updating all references to code elements.
Supports FR49 (find all call sites), FR50 (find all imports), FR51 (update all references).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .typed_graph import EdgeType, TypedGraph
from .primitives.base import PrimitiveResult, PrimitiveKind, Update

if TYPE_CHECKING:
    pass


@dataclass
class ReferenceUpdateResult:
    """Result of updating references."""

    success: bool
    updated_count: int
    affected_ids: list[str] = field(default_factory=list)
    error: str | None = None


def find_all_call_sites(graph: TypedGraph, target_id: str) -> list[str]:
    """Find all call sites for a function/method.

    FR49: System finds ALL call sites for a function.

    Args:
        graph: The code graph
        target_id: The function/method node ID to find calls to

    Returns:
        List of node IDs that call the target (CALLS edges pointing to target).
        Includes both direct calls and method calls.
    """
    call_sites = []

    # Find all edges that point TO the target with CALLS edge type
    for edge in graph.get_edges_to(target_id):
        if edge.edge_type == EdgeType.CALLS:
            call_sites.append(edge.source)

    return call_sites


def find_all_import_references(graph: TypedGraph, target_id: str) -> list[str]:
    """Find all import references for a module member.

    FR50: System finds ALL import references for a module member.

    Args:
        graph: The code graph
        target_id: The function/class node ID to find imports of

    Returns:
        List of import node IDs that reference the target.
        Includes both `from module import name` style and qualified references.
    """
    import_refs = []

    # Find IMPORTS edges pointing to target
    for edge in graph.get_edges_to(target_id):
        if edge.edge_type == EdgeType.IMPORTS:
            import_refs.append(edge.source)

    # Also find REFERENCES edges from import nodes (for module.name usage)
    for edge in graph.get_edges_to(target_id):
        if edge.edge_type == EdgeType.REFERENCES:
            source_node = graph.get_node(edge.source)
            if source_node and source_node.id.startswith("import:"):
                import_refs.append(edge.source)

    return import_refs


def update_all_references(
    graph: TypedGraph,
    target: str,
    old_name: str,
    new_name: str,
) -> tuple[ReferenceUpdateResult, TypedGraph]:
    """Update all references when a target is renamed.

    FR51: System updates ALL references when target is renamed.

    Args:
        graph: The code graph
        target: The node ID being renamed
        old_name: The old name
        new_name: The new name

    Returns:
        Tuple of (result, new_graph) where new_graph has updated references.
        Original graph is NOT modified.
    """
    new_graph = graph.copy()
    affected_ids = []

    # 1. Update call sites
    call_sites = find_all_call_sites(new_graph, target)
    for call_id in call_sites:
        call_node = new_graph.get_node(call_id)
        if call_node:
            callee = call_node.attrs.get("callee", "")
            if callee == old_name or callee.endswith(f".{old_name}"):
                new_callee = callee.replace(old_name, new_name)
                call_node.attrs["callee"] = new_callee
                affected_ids.append(call_id)

    # 2. Update import statements
    import_refs = find_all_import_references(new_graph, target)
    for import_id in import_refs:
        import_node = new_graph.get_node(import_id)
        if import_node:
            import_name = import_node.attrs.get("name", "")
            if import_name == old_name:
                import_node.attrs["name"] = new_name
                affected_ids.append(import_id)

    return (
        ReferenceUpdateResult(
            success=True,
            updated_count=len(affected_ids),
            affected_ids=affected_ids,
        ),
        new_graph,
    )


def update_references_for_move(
    graph: TypedGraph,
    target: str,
    old_module: str,
    new_module: str,
) -> tuple[ReferenceUpdateResult, TypedGraph]:
    """Update all references when a target is moved between modules.

    FR51: System updates ALL references when target is moved.

    Args:
        graph: The code graph
        target: The node ID being moved
        old_module: The old module path
        new_module: The new module path

    Returns:
        Tuple of (result, new_graph) where new_graph has updated references.
        Original graph is NOT modified.
    """
    new_graph = graph.copy()
    affected_ids = []

    # Get the target node's name
    target_node = new_graph.get_node(target)
    target_name = target_node.attrs.get("name", "") if target_node else ""

    # 1. Update import paths
    import_refs = find_all_import_references(new_graph, target)
    for import_id in import_refs:
        import_node = new_graph.get_node(import_id)
        if import_node:
            import_module = import_node.attrs.get("module", "")
            if old_module in import_module:
                new_import_module = import_module.replace(old_module, new_module)
                import_node.attrs["module"] = new_import_module
                affected_ids.append(import_id)

    # 2. Update qualified call references
    call_sites = find_all_call_sites(new_graph, target)
    for call_id in call_sites:
        call_node = new_graph.get_node(call_id)
        if call_node:
            callee = call_node.attrs.get("callee", "")
            is_qualified = call_node.attrs.get("is_qualified", False)

            if is_qualified and old_module in callee:
                new_callee = callee.replace(old_module, new_module)
                call_node.attrs["callee"] = new_callee
                affected_ids.append(call_id)

    return (
        ReferenceUpdateResult(
            success=True,
            updated_count=len(affected_ids),
            affected_ids=affected_ids,
        ),
        new_graph,
    )


def find_all_references(graph: TypedGraph, target_id: str) -> dict[str, list[str]]:
    """Find all references of any type to a target node.

    Comprehensive reference finder for analysis.

    Args:
        graph: The code graph
        target_id: The node ID to find references to

    Returns:
        Dictionary mapping reference type to list of referencing node IDs:
        - "calls": Call site node IDs
        - "imports": Import node IDs
        - "inherits": Class node IDs that inherit from target
        - "references": Generic reference node IDs
    """
    refs: dict[str, list[str]] = {
        "calls": [],
        "imports": [],
        "inherits": [],
        "references": [],
    }

    for edge in graph.get_edges_to(target_id):
        if edge.edge_type == EdgeType.CALLS:
            refs["calls"].append(edge.source)
        elif edge.edge_type == EdgeType.IMPORTS:
            refs["imports"].append(edge.source)
        elif edge.edge_type == EdgeType.INHERITS:
            refs["inherits"].append(edge.source)
        elif edge.edge_type == EdgeType.REFERENCES:
            refs["references"].append(edge.source)

    return refs
