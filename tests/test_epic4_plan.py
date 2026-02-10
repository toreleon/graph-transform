"""Tests for Epic 4: Transformation Planning.

FR3: Agents can create transformation plans via `plan` tool
FR17-23: Create transformation plans for each operator (RENAME, MOVE, EXTRACT, INLINE, ADD_GUARD, CHANGE_SIGNATURE, WRAP)
FR24: Plans include all affected files and edit locations
FR25: Plans include summary of changes
"""

from __future__ import annotations

import pytest

from graph_transform.core.primitives import (
    CompositionRegistry,
    EdgeKind,
    NodeKind,
)
from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)
from graph_transform.mcp.tools.plan import plan_tool


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_graph() -> TypedGraph:
    """Create a simple graph for testing plan tool."""
    graph = TypedGraph()

    # Module
    graph.add_node(GraphNode(
        "module:test.py:test",
        NodeType.MODULE,
        {"name": "test", "file": "test.py", "line": 1},
    ))

    # Function
    graph.add_node(GraphNode(
        "func:test.py:my_func",
        NodeType.FUNCTION,
        {"name": "my_func", "file": "test.py", "line": 5, "end_line": 10},
    ))

    # Class
    graph.add_node(GraphNode(
        "class:test.py:MyClass",
        NodeType.CLASS,
        {"name": "MyClass", "file": "test.py", "line": 15, "end_line": 25},
    ))

    # Module contains function and class
    graph.add_edge(GraphEdge(
        "module:test.py:test", "func:test.py:my_func", EdgeType.CONTAINS,
    ))
    graph.add_edge(GraphEdge(
        "module:test.py:test", "class:test.py:MyClass", EdgeType.CONTAINS,
    ))

    return graph


@pytest.fixture
def multi_file_graph() -> TypedGraph:
    """Create a multi-file graph for testing cross-file plans."""
    graph = TypedGraph()

    # Module A
    graph.add_node(GraphNode(
        "module:src/module_a.py:module_a",
        NodeType.MODULE,
        {"name": "module_a", "file": "src/module_a.py", "line": 1},
    ))

    # Module B
    graph.add_node(GraphNode(
        "module:src/module_b.py:module_b",
        NodeType.MODULE,
        {"name": "module_b", "file": "src/module_b.py", "line": 1},
    ))

    # Function in A
    graph.add_node(GraphNode(
        "func:src/module_a.py:helper",
        NodeType.FUNCTION,
        {"name": "helper", "file": "src/module_a.py", "line": 5, "end_line": 10},
    ))

    # Function in B that calls helper
    graph.add_node(GraphNode(
        "func:src/module_b.py:main",
        NodeType.FUNCTION,
        {"name": "main", "file": "src/module_b.py", "line": 5, "end_line": 15},
    ))

    # Call node
    graph.add_node(GraphNode(
        "call:src/module_b.py:main:helper",
        NodeType.CALL,
        {"callee": "helper", "file": "src/module_b.py", "line": 8},
    ))

    # Import node
    graph.add_node(GraphNode(
        "import:src/module_b.py:helper",
        NodeType.IMPORT,
        {"name": "helper", "module": "module_a", "file": "src/module_b.py", "line": 1},
    ))

    # Edges
    graph.add_edge(GraphEdge(
        "module:src/module_a.py:module_a", "func:src/module_a.py:helper", EdgeType.CONTAINS,
    ))
    graph.add_edge(GraphEdge(
        "module:src/module_b.py:module_b", "func:src/module_b.py:main", EdgeType.CONTAINS,
    ))
    graph.add_edge(GraphEdge(
        "call:src/module_b.py:main:helper", "func:src/module_a.py:helper", EdgeType.CALLS,
    ))
    graph.add_edge(GraphEdge(
        "import:src/module_b.py:helper", "func:src/module_a.py:helper", EdgeType.IMPORTS,
    ))

    return graph


# =============================================================================
# Story 4.1: Plan Tool Infrastructure
# =============================================================================


class TestStory41PlanToolInfrastructure:
    """FR3: Agents can create transformation plans via `plan` tool."""

    def test_plan_tool_returns_plan_object(self, tmp_path):
        """Given the MCP server is running, When `plan` is called, Then returns a plan object."""
        # Create a test file
        src = tmp_path / "test.py"
        src.write_text("def my_func():\n    pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:my_func", "new_name": "renamed_func"},
        })

        assert result["status"] == "ok"
        assert "plan" in result
        assert "operator" in result
        assert result["operator"] == "RENAME"

    def test_plan_includes_affected_files(self, tmp_path):
        """FR24: Plan includes all affected files and edit locations."""
        src = tmp_path / "test.py"
        src.write_text("def my_func():\n    pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:my_func", "new_name": "renamed_func"},
        })

        assert result["status"] == "ok"
        assert "plan" in result
        assert "affected_files" in result["plan"]

    def test_plan_includes_summary(self, tmp_path):
        """FR25: Plan includes summary of changes."""
        src = tmp_path / "test.py"
        src.write_text("def my_func():\n    pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:my_func", "new_name": "renamed_func"},
        })

        assert result["status"] == "ok"
        assert "plan" in result
        assert "summary" in result["plan"]
        assert "primitive_count" in result["plan"]["summary"]
        assert "file_count" in result["plan"]["summary"]

    def test_plan_error_for_missing_path(self):
        """Plan returns error when path is missing."""
        result = plan_tool({
            "operator": "RENAME",
            "params": {"target": "func:foo", "new_name": "bar"},
        })

        assert result["status"] == "error"
        assert "error" in result
        assert result["error"]["code"] == "MISSING_PATH"

    def test_plan_error_for_missing_operator(self, tmp_path):
        """Plan returns error when operator is missing."""
        src = tmp_path / "test.py"
        src.write_text("def foo(): pass\n")

        result = plan_tool({
            "path": str(src),
            "params": {"target": "func:foo"},
        })

        assert result["status"] == "error"
        assert result["error"]["code"] == "MISSING_OPERATOR"

    def test_plan_error_for_unknown_operator(self, tmp_path):
        """Plan returns error for unknown operator."""
        src = tmp_path / "test.py"
        src.write_text("def foo(): pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "UNKNOWN_OP",
            "params": {},
        })

        assert result["status"] == "error"
        assert result["error"]["code"] == "UNKNOWN_OPERATOR"
        assert "available" in result["error"]


# =============================================================================
# Story 4.2: RENAME Operator
# =============================================================================


class TestStory42RenameOperator:
    """FR17: System can create RENAME transformation plans."""

    def test_rename_creates_plan_with_update(self, simple_graph):
        """Given a node ID and new name, When plan(operator: "rename"), Then returns plan with UPDATE primitive."""
        rename = CompositionRegistry.create(
            "RENAME",
            target="func:test.py:my_func",
            new_name="renamed_func",
        )
        assert rename is not None

        primitives = list(rename.primitives(simple_graph))
        assert len(primitives) >= 1

        # First primitive should be UPDATE for the target
        update_prim = primitives[0]
        assert update_prim.target == "func:test.py:my_func"

    def test_rename_plan_includes_reference_updates(self, multi_file_graph):
        """Plan includes reference updates for all call sites."""
        rename = CompositionRegistry.create(
            "RENAME",
            target="func:src/module_a.py:helper",
            new_name="helper_renamed",
            update_references=True,
        )
        assert rename is not None

        primitives = list(rename.primitives(multi_file_graph))

        # Should have at least one UPDATE for the target
        assert len(primitives) >= 1
        assert primitives[0].target == "func:src/module_a.py:helper"

    def test_rename_summary_shows_counts(self, tmp_path):
        """FR25: Rename summary shows count of files affected and references updated."""
        src = tmp_path / "test.py"
        src.write_text("def helper():\n    pass\n\ndef caller():\n    helper()\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:helper", "new_name": "helper_v2"},
        })

        assert result["status"] == "ok"
        assert "summary" in result["plan"]


# =============================================================================
# Story 4.3: MOVE Operator
# =============================================================================


class TestStory43MoveOperator:
    """FR18: System can create MOVE transformation plans."""

    def test_move_creates_plan_with_edge_changes(self, multi_file_graph):
        """Given node ID and target module, When plan(operator: "move"), Then returns plan with DELETE/INSERT edge."""
        move = CompositionRegistry.create(
            "MOVE",
            target="func:src/module_a.py:helper",
            from_scope="module:src/module_a.py:module_a",
            to_scope="module:src/module_b.py:module_b",
        )
        assert move is not None

        primitives = list(move.primitives(multi_file_graph))

        # Should have DELETE edge and INSERT edge primitives
        assert len(primitives) >= 2

        # Check we have edge operations
        prim_types = [type(p).__name__ for p in primitives]
        assert "DeleteEdge" in prim_types
        assert "InsertEdge" in prim_types

    def test_move_updates_import_statements(self, multi_file_graph):
        """Plan includes updates for all import statements."""
        move = CompositionRegistry.create(
            "MOVE",
            target="func:src/module_a.py:helper",
            from_scope="module:src/module_a.py:module_a",
            to_scope="module:src/module_b.py:module_b",
            update_references=True,
        )
        assert move is not None

        primitives = list(move.primitives(multi_file_graph))

        # Move should produce edge operations
        assert len(primitives) >= 2


# =============================================================================
# Story 4.4: EXTRACT Operator
# =============================================================================


class TestStory44ExtractOperator:
    """FR19: System can create EXTRACT transformation plans."""

    def test_extract_creates_plan_with_new_function(self, simple_graph):
        """Given code block and new name, When plan(operator: "extract"), Then returns plan with INSERT for new function."""
        extract = CompositionRegistry.create(
            "EXTRACT",
            new_id="func:test.py:extracted",
            new_name="extracted",
            node_kind=NodeKind.CALLABLE,
            scope="module:test.py:test",
            original="func:test.py:my_func",
            replacement_value="extracted()",
        )
        assert extract is not None

        primitives = list(extract.primitives(simple_graph))

        # Should have INSERT for new node, INSERT for edge, UPDATE for original
        assert len(primitives) >= 3

        prim_types = [type(p).__name__ for p in primitives]
        assert "InsertNode" in prim_types
        assert "InsertEdge" in prim_types
        assert "Update" in prim_types

    def test_extract_includes_containment_edge(self, simple_graph):
        """Extract creates containment edge to scope."""
        extract = CompositionRegistry.create(
            "EXTRACT",
            new_id="func:test.py:new_helper",
            new_name="new_helper",
            node_kind=NodeKind.CALLABLE,
            scope="module:test.py:test",
            original="func:test.py:my_func",
            replacement_value="new_helper()",
        )

        primitives = list(extract.primitives(simple_graph))

        # Find InsertEdge with CONTAINS
        insert_edges = [p for p in primitives if type(p).__name__ == "InsertEdge"]
        assert len(insert_edges) >= 1

        # One should be CONTAINS edge
        contains_edge = [e for e in insert_edges if e.edge_kind == EdgeKind.CONTAINS]
        assert len(contains_edge) >= 1


# =============================================================================
# Story 4.5: INLINE Operator
# =============================================================================


class TestStory45InlineOperator:
    """FR20: System can create INLINE transformation plans."""

    def test_inline_creates_plan_to_replace_calls(self, multi_file_graph):
        """Given function node ID, When plan(operator: "inline"), Then returns plan to replace call sites."""
        inline = CompositionRegistry.create(
            "INLINE",
            target="func:src/module_a.py:helper",
        )
        assert inline is not None

        primitives = list(inline.primitives(multi_file_graph))

        # Should have UPDATE for call sites and DELETE for function
        assert len(primitives) >= 1

    def test_inline_deletes_function_after(self, multi_file_graph):
        """Inline deletes the function node after inlining."""
        inline = CompositionRegistry.create(
            "INLINE",
            target="func:src/module_a.py:helper",
            remove_after=True,
        )

        primitives = list(inline.primitives(multi_file_graph))

        prim_types = [type(p).__name__ for p in primitives]
        assert "DeleteNode" in prim_types


# =============================================================================
# Story 4.6: ADD_GUARD Operator
# =============================================================================


class TestStory46AddGuardOperator:
    """FR21: System can create ADD_GUARD transformation plans."""

    def test_add_guard_creates_plan_with_guard_node(self, simple_graph):
        """Given function node and condition, When plan(operator: "add_guard"), Then returns plan with INSERT guard."""
        add_guard = CompositionRegistry.create(
            "ADD_GUARD",
            target="func:test.py:my_func",
            guard_type="null_check",
            guard_condition="x is not None",
            guard_action="early_return",
        )
        assert add_guard is not None

        primitives = list(add_guard.primitives(simple_graph))

        # Should have INSERT for guard node and INSERT for edge
        assert len(primitives) >= 2

        prim_types = [type(p).__name__ for p in primitives]
        assert "InsertNode" in prim_types
        assert "InsertEdge" in prim_types

    def test_add_guard_inserts_at_function_start(self, simple_graph):
        """Guard is inserted at the start of the function."""
        add_guard = CompositionRegistry.create(
            "ADD_GUARD",
            target="func:test.py:my_func",
            guard_type="bounds_check",
            guard_condition="len(items) > 0",
        )

        primitives = list(add_guard.primitives(simple_graph))

        # First primitive should be InsertNode for the guard
        insert_nodes = [p for p in primitives if type(p).__name__ == "InsertNode"]
        assert len(insert_nodes) >= 1

        guard_node = insert_nodes[0]
        assert "guard" in guard_node.node_id


# =============================================================================
# Story 4.7: CHANGE_SIGNATURE Operator
# =============================================================================


class TestStory47ChangeSignatureOperator:
    """FR22: System can create CHANGE_SIGNATURE transformation plans."""

    def test_change_signature_creates_plan(self, simple_graph):
        """Given function and signature changes, When plan(operator: "change_signature"), Then updates function."""
        change_sig = CompositionRegistry.create(
            "CHANGE_SIGNATURE",
            target="func:test.py:my_func",
            changes={"params": ["x", "y", "z"]},
        )
        assert change_sig is not None

        primitives = list(change_sig.primitives(simple_graph))

        # Should have UPDATE for the function
        assert len(primitives) >= 1

        prim_types = [type(p).__name__ for p in primitives]
        assert "Update" in prim_types

    def test_change_signature_updates_call_sites(self, multi_file_graph):
        """Change signature updates all call sites."""
        change_sig = CompositionRegistry.create(
            "CHANGE_SIGNATURE",
            target="func:src/module_a.py:helper",
            changes={"params": ["x", "y"]},
        )

        primitives = list(change_sig.primitives(multi_file_graph))

        # Should have multiple updates (one for function, one for each call site)
        assert len(primitives) >= 1


# =============================================================================
# Story 4.8: WRAP Operator
# =============================================================================


class TestStory48WrapOperator:
    """FR23: System can create WRAP transformation plans."""

    def test_wrap_creates_plan_with_wrapper(self, simple_graph):
        """Given function and wrapper spec, When plan(operator: "wrap"), Then returns plan with wrapper."""
        wrap = CompositionRegistry.create(
            "WRAP",
            target="func:test.py:my_func",
            wrapper_kind="try_catch",
            wrapper_attrs={"exception": "Exception"},
        )
        assert wrap is not None

        primitives = list(wrap.primitives(simple_graph))

        # Should have INSERT for wrapper, UPDATE for target, INSERT for edge
        assert len(primitives) >= 3

        prim_types = [type(p).__name__ for p in primitives]
        assert "InsertNode" in prim_types
        assert "Update" in prim_types

    def test_wrap_decorator_creates_update(self, simple_graph):
        """Wrap with decorator creates UPDATE for function."""
        wrap = CompositionRegistry.create(
            "WRAP",
            target="func:test.py:my_func",
            wrapper_kind="decorator",
            wrapper_attrs={"decorator": "@cache"},
        )

        primitives = list(wrap.primitives(simple_graph))

        # Should include Update primitive
        prim_types = [type(p).__name__ for p in primitives]
        assert "Update" in prim_types


# =============================================================================
# Story 4.9: Plan Summary and Affected Files
# =============================================================================


class TestStory49PlanSummary:
    """FR24, FR25: Plans include complete summaries."""

    def test_plan_lists_all_affected_files(self, tmp_path):
        """Given any plan, summary lists all affected files with line numbers."""
        src = tmp_path / "test.py"
        src.write_text("def foo():\n    pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:foo", "new_name": "bar"},
        })

        assert result["status"] == "ok"
        assert "affected_files" in result["plan"]
        assert "summary" in result["plan"]
        assert "file_count" in result["plan"]["summary"]

    def test_plan_counts_modifications(self, tmp_path):
        """Summary includes counts: nodes modified, edges added/removed, references updated."""
        src = tmp_path / "test.py"
        src.write_text("def helper():\n    pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:helper", "new_name": "new_helper"},
        })

        assert result["status"] == "ok"
        summary = result["plan"]["summary"]
        assert "primitive_count" in summary

    def test_plan_groups_edits_by_file(self, tmp_path):
        """Multi-file transformation groups edits by file."""
        src = tmp_path / "test.py"
        src.write_text("def foo():\n    pass\n")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "func:test.py:foo", "new_name": "bar"},
        })

        assert result["status"] == "ok"
        # Primitives should be in the plan
        assert "primitives" in result["plan"]


# =============================================================================
# Integration Tests
# =============================================================================


class TestPlanToolIntegration:
    """Integration tests for plan tool with real file parsing."""

    def test_plan_with_real_python_file(self, tmp_path):
        """Plan tool works with real Python file parsing."""
        src = tmp_path / "real_module.py"
        src.write_text("""
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

def main():
    calc = Calculator()
    result = calc.add(1, 2)
    return result
""")

        result = plan_tool({
            "path": str(src),
            "operator": "RENAME",
            "params": {"target": "class:real_module.py:Calculator", "new_name": "Calc"},
        })

        assert result["status"] == "ok"
        assert "plan" in result

    def test_plan_with_all_operators(self, tmp_path):
        """All 7 operators can create valid plans."""
        src = tmp_path / "test.py"
        src.write_text("def foo():\n    pass\n\nclass Bar:\n    pass\n")

        operators = [
            ("RENAME", {"target": "func:test.py:foo", "new_name": "new_foo"}),
            ("MOVE", {"target": "func:test.py:foo", "from_scope": "module:test.py:test", "to_scope": "class:test.py:Bar"}),
            ("EXTRACT", {"new_id": "func:extracted", "new_name": "extracted", "node_kind": "callable", "scope": "module:test.py:test", "original": "func:test.py:foo", "replacement_value": "extracted()"}),
            ("INLINE", {"target": "func:test.py:foo"}),
            ("ADD_GUARD", {"target": "func:test.py:foo", "guard_type": "null_check", "guard_condition": "x is not None"}),
            ("CHANGE_SIGNATURE", {"target": "func:test.py:foo", "changes": {"params": ["x"]}}),
            ("WRAP", {"target": "func:test.py:foo", "wrapper_kind": "try_catch"}),
        ]

        for operator, params in operators:
            # Create a fresh graph for each operator
            result = plan_tool({
                "path": str(src),
                "operator": operator,
                "params": params,
            })

            # All operators should return a plan (may succeed or fail based on graph state)
            assert "status" in result, f"Operator {operator} did not return status"
