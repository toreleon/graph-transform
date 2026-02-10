"""Tests for graph_transform CLI commands."""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from graph_transform.cli import cli
from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    return CliRunner()


def _make_graph() -> TypedGraph:
    """Build a minimal graph with a class and method."""
    g = TypedGraph()
    g.add_node(GraphNode("class:Foo", NodeType.CLASS, {"name": "Foo", "file": "test.py", "line": 1}))
    g.add_node(GraphNode("func:bar", NodeType.FUNCTION, {
        "name": "bar", "file": "test.py", "line": 3, "is_method": True, "is_async": False,
    }))
    g.add_node(GraphNode("param:bar.self", NodeType.PARAMETER, {
        "name": "self", "position": 0, "has_default": False,
    }))
    g.add_edge(GraphEdge("class:Foo", "func:bar", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("func:bar", "param:bar.self", EdgeType.HAS_PARAMETER))
    return g


def _write_graph(path: Path, graph: TypedGraph | None = None) -> Path:
    """Write a graph JSON file and return its path."""
    if graph is None:
        graph = _make_graph()
    filepath = path / "graph.json"
    filepath.write_text(json.dumps(graph.to_dict(), indent=2))
    return filepath


# =============================================================================
# Tests: list command
# =============================================================================


class TestListCommand:
    def test_list_all(self, runner):
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        # Should show primitives and compositions
        assert "insert_node" in result.output
        assert "RENAME" in result.output

    def test_list_primitives(self, runner):
        result = runner.invoke(cli, ["list", "--primitives"])
        assert result.exit_code == 0
        assert "insert_node" in result.output
        assert "delete_node" in result.output
        assert "update" in result.output

    def test_list_compositions(self, runner):
        result = runner.invoke(cli, ["list", "--compositions"])
        assert result.exit_code == 0
        assert "RENAME" in result.output
        assert "MOVE" in result.output
        assert "EXTRACT" in result.output

    def test_list_json(self, runner):
        result = runner.invoke(cli, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "primitives" in data
        assert "compositions" in data
        assert len(data["primitives"]) == 5
        assert len(data["compositions"]) == 8  # Including UPDATE_IMPORT


# =============================================================================
# Tests: verify command
# =============================================================================


class TestVerifyCommand:
    def test_verify_valid_graph(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, ["verify", str(gf)])
        assert result.exit_code == 0

    def test_verify_json_output(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, ["verify", str(gf), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_verify_invalid_file(self, runner, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        result = runner.invoke(cli, ["verify", str(bad)])
        assert result.exit_code == 2

    def test_verify_dangling_edges(self, runner, tmp_path):
        g = TypedGraph()
        g.add_node(GraphNode("c1", NodeType.CALL, {"callee": "missing_func"}))
        g.add_edge(GraphEdge("c1", "nonexistent", EdgeType.CALLS))
        gf = _write_graph(tmp_path, g)
        result = runner.invoke(cli, ["verify", str(gf)])
        assert result.exit_code == 1


# =============================================================================
# Tests: build command
# =============================================================================


class TestBuildCommand:
    def test_build_from_source(self, runner, tmp_path):
        src = tmp_path / "module.py"
        src.write_text("class MyClass:\n    pass\n")
        out = tmp_path / "out.json"

        result = runner.invoke(cli, ["build", str(src), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()

        data = json.loads(out.read_text())
        assert "nodes" in data
        assert any(
            n["attrs"].get("name") == "MyClass"
            for n in data["nodes"].values()
        )

    def test_build_stdout(self, runner, tmp_path):
        src = tmp_path / "func.py"
        src.write_text("def hello(): pass\n")

        result = runner.invoke(cli, ["build", str(src)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "nodes" in data

    def test_build_verbose(self, runner, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class A:\n    pass\n\nclass B:\n    pass\n")

        result = runner.invoke(cli, ["build", str(src), "--verbose"])
        assert result.exit_code == 0

    def test_build_nonexistent(self, runner):
        result = runner.invoke(cli, ["build", "/nonexistent.py"])
        assert result.exit_code == 2


# =============================================================================
# Tests: apply command with primitives
# =============================================================================


class TestApplyCommand:
    def test_apply_insert_node(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "func:new_method",
                "node_kind": "callable",
                "attrs": {"name": "new_method", "file": "test.py", "line": 10},
            }),
        ])
        assert result.exit_code == 0

    def test_apply_json_output(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "func:baz",
                "node_kind": "callable",
                "attrs": {"name": "baz"},
            }),
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_apply_unknown_primitive(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "nonexistent_primitive",
            "--params", "{}",
        ])
        assert result.exit_code == 2

    def test_apply_invalid_params(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "insert_node",
            "--params", "not json",
        ])
        assert result.exit_code == 2

    def test_apply_to_file(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        out = tmp_path / "result.json"
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "func:baz",
                "node_kind": "callable",
                "attrs": {"name": "baz"},
            }),
            "-o", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()

    def test_apply_composition(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--composition", "RENAME",
            "--params", json.dumps({
                "target": "func:bar",
                "new_name": "renamed_bar",
            }),
        ])
        assert result.exit_code == 0


# =============================================================================
# Tests: invalid operation usage
# =============================================================================


class TestInvalidOperation:
    def test_apply_insert_duplicate_node(self, runner, tmp_path):
        """Insert a node that already exists should fail."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "class:Foo",  # Already exists
                "node_kind": "type",
                "attrs": {"name": "Foo"},
            }),
            "--json",
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_delete_nonexistent_node(self, runner, tmp_path):
        """Delete a node that doesn't exist should fail."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "delete_node",
            "--params", json.dumps({
                "node_id": "func:nonexistent",
            }),
            "--json",
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_update_nonexistent_node(self, runner, tmp_path):
        """Update a node that doesn't exist should fail."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--primitive", "update",
            "--params", json.dumps({
                "target": "func:ghost",
                "prop": "name",
                "value": "phantom",
            }),
            "--json",
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_corrupted_graph_file(self, runner, tmp_path):
        """Apply operation to a file with malformed JSON."""
        bad = tmp_path / "corrupt.json"
        bad.write_text('{"nodes": {}, "edges": [broken')
        result = runner.invoke(cli, [
            "apply", str(bad),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "func:x",
                "node_kind": "callable",
            }),
        ])
        assert result.exit_code == 2


# =============================================================================
# Tests: dry-run command
# =============================================================================


class TestDryRunCommand:
    def test_dry_run_applicable(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "func:new_method",
                "node_kind": "callable",
                "attrs": {"name": "new_method"},
            }),
        ])
        assert result.exit_code == 0

    def test_dry_run_json(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--primitive", "insert_node",
            "--params", json.dumps({
                "node_id": "func:new_method",
                "node_kind": "callable",
                "attrs": {"name": "new_method"},
            }),
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_dry_run_not_applicable(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--primitive", "delete_node",
            "--params", json.dumps({
                "node_id": "func:nonexistent",
            }),
        ])
        assert result.exit_code == 1

    def test_dry_run_invalid_primitive(self, runner, tmp_path):
        """dry-run with an unknown primitive name."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--primitive", "totally_bogus",
            "--params", "{}",
        ])
        assert result.exit_code == 2


# =============================================================================
# Tests: version
# =============================================================================


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "graph-transform" in result.output.lower() or "algebraic" in result.output.lower()
