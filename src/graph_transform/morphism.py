"""
Graph Morphisms

Structure-preserving maps between typed graphs.
Used in production rules (l: K -> L, r: K -> R) and match finding (m: L -> G).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .typed_graph import TypedGraph


# =============================================================================
# GraphMorphism
# =============================================================================


@dataclass
class GraphMorphism:
    """A morphism between two typed graphs.

    Maps nodes of source graph to nodes of target graph,
    preserving node types and edge structure.

    In DPO/SPO terminology:
    - m: L -> G  (match morphism)
    - l: K -> L  (LHS inclusion)
    - r: K -> R  (RHS inclusion)
    """

    node_map: dict[str, str]  # source_node_id -> target_node_id
    source: TypedGraph
    target: TypedGraph

    def is_valid(self) -> bool:
        """Check that morphism preserves node types and edge structure."""
        # All source nodes must be mapped
        for src_id, tgt_id in self.node_map.items():
            src_node = self.source.get_node(src_id)
            tgt_node = self.target.get_node(tgt_id)
            if src_node is None or tgt_node is None:
                return False
            if src_node.node_type != tgt_node.node_type:
                return False

        # Edge structure must be preserved
        for edge in self.source.edges:
            if edge.source not in self.node_map or edge.target not in self.node_map:
                continue
            mapped_source = self.node_map[edge.source]
            mapped_target = self.node_map[edge.target]
            if not self.target.has_edge(mapped_source, mapped_target, edge.edge_type):
                return False

        return True

    def is_injective(self) -> bool:
        """Check that morphism is injective (1-to-1 on nodes)."""
        values = list(self.node_map.values())
        return len(values) == len(set(values))

    def is_total(self) -> bool:
        """Check that all source nodes are mapped."""
        return all(nid in self.node_map for nid in self.source.nodes)

    def image(self) -> set[str]:
        """Return set of target node IDs in the image of this morphism."""
        return set(self.node_map.values())

    def preimage(self, target_id: str) -> list[str]:
        """Return source node IDs that map to the given target ID."""
        return [s for s, t in self.node_map.items() if t == target_id]

    def map_node(self, source_id: str) -> str | None:
        """Map a source node ID to its target ID."""
        return self.node_map.get(source_id)

    def inverse_map(self) -> dict[str, str]:
        """Return inverse mapping (target -> source). Only valid if injective."""
        return {t: s for s, t in self.node_map.items()}

    def compose(self, other: GraphMorphism) -> GraphMorphism:
        """Compose self with other: (other ∘ self).

        self: A -> B, other: B -> C  =>  result: A -> C
        """
        composed_map = {}
        for src_id, mid_id in self.node_map.items():
            if mid_id in other.node_map:
                composed_map[src_id] = other.node_map[mid_id]
        return GraphMorphism(
            node_map=composed_map,
            source=self.source,
            target=other.target,
        )

    def restrict(self, node_ids: set[str]) -> GraphMorphism:
        """Restrict morphism to a subset of source nodes."""
        restricted_map = {
            s: t for s, t in self.node_map.items() if s in node_ids
        }
        return GraphMorphism(
            node_map=restricted_map,
            source=self.source.subgraph(node_ids),
            target=self.target,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_map": self.node_map,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphMorphism:
        return cls(
            node_map=data["node_map"],
            source=TypedGraph.from_dict(data["source"]),
            target=TypedGraph.from_dict(data["target"]),
        )

    @classmethod
    def identity(cls, graph: TypedGraph) -> GraphMorphism:
        """Create an identity morphism on a graph."""
        return cls(
            node_map={nid: nid for nid in graph.nodes},
            source=graph,
            target=graph,
        )

    @classmethod
    def inclusion(cls, subgraph: TypedGraph, graph: TypedGraph) -> GraphMorphism:
        """Create an inclusion morphism from a subgraph into a graph.

        Maps each node in subgraph to the same-id node in graph.
        """
        node_map = {
            nid: nid for nid in subgraph.nodes if nid in graph.nodes
        }
        return cls(node_map=node_map, source=subgraph, target=graph)
