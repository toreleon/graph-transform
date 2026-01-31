"""Tests for the plan command and GraphChangeSet instrumentation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from graph_transform.cli import cli
from graph_transform.core.morphism import GraphMorphism
from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)
from graph_transform.engine.core import create_engine
from graph_transform.operators.primitive_operators import OperatorType
from graph_transform.rewriting.graph_change import (
    ChangeType,
    EdgeChange,
    GraphChangeSet,
    NodeChange,
)
from graph_transform.rewriting.production_rule import ProductionRule


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def runner():
    return CliRunner()


# =========================================================================
# Test: GraphChangeSet data model
# =========================================================================


class TestGraphChangeSet:
    def test_empty_changeset(self):
        cs = GraphChangeSet()
        assert not cs.has_changes
        assert cs.added_nodes() == []
        assert cs.removed_nodes() == []
        assert cs.updated_nodes() == []
        assert cs.added_edges() == []
        assert cs.removed_edges() == []

    def test_add_node_change(self):
        cs = GraphChangeSet()
        cs.node_changes.append(
            NodeChange(
                change_type=ChangeType.ADD_NODE,
                node_id="param",
                node_type=NodeType.PARAMETER,
                attrs={"name": "x"},
                host_node_id="param:foo.x:abc123",
            )
        )
        assert cs.has_changes
        assert len(cs.added_nodes()) == 1
        assert cs.added_nodes()[0].attrs["name"] == "x"
        assert cs.removed_nodes() == []

    def test_remove_node_change(self):
        cs = GraphChangeSet()
        cs.node_changes.append(
            NodeChange(
                change_type=ChangeType.REMOVE_NODE,
                node_id="func:old",
                node_type=NodeType.FUNCTION,
                attrs={"name": "old"},
            )
        )
        assert cs.has_changes
        assert len(cs.removed_nodes()) == 1
        assert cs.added_nodes() == []

    def test_update_attrs_change(self):
        cs = GraphChangeSet()
        cs.node_changes.append(
            NodeChange(
                change_type=ChangeType.UPDATE_ATTRS,
                node_id="func:foo",
                node_type=NodeType.FUNCTION,
                attrs={"name": "bar"},
                old_attrs={"name": "foo"},
            )
        )
        assert len(cs.updated_nodes()) == 1
        assert cs.updated_nodes()[0].old_attrs["name"] == "foo"
        assert cs.updated_nodes()[0].attrs["name"] == "bar"

    def test_edge_changes(self):
        cs = GraphChangeSet()
        cs.edge_changes.append(
            EdgeChange(
                change_type=ChangeType.ADD_EDGE,
                source="class:Foo",
                target="func:bar",
                edge_type=EdgeType.CONTAINS_METHOD,
            )
        )
        cs.edge_changes.append(
            EdgeChange(
                change_type=ChangeType.REMOVE_EDGE,
                source="class:Foo",
                target="func:old",
                edge_type=EdgeType.CONTAINS_METHOD,
            )
        )
        assert cs.has_changes
        assert len(cs.added_edges()) == 1
        assert len(cs.removed_edges()) == 1

    def test_to_dict(self):
        cs = GraphChangeSet()
        cs.node_changes.append(
            NodeChange(
                change_type=ChangeType.REMOVE_NODE,
                node_id="func:old",
                node_type=NodeType.FUNCTION,
                attrs={"name": "old"},
            )
        )
        cs.edge_changes.append(
            EdgeChange(
                change_type=ChangeType.ADD_EDGE,
                source="class:Foo",
                target="func:new",
                edge_type=EdgeType.CONTAINS_METHOD,
            )
        )
        d = cs.to_dict()
        assert len(d["node_changes"]) == 1
        assert len(d["edge_changes"]) == 1
        assert d["node_changes"][0]["change_type"] == "remove_node"
        assert d["edge_changes"][0]["change_type"] == "add_edge"


# =========================================================================
# Test: PushoutEngine records changes
# =========================================================================


class TestPushoutEngineChanges:
    def test_dpo_add_param_records_add_node_and_edge(self):
        host = TypedGraph()
        host.add_node(GraphNode("func:foo", NodeType.FUNCTION, {"name": "foo"}))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "foo", "param_name": "log", "default_value": "True"},
        )
        result = engine.apply_rule(rule, host)

        assert result.success
        assert result.changes is not None
        assert result.changes.has_changes

        added = result.changes.added_nodes()
        assert len(added) == 1
        assert added[0].node_type == NodeType.PARAMETER
        assert added[0].attrs["name"] == "log"
        assert added[0].host_node_id is not None

        added_edges = result.changes.added_edges()
        assert len(added_edges) == 1
        assert added_edges[0].edge_type == EdgeType.HAS_PARAMETER

    def test_dpo_add_method_records_changes(self):
        host = TypedGraph()
        host.add_node(GraphNode("class:Foo", NodeType.CLASS, {"name": "Foo"}))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_METHOD,
            {"class_name": "Foo", "method_name": "process"},
        )
        result = engine.apply_rule(rule, host)

        assert result.success
        assert result.changes is not None

        added = result.changes.added_nodes()
        assert len(added) == 1
        assert added[0].node_type == NodeType.FUNCTION
        assert added[0].attrs["name"] == "process"

        added_edges = result.changes.added_edges()
        assert len(added_edges) == 1
        assert added_edges[0].edge_type == EdgeType.CONTAINS_METHOD

    def test_dpo_remove_method_records_remove(self):
        host = TypedGraph()
        host.add_node(GraphNode("class:A", NodeType.CLASS, {"name": "A"}))
        host.add_node(
            GraphNode("func:m", NodeType.FUNCTION, {"name": "m", "is_method": True})
        )
        host.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.REMOVE_METHOD,
            {"class_name": "A", "method_name": "m"},
        )
        result = engine.apply_rule(rule, host)

        assert result.success
        assert result.changes is not None

        removed = result.changes.removed_nodes()
        assert len(removed) == 1
        assert removed[0].node_type == NodeType.FUNCTION
        assert removed[0].attrs["name"] == "m"

        removed_edges = result.changes.removed_edges()
        assert len(removed_edges) == 1

    def test_dpo_rename_records_update_attrs(self):
        host = TypedGraph()
        host.add_node(GraphNode("func:old", NodeType.FUNCTION, {"name": "old"}))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.RENAME_METHOD,
            {"old_name": "old", "new_name": "new"},
        )
        result = engine.apply_rule(rule, host)

        assert result.success
        assert result.changes is not None

        updated = result.changes.updated_nodes()
        assert len(updated) == 1
        assert updated[0].old_attrs["name"] == "old"
        assert updated[0].attrs["name"] == "new"

    def test_dpo_add_field_records_changes(self):
        host = TypedGraph()
        host.add_node(GraphNode("class:Cfg", NodeType.CLASS, {"name": "Cfg"}))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_FIELD,
            {"class_name": "Cfg", "field_name": "timeout", "default_value": "30"},
        )
        result = engine.apply_rule(rule, host)

        assert result.success
        assert result.changes is not None
        added = result.changes.added_nodes()
        assert len(added) == 1
        assert added[0].node_type == NodeType.FIELD
        assert added[0].attrs["name"] == "timeout"

    def test_failed_rewrite_has_no_changes(self):
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "nonexistent", "param_name": "x"},
        )
        result = engine.apply_rule(rule, graph)
        assert not result.success
        assert result.changes is None

    def test_spo_records_dangling_edge_removal(self):
        host = TypedGraph()
        host.add_node(GraphNode("func:m", NodeType.FUNCTION, {"name": "m"}))
        host.add_node(GraphNode("call:x", NodeType.CALL, {"callee": "m"}))
        host.add_edge(GraphEdge("call:x", "func:m", EdgeType.CALLS))

        engine = create_engine(mode="spo", check_invariants=False)
        # Build a simple rule that deletes func:m
        lhs = TypedGraph()
        lhs.add_node(GraphNode("method", NodeType.FUNCTION, {"name": "m"}))
        k = TypedGraph()
        rhs = TypedGraph()
        rule = ProductionRule(
            name="remove_m",
            op_type=OperatorType.REMOVE_METHOD,
            lhs=lhs,
            interface=k,
            rhs=rhs,
            lhs_inclusion=GraphMorphism(node_map={}, source=k, target=lhs),
            rhs_inclusion=GraphMorphism(node_map={}, source=k, target=rhs),
        )
        result = engine.apply_rule(rule, host)

        assert result.success
        assert result.changes is not None
        removed_edges = result.changes.removed_edges()
        # The CALLS edge should have been auto-removed
        assert len(removed_edges) >= 1
        assert any(e.edge_type == EdgeType.CALLS for e in removed_edges)


# =========================================================================
# Test: EditInstruction generation from changes
# =========================================================================


class TestEditsFromChanges:
    def test_add_param_generates_add_parameter_edit(self):
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(
            GraphNode(
                "func:foo", NodeType.FUNCTION, {"name": "foo", "file": "test.py", "line": 5}
            )
        )

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "foo", "param_name": "verbose", "default_value": "False"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        assert len(edits) >= 1
        param_edit = next(e for e in edits if e.edit_type == "add_parameter")
        assert param_edit.details["parameter"]["name"] == "verbose"
        assert param_edit.details["function"] == "foo"

    def test_rename_generates_rename_edit(self):
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(
            GraphNode(
                "func:old", NodeType.FUNCTION, {"name": "old", "file": "test.py", "line": 10}
            )
        )

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.RENAME_METHOD,
            {"old_name": "old", "new_name": "new"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        assert len(edits) == 1
        assert edits[0].edit_type == "rename"
        assert edits[0].details["old_name"] == "old"
        assert edits[0].details["new_name"] == "new"

    def test_add_method_generates_add_method_edit(self):
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("class:Foo", NodeType.CLASS, {"name": "Foo"}))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_METHOD,
            {"class_name": "Foo", "method_name": "run"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        method_edits = [e for e in edits if e.edit_type == "add_method"]
        assert len(method_edits) == 1
        assert method_edits[0].details["name"] == "run"

    def test_remove_field_generates_remove_edit(self):
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("class:Cfg", NodeType.CLASS, {"name": "Cfg"}))
        host.add_node(
            GraphNode("field:x", NodeType.FIELD, {"name": "x", "class_name": "Cfg"})
        )
        host.add_edge(GraphEdge("class:Cfg", "field:x", EdgeType.CONTAINS_FIELD))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.REMOVE_FIELD,
            {"class_name": "Cfg", "field_name": "x"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        remove_edits = [e for e in edits if e.edit_type == "remove_field"]
        assert len(remove_edits) == 1
        assert remove_edits[0].details["name"] == "x"


# =========================================================================
# Test: plan CLI command
# =========================================================================


class TestPlanCommand:
    def test_plan_inline_operators(self, runner, tmp_path):
        src = tmp_path / "module.py"
        src.write_text("class MyClass:\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "-op", "add_method",
                "-p", '{"class_name": "MyClass", "method_name": "process"}',
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "steps" in data
        assert len(data["steps"]) == 1
        assert data["steps"][0]["operator"] == "add_method"
        assert len(data["steps"][0]["edits"]) >= 1
        assert data["summary"]["total_edits"] >= 1

    def test_plan_output_file(self, runner, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        out = tmp_path / "plan.json"

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "-op", "add_field",
                "-p", '{"class_name": "Foo", "field_name": "count"}',
                "-o", str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["summary"]["total_edits"] >= 1

    def test_plan_multi_step(self, runner, tmp_path):
        src = tmp_path / "app.py"
        src.write_text("class Config:\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "-op", "add_method",
                "-p", '{"class_name": "Config", "method_name": "load"}',
                "-op", "add_field",
                "-p", '{"class_name": "Config", "field_name": "path"}',
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["steps"]) == 2
        assert "edits" in data["steps"][0]
        assert "edits" in data["steps"][1]

    def test_plan_yaml_file(self, runner, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        yaml_file = tmp_path / "refactor.yaml"
        yaml_file.write_text(
            "description: Test\n"
            "steps:\n"
            "  - op: add_method\n"
            "    params:\n"
            "      class_name: Foo\n"
            "      method_name: bar\n"
        )

        result = runner.invoke(
            cli,
            ["plan", str(src), "-F", str(yaml_file)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["steps"]) == 1
        assert data["steps"][0]["operator"] == "add_method"

    def test_plan_no_source_path(self, runner):
        result = runner.invoke(
            cli,
            [
                "plan",
                "-op", "add_method",
                "-p", '{"class_name":"X","method_name":"y"}',
            ],
        )
        assert result.exit_code == 2

    def test_plan_no_operators(self, runner, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        result = runner.invoke(cli, ["plan", str(src)])
        assert result.exit_code == 2

    def test_plan_invalid_operator(self, runner, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "-op", "nonexistent_op",
                "-p", "{}",
            ],
        )
        assert result.exit_code == 1

    def test_plan_verbose(self, runner, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "-op", "add_method",
                "-p", '{"class_name": "Foo", "method_name": "bar"}',
                "-v",
                "-o", str(tmp_path / "plan.json"),
            ],
        )
        assert result.exit_code == 0
        # With -o, JSON goes to file; verbose goes to stderr/output
        data = json.loads((tmp_path / "plan.json").read_text())
        assert "steps" in data

    def test_plan_grouped_output_structure(self, runner, tmp_path):
        """Verify the output JSON has the expected grouped structure."""
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "-op", "add_method",
                "-p", '{"class_name": "Foo", "method_name": "run"}',
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)

        # Top-level structure
        assert "description" in data
        assert "steps" in data
        assert "summary" in data

        # Step structure
        step = data["steps"][0]
        assert "step" in step
        assert "operator" in step
        assert "params" in step
        assert "description" in step
        assert "edits" in step
        assert step["step"] == 1
        assert step["operator"] == "add_method"

        # Summary
        assert data["summary"]["total_steps"] == 1
        assert data["summary"]["total_edits"] >= 1
