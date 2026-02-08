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

    def test_update_import_names_generates_split_edits(self):
        """update_import with names filter generates remove_from_import + add_import."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        # Multi-name import: from .exceptions import ConnectionError, FileModeWarning
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": ".exceptions", "name": "ConnectionError",
            "file": "pkg/__init__.py", "line": 10,
        }))
        host.add_node(GraphNode("i2", NodeType.IMPORT, {
            "module": ".exceptions", "name": "FileModeWarning",
            "file": "pkg/__init__.py", "line": 10,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": ".exceptions", "new_module": ".warnings", "names": ["FileModeWarning"]},
        )
        assert len(rules) == 1

        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                edits = edits_from_changes(
                    r.changes, r.result_graph, rule.name, rule.parameters
                )
                all_edits.extend(edits)
                current = r.result_graph

        # Should produce remove_from_import + add_import, NOT update_import
        remove_edits = [e for e in all_edits if e.edit_type == "remove_from_import"]
        add_edits = [e for e in all_edits if e.edit_type == "add_import"]
        update_edits = [e for e in all_edits if e.edit_type == "update_import"]

        assert len(remove_edits) == 1, f"Expected 1 remove_from_import, got {len(remove_edits)}"
        assert remove_edits[0].details["name"] == "FileModeWarning"
        assert remove_edits[0].details["module"] == ".exceptions"

        assert len(add_edits) == 1, f"Expected 1 add_import, got {len(add_edits)}"
        assert add_edits[0].details["name"] == "FileModeWarning"
        assert add_edits[0].details["module"] == ".warnings"

        assert len(update_edits) == 0, "Should not generate coarse update_import edits"

        # Verify command handles both single-line and multi-line imports
        cmd = remove_edits[0].details["command"]
        assert "from \\.exceptions import FileModeWarning" in cmd, (
            "Command must handle single-line imports"
        )
        assert "FileModeWarning" in cmd, "Command must handle multi-line import entries"

    def test_remove_from_import_command_deletes_single_line_import(self):
        """remove_from_import sed command deletes 'from MOD import NAME' (single-line)."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        # Single-name import: from .exceptions import RequestsDependencyWarning
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": ".exceptions", "name": "RequestsDependencyWarning",
            "file": "pkg/__init__.py", "line": 45,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": ".exceptions", "new_module": ".warnings",
             "names": ["RequestsDependencyWarning"]},
        )

        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                edits = edits_from_changes(
                    r.changes, r.result_graph, rule.name, rule.parameters
                )
                all_edits.extend(edits)
                current = r.result_graph

        remove_edits = [e for e in all_edits if e.edit_type == "remove_from_import"]
        assert len(remove_edits) == 1
        cmd = remove_edits[0].details["command"]

        # Test the sed command against actual file content
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "import warnings\n"
                "\n"
                "from .exceptions import RequestsDependencyWarning\n"
                "\n"
                "x = 1\n"
            )
            f.flush()
            # Substitute the original file path with our temp file
            test_cmd = cmd.replace("pkg/__init__.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result = open(f.name).read()
            os.unlink(f.name)

        assert "from .exceptions import RequestsDependencyWarning" not in result, (
            f"Single-line import was NOT deleted by command. File after:\n{result}"
        )
        assert "import warnings" in result, "Other lines should be preserved"
        assert "x = 1" in result, "Other lines should be preserved"

    def test_remove_from_import_inline_multi_name(self):
        """remove_from_import sed handles 'from mod import A, B' removing just A."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": "pkg.old", "name": "Foo",
            "file": "app.py", "line": 5,
        }))
        host.add_node(GraphNode("i2", NodeType.IMPORT, {
            "module": "pkg.old", "name": "Bar",
            "file": "app.py", "line": 5,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": "pkg.old", "new_module": "pkg.new", "names": ["Foo"]},
        )

        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                all_edits.extend(
                    edits_from_changes(r.changes, r.result_graph, rule.name, rule.parameters)
                )
                current = r.result_graph

        remove_edits = [e for e in all_edits if e.edit_type == "remove_from_import"]
        assert len(remove_edits) == 1
        cmd = remove_edits[0].details["command"]

        import subprocess, tempfile, os

        # Case A: Foo is first → "from pkg.old import Foo, Bar" → "from pkg.old import Bar"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("from pkg.old import Foo, Bar\nx = 1\n")
            f.flush()
            test_cmd = cmd.replace("app.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result = open(f.name).read()
            os.unlink(f.name)
        assert "from pkg.old import Bar" in result, f"Should keep Bar. Got:\n{result}"
        assert "Foo" not in result, f"Should remove Foo. Got:\n{result}"

        # Case B: Foo is last → "from pkg.old import Bar, Foo" → "from pkg.old import Bar"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("from pkg.old import Bar, Foo\nx = 1\n")
            f.flush()
            test_cmd = cmd.replace("app.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result = open(f.name).read()
            os.unlink(f.name)
        assert "from pkg.old import Bar" in result, f"Should keep Bar. Got:\n{result}"
        assert "Foo" not in result, f"Should remove Foo. Got:\n{result}"

    def test_add_import_preserves_indentation(self):
        """add_import sed preserves leading whitespace from matched import line."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": "pkg.old", "name": "MyClass",
            "file": "app.py", "line": 3,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": "pkg.old", "new_module": "pkg.new", "names": ["MyClass"]},
        )

        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                all_edits.extend(
                    edits_from_changes(r.changes, r.result_graph, rule.name, rule.parameters)
                )
                current = r.result_graph

        add_edits = [e for e in all_edits if e.edit_type == "add_import"]
        assert len(add_edits) == 1
        cmd = add_edits[0].details["command"]

        import subprocess, tempfile, os

        # Indented import inside an if block
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "if TYPE_CHECKING:\n"
                "    from pkg.old import MyClass\n"
                "\n"
                "x = 1\n"
            )
            f.flush()
            test_cmd = cmd.replace("app.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result = open(f.name).read()
            os.unlink(f.name)

        lines = result.split("\n")
        # The new import should be indented to match the context
        new_import_line = [l for l in lines if "pkg.new" in l]
        assert len(new_import_line) == 1, f"Expected new import. Got:\n{result}"
        assert new_import_line[0].startswith("    "), (
            f"New import should be indented. Got: {new_import_line[0]!r}"
        )
        assert "    from pkg.new import MyClass" in result, (
            f"New import should preserve indentation. Got:\n{result}"
        )

    def test_copy_command_adds_blank_line_separator(self):
        """copy_command prepends a blank line before appending to target."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes
        from graph_transform.rewriting.graph_change import EdgeChange

        host = TypedGraph()
        host.add_node(GraphNode("f1", NodeType.FUNCTION, {
            "name": "helper", "file": "src.py", "line": 5, "end_line": 10,
        }))
        host.add_node(GraphNode("m1", NodeType.MODULE, {
            "name": "src", "file": "src.py",
        }))
        host.add_node(GraphNode("m2", NodeType.MODULE, {
            "name": "dest", "file": "dest.py",
        }))
        host.add_edge(GraphEdge("f1", "m1", EdgeType.DEFINED_IN))

        changes = GraphChangeSet()
        changes.edge_changes.append(EdgeChange(
            change_type=ChangeType.ADD_EDGE,
            source="f1", target="m2",
            edge_type=EdgeType.DEFINED_IN,
        ))

        result_graph = host.copy()
        result_graph.add_edge(GraphEdge("f1", "m2", EdgeType.DEFINED_IN))

        edits = edits_from_changes(changes, result_graph, "move_to_module", {})
        move_edits = [e for e in edits if e.edit_type == "move_function"]
        assert len(move_edits) == 1
        copy_cmd = move_edits[0].details["copy_command"]

        assert copy_cmd.startswith("echo '' >> dest.py && "), (
            f"copy_command should prepend blank-line separator. Got: {copy_cmd}"
        )

    def test_update_import_without_names_generates_update_edit(self):
        """update_import without names filter generates normal update_import edits."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": ".exceptions", "name": "FileModeWarning",
            "file": "pkg/__init__.py", "line": 10,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": ".exceptions", "new_module": ".warnings"},
        )

        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                edits = edits_from_changes(
                    r.changes, r.result_graph, rule.name, rule.parameters
                )
                all_edits.extend(edits)
                current = r.result_graph

        update_edits = [e for e in all_edits if e.edit_type == "update_import"]
        assert len(update_edits) == 1
        assert update_edits[0].details["old_module"] == ".exceptions"
        assert update_edits[0].details["new_module"] == ".warnings"

    def test_move_class_generates_edit_from_edge_change(self):
        """move_class generates move_class edit with copy and delete commands."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("class:MyWarning", NodeType.CLASS, {
            "name": "MyWarning",
            "file": "src/pkg/exceptions.py",
            "line": 10,
            "end_line": 12,
        }))
        host.add_node(GraphNode("module:exceptions", NodeType.MODULE, {
            "name": "exceptions", "file": "src/pkg/exceptions.py",
        }))
        host.add_node(GraphNode("module:warnings", NodeType.MODULE, {
            "name": "warnings", "file": "src/pkg/warnings.py",
        }))
        host.add_edge(GraphEdge("class:MyWarning", "module:exceptions", EdgeType.DEFINED_IN))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.MOVE_CLASS,
            {"class_name": "MyWarning", "target_module": "warnings"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        move_edits = [e for e in edits if e.edit_type == "move_class"]
        assert len(move_edits) == 1
        ed = move_edits[0]
        assert ed.details["class_name"] == "MyWarning"
        assert ed.details["source_file"] == "src/pkg/exceptions.py"
        assert ed.details["target_file"] == "src/pkg/warnings.py"
        assert ed.details["start_line"] == 10
        assert ed.details["end_line"] == 12
        assert "copy_command" in ed.details
        assert "delete_command" in ed.details
        assert "10,12p" in ed.details["copy_command"]
        assert "10,12d" in ed.details["delete_command"]

    def test_move_class_infers_target_file(self):
        """move_class infers target file from source directory when not available."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("class:Foo", NodeType.CLASS, {
            "name": "Foo",
            "file": "src/mypackage/models.py",
            "line": 5,
            "end_line": 20,
        }))
        host.add_node(GraphNode("module:models", NodeType.MODULE, {
            "name": "models", "file": "src/mypackage/models.py",
        }))
        # Target module exists but has no file (e.g., created via create_module)
        host.add_node(GraphNode("module:entities", NodeType.MODULE, {
            "name": "entities",
        }))
        host.add_edge(GraphEdge("class:Foo", "module:models", EdgeType.DEFINED_IN))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.MOVE_CLASS,
            {"class_name": "Foo", "target_module": "entities"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        move_edits = [e for e in edits if e.edit_type == "move_class"]
        assert len(move_edits) == 1
        # Should infer target file from source directory
        assert move_edits[0].details["target_file"] == "src/mypackage/entities.py"

    def test_move_class_plan_command_produces_commands(self, runner, tmp_path):
        """move_class via CLI plan produces commands list with correct ordering."""
        source = tmp_path / "source.py"
        source.write_text(
            "class Alpha:\n"
            "    '''First class.'''\n"
            "\n"
            "\n"
            "class Beta:\n"
            "    '''Second class.'''\n"
        )
        target = tmp_path / "target.py"
        target.write_text("")  # empty target module

        yaml_file = tmp_path / "recipe.yaml"
        yaml_file.write_text(
            "steps:\n"
            "  - op: move_class\n"
            "    params:\n"
            "      class_name: Alpha\n"
            "      target_module: target\n"
            "  - op: move_class\n"
            "    params:\n"
            "      class_name: Beta\n"
            "      target_module: target\n"
        )

        result = runner.invoke(
            cli,
            ["plan", "-f", str(source), "-f", str(target), "-F", str(yaml_file)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)

        assert len(data["steps"]) == 2
        assert "commands" in data

        # Commands should have copies first, deletes last
        commands = data["commands"]
        copy_cmds = [c for c in commands if ">>" in c]
        delete_cmds = [c for c in commands if " -i " in c and "d'" in c]
        assert len(copy_cmds) == 2
        assert len(delete_cmds) == 2

        # Delete commands should come after copy commands
        first_delete_idx = min(commands.index(c) for c in delete_cmds)
        last_copy_idx = max(commands.index(c) for c in copy_cmds)
        assert first_delete_idx > last_copy_idx, "Deletes must come after copies"

    def test_move_class_stdlib_shadowing_hint(self, runner, tmp_path):
        """move_class to a stdlib-named module emits a shadowing hint."""
        source = tmp_path / "exceptions.py"
        source.write_text("class MyWarning:\n    pass\n")
        target = tmp_path / "warnings.py"
        target.write_text("")

        result = runner.invoke(
            cli,
            [
                "plan",
                "-f", str(source), "-f", str(target),
                "-op", "move_class",
                "-p", '{"class_name": "MyWarning", "target_module": "warnings"}',
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "hints" in data
        assert any("shadows" in h and "warnings" in h for h in data["hints"])

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

    def test_move_function_generates_edit_from_edge_change(self):
        """move_to_module generates move_function edit with copy and delete commands."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("func:order_patterns", NodeType.FUNCTION, {
            "name": "order_patterns",
            "file": "lib/inventory/manager.py",
            "line": 65,
            "end_line": 90,
            "is_method": False,
        }))
        host.add_node(GraphNode("module:manager", NodeType.MODULE, {
            "name": "manager", "file": "lib/inventory/manager.py",
        }))
        host.add_node(GraphNode("module:patterns", NodeType.MODULE, {
            "name": "patterns", "file": "lib/inventory/patterns.py",
        }))
        host.add_edge(GraphEdge("func:order_patterns", "module:manager", EdgeType.DEFINED_IN))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.MOVE_TO_MODULE,
            {"item_name": "order_patterns", "target_module": "patterns"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        move_edits = [e for e in edits if e.edit_type == "move_function"]
        assert len(move_edits) == 1
        ed = move_edits[0]
        assert ed.details["function_name"] == "order_patterns"
        assert ed.details["source_file"] == "lib/inventory/manager.py"
        assert ed.details["target_file"] == "lib/inventory/patterns.py"
        assert ed.details["start_line"] == 65
        assert ed.details["end_line"] == 90
        assert "copy_command" in ed.details
        assert "delete_command" in ed.details
        assert "65,90p" in ed.details["copy_command"]
        assert "65,90d" in ed.details["delete_command"]
        assert "patterns.py" in ed.details["copy_command"]
        assert "manager.py" in ed.details["delete_command"]

    def test_move_function_infers_target_file(self):
        """move_to_module infers target file from source directory when not available."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("func:my_func", NodeType.FUNCTION, {
            "name": "my_func",
            "file": "src/pkg/utils.py",
            "line": 10,
            "end_line": 25,
            "is_method": False,
        }))
        host.add_node(GraphNode("module:utils", NodeType.MODULE, {
            "name": "utils", "file": "src/pkg/utils.py",
        }))
        host.add_node(GraphNode("module:helpers", NodeType.MODULE, {
            "name": "helpers",
        }))
        host.add_edge(GraphEdge("func:my_func", "module:utils", EdgeType.DEFINED_IN))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.MOVE_TO_MODULE,
            {"item_name": "my_func", "target_module": "helpers"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        move_edits = [e for e in edits if e.edit_type == "move_function"]
        assert len(move_edits) == 1
        assert move_edits[0].details["target_file"] == "src/pkg/helpers.py"

    def test_move_function_commands_in_plan_output(self):
        """move_function edits produce copy+delete in the commands list."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("func:split_pattern", NodeType.FUNCTION, {
            "name": "split_pattern",
            "file": "manager.py",
            "line": 93,
            "end_line": 130,
            "is_method": False,
        }))
        host.add_node(GraphNode("module:manager", NodeType.MODULE, {
            "name": "manager", "file": "manager.py",
        }))
        host.add_node(GraphNode("module:patterns", NodeType.MODULE, {
            "name": "patterns", "file": "patterns.py",
        }))
        host.add_edge(GraphEdge("func:split_pattern", "module:manager", EdgeType.DEFINED_IN))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.MOVE_TO_MODULE,
            {"item_name": "split_pattern", "target_module": "patterns"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        move_edits = [e for e in edits if e.edit_type == "move_function"]
        assert len(move_edits) == 1

        # Verify the commands are structured for copy-first, delete-last
        ed = move_edits[0]
        copy_cmd = ed.details["copy_command"]
        del_cmd = ed.details["delete_command"]
        assert "echo '' >> patterns.py && sed -n '93,130p' manager.py >> patterns.py" == copy_cmd
        assert "sed -i '93,130d' manager.py" == del_cmd

    def test_submodule_import_rename_generates_command(self):
        """Case 2: from pkg import old_name → from pkg import new_name generates sed."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode("mod:test", NodeType.MODULE, {
            "name": "test", "file": "test.py",
        }))
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": "ansible.module_utils.facts",
            "name": "namespace",
            "file": "test_collector.py", "line": 26,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": "ansible.module_utils.facts.namespace",
             "new_module": "ansible.module_utils.facts.compat"},
        )

        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                edits = edits_from_changes(
                    r.changes, r.result_graph, rule.name, rule.parameters
                )
                all_edits.extend(edits)
                current = r.result_graph

        update_edits = [e for e in all_edits if e.edit_type == "update_import"]
        assert len(update_edits) == 1
        ed = update_edits[0]
        assert "command" in ed.details, "Submodule import rename must have a command"
        cmd = ed.details["command"]
        assert "import \\<namespace\\>" in cmd, "Must match import with word boundary"
        assert "import compat" in cmd, "Must replace with new name"
        assert "\\<namespace\\>\\." in cmd, "Must handle qualified references"
        assert "compat." in cmd, "Must replace qualified references"

    def test_submodule_import_rename_sed_works(self):
        """Case 2 sed command correctly renames import and qualified references."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes
        import subprocess, tempfile, os

        host = TypedGraph()
        host.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": "pkg.facts",
            "name": "namespace",
            "file": "test.py", "line": 1,
        }))

        engine = create_engine(check_invariants=False)
        rules = engine.catalog.create_rules(
            OperatorType.UPDATE_IMPORT,
            {"old_module": "pkg.facts.namespace",
             "new_module": "pkg.facts.compat"},
        )
        current = host
        all_edits = []
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                edits = edits_from_changes(
                    r.changes, r.result_graph, rule.name, rule.parameters
                )
                all_edits.extend(edits)
                current = r.result_graph

        update_edits = [e for e in all_edits if e.edit_type == "update_import"]
        assert len(update_edits) == 1
        cmd = update_edits[0].details["command"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "from pkg.facts import namespace\n"
                "\n"
                "ns = namespace.PrefixFactNamespace('a', 'b')\n"
                "result = do_stuff(namespace=ns)\n"
            )
            f.flush()
            test_cmd = cmd.replace("test.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result = open(f.name).read()
            os.unlink(f.name)

        assert "from pkg.facts import compat" in result, "Import must be renamed"
        assert "compat.PrefixFactNamespace" in result, "Qualified ref must be renamed"
        assert "namespace=ns" in result, "Keyword arg must NOT be renamed"
        assert "namespace.PrefixFactNamespace" not in result, "Old qualified ref must be gone"

    def test_rename_generates_command(self):
        """rename edit includes a line-specific sed command."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode(
            "func:old", NodeType.FUNCTION,
            {"name": "old", "file": "module.py", "line": 10},
        ))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.RENAME_METHOD, {"old_name": "old", "new_name": "new"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        rename_edits = [e for e in edits if e.edit_type == "rename"]
        assert len(rename_edits) == 1
        cmd = rename_edits[0].details["command"]
        assert "10s/" in cmd, "Must target specific line"
        assert "\\<old\\>" in cmd, "Must use word boundaries"
        assert "/new/" in cmd, "Must replace with new name"
        assert "module.py" in cmd

    def test_rename_sed_works(self):
        """rename sed command correctly renames on the target line only."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes
        import subprocess, tempfile, os

        host = TypedGraph()
        host.add_node(GraphNode(
            "func:get_data", NodeType.FUNCTION,
            {"name": "get_data", "file": "svc.py", "line": 3},
        ))
        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.RENAME_METHOD,
            {"old_name": "get_data", "new_name": "fetch_data"},
        )
        result = engine.apply_rule(rule, host)
        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        cmd = edits[0].details["command"]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "import os\n"
                "\n"
                "def get_data(x):\n"
                "    return get_data_helper(x)\n"
            )
            f.flush()
            test_cmd = cmd.replace("svc.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result_text = open(f.name).read()
            os.unlink(f.name)

        assert "def fetch_data(x):" in result_text, "Definition must be renamed"
        # Line 4 should NOT be changed (different line)
        assert "get_data_helper" in result_text, "Other lines must be untouched"

    def test_update_call_generates_command(self):
        """update_call edit includes a line-specific sed command."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode(
            "func:old", NodeType.FUNCTION, {"name": "old"},
        ))
        host.add_node(GraphNode(
            "call:test.py:15:1", NodeType.CALL,
            {"callee": "old", "file": "test.py", "line": 15},
        ))
        host.add_edge(GraphEdge("call:test.py:15:1", "func:old", EdgeType.CALLS))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.UPDATE_CALL,
            {"old_callee": "old", "new_callee": "new"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        call_edits = [e for e in edits if e.edit_type == "update_call"]
        assert len(call_edits) == 1
        cmd = call_edits[0].details["command"]
        assert "15s/" in cmd, "Must target specific line"
        assert "\\<old\\>" in cmd, "Must use word boundaries"
        assert "/new/" in cmd

    def test_add_parameter_generates_command(self):
        """add_parameter edit includes a sed command for single-line defs."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode(
            "func:foo", NodeType.FUNCTION,
            {"name": "foo", "file": "app.py", "line": 5},
        ))

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
        param_edits = [e for e in edits if e.edit_type == "add_parameter"]
        assert len(param_edits) == 1
        cmd = param_edits[0].details["command"]
        assert "5s/" in cmd, "Must target function def line"
        assert "verbose=False" in cmd, "Must include param with default"
        assert "def foo" in cmd, "Must match function name"

    def test_add_parameter_sed_works(self):
        """add_parameter sed handles both empty and non-empty param lists."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes
        import subprocess, tempfile, os

        # Test with existing params
        host = TypedGraph()
        host.add_node(GraphNode(
            "func:process", NodeType.FUNCTION,
            {"name": "process", "file": "svc.py", "line": 1},
        ))
        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "process", "param_name": "log", "default_value": "True"},
        )
        result = engine.apply_rule(rule, host)
        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        cmd = edits[0].details["command"]

        # Test empty params: def process():
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def process():\n    pass\n")
            f.flush()
            test_cmd = cmd.replace("svc.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result_text = open(f.name).read()
            os.unlink(f.name)
        assert "def process(log=True):" in result_text, f"Got: {result_text}"

        # Test with existing params: def process(self, data):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def process(self, data):\n    pass\n")
            f.flush()
            test_cmd = cmd.replace("svc.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result_text = open(f.name).read()
            os.unlink(f.name)
        assert "def process(self, data, log=True):" in result_text, f"Got: {result_text}"

    def test_add_argument_generates_command(self):
        """add_argument edit includes a sed command for single-line calls."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        host.add_node(GraphNode(
            "func:foo", NodeType.FUNCTION, {"name": "foo"},
        ))
        host.add_node(GraphNode(
            "call:test.py:10:1", NodeType.CALL,
            {"callee": "foo", "file": "test.py", "line": 10},
        ))
        host.add_edge(GraphEdge("call:test.py:10:1", "func:foo", EdgeType.CALLS))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_ARG,
            {"callee": "foo", "arg_name": "verbose", "arg_value": "True"},
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        arg_edits = [e for e in edits if e.edit_type == "add_argument"]
        assert len(arg_edits) == 1
        cmd = arg_edits[0].details["command"]
        assert "10s/" in cmd, "Must target call site line"
        assert "verbose=True" in cmd, "Must include keyword arg"
        assert "\\<foo\\>" in cmd, "Must use word boundaries for callee"

    def test_add_argument_sed_works(self):
        """add_argument sed handles both empty and non-empty arg lists."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes
        import subprocess, tempfile, os

        host = TypedGraph()
        host.add_node(GraphNode(
            "func:run", NodeType.FUNCTION, {"name": "run"},
        ))
        host.add_node(GraphNode(
            "call:main.py:5:1", NodeType.CALL,
            {"callee": "run", "file": "main.py", "line": 5},
        ))
        host.add_edge(GraphEdge("call:main.py:5:1", "func:run", EdgeType.CALLS))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_ARG,
            {"callee": "run", "arg_name": "dry", "arg_value": "False"},
        )
        result = engine.apply_rule(rule, host)
        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        arg_edits = [e for e in edits if e.edit_type == "add_argument"]
        cmd = arg_edits[0].details["command"]

        # Test empty args: run()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n\n\n\nresult = run()\n")
            f.flush()
            test_cmd = cmd.replace("main.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result_text = open(f.name).read()
            os.unlink(f.name)
        assert "run(dry=False)" in result_text, f"Got: {result_text}"

        # Test with existing args: run(config)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n\n\n\nresult = run(config)\n")
            f.flush()
            test_cmd = cmd.replace("main.py", f.name)
            subprocess.run(test_cmd, shell=True, check=True)
            result_text = open(f.name).read()
            os.unlink(f.name)
        assert "run(config, dry=False)" in result_text, f"Got: {result_text}"

    # ----- File parameter disambiguation tests -----

    def test_add_param_file_filter_matches_correct_function(self):
        """add_param with file= only modifies the function in that file."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        # Two functions with the same name in different files
        host.add_node(GraphNode(
            "func:service.py:is_systemd_managed", NodeType.FUNCTION,
            {"name": "is_systemd_managed", "file": "service.py", "line": 279},
        ))
        host.add_node(GraphNode(
            "func:service_mgr.py:is_systemd_managed", NodeType.FUNCTION,
            {"name": "is_systemd_managed", "file": "service_mgr.py", "line": 45},
        ))

        engine = create_engine(check_invariants=False)
        # Target only service.py
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {
                "function_name": "is_systemd_managed",
                "param_name": "log",
                "default_value": "None",
                "file": "service.py",
            },
        )
        result = engine.apply_rule(rule, host)
        assert result.success

        edits = edits_from_changes(
            result.changes, result.result_graph, rule.name, rule.parameters
        )
        param_edits = [e for e in edits if e.edit_type == "add_parameter"]
        assert len(param_edits) == 1
        # Should target service.py, not service_mgr.py
        assert param_edits[0].file == "service.py"
        assert param_edits[0].details["function"] == "is_systemd_managed"

    def test_add_param_without_file_matches_any(self):
        """add_param without file= matches whichever function it finds."""
        host = TypedGraph()
        host.add_node(GraphNode(
            "func:a.py:foo", NodeType.FUNCTION,
            {"name": "foo", "file": "a.py", "line": 1},
        ))
        host.add_node(GraphNode(
            "func:b.py:foo", NodeType.FUNCTION,
            {"name": "foo", "file": "b.py", "line": 1},
        ))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "foo", "param_name": "x"},
        )
        result = engine.apply_rule(rule, host)
        # Without file filter, it matches one of them (non-deterministic which)
        assert result.success

    def test_add_param_file_filter_no_match(self):
        """add_param with file= targeting a nonexistent file fails."""
        host = TypedGraph()
        host.add_node(GraphNode(
            "func:a.py:foo", NodeType.FUNCTION,
            {"name": "foo", "file": "a.py", "line": 1},
        ))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_PARAM,
            {"function_name": "foo", "param_name": "x", "file": "nonexistent.py"},
        )
        result = engine.apply_rule(rule, host)
        # Should fail because no function named foo in nonexistent.py
        assert not result.success

    def test_add_arg_file_filter_matches_correct_calls(self):
        """add_arg with file= only modifies calls in that file."""
        from graph_transform.cli.commands.plan_cmd import edits_from_changes

        host = TypedGraph()
        # Calls to is_systemd_managed in different files
        host.add_node(GraphNode(
            "call:service.py:100:1", NodeType.CALL,
            {"callee": "is_systemd_managed", "file": "service.py",
             "line": 100, "call_type": "direct"},
        ))
        host.add_node(GraphNode(
            "call:hostname.py:50:1", NodeType.CALL,
            {"callee": "is_systemd_managed", "file": "hostname.py",
             "line": 50, "call_type": "method"},
        ))

        engine = create_engine(check_invariants=False)
        # Target only direct calls in service.py
        rule = engine.catalog.create_rule(
            OperatorType.ADD_ARG,
            {
                "callee": "is_systemd_managed",
                "arg_name": "log",
                "arg_value": "True",
                "file": "service.py",
            },
        )
        results = engine.apply_all_matches(rule, host)
        assert len(results) == 1
        assert results[0].success

        edits = edits_from_changes(
            results[0].changes, results[0].result_graph,
            rule.name, rule.parameters,
        )
        arg_edits = [e for e in edits if e.edit_type == "add_argument"]
        assert len(arg_edits) == 1
        assert arg_edits[0].file == "service.py"

    def test_add_arg_call_type_filter(self):
        """add_arg with call_type='direct' skips method calls."""
        host = TypedGraph()
        host.add_node(GraphNode(
            "call:a.py:10:1", NodeType.CALL,
            {"callee": "foo", "file": "a.py", "line": 10, "call_type": "direct"},
        ))
        host.add_node(GraphNode(
            "call:b.py:20:1", NodeType.CALL,
            {"callee": "foo", "file": "b.py", "line": 20, "call_type": "method"},
        ))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_ARG,
            {
                "callee": "foo",
                "arg_name": "debug",
                "arg_value": "True",
                "call_type": "direct",
            },
        )
        results = engine.apply_all_matches(rule, host)
        assert len(results) == 1
        assert results[0].success

    def test_add_arg_file_and_call_type_combined(self):
        """add_arg with both file= and call_type= for precise targeting."""
        host = TypedGraph()
        # 3 calls: direct in a.py, method in a.py, direct in b.py
        host.add_node(GraphNode(
            "call:a.py:10:1", NodeType.CALL,
            {"callee": "foo", "file": "a.py", "line": 10, "call_type": "direct"},
        ))
        host.add_node(GraphNode(
            "call:a.py:20:1", NodeType.CALL,
            {"callee": "foo", "file": "a.py", "line": 20, "call_type": "method"},
        ))
        host.add_node(GraphNode(
            "call:b.py:5:1", NodeType.CALL,
            {"callee": "foo", "file": "b.py", "line": 5, "call_type": "direct"},
        ))

        engine = create_engine(check_invariants=False)
        rule = engine.catalog.create_rule(
            OperatorType.ADD_ARG,
            {
                "callee": "foo",
                "arg_name": "log",
                "arg_value": "True",
                "file": "a.py",
                "call_type": "direct",
            },
        )
        results = engine.apply_all_matches(rule, host)
        # Should only match the direct call in a.py
        assert len(results) == 1
        assert results[0].success


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
        assert "steps" in data
        assert "summary" in data

        # Step structure
        step = data["steps"][0]
        assert "step" in step
        assert "operator" in step
        assert "params" in step
        assert "edits" in step
        assert step["step"] == 1
        assert step["operator"] == "add_method"

        # Summary
        assert data["summary"]["total_steps"] == 1
        assert data["summary"]["total_edits"] >= 1

    def test_plan_partial_output_on_step_failure(self, runner, tmp_path):
        """When a later step fails, earlier steps' results should still be output."""
        src = tmp_path / "mod.py"
        src.write_text("class MyClass:\n    pass\n")

        # Step 1: add_method (will succeed)
        # Step 2: rename_func with a non-existent function (will fail)
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(
            "steps:\n"
            "  - op: add_method\n"
            "    params:\n"
            "      class_name: MyClass\n"
            "      method_name: do_work\n"
            "  - op: rename_func\n"
            "    params:\n"
            "      old_name: no_such_function\n"
            "      new_name: renamed_fn\n"
        )

        result = runner.invoke(cli, ["plan", str(src), "-F", str(recipe)])
        assert result.exit_code != 0
        # Extract JSON from output (stderr error messages may precede it)
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])

        # Should have partial results from step 1
        assert data["partial"] is True
        assert "error" in data
        assert len(data["steps"]) == 1
        assert data["steps"][0]["operator"] == "add_method"
        assert len(data["steps"][0]["edits"]) >= 1
        assert data["summary"]["total_edits"] >= 1

    def test_plan_partial_output_to_file(self, runner, tmp_path):
        """Partial results should also be written to output file."""
        src = tmp_path / "mod.py"
        src.write_text("class MyClass:\n    pass\n")
        out = tmp_path / "plan.json"

        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(
            "steps:\n"
            "  - op: add_method\n"
            "    params:\n"
            "      class_name: MyClass\n"
            "      method_name: do_work\n"
            "  - op: rename_func\n"
            "    params:\n"
            "      old_name: nonexistent\n"
            "      new_name: renamed\n"
        )

        result = runner.invoke(cli, ["plan", str(src), "-F", str(recipe), "-o", str(out)])
        assert result.exit_code != 0
        # File should still be written with partial data
        data = json.loads(out.read_text())
        assert data["partial"] is True
        assert data["error"]
        assert len(data["steps"]) == 1

    def test_plan_update_import_names_no_match_is_warning(self, runner, tmp_path):
        """update_import with names should warn (not fail) when no imports match."""
        src = tmp_path / "mod.py"
        # A file with a function and import, but the update_import targets
        # names that don't exist in any import statement.
        src.write_text(
            "from os.path import join\n"
            "\ndef my_func():\n"
            "    return join('a', 'b')\n"
        )

        # update_import looking for names that don't exist in the import
        result = runner.invoke(
            cli,
            [
                "plan", str(src),
                "-op", "update_import",
                "-p", json.dumps({
                    "old_module": "os.path",
                    "new_module": "posixpath",
                    "names": ["nonexistent_name"],
                }),
            ],
        )
        # Should succeed (update_import with names is lenient)
        assert result.exit_code == 0, f"Should not fail: {result.output}"
        # Extract JSON from output (Rich warning messages may precede it)
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert len(data["steps"]) == 1
        assert data["steps"][0]["operator"] == "update_import"
        # 0 edits — no imports of the specified names found
        assert data["steps"][0]["edits"] == []
