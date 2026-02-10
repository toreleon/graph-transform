"""Tests for the plan command and primitives/compositions system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from graph_transform.cli import cli
from graph_transform.core.morphism import GraphMorphism
from graph_transform.core.primitives import (
    CompositionRegistry,
    EdgeKind,
    NodeKind,
    insert_edge,
    insert_node,
    delete_node,
    delete_edge,
    update,
    primitive_from_dict,
    Rename,
    Move,
    Extract,
)
from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)
from graph_transform.rewriting.graph_change import (
    ChangeType,
    EdgeChange,
    GraphChangeSet,
    NodeChange,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    graph = TypedGraph()
    graph.add_node(GraphNode("module:test", NodeType.MODULE, {"name": "test", "file": "test.py"}))
    graph.add_node(GraphNode("func:foo", NodeType.FUNCTION, {"name": "foo", "file": "test.py", "line": 5}))
    graph.add_node(GraphNode("class:Bar", NodeType.CLASS, {"name": "Bar", "file": "test.py", "line": 10}))
    graph.add_edge(GraphEdge("module:test", "func:foo", EdgeType.CONTAINS_METHOD))
    graph.add_edge(GraphEdge("module:test", "class:Bar", EdgeType.DEFINED_IN))
    return graph


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
# Test: Primitive Operations
# =========================================================================


class TestPrimitiveOperations:
    def test_insert_node_succeeds(self, sample_graph):
        """InsertNode adds a new node to the graph."""
        prim = insert_node(
            "func:new_helper",
            NodeKind.CALLABLE,
            {"name": "new_helper", "file": "test.py", "line": 20},
        )
        result = prim.execute(sample_graph)

        assert result.success
        assert "func:new_helper" in result.affected_ids
        assert sample_graph.has_node("func:new_helper")

    def test_insert_node_fails_if_exists(self, sample_graph):
        """InsertNode fails if node already exists."""
        prim = insert_node("func:foo", NodeKind.CALLABLE, {"name": "foo"})
        result = prim.execute(sample_graph)

        assert not result.success
        assert "already exists" in result.error

    def test_insert_edge_succeeds(self, sample_graph):
        """InsertEdge adds an edge between nodes."""
        # First add a method node
        sample_graph.add_node(GraphNode("func:method", NodeType.FUNCTION, {"name": "method"}))

        prim = insert_edge("class:Bar", "func:method", EdgeKind.CONTAINS)
        result = prim.execute(sample_graph)

        assert result.success
        assert sample_graph.has_edge("class:Bar", "func:method")

    def test_insert_edge_fails_if_node_missing(self, sample_graph):
        """InsertEdge fails if source or target node doesn't exist."""
        prim = insert_edge("class:Bar", "func:nonexistent", EdgeKind.CONTAINS)
        result = prim.execute(sample_graph)

        assert not result.success
        assert "does not exist" in result.error.lower()

    def test_delete_node_succeeds(self, sample_graph):
        """DeleteNode removes a node from the graph."""
        prim = delete_node("func:foo", cascade=True)
        result = prim.execute(sample_graph)

        assert result.success
        assert not sample_graph.has_node("func:foo")

    def test_delete_node_fails_if_not_exists(self, sample_graph):
        """DeleteNode fails if node doesn't exist."""
        prim = delete_node("func:nonexistent")
        result = prim.execute(sample_graph)

        assert not result.success
        assert "does not exist" in result.error.lower()

    def test_delete_edge_succeeds(self, sample_graph):
        """DeleteEdge removes an edge from the graph."""
        prim = delete_edge("module:test", "func:foo")
        result = prim.execute(sample_graph)

        assert result.success
        assert not sample_graph.has_edge("module:test", "func:foo")

    def test_update_succeeds(self, sample_graph):
        """Update modifies node properties."""
        prim = update("func:foo", prop="name", value="renamed_foo")
        result = prim.execute(sample_graph)

        assert result.success
        node = sample_graph.get_node("func:foo")
        assert node.attrs["name"] == "renamed_foo"

    def test_update_fails_if_node_missing(self, sample_graph):
        """Update fails if target doesn't exist."""
        prim = update("func:nonexistent", prop="name", value="new")
        result = prim.execute(sample_graph)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_primitive_from_dict(self, sample_graph):
        """primitive_from_dict deserializes and executes correctly."""
        data = {
            "primitive": "insert_node",
            "node_id": "func:from_dict",
            "node_kind": "callable",
            "attrs": {"name": "from_dict"},
        }
        prim = primitive_from_dict(data)
        result = prim.execute(sample_graph)

        assert result.success
        assert sample_graph.has_node("func:from_dict")


# =========================================================================
# Test: Composition Operations
# =========================================================================


class TestCompositionOperations:
    def test_rename_composition(self, sample_graph):
        """Rename composition updates node name and references."""
        rename = CompositionRegistry.create("RENAME", target="func:foo", new_name="renamed_func")
        result = rename.execute(sample_graph)

        assert result.success
        node = sample_graph.get_node("func:foo")
        assert node.attrs["name"] == "renamed_func"

    def test_rename_fails_if_target_missing(self, sample_graph):
        """Rename fails if target doesn't exist."""
        rename = CompositionRegistry.create("RENAME", target="func:nonexistent", new_name="new")
        result = rename.execute(sample_graph)

        assert not result.success
        assert "not found" in result.error.lower()

    def test_move_composition(self, sample_graph):
        """Move composition relocates a node between scopes."""
        # Add a second module as destination
        sample_graph.add_node(GraphNode("module:utils", NodeType.MODULE, {"name": "utils"}))

        move = CompositionRegistry.create(
            "MOVE",
            target="func:foo",
            from_scope="module:test",
            to_scope="module:utils",
        )
        result = move.execute(sample_graph)

        assert result.success
        # Check edge was moved
        assert not sample_graph.has_edge("module:test", "func:foo")

    def test_extract_composition(self, sample_graph):
        """Extract composition can be created."""
        extract = CompositionRegistry.create(
            "EXTRACT",
            new_id="func:extracted",
            new_name="extracted",
            node_kind=NodeKind.CALLABLE,
            scope="module:test",
            original="func:foo",
            replacement_value="extracted()",
        )
        # Just verify the composition can be created
        assert extract is not None
        assert extract.new_id == "func:extracted"
        assert extract.new_name == "extracted"

    def test_composition_registry_list(self):
        """CompositionRegistry.list_compositions returns all available compositions."""
        compositions = CompositionRegistry.list_compositions()
        assert "RENAME" in compositions
        assert "MOVE" in compositions
        assert "EXTRACT" in compositions
        assert "INLINE" in compositions
        assert "ADD_GUARD" in compositions
        assert "CHANGE_SIGNATURE" in compositions
        assert "WRAP" in compositions


# =========================================================================
# Test: EditInstruction generation
# =========================================================================


class TestEditsFromResults:
    def test_primitive_edit_generation(self, sample_graph):
        """Primitive results generate appropriate edit instructions."""
        from graph_transform.cli.commands.plan_cmd import edits_from_primitive_result

        prim = insert_node(
            "func:helper",
            NodeKind.CALLABLE,
            {"name": "helper", "file": "test.py", "line": 30},
        )
        result = prim.execute(sample_graph)

        params = {
            "node_id": "func:helper",
            "node_kind": "callable",
            "attrs": {"name": "helper", "file": "test.py", "line": 30},
        }
        edits = edits_from_primitive_result(result, "insert_node", params)

        assert len(edits) >= 1
        assert edits[0].edit_type == "add_callable"

    def test_composition_edit_generation(self, sample_graph):
        """Composition results generate appropriate edit instructions."""
        from graph_transform.cli.commands.plan_cmd import edits_from_composition_result

        rename = CompositionRegistry.create("RENAME", target="func:foo", new_name="bar")
        result = rename.execute(sample_graph)

        params = {"target": "func:foo", "new_name": "bar"}
        edits, hints = edits_from_composition_result(result, "RENAME", params)

        assert len(edits) == 1
        assert edits[0].edit_type == "rename"
        assert edits[0].details["new_name"] == "bar"
        assert hints == []  # RENAME doesn't generate hints


# =========================================================================
# Test: plan CLI command
# =========================================================================


class TestPlanCommand:
    def test_plan_inline_primitive(self, runner, tmp_path):
        """Plan command with inline primitive works."""
        src = tmp_path / "module.py"
        src.write_text("def existing():\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:new_func",
                    "node_kind": "callable",
                    "attrs": {"name": "new_func", "file": str(src), "line": 5},
                }),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "steps" in data
        assert len(data["steps"]) == 1
        assert data["steps"][0]["type"] == "primitive"
        assert data["steps"][0]["name"] == "insert_node"

    def test_plan_inline_composition(self, runner, tmp_path):
        """Plan command with inline composition works."""
        src = tmp_path / "module.py"
        src.write_text("def my_func():\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--composition", "RENAME",
                "-p", json.dumps({
                    "target": "func:my_func",
                    "new_name": "renamed_func",
                }),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "steps" in data
        assert len(data["steps"]) == 1
        assert data["steps"][0]["type"] == "composition"
        assert data["steps"][0]["name"] == "RENAME"

    def test_plan_output_file(self, runner, tmp_path):
        """Plan command writes to output file."""
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        out = tmp_path / "plan.json"

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:new",
                    "node_kind": "callable",
                    "attrs": {"name": "new"},
                }),
                "-o", str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert "steps" in data

    def test_plan_multi_step(self, runner, tmp_path):
        """Plan command handles multiple steps."""
        src = tmp_path / "app.py"
        src.write_text("class Config:\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:new1",
                    "node_kind": "callable",
                    "attrs": {"name": "new1"},
                }),
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:new2",
                    "node_kind": "callable",
                    "attrs": {"name": "new2"},
                }),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["steps"]) == 2

    def test_plan_yaml_file(self, runner, tmp_path):
        """Plan command with YAML recipe file."""
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        yaml_file = tmp_path / "refactor.yaml"
        yaml_file.write_text(
            "description: Test refactoring\n"
            "steps:\n"
            "  - primitive: insert_node\n"
            "    params:\n"
            "      node_id: func:helper\n"
            "      node_kind: callable\n"
            "      attrs:\n"
            "        name: helper\n"
        )

        result = runner.invoke(
            cli,
            ["plan", str(src), "-F", str(yaml_file)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["steps"]) == 1
        assert data["steps"][0]["name"] == "insert_node"

    def test_plan_yaml_with_composition(self, runner, tmp_path):
        """Plan command with composition in YAML file."""
        src = tmp_path / "mod.py"
        src.write_text("def old_func():\n    pass\n")
        yaml_file = tmp_path / "refactor.yaml"
        yaml_file.write_text(
            "steps:\n"
            "  - composition: RENAME\n"
            "    params:\n"
            "      target: func:old_func\n"
            "      new_name: new_func\n"
        )

        result = runner.invoke(
            cli,
            ["plan", str(src), "-F", str(yaml_file)],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["steps"]) == 1
        assert data["steps"][0]["type"] == "composition"
        assert data["steps"][0]["name"] == "RENAME"

    def test_plan_no_source_path(self, runner):
        """Plan command fails without source path."""
        result = runner.invoke(
            cli,
            [
                "plan",
                "--primitive", "insert_node",
                "-p", json.dumps({"node_id": "test", "node_kind": "callable"}),
            ],
        )
        assert result.exit_code == 2

    def test_plan_no_operations(self, runner, tmp_path):
        """Plan command fails without operations."""
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        result = runner.invoke(cli, ["plan", str(src)])
        assert result.exit_code == 2

    def test_plan_invalid_primitive(self, runner, tmp_path):
        """Plan command fails with invalid primitive name."""
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")
        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--primitive", "nonexistent_primitive",
                "-p", "{}",
            ],
        )
        assert result.exit_code == 1

    def test_plan_verbose(self, runner, tmp_path):
        """Plan command verbose mode works."""
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:test",
                    "node_kind": "callable",
                    "attrs": {"name": "test"},
                }),
                "-v",
                "-o", str(tmp_path / "plan.json"),
            ],
        )
        assert result.exit_code == 0
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
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:run",
                    "node_kind": "callable",
                    "attrs": {"name": "run"},
                }),
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
        assert "type" in step
        assert "name" in step
        assert "params" in step
        assert "edits" in step
        assert step["step"] == 1
        assert step["type"] == "primitive"
        assert step["name"] == "insert_node"

        # Summary
        assert data["summary"]["total_steps"] == 1

    def test_plan_partial_output_on_step_failure(self, runner, tmp_path):
        """When a later step fails, earlier steps' results should still be output."""
        src = tmp_path / "mod.py"
        src.write_text("class MyClass:\n    pass\n")

        # Step 1: insert_node (will succeed)
        # Step 2: update with non-existent target (will fail)
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(
            "steps:\n"
            "  - primitive: insert_node\n"
            "    params:\n"
            "      node_id: func:new\n"
            "      node_kind: callable\n"
            "      attrs:\n"
            "        name: new\n"
            "  - primitive: update\n"
            "    params:\n"
            "      target: nonexistent\n"
            "      prop: name\n"
            "      value: renamed\n"
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
        assert data["steps"][0]["name"] == "insert_node"

    def test_plan_partial_output_to_file(self, runner, tmp_path):
        """Partial results should also be written to output file."""
        src = tmp_path / "mod.py"
        src.write_text("class MyClass:\n    pass\n")
        out = tmp_path / "plan.json"

        recipe = tmp_path / "recipe.yaml"
        recipe.write_text(
            "steps:\n"
            "  - primitive: insert_node\n"
            "    params:\n"
            "      node_id: func:new\n"
            "      node_kind: callable\n"
            "      attrs:\n"
            "        name: new\n"
            "  - primitive: delete_node\n"
            "    params:\n"
            "      node_id: nonexistent\n"
        )

        result = runner.invoke(cli, ["plan", str(src), "-F", str(recipe), "-o", str(out)])
        assert result.exit_code != 0
        # File should still be written with partial data
        data = json.loads(out.read_text())
        assert data["partial"] is True
        assert data["error"]
        assert len(data["steps"]) == 1

    def test_plan_mixed_primitives_and_compositions(self, runner, tmp_path):
        """Plan with both primitives and compositions."""
        src = tmp_path / "mod.py"
        src.write_text("def existing():\n    pass\n")

        result = runner.invoke(
            cli,
            [
                "plan",
                str(src),
                "--primitive", "insert_node",
                "-p", json.dumps({
                    "node_id": "func:new",
                    "node_kind": "callable",
                    "attrs": {"name": "new"},
                }),
                "--composition", "RENAME",
                "-p", json.dumps({
                    "target": "func:existing",
                    "new_name": "old",
                }),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data["steps"]) == 2
        assert data["steps"][0]["type"] == "primitive"
        assert data["steps"][1]["type"] == "composition"
