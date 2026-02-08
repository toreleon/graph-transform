"""
Tests for the Three Primitives (INSERT, DELETE, UPDATE)

These tests verify that the fundamental operators work correctly
on the TypedGraph.
"""

import pytest

from graph_transform.core.typed_graph import (
    TypedGraph,
    GraphNode,
    GraphEdge,
    NodeType,
    EdgeType,
)
from graph_transform.core.primitives import (
    # Primitives
    InsertNode,
    InsertEdge,
    DeleteNode,
    DeleteEdge,
    Update,
    # Factory functions
    insert_node,
    insert_edge,
    delete_node,
    delete_edge,
    update,
    # Enums
    NodeKind,
    EdgeKind,
    PrimitiveKind,
    # Position
    Position,
    Relation,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_graph() -> TypedGraph:
    """Create an empty graph."""
    return TypedGraph()


@pytest.fixture
def simple_graph() -> TypedGraph:
    """Create a graph with a class and method."""
    graph = TypedGraph()

    # Add a class
    graph.add_node(GraphNode(
        id="class:MyClass",
        node_type=NodeType.CLASS,
        attrs={"name": "MyClass", "file": "test.py", "line": 1},
    ))

    # Add a method
    graph.add_node(GraphNode(
        id="func:MyClass.my_method",
        node_type=NodeType.FUNCTION,
        attrs={"name": "my_method", "file": "test.py", "line": 5, "is_method": True},
    ))

    # Add containment edge
    graph.add_edge(GraphEdge(
        source="class:MyClass",
        target="func:MyClass.my_method",
        edge_type=EdgeType.CONTAINS_METHOD,
    ))

    return graph


@pytest.fixture
def graph_with_calls() -> TypedGraph:
    """Create a graph with call relationships."""
    graph = TypedGraph()

    # Add functions
    graph.add_node(GraphNode(
        id="func:caller",
        node_type=NodeType.FUNCTION,
        attrs={"name": "caller", "file": "test.py", "line": 1},
    ))
    graph.add_node(GraphNode(
        id="func:callee",
        node_type=NodeType.FUNCTION,
        attrs={"name": "callee", "file": "test.py", "line": 10},
    ))

    # Add call node
    graph.add_node(GraphNode(
        id="call:test.py:5:0",
        node_type=NodeType.CALL,
        attrs={"callee": "callee", "file": "test.py", "line": 5},
    ))

    # Add edges
    graph.add_edge(GraphEdge(
        source="call:test.py:5:0",
        target="func:callee",
        edge_type=EdgeType.CALLS,
    ))
    graph.add_edge(GraphEdge(
        source="func:caller",
        target="call:test.py:5:0",
        edge_type=EdgeType.CALLER_OF,
    ))

    return graph


# =============================================================================
# INSERT Node Tests
# =============================================================================


class TestInsertNode:
    """Tests for InsertNode primitive."""

    def test_insert_node_basic(self, empty_graph: TypedGraph) -> None:
        """Test basic node insertion."""
        primitive = InsertNode(
            node_id="func:new_func",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "new_func", "file": "test.py", "line": 1},
        )

        result = primitive.execute(empty_graph)

        assert result.success
        assert result.primitive_kind == PrimitiveKind.INSERT
        assert "func:new_func" in result.affected_ids
        assert empty_graph.has_node("func:new_func")

        node = empty_graph.get_node("func:new_func")
        assert node is not None
        assert node.attrs["name"] == "new_func"

    def test_insert_node_with_position(self, simple_graph: TypedGraph) -> None:
        """Test insertion with position specification."""
        primitive = InsertNode(
            node_id="func:MyClass.new_method",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "new_method", "is_method": True},
            position=Position.at_end_of("class:MyClass"),
        )

        result = primitive.execute(simple_graph)

        assert result.success
        assert simple_graph.has_node("func:MyClass.new_method")
        assert result.metadata.get("position") is not None

    def test_insert_duplicate_node_fails(self, simple_graph: TypedGraph) -> None:
        """Test that inserting duplicate node fails."""
        primitive = InsertNode(
            node_id="class:MyClass",  # Already exists
            node_kind=NodeKind.TYPE,
            attrs={"name": "MyClass"},
        )

        result = primitive.execute(simple_graph)

        assert not result.success
        assert "already exists" in result.error

    def test_insert_different_node_kinds(self, empty_graph: TypedGraph) -> None:
        """Test inserting various node kinds."""
        kinds_to_test = [
            (NodeKind.CALLABLE, "func:test"),
            (NodeKind.TYPE, "class:Test"),
            (NodeKind.REFERENCE, "import:test:os"),
            (NodeKind.CONTAINER, "module:test"),
        ]

        for kind, node_id in kinds_to_test:
            primitive = InsertNode(
                node_id=node_id,
                node_kind=kind,
                attrs={"name": node_id.split(":")[-1]},
            )
            result = primitive.execute(empty_graph)
            assert result.success, f"Failed for {kind}: {result.error}"
            assert empty_graph.has_node(node_id)

    def test_insert_node_factory_function(self, empty_graph: TypedGraph) -> None:
        """Test the insert_node factory function."""
        primitive = insert_node(
            "func:helper",
            NodeKind.CALLABLE,
            attrs={"name": "helper"},
        )

        result = primitive.execute(empty_graph)
        assert result.success
        assert empty_graph.has_node("func:helper")


# =============================================================================
# INSERT Edge Tests
# =============================================================================


class TestInsertEdge:
    """Tests for InsertEdge primitive."""

    def test_insert_edge_basic(self, simple_graph: TypedGraph) -> None:
        """Test basic edge insertion."""
        # First add another method
        simple_graph.add_node(GraphNode(
            id="func:MyClass.helper",
            node_type=NodeType.FUNCTION,
            attrs={"name": "helper"},
        ))

        primitive = InsertEdge(
            source="class:MyClass",
            target="func:MyClass.helper",
            edge_kind=EdgeKind.CONTAINS,
        )

        result = primitive.execute(simple_graph)

        assert result.success
        assert simple_graph.has_edge("class:MyClass", "func:MyClass.helper")

    def test_insert_edge_missing_source_fails(self, simple_graph: TypedGraph) -> None:
        """Test that edge with missing source fails."""
        primitive = InsertEdge(
            source="class:NonExistent",
            target="func:MyClass.my_method",
            edge_kind=EdgeKind.CONTAINS,
        )

        result = primitive.execute(simple_graph)

        assert not result.success
        assert "does not exist" in result.error

    def test_insert_edge_missing_target_fails(self, simple_graph: TypedGraph) -> None:
        """Test that edge with missing target fails."""
        primitive = InsertEdge(
            source="class:MyClass",
            target="func:NonExistent",
            edge_kind=EdgeKind.CALLS,
        )

        result = primitive.execute(simple_graph)

        assert not result.success
        assert "does not exist" in result.error

    def test_insert_edge_factory_function(self, simple_graph: TypedGraph) -> None:
        """Test the insert_edge factory function."""
        simple_graph.add_node(GraphNode(
            id="func:other",
            node_type=NodeType.FUNCTION,
            attrs={"name": "other"},
        ))

        primitive = insert_edge(
            "class:MyClass",
            "func:other",
            EdgeKind.CONTAINS,
        )

        result = primitive.execute(simple_graph)
        assert result.success


# =============================================================================
# DELETE Node Tests
# =============================================================================


class TestDeleteNode:
    """Tests for DeleteNode primitive."""

    def test_delete_node_basic(self, simple_graph: TypedGraph) -> None:
        """Test basic node deletion with cascade."""
        initial_edge_count = simple_graph.edge_count

        primitive = DeleteNode(node_id="func:MyClass.my_method", cascade=True)
        result = primitive.execute(simple_graph)

        assert result.success
        assert not simple_graph.has_node("func:MyClass.my_method")
        # Edge should also be removed
        assert simple_graph.edge_count < initial_edge_count

    def test_delete_node_no_cascade_with_edges_fails(self, simple_graph: TypedGraph) -> None:
        """Test that deleting node without cascade fails if edges exist."""
        primitive = DeleteNode(node_id="func:MyClass.my_method", cascade=False)
        result = primitive.execute(simple_graph)

        assert not result.success
        assert "connected edges" in result.error
        # Node should still exist
        assert simple_graph.has_node("func:MyClass.my_method")

    def test_delete_nonexistent_node_fails(self, simple_graph: TypedGraph) -> None:
        """Test that deleting nonexistent node fails."""
        primitive = DeleteNode(node_id="func:NonExistent")
        result = primitive.execute(simple_graph)

        assert not result.success
        assert "does not exist" in result.error

    def test_delete_node_factory_function(self, empty_graph: TypedGraph) -> None:
        """Test the delete_node factory function."""
        # First add a node
        empty_graph.add_node(GraphNode(
            id="func:to_delete",
            node_type=NodeType.FUNCTION,
            attrs={"name": "to_delete"},
        ))

        primitive = delete_node("func:to_delete")
        result = primitive.execute(empty_graph)

        assert result.success
        assert not empty_graph.has_node("func:to_delete")


# =============================================================================
# DELETE Edge Tests
# =============================================================================


class TestDeleteEdge:
    """Tests for DeleteEdge primitive."""

    def test_delete_edge_basic(self, simple_graph: TypedGraph) -> None:
        """Test basic edge deletion."""
        primitive = DeleteEdge(
            source="class:MyClass",
            target="func:MyClass.my_method",
            edge_kind=EdgeKind.CONTAINS,
        )

        result = primitive.execute(simple_graph)

        assert result.success
        assert not simple_graph.has_edge("class:MyClass", "func:MyClass.my_method")
        # Nodes should still exist
        assert simple_graph.has_node("class:MyClass")
        assert simple_graph.has_node("func:MyClass.my_method")

    def test_delete_edge_without_kind(self, simple_graph: TypedGraph) -> None:
        """Test deleting all edges between two nodes."""
        primitive = DeleteEdge(
            source="class:MyClass",
            target="func:MyClass.my_method",
            edge_kind=None,  # Delete all
        )

        result = primitive.execute(simple_graph)

        assert result.success
        assert not simple_graph.has_edge("class:MyClass", "func:MyClass.my_method")

    def test_delete_nonexistent_edge_fails(self, simple_graph: TypedGraph) -> None:
        """Test that deleting nonexistent edge fails."""
        primitive = DeleteEdge(
            source="class:MyClass",
            target="class:MyClass",  # No self-edge exists
        )

        result = primitive.execute(simple_graph)

        assert not result.success
        assert "No edge found" in result.error

    def test_delete_edge_factory_function(self, simple_graph: TypedGraph) -> None:
        """Test the delete_edge factory function."""
        primitive = delete_edge(
            "class:MyClass",
            "func:MyClass.my_method",
            EdgeKind.CONTAINS,
        )

        result = primitive.execute(simple_graph)
        assert result.success


# =============================================================================
# UPDATE Tests
# =============================================================================


class TestUpdate:
    """Tests for Update primitive."""

    def test_update_single_property(self, simple_graph: TypedGraph) -> None:
        """Test updating a single property."""
        primitive = Update(
            target="func:MyClass.my_method",
            prop="name",
            value="renamed_method",
        )

        result = primitive.execute(simple_graph)

        assert result.success
        node = simple_graph.get_node("func:MyClass.my_method")
        assert node is not None
        assert node.attrs["name"] == "renamed_method"

    def test_update_multiple_properties(self, simple_graph: TypedGraph) -> None:
        """Test updating multiple properties at once."""
        primitive = Update(
            target="func:MyClass.my_method",
            properties={
                "name": "new_name",
                "is_async": True,
                "line": 100,
            },
        )

        result = primitive.execute(simple_graph)

        assert result.success
        node = simple_graph.get_node("func:MyClass.my_method")
        assert node is not None
        assert node.attrs["name"] == "new_name"
        assert node.attrs["is_async"] is True
        assert node.attrs["line"] == 100

    def test_update_nonexistent_node_fails(self, simple_graph: TypedGraph) -> None:
        """Test that updating nonexistent node fails."""
        primitive = Update(
            target="func:NonExistent",
            prop="name",
            value="new_name",
        )

        result = primitive.execute(simple_graph)

        assert not result.success
        assert "not found" in result.error

    def test_update_preserves_old_values(self, simple_graph: TypedGraph) -> None:
        """Test that old values are preserved in result."""
        node = simple_graph.get_node("func:MyClass.my_method")
        old_name = node.attrs["name"]

        primitive = Update(
            target="func:MyClass.my_method",
            prop="name",
            value="new_name",
        )

        result = primitive.execute(simple_graph)

        assert result.success
        assert result.metadata.get("old_values", {}).get("name") == old_name

    def test_update_factory_function(self, simple_graph: TypedGraph) -> None:
        """Test the update factory function."""
        # Single property
        primitive = update("func:MyClass.my_method", "name", "updated")
        result = primitive.execute(simple_graph)
        assert result.success

        # Multiple properties via kwargs
        primitive = update("func:MyClass.my_method", is_async=True, line=50)
        result = primitive.execute(simple_graph)
        assert result.success

        node = simple_graph.get_node("func:MyClass.my_method")
        assert node.attrs["is_async"] is True
        assert node.attrs["line"] == 50

    def test_update_no_properties_fails(self, simple_graph: TypedGraph) -> None:
        """Test that update with no properties fails."""
        primitive = Update(target="func:MyClass.my_method")
        result = primitive.execute(simple_graph)

        assert not result.success
        assert "No properties" in result.error


# =============================================================================
# Serialization Tests
# =============================================================================


class TestPrimitiveSerialization:
    """Tests for primitive serialization/deserialization."""

    def test_insert_node_roundtrip(self) -> None:
        """Test InsertNode serialization roundtrip."""
        original = InsertNode(
            node_id="func:test",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "test", "line": 10},
            position=Position.at_end_of("module:main"),
        )

        data = original.to_dict()
        restored = InsertNode.from_dict(data)

        assert restored.node_id == original.node_id
        assert restored.node_kind == original.node_kind
        assert restored.attrs == original.attrs
        assert restored.position.scope == original.position.scope

    def test_insert_edge_roundtrip(self) -> None:
        """Test InsertEdge serialization roundtrip."""
        original = InsertEdge(
            source="class:A",
            target="func:A.method",
            edge_kind=EdgeKind.CONTAINS,
            attrs={"order": 1},
        )

        data = original.to_dict()
        restored = InsertEdge.from_dict(data)

        assert restored.source == original.source
        assert restored.target == original.target
        assert restored.edge_kind == original.edge_kind
        assert restored.attrs == original.attrs

    def test_delete_node_roundtrip(self) -> None:
        """Test DeleteNode serialization roundtrip."""
        original = DeleteNode(node_id="func:to_delete", cascade=False)

        data = original.to_dict()
        restored = DeleteNode.from_dict(data)

        assert restored.node_id == original.node_id
        assert restored.cascade == original.cascade

    def test_update_roundtrip(self) -> None:
        """Test Update serialization roundtrip."""
        original = Update(
            target="func:test",
            properties={"name": "new", "line": 20},
        )

        data = original.to_dict()
        restored = Update.from_dict(data)

        assert restored.target == original.target
        assert restored.properties == original.properties


# =============================================================================
# Position Tests
# =============================================================================


class TestPosition:
    """Tests for the Position system."""

    def test_position_at_end_of(self) -> None:
        """Test at_end_of factory."""
        pos = Position.at_end_of("class:MyClass")
        assert pos.scope == "class:MyClass"
        assert pos.relation == Relation.LAST_CHILD

    def test_position_at_start_of(self) -> None:
        """Test at_start_of factory."""
        pos = Position.at_start_of("class:MyClass")
        assert pos.scope == "class:MyClass"
        assert pos.relation == Relation.FIRST_CHILD

    def test_position_before(self) -> None:
        """Test before factory."""
        pos = Position.before("func:method", scope="class:MyClass")
        assert pos.anchor == "func:method"
        assert pos.relation == Relation.BEFORE

    def test_position_after(self) -> None:
        """Test after factory."""
        pos = Position.after("func:method")
        assert pos.anchor == "func:method"
        assert pos.relation == Relation.AFTER

    def test_position_at_index(self) -> None:
        """Test at_index factory."""
        pos = Position.at_index("func:my_func", 2, slot="parameters")
        assert pos.scope == "func:my_func"
        assert pos.index == 2
        assert pos.slot == "parameters"

    def test_position_serialization(self) -> None:
        """Test Position serialization roundtrip."""
        original = Position(
            scope="class:Test",
            anchor="func:method",
            relation=Relation.BEFORE,
            slot="methods",
            index=5,
            metadata={"custom": "value"},
        )

        data = original.to_dict()
        restored = Position.from_dict(data)

        assert restored.scope == original.scope
        assert restored.anchor == original.anchor
        assert restored.relation == original.relation
        assert restored.slot == original.slot
        assert restored.index == original.index
        assert restored.metadata == original.metadata
