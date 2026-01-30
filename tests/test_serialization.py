"""Tests for graph_transform.serialization."""

import json
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
from graph_transform.io.serialization import (
    format_result_json,
    load_graph,
    load_json,
    save_graph,
    validate_graph_json,
)
from graph_transform.rewriting.production_rule import RewriteResult


# =============================================================================
# Fixtures
# =============================================================================


def _make_simple_graph() -> TypedGraph:
    g = TypedGraph()
    g.add_node(GraphNode("class:Foo", NodeType.CLASS, {"name": "Foo"}))
    g.add_node(GraphNode("func:bar", NodeType.FUNCTION, {"name": "bar", "is_method": True}))
    g.add_edge(GraphEdge("class:Foo", "func:bar", EdgeType.CONTAINS_METHOD))
    return g


def _write_graph_json(path: Path, graph: TypedGraph) -> None:
    path.write_text(json.dumps(graph.to_dict(), indent=2))


# =============================================================================
# Tests: validate_graph_json
# =============================================================================


class TestValidateGraphJson:
    def test_valid_graph(self):
        g = _make_simple_graph()
        errors = validate_graph_json(g.to_dict())
        assert errors == []

    def test_missing_nodes(self):
        errors = validate_graph_json({"edges": []})
        assert any("nodes" in e for e in errors)

    def test_missing_edges(self):
        errors = validate_graph_json({"nodes": {}})
        assert any("edges" in e for e in errors)

    def test_node_missing_id(self):
        data = {
            "nodes": {"x": {"node_type": "class", "attrs": {}}},
            "edges": [],
        }
        errors = validate_graph_json(data)
        assert any("id" in e for e in errors)

    def test_edge_missing_fields(self):
        data = {
            "nodes": {},
            "edges": [{"source": "a"}],
        }
        errors = validate_graph_json(data)
        assert any("target" in e for e in errors)

    def test_empty_graph_is_valid(self):
        errors = validate_graph_json({"nodes": {}, "edges": []})
        assert errors == []


# =============================================================================
# Tests: load/save round-trip
# =============================================================================


class TestLoadSave:
    def test_round_trip_file(self, tmp_path):
        g = _make_simple_graph()
        filepath = tmp_path / "graph.json"
        _write_graph_json(filepath, g)

        loaded = load_graph(str(filepath))
        assert loaded.node_count == g.node_count
        assert loaded.edge_count == g.edge_count
        assert "class:Foo" in loaded.nodes

    def test_save_and_load(self, tmp_path):
        g = _make_simple_graph()
        out = tmp_path / "out.json"
        save_graph(g, str(out))

        loaded = load_graph(str(out))
        assert loaded.node_count == 2
        assert loaded.edge_count == 1

    def test_load_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            load_graph("/nonexistent/path.json")

    def test_load_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{{")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_graph(str(bad))

    def test_load_invalid_graph(self, tmp_path):
        bad = tmp_path / "bad_graph.json"
        bad.write_text(json.dumps({"not_nodes": {}}))
        with pytest.raises(ValueError, match="Invalid graph"):
            load_graph(str(bad))


# =============================================================================
# Tests: format_result_json
# =============================================================================


class TestFormatResultJson:
    def test_success_result(self):
        g = _make_simple_graph()
        result = RewriteResult(success=True, result_graph=g, rule_name="test_rule")
        data = format_result_json(result)
        assert data["success"] is True
        assert data["rule_name"] == "test_rule"
        assert "result_graph" in data
        assert "nodes" in data["result_graph"]

    def test_failure_result(self):
        result = RewriteResult(
            success=False,
            errors=["No match found"],
            rule_name="test_rule",
        )
        data = format_result_json(result)
        assert data["success"] is False
        assert "No match found" in data["errors"]
        assert "result_graph" not in data


# =============================================================================
# Tests: load_json
# =============================================================================


class TestLoadJson:
    def test_load_from_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        data = load_json(str(f))
        assert data["key"] == "value"

    def test_load_non_object(self, tmp_path):
        f = tmp_path / "array.json"
        f.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="Expected a JSON object"):
            load_json(str(f))
