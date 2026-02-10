"""
The Three Primitive Operators

All code transformations reduce to these three atomic operations:
- INSERT: Add a node or edge to the graph
- DELETE: Remove a node or edge from the graph
- UPDATE: Modify a property of an existing element

Every refactoring, migration, and code fix is a composition of these primitives.

IMPORTANT: Primitives are IMMUTABLE (frozen=True) and return NEW graphs.
They never mutate the input graph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .node_kinds import EdgeKind, NodeKind
from .position import EdgePosition, Position

if TYPE_CHECKING:
    from ..typed_graph import GraphEdge, GraphNode, TypedGraph


class PrimitiveKind(Enum):
    """The three primitive operation types."""

    INSERT = "insert"
    DELETE = "delete"
    UPDATE = "update"


@dataclass
class PrimitiveResult:
    """Result of executing a primitive operation."""

    success: bool
    primitive_kind: PrimitiveKind
    affected_ids: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        kind: PrimitiveKind,
        affected: list[str] | None = None,
        **metadata: Any,
    ) -> PrimitiveResult:
        return cls(
            success=True,
            primitive_kind=kind,
            affected_ids=affected or [],
            metadata=metadata,
        )

    @classmethod
    def fail(cls, kind: PrimitiveKind, error: str) -> PrimitiveResult:
        return cls(success=False, primitive_kind=kind, error=error)


class Primitive(ABC):
    """Base class for all primitive operations.

    Primitives are IMMUTABLE and return NEW graphs (never mutate).
    """

    @property
    @abstractmethod
    def kind(self) -> PrimitiveKind:
        """Return the primitive kind."""
        ...

    @abstractmethod
    def apply(self, graph: TypedGraph) -> tuple[PrimitiveResult, TypedGraph]:
        """Apply this primitive to the graph, returning (result, new_graph).

        IMPORTANT: Does NOT mutate the input graph. Returns a new graph.
        """
        ...

    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Execute this primitive on the graph (mutates in place).

        DEPRECATED: Use apply() instead for immutability.
        This method exists for backward compatibility with compositions.
        """
        result, new_graph = self.apply(graph)
        if result.success:
            # Copy new_graph state back to original (for backward compat)
            graph.nodes.clear()
            graph.nodes.update(new_graph.nodes)
            graph.edges.clear()
            graph.edges.extend(new_graph.edges)
        return result

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> Primitive:
        """Deserialize from dictionary."""
        ...


# =============================================================================
# INSERT Primitive
# =============================================================================


@dataclass(frozen=True)
class InsertNode(Primitive):
    """Insert a new node into the graph.

    This is the atomic operation for adding any code element:
    functions, classes, variables, imports, etc.

    IMMUTABLE: Does not mutate input graph, returns new graph.

    Examples:
        # Add a new function
        InsertNode(
            node_id="func:new_helper",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "new_helper", "file": "utils.py", "line": 10},
        )
    """

    node_id: str
    node_kind: NodeKind
    attrs: tuple[tuple[str, Any], ...] = field(default_factory=tuple)  # Immutable attrs
    position: Position | None = None

    def __init__(
        self,
        node_id: str,
        node_kind: NodeKind,
        attrs: dict[str, Any] | tuple[tuple[str, Any], ...] | None = None,
        position: Position | None = None,
    ):
        """Initialize with dict or tuple attrs (converted to immutable tuple)."""
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "node_kind", node_kind)
        object.__setattr__(self, "position", position)

        # Convert dict to immutable tuple of tuples
        if attrs is None:
            object.__setattr__(self, "attrs", ())
        elif isinstance(attrs, dict):
            object.__setattr__(self, "attrs", tuple(attrs.items()))
        else:
            object.__setattr__(self, "attrs", attrs)

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.INSERT

    @property
    def attrs_dict(self) -> dict[str, Any]:
        """Get attrs as a mutable dict (for convenience)."""
        return dict(self.attrs)

    def apply(self, graph: TypedGraph) -> tuple[PrimitiveResult, TypedGraph]:
        """Add the node to a copy of the graph."""
        from ..typed_graph import GraphNode, NodeType

        # Create a copy of the graph
        new_graph = graph.copy()

        # Check if node already exists
        if new_graph.has_node(self.node_id):
            return (
                PrimitiveResult.fail(
                    self.kind,
                    f"Node '{self.node_id}' already exists",
                ),
                graph,  # Return original on failure
            )

        # Map NodeKind to NodeType
        try:
            node_type = self._map_to_node_type()
        except ValueError as e:
            return PrimitiveResult.fail(self.kind, str(e)), graph

        # Create and add the node
        node = GraphNode(
            id=self.node_id,
            node_type=node_type,
            attrs=self.attrs_dict,
        )
        new_graph.add_node(node)

        return (
            PrimitiveResult.ok(
                self.kind,
                affected=[self.node_id],
                position=self.position.to_dict() if self.position else None,
            ),
            new_graph,
        )

    def _map_to_node_type(self) -> Any:
        """Map NodeKind to existing NodeType enum."""
        from ..typed_graph import NodeType

        mapping = {
            NodeKind.CALLABLE: NodeType.FUNCTION,
            NodeKind.TYPE: NodeType.CLASS,
            NodeKind.BINDING: NodeType.FIELD,
            NodeKind.CONTAINER: NodeType.MODULE,
            NodeKind.REFERENCE: NodeType.IMPORT,
            NodeKind.CALL: NodeType.CALL,
            NodeKind.ARGUMENT: NodeType.ARGUMENT,
            NodeKind.BLOCK: NodeType.BLOCK,
            NodeKind.BRANCH: NodeType.BRANCH,
            NodeKind.LOOP: NodeType.LOOP,
            NodeKind.EXPRESSION: NodeType.EXPRESSION,
            NodeKind.LITERAL: NodeType.LITERAL,
            NodeKind.ANNOTATION: NodeType.ANNOTATION,
        }

        if self.node_kind not in mapping:
            attrs_dict = self.attrs_dict
            if "node_type" in attrs_dict:
                return NodeType(attrs_dict["node_type"])
            raise ValueError(f"Cannot map NodeKind.{self.node_kind.name} to NodeType")

        return mapping[self.node_kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "insert_node",
            "node_id": self.node_id,
            "node_kind": self.node_kind.value,
            "attrs": self.attrs_dict,
            "position": self.position.to_dict() if self.position else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InsertNode:
        return cls(
            node_id=data["node_id"],
            node_kind=NodeKind(data["node_kind"]),
            attrs=data.get("attrs", {}),
            position=Position.from_dict(data["position"]) if data.get("position") else None,
        )


@dataclass(frozen=True)
class InsertEdge(Primitive):
    """Insert a new edge into the graph.

    IMMUTABLE: Does not mutate input graph, returns new graph.

    Examples:
        # Add method to class
        InsertEdge(
            source="class:MyClass",
            target="func:MyClass.new_method",
            edge_kind=EdgeKind.CONTAINS,
        )
    """

    source: str
    target: str
    edge_kind: EdgeKind
    attrs: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    position: EdgePosition | None = None

    def __init__(
        self,
        source: str,
        target: str,
        edge_kind: EdgeKind,
        attrs: dict[str, Any] | tuple[tuple[str, Any], ...] | None = None,
        position: EdgePosition | None = None,
    ):
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "edge_kind", edge_kind)
        object.__setattr__(self, "position", position)

        if attrs is None:
            object.__setattr__(self, "attrs", ())
        elif isinstance(attrs, dict):
            object.__setattr__(self, "attrs", tuple(attrs.items()))
        else:
            object.__setattr__(self, "attrs", attrs)

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.INSERT

    @property
    def attrs_dict(self) -> dict[str, Any]:
        return dict(self.attrs)

    def apply(self, graph: TypedGraph) -> tuple[PrimitiveResult, TypedGraph]:
        """Add the edge to a copy of the graph."""
        from ..typed_graph import EdgeType, GraphEdge

        new_graph = graph.copy()

        # Check source and target exist
        if not new_graph.has_node(self.source):
            return (
                PrimitiveResult.fail(
                    self.kind,
                    f"Source node '{self.source}' does not exist",
                ),
                graph,
            )
        if not new_graph.has_node(self.target):
            return (
                PrimitiveResult.fail(
                    self.kind,
                    f"Target node '{self.target}' does not exist",
                ),
                graph,
            )

        # Map EdgeKind to EdgeType
        try:
            edge_type = self._map_to_edge_type()
        except ValueError as e:
            return PrimitiveResult.fail(self.kind, str(e)), graph

        # Create and add the edge
        edge = GraphEdge(
            source=self.source,
            target=self.target,
            edge_type=edge_type,
            attrs=self.attrs_dict,
        )
        new_graph.add_edge(edge)

        edge_id = f"{self.source}->{self.target}:{self.edge_kind.value}"
        return PrimitiveResult.ok(self.kind, affected=[edge_id]), new_graph

    def _map_to_edge_type(self) -> Any:
        """Map EdgeKind to existing EdgeType enum."""
        from ..typed_graph import EdgeType

        mapping = {
            EdgeKind.CONTAINS: EdgeType.CONTAINS,
            EdgeKind.CALLS: EdgeType.CALLS,
            EdgeKind.INHERITS: EdgeType.INHERITS,
            EdgeKind.IMPORTS: EdgeType.IMPORTS,
            EdgeKind.EXPORTS: EdgeType.EXPORTS,
            EdgeKind.DEFINES: EdgeType.DEFINED_IN,
            EdgeKind.REFERENCES: EdgeType.REFERENCES,
            EdgeKind.HAS_PARAMETER: EdgeType.HAS_PARAMETER,
            EdgeKind.HAS_ARGUMENT: EdgeType.HAS_ARGUMENT,
        }

        if self.edge_kind not in mapping:
            attrs_dict = self.attrs_dict
            if "edge_type" in attrs_dict:
                return EdgeType(attrs_dict["edge_type"])
            raise ValueError(f"Cannot map EdgeKind.{self.edge_kind.name} to EdgeType")

        return mapping[self.edge_kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "insert_edge",
            "source": self.source,
            "target": self.target,
            "edge_kind": self.edge_kind.value,
            "attrs": self.attrs_dict,
            "position": self.position.to_dict() if self.position else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InsertEdge:
        return cls(
            source=data["source"],
            target=data["target"],
            edge_kind=EdgeKind(data["edge_kind"]),
            attrs=data.get("attrs", {}),
            position=EdgePosition.from_dict(data["position"]) if data.get("position") else None,
        )


# =============================================================================
# DELETE Primitive
# =============================================================================


@dataclass(frozen=True)
class DeleteNode(Primitive):
    """Delete a node from the graph.

    IMMUTABLE: Does not mutate input graph, returns new graph.
    By default, also removes all edges connected to the node (cascade).

    Examples:
        # Remove a function
        DeleteNode(node_id="func:old_helper")

        # Remove without cascading edges (will fail if edges exist)
        DeleteNode(node_id="func:old_helper", cascade=False)
    """

    node_id: str
    cascade: bool = True

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.DELETE

    def apply(self, graph: TypedGraph) -> tuple[PrimitiveResult, TypedGraph]:
        """Remove the node from a copy of the graph."""
        new_graph = graph.copy()

        # Check node exists
        if not new_graph.has_node(self.node_id):
            return (
                PrimitiveResult.fail(
                    self.kind,
                    f"Node '{self.node_id}' does not exist",
                ),
                graph,
            )

        affected = [self.node_id]

        # Handle edges
        incident_edges = (
            new_graph.get_edges_from(self.node_id) +
            new_graph.get_edges_to(self.node_id)
        )

        if incident_edges and not self.cascade:
            return (
                PrimitiveResult.fail(
                    self.kind,
                    f"Node '{self.node_id}' has {len(incident_edges)} connected edges. "
                    "Use cascade=True to remove them.",
                ),
                graph,
            )

        # Remove node (TypedGraph.remove_node handles edge removal)
        new_graph.remove_node(self.node_id)

        # Track removed edges
        for edge in incident_edges:
            edge_id = f"{edge.source}->{edge.target}:{edge.edge_type.value}"
            affected.append(edge_id)

        return (
            PrimitiveResult.ok(self.kind, affected=affected, cascade=self.cascade),
            new_graph,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "delete_node",
            "node_id": self.node_id,
            "cascade": self.cascade,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeleteNode:
        return cls(
            node_id=data["node_id"],
            cascade=data.get("cascade", True),
        )


@dataclass(frozen=True)
class DeleteEdge(Primitive):
    """Delete an edge from the graph.

    IMMUTABLE: Does not mutate input graph, returns new graph.

    Examples:
        # Remove specific edge
        DeleteEdge(
            source="class:MyClass",
            target="func:MyClass.old_method",
            edge_kind=EdgeKind.CONTAINS,
        )
    """

    source: str
    target: str
    edge_kind: EdgeKind | None = None  # If None, remove all edges between source/target

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.DELETE

    def apply(self, graph: TypedGraph) -> tuple[PrimitiveResult, TypedGraph]:
        """Remove the edge from a copy of the graph."""
        from ..typed_graph import EdgeType

        new_graph = graph.copy()

        # Find matching edges
        if self.edge_kind:
            edge_type = self._map_to_edge_type()
            edges = new_graph.get_edges_between(self.source, self.target, edge_type)

            # For CONTAINS kind, also check related containment types
            if not edges and self.edge_kind == EdgeKind.CONTAINS:
                for alt_type in [EdgeType.CONTAINS_METHOD, EdgeType.CONTAINS_FIELD]:
                    edges = new_graph.get_edges_between(self.source, self.target, alt_type)
                    if edges:
                        break
        else:
            edges = new_graph.get_edges_between(self.source, self.target)

        if not edges:
            return (
                PrimitiveResult.fail(
                    self.kind,
                    f"No edge found from '{self.source}' to '{self.target}'"
                    + (f" of kind {self.edge_kind.value}" if self.edge_kind else ""),
                ),
                graph,
            )

        # Remove edges
        affected = []
        for edge in edges:
            new_graph.remove_edge(edge.source, edge.target, edge.edge_type)
            edge_id = f"{edge.source}->{edge.target}:{edge.edge_type.value}"
            affected.append(edge_id)

        return PrimitiveResult.ok(self.kind, affected=affected), new_graph

    def _map_to_edge_type(self) -> Any:
        """Map EdgeKind to EdgeType."""
        from ..typed_graph import EdgeType

        if self.edge_kind is None:
            return None

        mapping = {
            EdgeKind.CONTAINS: EdgeType.CONTAINS,
            EdgeKind.CALLS: EdgeType.CALLS,
            EdgeKind.INHERITS: EdgeType.INHERITS,
            EdgeKind.IMPORTS: EdgeType.IMPORTS,
            EdgeKind.EXPORTS: EdgeType.EXPORTS,
            EdgeKind.DEFINES: EdgeType.DEFINED_IN,
            EdgeKind.REFERENCES: EdgeType.REFERENCES,
            EdgeKind.HAS_PARAMETER: EdgeType.HAS_PARAMETER,
            EdgeKind.HAS_ARGUMENT: EdgeType.HAS_ARGUMENT,
        }
        return mapping.get(self.edge_kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "delete_edge",
            "source": self.source,
            "target": self.target,
            "edge_kind": self.edge_kind.value if self.edge_kind else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeleteEdge:
        return cls(
            source=data["source"],
            target=data["target"],
            edge_kind=EdgeKind(data["edge_kind"]) if data.get("edge_kind") else None,
        )


# =============================================================================
# UPDATE Primitive
# =============================================================================


@dataclass(frozen=True)
class Update(Primitive):
    """Update a property of an existing node or edge.

    IMMUTABLE: Does not mutate input graph, returns new graph.

    Examples:
        # Rename a function
        Update(
            target="func:old_name",
            prop="name",
            value="new_name",
        )

        # Update multiple properties
        Update(
            target="func:my_func",
            properties={"name": "new_name", "is_async": True},
        )
    """

    target: str  # Node ID or edge identifier
    prop: str | None = None  # Single property to update
    value: Any = None  # New value for single property
    properties: tuple[tuple[str, Any], ...] | None = None  # Multiple properties

    def __init__(
        self,
        target: str,
        prop: str | None = None,
        value: Any = None,
        properties: dict[str, Any] | tuple[tuple[str, Any], ...] | None = None,
    ):
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "prop", prop)
        object.__setattr__(self, "value", value)

        if properties is None:
            object.__setattr__(self, "properties", None)
        elif isinstance(properties, dict):
            object.__setattr__(self, "properties", tuple(properties.items()))
        else:
            object.__setattr__(self, "properties", properties)

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.UPDATE

    @property
    def properties_dict(self) -> dict[str, Any] | None:
        if self.properties is None:
            return None
        return dict(self.properties)

    def apply(self, graph: TypedGraph) -> tuple[PrimitiveResult, TypedGraph]:
        """Update the target element's properties in a copy of the graph."""
        new_graph = graph.copy()

        # Build updates dict
        updates = {}
        if self.properties:
            updates.update(self.properties_dict)
        if self.prop is not None:
            updates[self.prop] = self.value

        if not updates:
            return (
                PrimitiveResult.fail(
                    self.kind,
                    "No properties to update",
                ),
                graph,
            )

        # Check if target is a node
        node = new_graph.get_node(self.target)
        if node:
            old_values = {k: node.attrs.get(k) for k in updates}
            node.attrs.update(updates)
            return (
                PrimitiveResult.ok(
                    self.kind,
                    affected=[self.target],
                    old_values=old_values,
                    new_values=updates,
                ),
                new_graph,
            )

        # Check if target is an edge (format: "source->target:edge_type")
        if "->" in self.target:
            edge_result, new_graph = self._update_edge(new_graph, graph, updates)
            if edge_result:
                return edge_result, new_graph

        return (
            PrimitiveResult.fail(
                self.kind,
                f"Target '{self.target}' not found (not a node or edge)",
            ),
            graph,
        )

    def _update_edge(
        self, new_graph: TypedGraph, original_graph: TypedGraph, updates: dict[str, Any]
    ) -> tuple[PrimitiveResult | None, TypedGraph]:
        """Try to update an edge."""
        # Parse edge identifier: "source->target:edge_type"
        try:
            parts = self.target.split("->")
            source = parts[0]
            rest = parts[1]
            if ":" in rest:
                target, edge_type_str = rest.rsplit(":", 1)
            else:
                target = rest
                edge_type_str = None
        except (IndexError, ValueError):
            return None, original_graph

        # Find the edge
        edges = new_graph.get_edges_between(source, target)
        if edge_type_str:
            edges = [e for e in edges if e.edge_type.value == edge_type_str]

        if not edges:
            return None, original_graph

        # Update edge attributes
        old_values = {}
        for edge in edges:
            old_values.update({k: edge.attrs.get(k) for k in updates})
            edge.attrs.update(updates)

        return (
            PrimitiveResult.ok(
                self.kind,
                affected=[self.target],
                old_values=old_values,
                new_values=updates,
            ),
            new_graph,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "update",
            "target": self.target,
            "prop": self.prop,
            "value": self.value,
            "properties": self.properties_dict,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Update:
        return cls(
            target=data["target"],
            prop=data.get("prop"),
            value=data.get("value"),
            properties=data.get("properties"),
        )


# =============================================================================
# Factory Functions
# =============================================================================


def insert_node(
    node_id: str,
    node_kind: NodeKind,
    attrs: dict[str, Any] | None = None,
    position: Position | None = None,
) -> InsertNode:
    """Create an INSERT node primitive."""
    return InsertNode(
        node_id=node_id,
        node_kind=node_kind,
        attrs=attrs or {},
        position=position,
    )


def insert_edge(
    source: str,
    target: str,
    edge_kind: EdgeKind,
    attrs: dict[str, Any] | None = None,
) -> InsertEdge:
    """Create an INSERT edge primitive."""
    return InsertEdge(
        source=source,
        target=target,
        edge_kind=edge_kind,
        attrs=attrs or {},
    )


def delete_node(node_id: str, cascade: bool = True) -> DeleteNode:
    """Create a DELETE node primitive."""
    return DeleteNode(node_id=node_id, cascade=cascade)


def delete_edge(
    source: str,
    target: str,
    edge_kind: EdgeKind | None = None,
) -> DeleteEdge:
    """Create a DELETE edge primitive."""
    return DeleteEdge(source=source, target=target, edge_kind=edge_kind)


def update(
    target: str,
    prop: str | None = None,
    value: Any = None,
    **properties: Any,
) -> Update:
    """Create an UPDATE primitive.

    Can be used with single property:
        update("func:foo", "name", "bar")

    Or multiple properties:
        update("func:foo", name="bar", is_async=True)
    """
    if properties:
        return Update(target=target, properties=properties)
    return Update(target=target, prop=prop, value=value)


# =============================================================================
# Primitive Deserialization
# =============================================================================


def primitive_from_dict(data: dict[str, Any]) -> Primitive:
    """Deserialize a primitive from dictionary."""
    primitive_type = data.get("primitive")

    if primitive_type == "insert_node":
        return InsertNode.from_dict(data)
    elif primitive_type == "insert_edge":
        return InsertEdge.from_dict(data)
    elif primitive_type == "delete_node":
        return DeleteNode.from_dict(data)
    elif primitive_type == "delete_edge":
        return DeleteEdge.from_dict(data)
    elif primitive_type == "update":
        return Update.from_dict(data)
    else:
        raise ValueError(f"Unknown primitive type: {primitive_type}")
