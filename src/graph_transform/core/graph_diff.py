"""
Graph Diff

Compare two TypedGraphs and extract structured differences.
Used by codegen to generate edit instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from graph_transform.core.typed_graph import TypedGraph, NodeType, EdgeType, GraphNode, GraphEdge


@dataclass
class NodeChange:
    """A change to a node."""
    change_type: str  # "added", "removed", "modified"
    node_id: str
    node_type: NodeType
    attrs: dict[str, Any]
    old_attrs: dict[str, Any] | None = None  # For modifications
    
    # Location info extracted from node
    file: str | None = None
    line: int | None = None
    col: int | None = None


@dataclass
class EdgeChange:
    """A change to an edge."""
    change_type: str  # "added", "removed"
    source: str
    target: str
    edge_type: EdgeType
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphDiff:
    """Differences between two graphs."""
    node_changes: list[NodeChange] = field(default_factory=list)
    edge_changes: list[EdgeChange] = field(default_factory=list)
    
    @property
    def has_changes(self) -> bool:
        return bool(self.node_changes or self.edge_changes)
    
    def added_nodes(self) -> list[NodeChange]:
        return [c for c in self.node_changes if c.change_type == "added"]
    
    def removed_nodes(self) -> list[NodeChange]:
        return [c for c in self.node_changes if c.change_type == "removed"]
    
    def modified_nodes(self) -> list[NodeChange]:
        return [c for c in self.node_changes if c.change_type == "modified"]


def extract_location_from_id(node_id: str) -> tuple[str | None, int | None, int | None]:
    """Extract file, line, col from node ID like 'call:test/manager.py:240:63'."""
    # Pattern: type:file:line or type:file:line:col
    parts = node_id.split(":")
    if len(parts) >= 3:
        # Rejoin file path parts (in case file has no colons, take all but first and last 1-2)
        try:
            # Find where line number starts (first numeric part from end)
            line_idx = None
            for i in range(len(parts) - 1, 0, -1):
                if parts[i].isdigit():
                    line_idx = i
                else:
                    break
            
            if line_idx and line_idx > 1:
                file_parts = parts[1:line_idx]
                file_path = ":".join(file_parts) if file_parts else None
                line = int(parts[line_idx]) if parts[line_idx].isdigit() else None
                col = int(parts[line_idx + 1]) if len(parts) > line_idx + 1 and parts[line_idx + 1].isdigit() else None
                return file_path, line, col
        except (ValueError, IndexError):
            pass
    
    return None, None, None


def extract_location_from_attrs(attrs: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    """Extract file, line, col from node attributes."""
    file = attrs.get("file")
    line = attrs.get("line")
    col = attrs.get("col") or attrs.get("column")
    return file, line, col


def diff_graphs(before: TypedGraph, after: TypedGraph) -> GraphDiff:
    """
    Compute the difference between two graphs.
    
    Returns a GraphDiff with:
    - added nodes: in after but not in before
    - removed nodes: in before but not in after
    - modified nodes: same ID but different attrs
    - added/removed edges
    """
    diff = GraphDiff()
    
    before_ids = set(before.nodes.keys())
    after_ids = set(after.nodes.keys())
    
    # Added nodes
    for node_id in after_ids - before_ids:
        node = after.get_node(node_id)
        file, line, col = extract_location_from_id(node_id)
        if not file:
            file, line, col = extract_location_from_attrs(node.attrs)
        
        diff.node_changes.append(NodeChange(
            change_type="added",
            node_id=node_id,
            node_type=node.node_type,
            attrs=node.attrs,
            file=file,
            line=line,
            col=col,
        ))
    
    # Removed nodes
    for node_id in before_ids - after_ids:
        node = before.get_node(node_id)
        file, line, col = extract_location_from_id(node_id)
        if not file:
            file, line, col = extract_location_from_attrs(node.attrs)
        
        diff.node_changes.append(NodeChange(
            change_type="removed",
            node_id=node_id,
            node_type=node.node_type,
            attrs=node.attrs,
            file=file,
            line=line,
            col=col,
        ))
    
    # Modified nodes
    for node_id in before_ids & after_ids:
        before_node = before.get_node(node_id)
        after_node = after.get_node(node_id)
        
        if before_node.attrs != after_node.attrs:
            file, line, col = extract_location_from_id(node_id)
            if not file:
                file, line, col = extract_location_from_attrs(after_node.attrs)
            
            diff.node_changes.append(NodeChange(
                change_type="modified",
                node_id=node_id,
                node_type=after_node.node_type,
                attrs=after_node.attrs,
                old_attrs=before_node.attrs,
                file=file,
                line=line,
                col=col,
            ))
    
    # Edge changes
    before_edges = {(e.source, e.target, e.edge_type) for e in before.edges}
    after_edges = {(e.source, e.target, e.edge_type) for e in after.edges}
    
    for src, tgt, etype in after_edges - before_edges:
        diff.edge_changes.append(EdgeChange(
            change_type="added",
            source=src,
            target=tgt,
            edge_type=etype,
        ))
    
    for src, tgt, etype in before_edges - after_edges:
        diff.edge_changes.append(EdgeChange(
            change_type="removed",
            source=src,
            target=tgt,
            edge_type=etype,
        ))
    
    return diff
