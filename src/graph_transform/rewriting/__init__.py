"""Algebraic rewriting engine (DPO/SPO)."""

from .graph_change import ChangeType, EdgeChange, GraphChangeSet, NodeChange
from .invariants import Invariant, InvariantRegistry, InvariantViolation
from .match_finder import MatchFinder
from .production_rule import ProductionRule, RewriteMode, RewriteResult
from .pushout_engine import PushoutEngine

__all__ = [
    "ChangeType",
    "EdgeChange",
    "GraphChangeSet",
    "Invariant",
    "InvariantRegistry",
    "InvariantViolation",
    "MatchFinder",
    "NodeChange",
    "ProductionRule",
    "PushoutEngine",
    "RewriteMode",
    "RewriteResult",
]
