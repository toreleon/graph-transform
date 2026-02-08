"""
Three Primitives Core

All code transformations reduce to three atomic operations:
- INSERT: Add a node or edge to the graph
- DELETE: Remove a node or edge from the graph
- UPDATE: Modify a property of an existing element

This module provides these primitives and the composition system
to build complex transformations from them.
"""

from .base import (
    # Primitive base
    Primitive,
    PrimitiveKind,
    PrimitiveResult,
    # INSERT primitives
    InsertNode,
    InsertEdge,
    # DELETE primitives
    DeleteNode,
    DeleteEdge,
    # UPDATE primitive
    Update,
    # Factory functions
    insert_node,
    insert_edge,
    delete_node,
    delete_edge,
    update,
    # Deserialization
    primitive_from_dict,
)

from .node_kinds import (
    NodeKind,
    EdgeKind,
    map_node_kind_to_node_type,
    map_edge_kind_to_edge_type,
)

from .position import (
    Position,
    EdgePosition,
    Relation,
)

from .compositions import (
    # Composition base
    Composition,
    CompositionResult,
    CompositionStatus,
    # Standard compositions
    Rename,
    Move,
    Extract,
    Inline,
    AddGuard,
    ChangeSignature,
    Wrap,
    # Registry
    CompositionRegistry,
    # Builder
    CompositionBuilder,
)

from .migrations import (
    # Migration compositions
    Migrate,
    MigrateNaming,
    MigrateTypes,
    MigrateStructure,
)

__all__ = [
    # Primitive types
    "Primitive",
    "PrimitiveKind",
    "PrimitiveResult",
    # INSERT
    "InsertNode",
    "InsertEdge",
    "insert_node",
    "insert_edge",
    # DELETE
    "DeleteNode",
    "DeleteEdge",
    "delete_node",
    "delete_edge",
    # UPDATE
    "Update",
    "update",
    # Deserialization
    "primitive_from_dict",
    # Node/Edge kinds
    "NodeKind",
    "EdgeKind",
    "map_node_kind_to_node_type",
    "map_edge_kind_to_edge_type",
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
    # Migration compositions
    "Migrate",
    "MigrateNaming",
    "MigrateTypes",
    "MigrateStructure",
]
