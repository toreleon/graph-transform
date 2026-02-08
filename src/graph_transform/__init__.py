"""
Graph Transformation Engine

Algebraic graph rewriting (DPO/SPO) with pre/post invariant checking
for verifying and applying refactoring operations on code graphs.

Core concepts:
- TypedGraph: Uniform typed attributed graph for algebraic operations
- ProductionRule: L <- K -> R rewriting rule
- GraphMorphism: Structure-preserving map between graphs
- PushoutEngine: DPO/SPO pushout construction
- MatchFinder: VF2-style subgraph isomorphism
- InvariantRegistry: Pre/post conditions and graph invariants
- Primitives: INSERT, DELETE, UPDATE operations
- Compositions: RENAME, MOVE, EXTRACT, INLINE, etc.
- GraphTransformationEngine: Main engine combining all components
"""

# Core graph data structures
from .core.nodes import ClassNode, FieldNode, ImportNode, ModuleNode
from .core.morphism import GraphMorphism
from .core.typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph

# Primitives system
from .core.primitives import (
    # Primitive types
    Primitive,
    PrimitiveKind,
    PrimitiveResult,
    # INSERT operations
    InsertNode,
    InsertEdge,
    insert_node,
    insert_edge,
    # DELETE operations
    DeleteNode,
    DeleteEdge,
    delete_node,
    delete_edge,
    # UPDATE operation
    Update,
    update,
    # Deserialization
    primitive_from_dict,
    # Node/Edge kinds
    NodeKind,
    EdgeKind,
    # Position system
    Position,
    EdgePosition,
    Relation,
    # Compositions
    Composition,
    CompositionResult,
    CompositionStatus,
    Rename,
    Move,
    Extract,
    Inline,
    AddGuard,
    ChangeSignature,
    Wrap,
    CompositionRegistry,
    CompositionBuilder,
)

# Algebraic rewriting
from .rewriting.graph_change import ChangeType, GraphChangeSet
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

# Engine
from .engine.core import (
    GraphTransformationEngine,
    create_engine,
    verify_graph_invariants,
)
from .engine.transformation_path import RuleApplication, TransformationPath

# I/O
from .io.serialization import load_graph, save_graph
from .io.builder import build_graph_from_source, build_graph_from_files

# Language adapters
from .languages import (
    LanguageAdapter,
    LanguageRegistry,
    EditInstruction,
    PythonAdapter,
)

# Visualization (optional -- graphviz must be installed)
try:
    from .io.visualization import diff_edges, diff_nodes, render_graph
except ImportError:
    pass

__all__ = [
    # Primitives
    "Primitive",
    "PrimitiveKind",
    "PrimitiveResult",
    "InsertNode",
    "InsertEdge",
    "insert_node",
    "insert_edge",
    "DeleteNode",
    "DeleteEdge",
    "delete_node",
    "delete_edge",
    "Update",
    "update",
    "primitive_from_dict",
    # Node/Edge kinds
    "NodeKind",
    "EdgeKind",
    # Position
    "Position",
    "EdgePosition",
    "Relation",
    # Compositions
    "Composition",
    "CompositionResult",
    "CompositionStatus",
    "Rename",
    "Move",
    "Extract",
    "Inline",
    "AddGuard",
    "ChangeSignature",
    "Wrap",
    "CompositionRegistry",
    "CompositionBuilder",
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
    # Graph changes
    "ChangeType",
    "GraphChangeSet",
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
    # Path
    "RuleApplication",
    "TransformationPath",
    # Engine
    "GraphTransformationEngine",
    "create_engine",
    "verify_graph_invariants",
    # Serialization
    "load_graph",
    "save_graph",
    # Builder
    "build_graph_from_source",
    "build_graph_from_files",
    # Language adapters
    "LanguageAdapter",
    "LanguageRegistry",
    "EditInstruction",
    "PythonAdapter",
    # Visualization (optional)
    "render_graph",
    "diff_nodes",
    "diff_edges",
]
