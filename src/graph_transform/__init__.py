"""
Graph Transformation Engine

Algebraic graph rewriting (DPO/SPO) with pre/post invariant checking
for verifying and applying refactoring operators on code graphs.

Core concepts:
- TypedGraph: Uniform typed attributed graph for algebraic operations
- ProductionRule: L <- K -> R rewriting rule
- GraphMorphism: Structure-preserving map between graphs
- PushoutEngine: DPO/SPO pushout construction
- MatchFinder: VF2-style subgraph isomorphism
- InvariantRegistry: Pre/post conditions and graph invariants
- ProductionRuleCatalog: Factory for all 40+ operator rules
- GraphTransformationEngine: Main engine combining all components
"""

# Core graph data structures
from .core.nodes import ClassNode, FieldNode, ImportNode, ModuleNode
from .core.morphism import GraphMorphism
from .core.typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph

# Algebraic rewriting
from .rewriting.production_rule import ProductionRule, RewriteMode, RewriteResult
from .rewriting.match_finder import MatchFinder
from .rewriting.pushout_engine import PushoutEngine
from .rewriting.invariants import (
    EdgeConstraint,
    GraphSchema,
    Invariant,
    InvariantLayer,
    InvariantRegistry,
    InvariantSeverity,
    InvariantViolation,
    ScopeRule,
)

# Operators
from .operators.primitive_operators import (
    GraphOperator,
    MatchedSite,
    MatchError,
    OperatorAlgebra,
    OperatorStatus,
    OperatorType,
    Pattern,
    RefactorPlan,
)
from .operators.rule_catalog import ProductionRuleCatalog

# Engine
from .engine.core import (
    GraphTransformationEngine,
    apply_operator,
    create_engine,
    verify_graph_invariants,
)
from .engine.transformation_path import RuleApplication, TransformationPath

# I/O
from .io.serialization import load_graph, save_graph
from .io.builder import build_graph_from_source

# Visualization (optional -- graphviz must be installed)
try:
    from .io.visualization import diff_edges, diff_nodes, render_graph
except ImportError:
    pass

__all__ = [
    # Primitive operators
    "OperatorType",
    "OperatorStatus",
    "OperatorAlgebra",
    "Pattern",
    "MatchedSite",
    "MatchError",
    "GraphOperator",
    "RefactorPlan",
    # Nodes
    "ClassNode",
    "FieldNode",
    "ImportNode",
    "ModuleNode",
    # Typed graph
    "NodeType",
    "EdgeType",
    "GraphNode",
    "GraphEdge",
    "TypedGraph",
    # Morphism
    "GraphMorphism",
    # Production rules
    "ProductionRule",
    "RewriteMode",
    "RewriteResult",
    # Match finding
    "MatchFinder",
    # Pushout
    "PushoutEngine",
    # Invariants
    "Invariant",
    "InvariantViolation",
    "InvariantRegistry",
    "InvariantSeverity",
    "InvariantLayer",
    "GraphSchema",
    "EdgeConstraint",
    "ScopeRule",
    # Rule catalog
    "ProductionRuleCatalog",
    # Path
    "RuleApplication",
    "TransformationPath",
    # Engine
    "GraphTransformationEngine",
    "create_engine",
    "apply_operator",
    "verify_graph_invariants",
    # Serialization
    "load_graph",
    "save_graph",
    # Builder
    "build_graph_from_source",
    # Visualization (optional)
    "render_graph",
    "diff_nodes",
    "diff_edges",
]
