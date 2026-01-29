"""
Production Rule Formalism

Algebraic graph rewriting production rules: L <- K -> R
where L is the left-hand side (pattern), K is the interface (preserved),
and R is the right-hand side (replacement).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from .morphism import GraphMorphism
from .typed_graph import TypedGraph

if TYPE_CHECKING:
    from .invariants import Invariant


# =============================================================================
# Rewrite Mode
# =============================================================================


class RewriteMode(Enum):
    """Graph rewriting semantics."""

    DPO = "dpo"  # Double Pushout: safe, no dangling edges
    SPO = "spo"  # Single Pushout: permissive, auto-removes dangling


# =============================================================================
# Production Rule
# =============================================================================


@dataclass
class ProductionRule:
    """Algebraic graph rewriting production rule.

    A rule p consists of:
    - L (left-hand side): pattern graph to match in the host graph
    - K (interface/gluing graph): subgraph preserved by the rewriting
    - R (right-hand side): replacement graph
    - l: K -> L (inclusion of interface into LHS)
    - r: K -> R (inclusion of interface into RHS)

    Semantics:
    - L \\ K: nodes/edges deleted by the rule
    - R \\ K: nodes/edges created by the rule
    - K: nodes/edges preserved

    Additional:
    - preconditions: predicates that must hold before application
    - postconditions: predicates that must hold after application
    - attr_transfer: compute attributes for new nodes in R
    - parameters: concrete values for this rule instance
    """

    name: str
    op_type: Any  # OperatorType
    lhs: TypedGraph
    interface: TypedGraph
    rhs: TypedGraph
    lhs_inclusion: GraphMorphism  # l: K -> L
    rhs_inclusion: GraphMorphism  # r: K -> R
    preconditions: list[Any] = field(default_factory=list)  # list[Invariant]
    postconditions: list[Any] = field(default_factory=list)  # list[Invariant]
    attr_transfer: dict[str, Callable] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    category: str | None = None

    def deleted_nodes(self) -> set[str]:
        """Nodes in L but not in the image of l: K -> L."""
        lhs_image = self.lhs_inclusion.image()
        return set(self.lhs.nodes.keys()) - lhs_image

    def deleted_edges(self) -> list:
        """Edges in L but not mapped from K."""
        from .typed_graph import GraphEdge

        lhs_image = self.lhs_inclusion.image()
        return [
            e for e in self.lhs.edges
            if e.source not in lhs_image or e.target not in lhs_image
        ]

    def created_nodes(self) -> set[str]:
        """Nodes in R but not in the image of r: K -> R."""
        rhs_image = self.rhs_inclusion.image()
        return set(self.rhs.nodes.keys()) - rhs_image

    def created_edges(self) -> list:
        """Edges in R but not mapped from K."""
        rhs_image = self.rhs_inclusion.image()
        return [
            e for e in self.rhs.edges
            if e.source not in rhs_image or e.target not in rhs_image
        ]

    def preserved_nodes(self) -> set[str]:
        """Nodes in K (mapped to both L and R)."""
        return set(self.interface.nodes.keys())

    def validate(self) -> list[str]:
        """Validate rule well-formedness. Returns list of error messages."""
        errors = []

        # l: K -> L must be valid
        if not self.lhs_inclusion.is_valid():
            errors.append("LHS inclusion l: K -> L is not a valid morphism")

        # r: K -> R must be valid
        if not self.rhs_inclusion.is_valid():
            errors.append("RHS inclusion r: K -> R is not a valid morphism")

        # l must be injective
        if not self.lhs_inclusion.is_injective():
            errors.append("LHS inclusion l: K -> L must be injective")

        # r must be injective
        if not self.rhs_inclusion.is_injective():
            errors.append("RHS inclusion r: K -> R must be injective")

        # All K nodes must be in both L and R
        for kid in self.interface.nodes:
            if self.lhs_inclusion.map_node(kid) is None:
                errors.append(f"Interface node {kid} not mapped to LHS")
            if self.rhs_inclusion.map_node(kid) is None:
                errors.append(f"Interface node {kid} not mapped to RHS")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "op_type": self.op_type.value if hasattr(self.op_type, "value") else str(self.op_type),
            "lhs": self.lhs.to_dict(),
            "interface": self.interface.to_dict(),
            "rhs": self.rhs.to_dict(),
            "lhs_inclusion": self.lhs_inclusion.to_dict(),
            "rhs_inclusion": self.rhs_inclusion.to_dict(),
            "parameters": self.parameters,
            "description": self.description,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductionRule:
        lhs = TypedGraph.from_dict(data["lhs"])
        interface = TypedGraph.from_dict(data["interface"])
        rhs = TypedGraph.from_dict(data["rhs"])
        return cls(
            name=data["name"],
            op_type=data.get("op_type", "unknown"),
            lhs=lhs,
            interface=interface,
            rhs=rhs,
            lhs_inclusion=GraphMorphism.from_dict(data["lhs_inclusion"]),
            rhs_inclusion=GraphMorphism.from_dict(data["rhs_inclusion"]),
            parameters=data.get("parameters", {}),
            description=data.get("description"),
            category=data.get("category"),
        )


# =============================================================================
# Rewrite Result
# =============================================================================


@dataclass
class RewriteResult:
    """Result of applying a production rule."""

    success: bool
    result_graph: TypedGraph | None = None
    match: GraphMorphism | None = None
    errors: list[str] = field(default_factory=list)
    pre_violations: list[Any] = field(default_factory=list)
    post_violations: list[Any] = field(default_factory=list)
    rule_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "errors": self.errors,
            "rule_name": self.rule_name,
            "has_result_graph": self.result_graph is not None,
            "pre_violation_count": len(self.pre_violations),
            "post_violation_count": len(self.post_violations),
        }
