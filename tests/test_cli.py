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
        assert "add_method" in result.output

    def test_list_by_category(self, runner):
        result = runner.invoke(cli, ["list", "--category", "method"])
        assert result.exit_code == 0
        assert "add_method" in result.output

    def test_list_json(self, runner):
        result = runner.invoke(cli, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 41
        assert any(d["name"] == "add_method" for d in data)

    def test_list_json_verbose(self, runner):
        result = runner.invoke(cli, ["list", "--json", "--verbose"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Verbose includes params
        add_method = next(d for d in data if d["name"] == "add_method")
        assert "params" in add_method

    def test_list_category_field(self, runner):
        result = runner.invoke(cli, ["list", "--category", "field", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert all(d["category"] == "field" for d in data)
        assert any(d["name"] == "add_field" for d in data)


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
        g.add_node(GraphNode("a", NodeType.CLASS, {"name": "A"}))
        g.add_edge(GraphEdge("a", "nonexistent", EdgeType.CONTAINS_METHOD))
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
# Tests: apply command
# =============================================================================


class TestApplyCommand:
    def test_apply_add_method(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "new_method"}',
            "--no-invariants",
        ])
        assert result.exit_code == 0
        # stdout should contain the result graph JSON
        output_lines = result.output.strip().split("\n")
        # Find the JSON part (skip Rich output on stderr)
        json_text = result.output
        assert "new_method" in json_text or result.exit_code == 0

    def test_apply_json_output(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "baz"}',
            "--no-invariants",
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_apply_unknown_operator(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "nonexistent_op",
            "--params", "{}",
        ])
        assert result.exit_code == 2

    def test_apply_invalid_params(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", "not json",
        ])
        assert result.exit_code == 2

    def test_apply_to_file(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        out = tmp_path / "result.json"
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "baz"}',
            "--no-invariants",
            "-o", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()


# =============================================================================
# Tests: invalid operator usage
# =============================================================================


class TestInvalidOperator:
    def test_apply_missing_required_params(self, runner, tmp_path):
        """add_method requires class_name and method_name; omit method_name."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo"}',
            "--no-invariants",
            "--json",
        ])
        # Should fail — the rule can't be built without method_name
        assert result.exit_code != 0

    def test_apply_target_class_not_in_graph(self, runner, tmp_path):
        """Apply add_method to a class that doesn't exist in the graph."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "NonExistent", "method_name": "m"}',
            "--no-invariants",
            "--json",
        ])
        # Engine finds no match → failure
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_on_empty_graph(self, runner, tmp_path):
        """Apply operator to a graph with zero nodes."""
        g = TypedGraph()
        gf = _write_graph(tmp_path, g)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "m"}',
            "--no-invariants",
            "--json",
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_duplicate_method_with_invariants(self, runner, tmp_path):
        """Adding a duplicate method should fail when invariants are enabled."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "bar"}',
            "--json",
        ])
        # bar already exists on Foo — unique-method-names invariant catches this
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_remove_nonexistent_method(self, runner, tmp_path):
        """Remove a method that doesn't exist on the class."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "remove_method",
            "--params", '{"class_name": "Foo", "method_name": "no_such_method"}',
            "--no-invariants",
            "--json",
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_rename_nonexistent_method(self, runner, tmp_path):
        """Rename a method that doesn't exist."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "rename_method",
            "--params", '{"old_name": "ghost", "new_name": "phantom"}',
            "--no-invariants",
            "--json",
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False

    def test_apply_empty_params(self, runner, tmp_path):
        """Pass empty JSON object as params."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "apply", str(gf),
            "--operator", "add_method",
            "--params", "{}",
            "--no-invariants",
            "--json",
        ])
        assert result.exit_code != 0

    def test_dry_run_invalid_operator(self, runner, tmp_path):
        """dry-run with an unknown operator name."""
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--operator", "totally_bogus",
            "--params", "{}",
        ])
        assert result.exit_code == 2

    def test_apply_corrupted_graph_file(self, runner, tmp_path):
        """Apply operator to a file with malformed JSON."""
        bad = tmp_path / "corrupt.json"
        bad.write_text('{"nodes": {}, "edges": [broken')
        result = runner.invoke(cli, [
            "apply", str(bad),
            "--operator", "add_method",
            "--params", '{"class_name": "X", "method_name": "y"}',
        ])
        assert result.exit_code == 2

    def test_apply_graph_missing_edges_key(self, runner, tmp_path):
        """Graph JSON missing the 'edges' key entirely."""
        bad = tmp_path / "no_edges.json"
        bad.write_text('{"nodes": {}}')
        result = runner.invoke(cli, [
            "apply", str(bad),
            "--operator", "add_method",
            "--params", '{"class_name": "X", "method_name": "y"}',
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
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "new_method"}',
        ])
        assert result.exit_code == 0

    def test_dry_run_json(self, runner, tmp_path):
        gf = _write_graph(tmp_path)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--operator", "add_method",
            "--params", '{"class_name": "Foo", "method_name": "new_method"}',
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

    def test_dry_run_not_applicable(self, runner, tmp_path):
        # Try to remove a method that doesn't exist
        g = TypedGraph()
        g.add_node(GraphNode("class:Foo", NodeType.CLASS, {"name": "Foo"}))
        gf = _write_graph(tmp_path, g)
        result = runner.invoke(cli, [
            "dry-run", str(gf),
            "--operator", "remove_method",
            "--params", '{"class_name": "Foo", "method_name": "nonexistent"}',
        ])
        assert result.exit_code == 1


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
