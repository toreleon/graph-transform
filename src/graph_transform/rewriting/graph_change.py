"""
Graph Change Records

Structured records of changes made during pushout construction.
Captured at rewrite time by the PushoutEngine, eliminating the need
for post-hoc graph diffing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from graph_transform.core.typed_graph import EdgeType, NodeType


class ChangeType(Enum):
    """Types of changes made during rewriting."""

    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    ADD_EDGE = "add_edge"
    REMOVE_EDGE = "remove_edge"
    UPDATE_ATTRS = "update_attrs"


@dataclass
class NodeChange:
    """Record of a node added, removed, or modified during rewriting."""

    change_type: ChangeType
    node_id: str
    node_type: NodeType
    attrs: dict[str, Any] = field(default_factory=dict)
    old_attrs: dict[str, Any] | None = None  # For UPDATE_ATTRS only
    host_node_id: str | None = None  # The ID in the result graph

    def to_dict(self) -> dict[str, Any]:
        result = {
            "change_type": self.change_type.value,
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "attrs": self.attrs,
        }
        if self.old_attrs is not None:
            result["old_attrs"] = self.old_attrs
        if self.host_node_id is not None:
            result["host_node_id"] = self.host_node_id
        return result


@dataclass
class EdgeChange:
    """Record of an edge added or removed during rewriting."""

    change_type: ChangeType  # ADD_EDGE or REMOVE_EDGE
    source: str
    target: str
    edge_type: EdgeType
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type.value,
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "attrs": self.attrs,
        }


@dataclass
class GraphChangeSet:
    """All changes from a single rule application.

    Captured by the PushoutEngine during _apply_dpo / _apply_spo.
    Each field is populated in the same order as the pushout steps.
    """

    node_changes: list[NodeChange] = field(default_factory=list)
    edge_changes: list[EdgeChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.node_changes or self.edge_changes)

    def added_nodes(self) -> list[NodeChange]:
        return [c for c in self.node_changes if c.change_type == ChangeType.ADD_NODE]

    def removed_nodes(self) -> list[NodeChange]:
        return [c for c in self.node_changes if c.change_type == ChangeType.REMOVE_NODE]

    def updated_nodes(self) -> list[NodeChange]:
        return [c for c in self.node_changes if c.change_type == ChangeType.UPDATE_ATTRS]

    def added_edges(self) -> list[EdgeChange]:
        return [c for c in self.edge_changes if c.change_type == ChangeType.ADD_EDGE]

    def removed_edges(self) -> list[EdgeChange]:
        return [c for c in self.edge_changes if c.change_type == ChangeType.REMOVE_EDGE]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_changes": [c.to_dict() for c in self.node_changes],
            "edge_changes": [c.to_dict() for c in self.edge_changes],
        }
