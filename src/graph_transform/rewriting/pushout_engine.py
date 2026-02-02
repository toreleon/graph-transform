"""
Pushout Engine

Implements Double Pushout (DPO) and Single Pushout (SPO) graph rewriting.

DPO algorithm (given rule L <-l- K -r-> R and match m: L -> G):
1. Check gluing condition (dangling + identification)
2. Compute pushout complement D (context graph)
3. Compute pushout G' = D +_K R

SPO: auto-removes dangling edges instead of failing.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from graph_transform.core.morphism import GraphMorphism
from graph_transform.core.typed_graph import GraphEdge, GraphNode, TypedGraph

from .graph_change import ChangeType, EdgeChange, GraphChangeSet, NodeChange
from .production_rule import ProductionRule, RewriteMode, RewriteResult


# =============================================================================
# PushoutEngine
# =============================================================================


class PushoutEngine:
    """Computes pushout complements and pushouts for graph rewriting."""

    def __init__(self, mode: RewriteMode = RewriteMode.DPO):
        self.mode = mode

    def apply(
        self,
        rule: ProductionRule,
        match: GraphMorphism,
        host: TypedGraph,
    ) -> RewriteResult:
        """Apply production rule at match to host graph.

        Args:
            rule: The production rule (L <- K -> R)
            match: Morphism m: L -> G (match in host)
            host: The host graph G

        Returns:
            RewriteResult with the rewritten graph G'
        """
        # Validate match
        if not match.is_injective():
            return RewriteResult(
                success=False,
                errors=["Match morphism m: L -> G must be injective"],
                rule_name=rule.name,
            )

        # DPO: check gluing condition
        if self.mode == RewriteMode.DPO:
            gluing_errors = self._check_gluing_condition(rule, match, host)
            if gluing_errors:
                return RewriteResult(
                    success=False,
                    errors=gluing_errors,
                    match=match,
                    rule_name=rule.name,
                )

        # Compute the rewrite, recording all changes
        changes = GraphChangeSet()

        if self.mode == RewriteMode.DPO:
            result_graph = self._apply_dpo(rule, match, host, changes)
        else:
            result_graph = self._apply_spo(rule, match, host, changes)

        # Apply attribute transfer
        self._apply_attr_transfer(result_graph, rule, match, host, changes)

        return RewriteResult(
            success=True,
            result_graph=result_graph,
            match=match,
            rule_name=rule.name,
            changes=changes,
        )

    # -------------------------------------------------------------------------
    # Gluing Condition
    # -------------------------------------------------------------------------

    def _check_gluing_condition(
        self,
        rule: ProductionRule,
        match: GraphMorphism,
        host: TypedGraph,
    ) -> list[str]:
        """Check DPO gluing condition.

        Two parts:
        1. Dangling condition: no edge in G \\ m(L) is incident to a deleted node
        2. Identification condition: m is injective on nodes to be deleted
        """
        errors: list[str] = []

        deleted_in_lhs = rule.deleted_nodes()
        deleted_in_host = {match.node_map[d] for d in deleted_in_lhs if d in match.node_map}
        matched_in_host = match.image()

        # Dangling condition
        for node_id in deleted_in_host:
            for edge in host.edges:
                # Check edges NOT in the match image but incident to deleted node
                is_edge_in_match = (
                    edge.source in matched_in_host
                    and edge.target in matched_in_host
                )
                incident_to_deleted = (
                    edge.source == node_id or edge.target == node_id
                )
                if incident_to_deleted and not is_edge_in_match:
                    errors.append(
                        f"Dangling condition violated: edge ({edge.source} -> {edge.target}, "
                        f"type={edge.edge_type.value}) is incident to deleted node {node_id} "
                        f"but not part of the match"
                    )

        # Identification condition: m must be injective on deleted nodes
        deleted_targets = [match.node_map[d] for d in deleted_in_lhs if d in match.node_map]
        if len(deleted_targets) != len(set(deleted_targets)):
            errors.append(
                "Identification condition violated: match maps distinct "
                "deleted nodes to the same host node"
            )

        return errors

    # -------------------------------------------------------------------------
    # DPO Rewriting
    # -------------------------------------------------------------------------

    def _apply_dpo(
        self,
        rule: ProductionRule,
        match: GraphMorphism,
        host: TypedGraph,
        changes: GraphChangeSet,
    ) -> TypedGraph:
        """Apply DPO rewriting.

        Steps:
        1. Build context D = G \\ (m(L \\ l(K))) — remove matched deleted items
        2. Build result G' = D +_K R — glue RHS onto context via interface
        """
        result = host.copy()

        # Step 1: Remove deleted nodes and their edges
        deleted_in_lhs = rule.deleted_nodes()
        for lhs_node_id in deleted_in_lhs:
            host_node_id = match.node_map.get(lhs_node_id)
            if host_node_id and host_node_id in result.nodes:
                removed = result.nodes[host_node_id]
                changes.node_changes.append(NodeChange(
                    change_type=ChangeType.REMOVE_NODE,
                    node_id=host_node_id,
                    node_type=removed.node_type,
                    attrs=dict(removed.attrs),
                    host_node_id=host_node_id,
                ))
                result.remove_node(host_node_id)

        # Remove deleted edges (edges in L but not in K)
        deleted_lhs_edges = rule.deleted_edges()
        for lhs_edge in deleted_lhs_edges:
            mapped_src = match.node_map.get(lhs_edge.source)
            mapped_tgt = match.node_map.get(lhs_edge.target)
            if mapped_src and mapped_tgt:
                changes.edge_changes.append(EdgeChange(
                    change_type=ChangeType.REMOVE_EDGE,
                    source=mapped_src,
                    target=mapped_tgt,
                    edge_type=lhs_edge.edge_type,
                ))
                result.remove_edge(mapped_src, mapped_tgt, lhs_edge.edge_type)

        # Step 2: Add created nodes (in R but not in K)
        created_nodes = rule.created_nodes()
        node_id_map = self._build_node_id_map(rule, match, created_nodes)

        for rhs_node_id in created_nodes:
            rhs_node = rule.rhs.nodes[rhs_node_id]
            new_id = node_id_map[rhs_node_id]
            result.add_node(GraphNode(
                id=new_id,
                node_type=rhs_node.node_type,
                attrs=dict(rhs_node.attrs),
            ))
            changes.node_changes.append(NodeChange(
                change_type=ChangeType.ADD_NODE,
                node_id=rhs_node_id,
                node_type=rhs_node.node_type,
                attrs=dict(rhs_node.attrs),
                host_node_id=new_id,
            ))

        # Step 3: Add created edges (in R but not in K)
        created_edges = rule.created_edges()
        for rhs_edge in created_edges:
            src_id = self._resolve_rhs_node(
                rhs_edge.source, rule, match, node_id_map
            )
            tgt_id = self._resolve_rhs_node(
                rhs_edge.target, rule, match, node_id_map
            )
            if src_id and tgt_id:
                result.add_edge(GraphEdge(
                    source=src_id,
                    target=tgt_id,
                    edge_type=rhs_edge.edge_type,
                    attrs=dict(rhs_edge.attrs),
                ))
                changes.edge_changes.append(EdgeChange(
                    change_type=ChangeType.ADD_EDGE,
                    source=src_id,
                    target=tgt_id,
                    edge_type=rhs_edge.edge_type,
                    attrs=dict(rhs_edge.attrs),
                ))

        # Update attributes on preserved nodes
        self._update_preserved_attrs(result, rule, match, changes)

        return result

    # -------------------------------------------------------------------------
    # SPO Rewriting
    # -------------------------------------------------------------------------

    def _apply_spo(
        self,
        rule: ProductionRule,
        match: GraphMorphism,
        host: TypedGraph,
        changes: GraphChangeSet,
    ) -> TypedGraph:
        """Apply SPO rewriting.

        Like DPO but auto-removes dangling edges (no gluing condition check).
        """
        result = host.copy()

        # Remove deleted nodes (auto-removes incident edges via remove_node)
        deleted_in_lhs = rule.deleted_nodes()
        for lhs_node_id in deleted_in_lhs:
            host_node_id = match.node_map.get(lhs_node_id)
            if host_node_id and host_node_id in result.nodes:
                # Record auto-removed dangling edges before node removal
                for edge in list(result.edges):
                    if edge.source == host_node_id or edge.target == host_node_id:
                        changes.edge_changes.append(EdgeChange(
                            change_type=ChangeType.REMOVE_EDGE,
                            source=edge.source,
                            target=edge.target,
                            edge_type=edge.edge_type,
                            attrs=dict(edge.attrs),
                        ))
                removed = result.nodes[host_node_id]
                changes.node_changes.append(NodeChange(
                    change_type=ChangeType.REMOVE_NODE,
                    node_id=host_node_id,
                    node_type=removed.node_type,
                    attrs=dict(removed.attrs),
                    host_node_id=host_node_id,
                ))
                result.remove_node(host_node_id)

        # Remove deleted edges
        deleted_lhs_edges = rule.deleted_edges()
        for lhs_edge in deleted_lhs_edges:
            mapped_src = match.node_map.get(lhs_edge.source)
            mapped_tgt = match.node_map.get(lhs_edge.target)
            if mapped_src and mapped_tgt:
                changes.edge_changes.append(EdgeChange(
                    change_type=ChangeType.REMOVE_EDGE,
                    source=mapped_src,
                    target=mapped_tgt,
                    edge_type=lhs_edge.edge_type,
                ))
                result.remove_edge(mapped_src, mapped_tgt, lhs_edge.edge_type)

        # Add created nodes
        created_nodes = rule.created_nodes()
        node_id_map = self._build_node_id_map(rule, match, created_nodes)

        for rhs_node_id in created_nodes:
            rhs_node = rule.rhs.nodes[rhs_node_id]
            new_id = node_id_map[rhs_node_id]
            result.add_node(GraphNode(
                id=new_id,
                node_type=rhs_node.node_type,
                attrs=dict(rhs_node.attrs),
            ))
            changes.node_changes.append(NodeChange(
                change_type=ChangeType.ADD_NODE,
                node_id=rhs_node_id,
                node_type=rhs_node.node_type,
                attrs=dict(rhs_node.attrs),
                host_node_id=new_id,
            ))

        # Add created edges
        created_edges = rule.created_edges()
        for rhs_edge in created_edges:
            src_id = self._resolve_rhs_node(
                rhs_edge.source, rule, match, node_id_map
            )
            tgt_id = self._resolve_rhs_node(
                rhs_edge.target, rule, match, node_id_map
            )
            if src_id and tgt_id:
                result.add_edge(GraphEdge(
                    source=src_id,
                    target=tgt_id,
                    edge_type=rhs_edge.edge_type,
                    attrs=dict(rhs_edge.attrs),
                ))
                changes.edge_changes.append(EdgeChange(
                    change_type=ChangeType.ADD_EDGE,
                    source=src_id,
                    target=tgt_id,
                    edge_type=rhs_edge.edge_type,
                    attrs=dict(rhs_edge.attrs),
                ))

        # Update preserved attrs
        self._update_preserved_attrs(result, rule, match, changes)

        return result

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _build_node_id_map(
        self,
        rule: ProductionRule,
        match: GraphMorphism,
        created_nodes: set[str],
    ) -> dict[str, str]:
        """Build mapping from RHS node IDs to result graph node IDs.

        - Preserved nodes: map via K -> L -> match -> host
        - Created nodes: generate new unique IDs, using RHS attrs if available
        """
        node_id_map: dict[str, str] = {}

        # Preserved nodes: RHS id -> K id -> L id -> host id
        rhs_inverse = rule.rhs_inclusion.inverse_map()  # rhs_id -> k_id
        lhs_map = rule.lhs_inclusion.node_map  # k_id -> l_id

        for rhs_id in rule.rhs.nodes:
            if rhs_id in created_nodes:
                # Created node: use RHS node attrs to build meaningful ID
                rhs_node = rule.rhs.nodes[rhs_id]
                name = rhs_node.attrs.get("name", "")
                if name:
                    new_id = f"{rhs_node.node_type.value}:{name}:{uuid.uuid4().hex[:8]}"
                else:
                    new_id = f"{rhs_node.node_type.value}:{uuid.uuid4().hex[:8]}"
                node_id_map[rhs_id] = new_id
            else:
                # Preserved: trace K -> L -> match
                k_id = rhs_inverse.get(rhs_id)
                if k_id:
                    l_id = lhs_map.get(k_id)
                    if l_id:
                        host_id = match.node_map.get(l_id)
                        if host_id:
                            node_id_map[rhs_id] = host_id

        return node_id_map

    def _resolve_rhs_node(
        self,
        rhs_node_id: str,
        rule: ProductionRule,
        match: GraphMorphism,
        node_id_map: dict[str, str],
    ) -> str | None:
        """Resolve an RHS node ID to the corresponding result graph node ID."""
        # Check the node_id_map first (covers both created and preserved)
        if rhs_node_id in node_id_map:
            return node_id_map[rhs_node_id]

        # Fallback: trace through K -> L -> match
        rhs_inverse = rule.rhs_inclusion.inverse_map()
        k_id = rhs_inverse.get(rhs_node_id)
        if k_id:
            l_id = rule.lhs_inclusion.map_node(k_id)
            if l_id:
                return match.map_node(l_id)

        return None

    def _update_preserved_attrs(
        self,
        result: TypedGraph,
        rule: ProductionRule,
        match: GraphMorphism,
        changes: GraphChangeSet,
    ) -> None:
        """Update attributes on preserved nodes from RHS specification."""
        rhs_inverse = rule.rhs_inclusion.inverse_map()

        for rhs_id, rhs_node in rule.rhs.nodes.items():
            if rhs_id in rule.created_nodes():
                continue  # skip created nodes, handled separately

            # Find the host node for this preserved node
            k_id = rhs_inverse.get(rhs_id)
            if not k_id:
                continue
            l_id = rule.lhs_inclusion.map_node(k_id)
            if not l_id:
                continue
            host_id = match.map_node(l_id)
            if not host_id or host_id not in result.nodes:
                continue

            # Update attrs that differ between LHS and RHS
            lhs_node = rule.lhs.get_node(l_id)
            if lhs_node:
                old_attrs = dict(result.nodes[host_id].attrs)
                changed = False
                for key, value in rhs_node.attrs.items():
                    if value is not None and value != lhs_node.attrs.get(key):
                        result.nodes[host_id].attrs[key] = value
                        changed = True
                if changed:
                    changes.node_changes.append(NodeChange(
                        change_type=ChangeType.UPDATE_ATTRS,
                        node_id=host_id,
                        node_type=rhs_node.node_type,
                        attrs=dict(result.nodes[host_id].attrs),
                        old_attrs=old_attrs,
                        host_node_id=host_id,
                    ))

    def _apply_attr_transfer(
        self,
        result: TypedGraph,
        rule: ProductionRule,
        match: GraphMorphism,
        host: TypedGraph,
        changes: GraphChangeSet | None = None,
    ) -> None:
        """Apply attribute transfer functions to created/updated nodes."""
        created = rule.created_nodes()

        # Build lookup from RHS node ID → host node ID using change records
        created_id_map: dict[str, str] = {}
        if changes:
            for nc in changes.node_changes:
                if nc.change_type == ChangeType.ADD_NODE and nc.host_node_id:
                    created_id_map[nc.node_id] = nc.host_node_id

        for rhs_node_id, transfer_fn in rule.attr_transfer.items():
            # Find the result node ID
            rhs_inverse = rule.rhs_inclusion.inverse_map()
            if rhs_node_id in created:
                # Created node: use change records for exact ID when available
                host_node_id = created_id_map.get(rhs_node_id)
                if host_node_id and host_node_id in result.nodes:
                    computed_attrs = transfer_fn(match, host)
                    result.nodes[host_node_id].attrs.update(computed_attrs)
                    continue
                # Fallback: find by matching in result
                rhs_node = rule.rhs.nodes.get(rhs_node_id)
                if not rhs_node:
                    continue
                for result_id, result_node in result.nodes.items():
                    if (
                        result_node.node_type == rhs_node.node_type
                        and result_node.matches(rhs_node)
                    ):
                        computed_attrs = transfer_fn(match, host)
                        result_node.attrs.update(computed_attrs)
                        break
            else:
                # Preserved node: trace through to host
                k_id = rhs_inverse.get(rhs_node_id)
                if not k_id:
                    continue
                l_id = rule.lhs_inclusion.map_node(k_id)
                if not l_id:
                    continue
                host_id = match.map_node(l_id)
                if host_id and host_id in result.nodes:
                    computed_attrs = transfer_fn(match, host)
                    result.nodes[host_id].attrs.update(computed_attrs)
