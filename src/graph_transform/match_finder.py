"""
Match Finder

VF2-style backtracking algorithm for finding subgraph morphisms
from a pattern graph into a host graph. Used to find matches
m: L -> G for production rule application.
"""

from __future__ import annotations

from .morphism import GraphMorphism
from .typed_graph import EdgeType, GraphNode, NodeType, TypedGraph


# =============================================================================
# MatchFinder
# =============================================================================


class MatchFinder:
    """Find morphisms m: L -> G (matches of a pattern in a host graph).

    Uses a backtracking algorithm that respects node types and edge structure.
    Optimized for the practical case: patterns are small (2-10 nodes),
    host graphs are moderate (100s-1000s of nodes).
    """

    def __init__(self, host: TypedGraph):
        self.host = host
        self._type_index: dict[NodeType, list[str]] = {}
        self._build_indices()

    def _build_indices(self) -> None:
        """Build type-based index for efficient candidate lookup."""
        self._type_index.clear()
        for node_id, node in self.host.nodes.items():
            if node.node_type not in self._type_index:
                self._type_index[node.node_type] = []
            self._type_index[node.node_type].append(node_id)

    def find_matches(
        self,
        pattern: TypedGraph,
        max_matches: int = 100,
    ) -> list[GraphMorphism]:
        """Find all injective morphisms from pattern into host.

        Returns list of GraphMorphism objects m: pattern -> host.
        """
        if pattern.is_empty():
            return [GraphMorphism(node_map={}, source=pattern, target=self.host)]

        results: list[GraphMorphism] = []
        pattern_nodes = list(pattern.nodes.keys())

        # Sort pattern nodes to check most constrained first
        pattern_nodes.sort(key=lambda nid: self._candidate_count(pattern.nodes[nid]))

        self._backtrack(
            pattern=pattern,
            pattern_nodes=pattern_nodes,
            assignment={},
            used_targets=set(),
            depth=0,
            results=results,
            max_matches=max_matches,
        )
        return results

    def find_first_match(self, pattern: TypedGraph) -> GraphMorphism | None:
        """Find first match or None."""
        matches = self.find_matches(pattern, max_matches=1)
        return matches[0] if matches else None

    def _candidate_count(self, pattern_node: GraphNode) -> int:
        """Count host candidates for a pattern node (fewer = more constrained)."""
        candidates = self._type_index.get(pattern_node.node_type, [])
        if not pattern_node.attrs:
            return len(candidates)
        count = 0
        for cid in candidates:
            host_node = self.host.nodes[cid]
            if host_node.matches(pattern_node):
                count += 1
        return count

    def _backtrack(
        self,
        pattern: TypedGraph,
        pattern_nodes: list[str],
        assignment: dict[str, str],
        used_targets: set[str],
        depth: int,
        results: list[GraphMorphism],
        max_matches: int,
    ) -> None:
        """Recursive backtracking for subgraph matching."""
        if len(results) >= max_matches:
            return

        if depth == len(pattern_nodes):
            # Full assignment found — verify edge consistency
            if self._check_edge_consistency(assignment, pattern):
                results.append(GraphMorphism(
                    node_map=dict(assignment),
                    source=pattern,
                    target=self.host,
                ))
            return

        pattern_nid = pattern_nodes[depth]
        pattern_node = pattern.nodes[pattern_nid]

        # Get candidates from type index
        candidates = self._type_index.get(pattern_node.node_type, [])

        for host_nid in candidates:
            if host_nid in used_targets:
                continue  # injective

            host_node = self.host.nodes[host_nid]
            if not host_node.matches(pattern_node):
                continue

            # Check partial edge consistency before going deeper
            if not self._check_partial_edges(assignment, pattern, pattern_nid, host_nid):
                continue

            assignment[pattern_nid] = host_nid
            used_targets.add(host_nid)

            self._backtrack(
                pattern, pattern_nodes, assignment, used_targets,
                depth + 1, results, max_matches,
            )

            del assignment[pattern_nid]
            used_targets.discard(host_nid)

    def _check_partial_edges(
        self,
        assignment: dict[str, str],
        pattern: TypedGraph,
        pattern_nid: str,
        host_nid: str,
    ) -> bool:
        """Check edge consistency for the current partial assignment.

        Only checks edges involving already-assigned nodes + the new node.
        """
        for edge in pattern.edges:
            # Edge from new node to already-assigned node
            if edge.source == pattern_nid and edge.target in assignment:
                mapped_target = assignment[edge.target]
                if not self.host.has_edge(host_nid, mapped_target, edge.edge_type):
                    return False
            # Edge from already-assigned node to new node
            if edge.target == pattern_nid and edge.source in assignment:
                mapped_source = assignment[edge.source]
                if not self.host.has_edge(mapped_source, host_nid, edge.edge_type):
                    return False
        return True

    def _check_edge_consistency(
        self,
        assignment: dict[str, str],
        pattern: TypedGraph,
    ) -> bool:
        """Check that all pattern edges are preserved by the assignment."""
        for edge in pattern.edges:
            if edge.source not in assignment or edge.target not in assignment:
                return False
            mapped_source = assignment[edge.source]
            mapped_target = assignment[edge.target]
            if not self.host.has_edge(mapped_source, mapped_target, edge.edge_type):
                return False
        return True
