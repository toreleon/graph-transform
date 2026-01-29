"""
Graph Transformation Engine

Algebraic graph transformation engine combining:
- Match finding (subgraph isomorphism)
- DPO/SPO pushout construction (formal rewriting)
- Pre/post invariant checking (correctness guarantees)
- Production rule catalog (all 40+ operator types)
"""

from __future__ import annotations

from typing import Any

from .invariants import InvariantRegistry, InvariantViolation
from .match_finder import MatchFinder
from .morphism import GraphMorphism
from .production_rule import ProductionRule, RewriteMode, RewriteResult
from .pushout_engine import PushoutEngine
from .rule_catalog import ProductionRuleCatalog
from .transformation_path import RuleApplication, TransformationPath
from .typed_graph import TypedGraph


# =============================================================================
# GraphTransformationEngine
# =============================================================================


class GraphTransformationEngine:
    """Algebraic graph transformation engine for code refactoring.

    Combines:
    - Match finding (subgraph isomorphism via VF2 backtracking)
    - DPO/SPO pushout construction (formal rewriting)
    - Pre/post invariant checking (correctness guarantees)
    - Production rule catalog (all 40+ operator types)

    Usage:
        engine = GraphTransformationEngine()

        # Build typed graph from existing CodeGraph
        tg = TypedGraph.from_code_graph(code_graph)

        # Create a rule
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "get_data", "param_name": "log", "default_value": "True"}
        )

        # Find matches and apply
        result = engine.apply_rule(rule, tg)

        # Or apply entire transformation path
        path_result = engine.apply_path(path, tg)
    """

    def __init__(
        self,
        mode: RewriteMode = RewriteMode.DPO,
        invariants: InvariantRegistry | None = None,
        check_invariants: bool = True,
    ):
        self.mode = mode
        self.invariants = invariants or InvariantRegistry()
        self.catalog = ProductionRuleCatalog()
        self.check_invariants = check_invariants
        self._pushout = PushoutEngine(mode)

    def apply_rule(
        self,
        rule: ProductionRule,
        graph: TypedGraph,
        match: GraphMorphism | None = None,
    ) -> RewriteResult:
        """Apply a single production rule to the graph.

        Steps:
        1. Find match m: L -> G (if not provided)
        2. Verify preconditions
        3. Verify graph invariants on G (optional)
        4. Compute pushout (DPO or SPO)
        5. Verify postconditions on G'
        6. Verify graph invariants on G' (optional)

        Args:
            rule: The production rule to apply
            graph: The host graph
            match: Optional pre-computed match morphism

        Returns:
            RewriteResult with the rewritten graph
        """
        # Step 1: Find match
        if match is None:
            finder = MatchFinder(graph)
            match = finder.find_first_match(rule.lhs)
            if match is None:
                return RewriteResult(
                    success=False,
                    errors=[f"No match found for rule '{rule.name}' LHS in host graph"],
                    rule_name=rule.name,
                )

        # Step 2: Verify preconditions
        if rule.preconditions:
            pre_violations = self.invariants.verify_preconditions(
                rule.preconditions, graph
            )
            if any(v.severity == "error" for v in pre_violations):
                return RewriteResult(
                    success=False,
                    errors=[f"Precondition violated: {v.message}" for v in pre_violations],
                    pre_violations=pre_violations,
                    match=match,
                    rule_name=rule.name,
                )

        # Step 3: Verify graph invariants on G
        if self.check_invariants:
            graph_violations = self.invariants.verify_graph(graph)
            errors = [v for v in graph_violations if v.severity == "error"]
            if errors:
                return RewriteResult(
                    success=False,
                    errors=[f"Graph invariant violated: {v.message}" for v in errors],
                    pre_violations=graph_violations,
                    match=match,
                    rule_name=rule.name,
                )

        # Step 4: Compute pushout
        result = self._pushout.apply(rule, match, graph)
        if not result.success:
            return result

        # Step 5: Verify postconditions
        if rule.postconditions and result.result_graph:
            post_violations = self.invariants.verify_postconditions(
                rule.postconditions, result.result_graph
            )
            if any(v.severity == "error" for v in post_violations):
                return RewriteResult(
                    success=False,
                    result_graph=result.result_graph,
                    errors=[f"Postcondition violated: {v.message}" for v in post_violations],
                    post_violations=post_violations,
                    match=match,
                    rule_name=rule.name,
                )

        # Step 6: Verify graph invariants on G'
        if self.check_invariants and result.result_graph:
            post_graph_violations = self.invariants.verify_graph(result.result_graph)
            errors = [v for v in post_graph_violations if v.severity == "error"]
            if errors:
                return RewriteResult(
                    success=False,
                    result_graph=result.result_graph,
                    errors=[f"Post-rewrite invariant violated: {v.message}" for v in errors],
                    post_violations=post_graph_violations,
                    match=match,
                    rule_name=rule.name,
                )

        return result

    def apply_all_matches(
        self,
        rule: ProductionRule,
        graph: TypedGraph,
        max_applications: int = 100,
    ) -> list[RewriteResult]:
        """Apply rule at all non-overlapping matches.

        Finds all matches, applies rule at each one sequentially,
        re-matching after each application (since the graph changes).
        Tracks matched host-node images to avoid re-applying at the
        same site when preserved nodes still match the LHS pattern.
        """
        results: list[RewriteResult] = []
        current_graph = graph
        used_images: set[frozenset[str]] = set()

        for _ in range(max_applications):
            finder = MatchFinder(current_graph)
            all_matches = finder.find_matches(rule.lhs, max_applications)

            # Pick the first match whose image hasn't been used yet
            match = None
            for m in all_matches:
                image = frozenset(m.image())
                if image not in used_images:
                    match = m
                    used_images.add(image)
                    break

            if match is None:
                break

            result = self.apply_rule(rule, current_graph, match)
            results.append(result)

            if not result.success or not result.result_graph:
                break

            current_graph = result.result_graph

        return results

    def apply_path(
        self,
        path: TransformationPath,
        graph: TypedGraph,
        stop_on_failure: bool = True,
    ) -> TransformationPath:
        """Apply entire transformation path to graph.

        Applies each step in order, updating the graph after each step.

        Args:
            path: The transformation path with rules
            graph: The initial host graph
            stop_on_failure: If True, stop on first failure

        Returns:
            Updated TransformationPath with results
        """
        path.initial_graph = graph
        current_graph = graph

        for step in path.steps:
            result = self.apply_rule(step.rule, current_graph)
            step.result = result

            if result.success and result.result_graph:
                step.match = result.match
                current_graph = result.result_graph
                path.current_graph = current_graph
            elif stop_on_failure:
                break

        return path

    def verify_graph(self, graph: TypedGraph) -> list[InvariantViolation]:
        """Run all graph-level invariants on a graph."""
        return self.invariants.verify_graph(graph)

    def find_matches(
        self,
        rule: ProductionRule,
        graph: TypedGraph,
        max_matches: int = 100,
    ) -> list[GraphMorphism]:
        """Find all matches of rule's LHS in graph."""
        finder = MatchFinder(graph)
        return finder.find_matches(rule.lhs, max_matches)

    def dry_run(
        self,
        rule: ProductionRule,
        graph: TypedGraph,
    ) -> RewriteResult:
        """Check if rule can be applied without actually modifying the graph.

        Finds match, checks preconditions and gluing condition,
        but returns the result from a copy to leave original intact.
        """
        finder = MatchFinder(graph)
        match = finder.find_first_match(rule.lhs)
        if match is None:
            return RewriteResult(
                success=False,
                errors=[f"No match found for rule '{rule.name}'"],
                rule_name=rule.name,
            )

        # Check preconditions
        if rule.preconditions:
            pre_violations = self.invariants.verify_preconditions(
                rule.preconditions, graph
            )
            if any(v.severity == "error" for v in pre_violations):
                return RewriteResult(
                    success=False,
                    errors=[f"Precondition: {v.message}" for v in pre_violations],
                    pre_violations=pre_violations,
                    match=match,
                    rule_name=rule.name,
                )

        # Apply to a copy
        graph_copy = graph.copy()
        finder_copy = MatchFinder(graph_copy)
        match_copy = finder_copy.find_first_match(rule.lhs)
        if match_copy:
            return self._pushout.apply(rule, match_copy, graph_copy)

        return RewriteResult(
            success=True,
            match=match,
            rule_name=rule.name,
            errors=["Dry run: match found, preconditions satisfied"],
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def create_engine(
    mode: str = "dpo",
    check_invariants: bool = True,
) -> GraphTransformationEngine:
    """Create a new GraphTransformationEngine."""
    return GraphTransformationEngine(
        mode=RewriteMode(mode),
        check_invariants=check_invariants,
    )


def apply_operator(
    op_type: Any,
    params: dict[str, Any],
    graph: TypedGraph,
    mode: str = "dpo",
) -> RewriteResult:
    """One-shot: create rule, find match, apply."""
    engine = create_engine(mode)
    rule = engine.catalog.create_rule(op_type, params)
    return engine.apply_rule(rule, graph)


def verify_graph_invariants(graph: TypedGraph) -> list[InvariantViolation]:
    """Check all graph invariants."""
    registry = InvariantRegistry()
    return registry.verify_graph(graph)
