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

# Primitive operators (moved from agent/minisweagent/metrics/)
from .primitive_operators import (
    GraphOperator,
    MatchedSite,
    MatchError,
    OperatorAlgebra,
    OperatorStatus,
    OperatorType,
    Pattern,
    RefactorPlan,
)

# Extended node types
from .nodes import ClassNode, FieldNode, ImportNode, ModuleNode

# Typed graph infrastructure
from .typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph

# Graph morphisms
from .morphism import GraphMorphism

# Production rules
from .production_rule import ProductionRule, RewriteMode, RewriteResult

# Match finding
from .match_finder import MatchFinder

# Pushout engine
from .pushout_engine import PushoutEngine

# Invariant system
from .invariants import Invariant, InvariantRegistry, InvariantViolation

# Rule catalog
from .rule_catalog import ProductionRuleCatalog

# Transformation path
from .transformation_path import RuleApplication, TransformationPath

# Engine
from .engine import (
    GraphTransformationEngine,
    apply_operator,
    create_engine,
    verify_graph_invariants,
)

# Serialization
from .serialization import load_graph, save_graph

# Builder
from .builder import build_graph_from_source

# Visualization (optional -- graphviz must be installed)
try:
    from .visualization import diff_edges, diff_nodes, render_graph
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
