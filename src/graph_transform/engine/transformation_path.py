"""
Transformation Path

An ordered sequence of rule applications forming a complete refactoring.
Bridges to the existing RefactorPlan system from primitive_operators.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from graph_transform.core.morphism import GraphMorphism
from graph_transform.core.typed_graph import TypedGraph
from graph_transform.rewriting.production_rule import ProductionRule, RewriteResult


# =============================================================================
# RuleApplication
# =============================================================================


@dataclass
class RuleApplication:
    """Record of a single rule application."""

    rule: ProductionRule
    match: GraphMorphism | None = None
    result: RewriteResult | None = None
    step_index: int = 0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule.name,
            "step_index": self.step_index,
            "success": self.result.success if self.result else False,
            "timestamp": self.timestamp,
        }


# =============================================================================
# TransformationPath
# =============================================================================


@dataclass
class TransformationPath:
    """An ordered sequence of rule applications forming a complete refactoring.

    Each step is a ProductionRule applied at a specific match.
    Tracks graph state evolution through the path.
    """

    steps: list[RuleApplication] = field(default_factory=list)
    initial_graph: TypedGraph | None = None
    current_graph: TypedGraph | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, application: RuleApplication) -> None:
        """Record a rule application."""
        application.step_index = len(self.steps)
        application.timestamp = time.time()
        self.steps.append(application)
        if application.result and application.result.result_graph:
            self.current_graph = application.result.result_graph

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def all_succeeded(self) -> bool:
        return all(
            s.result is not None and s.result.success
            for s in self.steps
        )

    @property
    def success_count(self) -> int:
        return sum(
            1 for s in self.steps
            if s.result is not None and s.result.success
        )

    @property
    def failure_count(self) -> int:
        return sum(
            1 for s in self.steps
            if s.result is not None and not s.result.success
        )

    def get_graph_at_step(self, step: int) -> TypedGraph | None:
        """Get graph state after applying steps 0..step."""
        if step < 0 or step >= len(self.steps):
            return None
        app = self.steps[step]
        if app.result and app.result.result_graph:
            return app.result.result_graph
        return None

    def get_errors(self) -> list[str]:
        """Collect all errors from failed steps."""
        errors = []
        for step in self.steps:
            if step.result and not step.result.success:
                errors.extend(step.result.errors)
        return errors

    def validate_sequence(self) -> list[str]:
        """Check that the sequence is well-formed."""
        errors = []
        for i, step in enumerate(self.steps):
            rule_errors = step.rule.validate()
            for err in rule_errors:
                errors.append(f"Step {i} ({step.rule.name}): {err}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "length": self.length,
            "all_succeeded": self.all_succeeded,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "metadata": self.metadata,
        }
