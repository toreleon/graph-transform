"""
The Three Primitive Operators

All code transformations reduce to these three atomic operations:
- INSERT: Add a node or edge to the graph
- DELETE: Remove a node or edge from the graph
- UPDATE: Modify a property of an existing element

Every refactoring, migration, and code fix is a composition of these primitives.
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
    """Base class for all primitive operations."""

    @property
    @abstractmethod
    def kind(self) -> PrimitiveKind:
        """Return the primitive kind."""
        ...

    @abstractmethod
    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Execute this primitive on the graph.

        Modifies the graph in place and returns the result.
        """
        ...

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


@dataclass
class InsertNode(Primitive):
    """Insert a new node into the graph.

    This is the atomic operation for adding any code element:
    functions, classes, variables, imports, etc.

    Examples:
        # Add a new function
        InsertNode(
            node_id="func:new_helper",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "new_helper", "file": "utils.py", "line": 10},
            position=Position.at_end_of("module:utils"),
        )

        # Add a parameter to a function
        InsertNode(
            node_id="param:my_func.new_param",
            node_kind=NodeKind.BINDING,
            attrs={"name": "new_param", "position": 2},
            position=Position.in_slot("func:my_func", "parameters"),
        )
    """

    node_id: str
    node_kind: NodeKind
    attrs: dict[str, Any] = field(default_factory=dict)
    position: Position | None = None

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.INSERT

    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Add the node to the graph."""
        from ..typed_graph import GraphNode, NodeType

        # Check if node already exists
        if graph.has_node(self.node_id):
            return PrimitiveResult.fail(
                self.kind,
                f"Node '{self.node_id}' already exists",
            )

        # Map NodeKind to NodeType
        try:
            node_type = self._map_to_node_type()
        except ValueError as e:
            return PrimitiveResult.fail(self.kind, str(e))

        # Create and add the node
        node = GraphNode(
            id=self.node_id,
            node_type=node_type,
            attrs=self.attrs.copy(),
        )
        graph.add_node(node)

        return PrimitiveResult.ok(
            self.kind,
            affected=[self.node_id],
            position=self.position.to_dict() if self.position else None,
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
            # For kinds not in existing NodeType, check attrs for hint
            if "node_type" in self.attrs:
                return NodeType(self.attrs["node_type"])
            # Default to most general available type
            raise ValueError(f"Cannot map NodeKind.{self.node_kind.name} to NodeType")

        return mapping[self.node_kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "insert_node",
            "node_id": self.node_id,
            "node_kind": self.node_kind.value,
            "attrs": self.attrs,
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


@dataclass
class InsertEdge(Primitive):
    """Insert a new edge into the graph.

    This is the atomic operation for adding relationships:
    containment, calls, inheritance, etc.

    Examples:
        # Add method to class
        InsertEdge(
            source="class:MyClass",
            target="func:MyClass.new_method",
            edge_kind=EdgeKind.CONTAINS,
        )

        # Add call relationship
        InsertEdge(
            source="call:foo.py:10:0",
            target="func:helper",
            edge_kind=EdgeKind.CALLS,
        )
    """

    source: str
    target: str
    edge_kind: EdgeKind
    attrs: dict[str, Any] = field(default_factory=dict)
    position: EdgePosition | None = None

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.INSERT

    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Add the edge to the graph."""
        from ..typed_graph import EdgeType, GraphEdge

        # Check source and target exist
        if not graph.has_node(self.source):
            return PrimitiveResult.fail(
                self.kind,
                f"Source node '{self.source}' does not exist",
            )
        if not graph.has_node(self.target):
            return PrimitiveResult.fail(
                self.kind,
                f"Target node '{self.target}' does not exist",
            )

        # Map EdgeKind to EdgeType
        try:
            edge_type = self._map_to_edge_type()
        except ValueError as e:
            return PrimitiveResult.fail(self.kind, str(e))

        # Create and add the edge
        edge = GraphEdge(
            source=self.source,
            target=self.target,
            edge_type=edge_type,
            attrs=self.attrs.copy(),
        )
        graph.add_edge(edge)

        edge_id = f"{self.source}->{self.target}:{self.edge_kind.value}"
        return PrimitiveResult.ok(self.kind, affected=[edge_id])

    def _map_to_edge_type(self) -> Any:
        """Map EdgeKind to existing EdgeType enum."""
        from ..typed_graph import EdgeType

        mapping = {
            EdgeKind.CONTAINS: EdgeType.CONTAINS_METHOD,  # May need context
            EdgeKind.CALLS: EdgeType.CALLS,
            EdgeKind.INHERITS: EdgeType.INHERITS,
            EdgeKind.IMPORTS: EdgeType.IMPORTS,
            EdgeKind.DEFINES: EdgeType.DEFINED_IN,
            EdgeKind.REFERENCES: EdgeType.REFERENCES,
            EdgeKind.HAS_PARAMETER: EdgeType.HAS_PARAMETER,
            EdgeKind.HAS_ARGUMENT: EdgeType.HAS_ARGUMENT,
        }

        if self.edge_kind not in mapping:
            if "edge_type" in self.attrs:
                return EdgeType(self.attrs["edge_type"])
            raise ValueError(f"Cannot map EdgeKind.{self.edge_kind.name} to EdgeType")

        return mapping[self.edge_kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "insert_edge",
            "source": self.source,
            "target": self.target,
            "edge_kind": self.edge_kind.value,
            "attrs": self.attrs,
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


@dataclass
class DeleteNode(Primitive):
    """Delete a node from the graph.

    This is the atomic operation for removing any code element.
    By default, also removes all edges connected to the node (cascade).

    Examples:
        # Remove a function
        DeleteNode(node_id="func:old_helper")

        # Remove without cascading edges (will fail if edges exist)
        DeleteNode(node_id="func:old_helper", cascade=False)
    """

    node_id: str
    cascade: bool = True  # Also remove connected edges

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.DELETE

    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Remove the node from the graph."""
        # Check node exists
        if not graph.has_node(self.node_id):
            return PrimitiveResult.fail(
                self.kind,
                f"Node '{self.node_id}' does not exist",
            )

        affected = [self.node_id]

        # Handle edges
        incident_edges = (
            graph.get_edges_from(self.node_id) +
            graph.get_edges_to(self.node_id)
        )

        if incident_edges and not self.cascade:
            return PrimitiveResult.fail(
                self.kind,
                f"Node '{self.node_id}' has {len(incident_edges)} connected edges. "
                "Use cascade=True to remove them.",
            )

        # Remove node (TypedGraph.remove_node handles edge removal)
        graph.remove_node(self.node_id)

        # Track removed edges
        for edge in incident_edges:
            edge_id = f"{edge.source}->{edge.target}:{edge.edge_type.value}"
            affected.append(edge_id)

        return PrimitiveResult.ok(self.kind, affected=affected, cascade=self.cascade)

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


@dataclass
class DeleteEdge(Primitive):
    """Delete an edge from the graph.

    This is the atomic operation for removing relationships.

    Examples:
        # Remove specific edge
        DeleteEdge(
            source="class:MyClass",
            target="func:MyClass.old_method",
            edge_kind=EdgeKind.CONTAINS,
        )

        # Remove all edges between two nodes
        DeleteEdge(
            source="class:MyClass",
            target="func:MyClass.old_method",
        )
    """

    source: str
    target: str
    edge_kind: EdgeKind | None = None  # If None, remove all edges between source/target

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.DELETE

    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Remove the edge from the graph."""
        from ..typed_graph import EdgeType

        # Find matching edges
        if self.edge_kind:
            edge_type = self._map_to_edge_type()
            edges = graph.get_edges_between(self.source, self.target, edge_type)
        else:
            edges = graph.get_edges_between(self.source, self.target)

        if not edges:
            return PrimitiveResult.fail(
                self.kind,
                f"No edge found from '{self.source}' to '{self.target}'"
                + (f" of kind {self.edge_kind.value}" if self.edge_kind else ""),
            )

        # Remove edges
        affected = []
        for edge in edges:
            graph.remove_edge(edge.source, edge.target, edge.edge_type)
            edge_id = f"{edge.source}->{edge.target}:{edge.edge_type.value}"
            affected.append(edge_id)

        return PrimitiveResult.ok(self.kind, affected=affected)

    def _map_to_edge_type(self) -> Any:
        """Map EdgeKind to EdgeType."""
        from ..typed_graph import EdgeType

        if self.edge_kind is None:
            return None

        mapping = {
            EdgeKind.CONTAINS: EdgeType.CONTAINS_METHOD,
            EdgeKind.CALLS: EdgeType.CALLS,
            EdgeKind.INHERITS: EdgeType.INHERITS,
            EdgeKind.IMPORTS: EdgeType.IMPORTS,
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


@dataclass
class Update(Primitive):
    """Update a property of an existing node or edge.

    This is the atomic operation for modifying attributes:
    renaming, changing types, updating values, etc.

    Examples:
        # Rename a function
        Update(
            target="func:old_name",
            property="name",
            value="new_name",
        )

        # Change parameter default value
        Update(
            target="param:my_func.x",
            property="default_value",
            value="42",
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
    properties: dict[str, Any] | None = None  # Multiple properties to update

    @property
    def kind(self) -> PrimitiveKind:
        return PrimitiveKind.UPDATE

    def execute(self, graph: TypedGraph) -> PrimitiveResult:
        """Update the target element's properties."""
        # Build updates dict
        updates = {}
        if self.properties:
            updates.update(self.properties)
        if self.prop is not None:
            updates[self.prop] = self.value

        if not updates:
            return PrimitiveResult.fail(
                self.kind,
                "No properties to update",
            )

        # Check if target is a node
        node = graph.get_node(self.target)
        if node:
            old_values = {k: node.attrs.get(k) for k in updates}
            node.attrs.update(updates)
            return PrimitiveResult.ok(
                self.kind,
                affected=[self.target],
                old_values=old_values,
                new_values=updates,
            )

        # Check if target is an edge (format: "source->target:edge_type")
        if "->" in self.target:
            edge_result = self._update_edge(graph, updates)
            if edge_result:
                return edge_result

        return PrimitiveResult.fail(
            self.kind,
            f"Target '{self.target}' not found (not a node or edge)",
        )

    def _update_edge(
        self, graph: TypedGraph, updates: dict[str, Any]
    ) -> PrimitiveResult | None:
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
            return None

        # Find the edge
        edges = graph.get_edges_between(source, target)
        if edge_type_str:
            edges = [e for e in edges if e.edge_type.value == edge_type_str]

        if not edges:
            return None

        # Update edge attributes
        old_values = {}
        for edge in edges:
            old_values.update({k: edge.attrs.get(k) for k in updates})
            edge.attrs.update(updates)

        return PrimitiveResult.ok(
            self.kind,
            affected=[self.target],
            old_values=old_values,
            new_values=updates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": "update",
            "target": self.target,
            "prop": self.prop,
            "value": self.value,
            "properties": self.properties,
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
