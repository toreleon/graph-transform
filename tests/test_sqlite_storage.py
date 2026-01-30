"""Tests for SQLite graph storage."""

import tempfile
from pathlib import Path

import pytest

from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)
from graph_transform.io.sqlite_storage import SQLiteGraphStore


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_graphs.db"


@pytest.fixture
def store(temp_db: Path) -> SQLiteGraphStore:
    """Create a store with a temporary database."""
    return SQLiteGraphStore(temp_db)


def _make_simple_graph() -> TypedGraph:
    """Create a simple test graph with a class and method."""
    g = TypedGraph()
    g.add_node(GraphNode("class:Foo", NodeType.CLASS, {"name": "Foo", "file": "foo.py"}))
    g.add_node(GraphNode("func:bar", NodeType.FUNCTION, {"name": "bar", "is_method": True}))
    g.add_edge(GraphEdge("class:Foo", "func:bar", EdgeType.CONTAINS_METHOD))
    return g


def _make_complex_graph() -> TypedGraph:
    """Create a more complex graph with multiple node types and edges."""
    g = TypedGraph()
    # Module
    g.add_node(GraphNode("module:mymodule", NodeType.MODULE, {"name": "mymodule", "file": "mymodule.py"}))
    # Class
    g.add_node(GraphNode("class:Calculator", NodeType.CLASS, {"name": "Calculator", "line": 10}))
    # Methods
    g.add_node(GraphNode("func:add", NodeType.FUNCTION, {"name": "add", "is_method": True}))
    g.add_node(GraphNode("func:subtract", NodeType.FUNCTION, {"name": "subtract", "is_method": True}))
    # Parameters
    g.add_node(GraphNode("param:add.a", NodeType.PARAMETER, {"name": "a", "position": 0}))
    g.add_node(GraphNode("param:add.b", NodeType.PARAMETER, {"name": "b", "position": 1}))
    # Field
    g.add_node(GraphNode("field:Calculator.result", NodeType.FIELD, {"name": "result", "field_type": "int"}))
    
    # Edges
    g.add_edge(GraphEdge("class:Calculator", "module:mymodule", EdgeType.DEFINED_IN))
    g.add_edge(GraphEdge("class:Calculator", "func:add", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("class:Calculator", "func:subtract", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("class:Calculator", "field:Calculator.result", EdgeType.CONTAINS_FIELD))
    g.add_edge(GraphEdge("func:add", "param:add.a", EdgeType.HAS_PARAMETER))
    g.add_edge(GraphEdge("func:add", "param:add.b", EdgeType.HAS_PARAMETER))
    
    return g


# =============================================================================
# Tests: Basic Operations
# =============================================================================


class TestBasicOperations:
    """Test basic save/load/list/delete operations."""

    def test_save_and_load_simple_graph(self, store: SQLiteGraphStore):
        """Round-trip save/load preserves graph structure."""
        original = _make_simple_graph()
        store.save_graph(original, "test")

        loaded = store.load_graph("test")

        assert loaded.node_count == original.node_count
        assert loaded.edge_count == original.edge_count
        assert "class:Foo" in loaded.nodes
        assert "func:bar" in loaded.nodes
        assert loaded.nodes["class:Foo"].attrs["name"] == "Foo"

    def test_save_and_load_complex_graph(self, store: SQLiteGraphStore):
        """Complex graph with multiple node/edge types round-trips correctly."""
        original = _make_complex_graph()
        store.save_graph(original, "calculator")

        loaded = store.load_graph("calculator")

        assert loaded.node_count == original.node_count
        assert loaded.edge_count == original.edge_count

        # Verify node types
        assert loaded.nodes["module:mymodule"].node_type == NodeType.MODULE
        assert loaded.nodes["class:Calculator"].node_type == NodeType.CLASS
        assert loaded.nodes["param:add.a"].node_type == NodeType.PARAMETER

        # Verify attributes
        assert loaded.nodes["param:add.b"].attrs["position"] == 1

    def test_list_graphs_empty(self, store: SQLiteGraphStore):
        """List graphs returns empty list when no graphs stored."""
        assert store.list_graphs() == []

    def test_list_graphs_multiple(self, store: SQLiteGraphStore):
        """List graphs returns all stored graph names."""
        g1 = _make_simple_graph()
        g2 = _make_complex_graph()

        store.save_graph(g1, "alpha")
        store.save_graph(g2, "beta")
        store.save_graph(g1, "gamma")

        names = store.list_graphs()
        assert names == ["alpha", "beta", "gamma"]

    def test_delete_graph(self, store: SQLiteGraphStore):
        """Delete removes graph and returns True."""
        store.save_graph(_make_simple_graph(), "to_delete")
        assert store.graph_exists("to_delete")

        result = store.delete_graph("to_delete")

        assert result is True
        assert not store.graph_exists("to_delete")
        assert "to_delete" not in store.list_graphs()

    def test_delete_nonexistent_graph(self, store: SQLiteGraphStore):
        """Delete returns False for non-existent graph."""
        result = store.delete_graph("nonexistent")
        assert result is False

    def test_graph_exists(self, store: SQLiteGraphStore):
        """graph_exists correctly reports existence."""
        assert not store.graph_exists("mytest")

        store.save_graph(_make_simple_graph(), "mytest")
        assert store.graph_exists("mytest")


# =============================================================================
# Tests: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_load_nonexistent_graph(self, store: SQLiteGraphStore):
        """Loading a graph that doesn't exist raises KeyError."""
        with pytest.raises(KeyError, match="Graph not found"):
            store.load_graph("nonexistent")

    def test_save_empty_graph(self, store: SQLiteGraphStore):
        """Empty graph can be saved and loaded."""
        empty = TypedGraph()
        store.save_graph(empty, "empty")

        loaded = store.load_graph("empty")
        assert loaded.node_count == 0
        assert loaded.edge_count == 0

    def test_overwrite_existing_graph(self, store: SQLiteGraphStore):
        """Saving with same name overwrites existing graph."""
        g1 = _make_simple_graph()
        g2 = _make_complex_graph()

        store.save_graph(g1, "myproject")
        store.save_graph(g2, "myproject")

        loaded = store.load_graph("myproject")
        assert loaded.node_count == g2.node_count
        assert "module:mymodule" in loaded.nodes

    def test_special_characters_in_attrs(self, store: SQLiteGraphStore):
        """Attributes with special characters are preserved."""
        g = TypedGraph()
        g.add_node(GraphNode(
            "func:test",
            NodeType.FUNCTION,
            {"name": "test", "docstring": 'A "quoted" docstring with\nnewlines and unicode: 日本語'}
        ))
        store.save_graph(g, "special")

        loaded = store.load_graph("special")
        assert "日本語" in loaded.nodes["func:test"].attrs["docstring"]
        assert "\n" in loaded.nodes["func:test"].attrs["docstring"]


# =============================================================================
# Tests: Graph Info
# =============================================================================


class TestGraphInfo:
    """Test graph metadata retrieval."""

    def test_get_graph_info(self, store: SQLiteGraphStore):
        """get_graph_info returns metadata about stored graph."""
        g = _make_simple_graph()
        store.save_graph(g, "info_test")

        info = store.get_graph_info("info_test")

        assert info is not None
        assert info["name"] == "info_test"
        assert info["node_count"] == 2
        assert info["edge_count"] == 1
        assert "created_at" in info

    def test_get_graph_info_nonexistent(self, store: SQLiteGraphStore):
        """get_graph_info returns None for non-existent graph."""
        info = store.get_graph_info("nonexistent")
        assert info is None


# =============================================================================
# Tests: Multiple Stores
# =============================================================================


class TestMultipleStores:
    """Test behavior with multiple store instances."""

    def test_separate_databases(self, tmp_path: Path):
        """Different stores with different paths are independent."""
        store1 = SQLiteGraphStore(tmp_path / "db1.db")
        store2 = SQLiteGraphStore(tmp_path / "db2.db")

        store1.save_graph(_make_simple_graph(), "graph_a")
        store2.save_graph(_make_complex_graph(), "graph_b")

        assert store1.list_graphs() == ["graph_a"]
        assert store2.list_graphs() == ["graph_b"]

    def test_same_database_different_instances(self, temp_db: Path):
        """Different store instances pointing to same DB share data."""
        store1 = SQLiteGraphStore(temp_db)
        store1.save_graph(_make_simple_graph(), "shared")

        store2 = SQLiteGraphStore(temp_db)
        assert store2.graph_exists("shared")

        loaded = store2.load_graph("shared")
        assert loaded.node_count == 2
