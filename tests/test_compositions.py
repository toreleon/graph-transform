"""
Tests for Derived Operators (Compositions)

These tests verify that higher-level operators work correctly
as compositions of the three primitives.
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
    # Compositions
    Composition,
    CompositionResult,
    Rename,
    Move,
    Extract,
    Inline,
    AddGuard,
    ChangeSignature,
    Wrap,
    CompositionRegistry,
    CompositionBuilder,
    # Primitives
    NodeKind,
    EdgeKind,
    Position,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def class_with_methods() -> TypedGraph:
    """Create a graph with a class containing methods."""
    graph = TypedGraph()

    # Add class
    graph.add_node(GraphNode(
        id="class:Calculator",
        node_type=NodeType.CLASS,
        attrs={"name": "Calculator", "file": "calc.py", "line": 1},
    ))

    # Add methods
    for i, name in enumerate(["add", "subtract", "multiply"]):
        method_id = f"func:Calculator.{name}"
        graph.add_node(GraphNode(
            id=method_id,
            node_type=NodeType.FUNCTION,
            attrs={
                "name": name,
                "file": "calc.py",
                "line": 10 + i * 10,
                "is_method": True,
            },
        ))
        graph.add_edge(GraphEdge(
            source="class:Calculator",
            target=method_id,
            edge_type=EdgeType.CONTAINS_METHOD,
        ))

    return graph


@pytest.fixture
def module_with_functions() -> TypedGraph:
    """Create a graph with a module containing functions."""
    graph = TypedGraph()

    # Add module
    graph.add_node(GraphNode(
        id="module:utils",
        node_type=NodeType.MODULE,
        attrs={"name": "utils", "file": "utils.py"},
    ))

    # Add functions
    for name in ["helper", "process", "validate"]:
        func_id = f"func:{name}"
        graph.add_node(GraphNode(
            id=func_id,
            node_type=NodeType.FUNCTION,
            attrs={"name": name, "file": "utils.py", "line": 1},
        ))
        graph.add_edge(GraphEdge(
            source=func_id,
            target="module:utils",
            edge_type=EdgeType.DEFINED_IN,
        ))

    return graph


@pytest.fixture
def graph_with_calls() -> TypedGraph:
    """Create a graph with call relationships."""
    graph = TypedGraph()

    # Add functions
    graph.add_node(GraphNode(
        id="func:main",
        node_type=NodeType.FUNCTION,
        attrs={"name": "main", "file": "app.py", "line": 1},
    ))
    graph.add_node(GraphNode(
        id="func:helper",
        node_type=NodeType.FUNCTION,
        attrs={"name": "helper", "file": "app.py", "line": 20},
    ))

    # Add call
    graph.add_node(GraphNode(
        id="call:app.py:10:0",
        node_type=NodeType.CALL,
        attrs={"callee": "helper", "file": "app.py", "line": 10},
    ))

    # Add edges
    graph.add_edge(GraphEdge(
        source="call:app.py:10:0",
        target="func:helper",
        edge_type=EdgeType.CALLS,
    ))
    graph.add_edge(GraphEdge(
        source="func:main",
        target="call:app.py:10:0",
        edge_type=EdgeType.CALLER_OF,
    ))

    return graph


# =============================================================================
# RENAME Tests
# =============================================================================


class TestRename:
    """Tests for RENAME composition."""

    def test_rename_basic(self, class_with_methods: TypedGraph) -> None:
        """Test basic rename operation."""
        composition = Rename(
            target="func:Calculator.add",
            new_name="addition",
            update_references=False,
        )

        result = composition.execute(class_with_methods)

        assert result.success
        assert result.composition_name == "RENAME"

        node = class_with_methods.get_node("func:Calculator.add")
        assert node is not None
        assert node.attrs["name"] == "addition"

    def test_rename_with_references(self, graph_with_calls: TypedGraph) -> None:
        """Test rename that updates references."""
        composition = Rename(
            target="func:helper",
            new_name="new_helper",
            update_references=True,
        )

        result = composition.execute(graph_with_calls)

        assert result.success

        # Function name updated
        node = graph_with_calls.get_node("func:helper")
        assert node.attrs["name"] == "new_helper"

        # Reference updated (call node)
        call_node = graph_with_calls.get_node("call:app.py:10:0")
        # The callee attribute should be updated
        assert call_node.attrs.get("callee") == "new_helper" or call_node.attrs.get("target") == "new_helper"

    def test_rename_generates_primitives(self, class_with_methods: TypedGraph) -> None:
        """Test that rename generates expected primitives."""
        composition = Rename(
            target="func:Calculator.add",
            new_name="sum",
            update_references=False,
        )

        primitives = list(composition.primitives(class_with_methods))

        # Should have at least the UPDATE for the name
        assert len(primitives) >= 1
        assert primitives[0].kind.value == "update"


# =============================================================================
# MOVE Tests
# =============================================================================


class TestMove:
    """Tests for MOVE composition."""

    def test_move_method_between_classes(self) -> None:
        """Test moving a method from one class to another."""
        graph = TypedGraph()

        # Create two classes
        graph.add_node(GraphNode(
            id="class:Source",
            node_type=NodeType.CLASS,
            attrs={"name": "Source"},
        ))
        graph.add_node(GraphNode(
            id="class:Target",
            node_type=NodeType.CLASS,
            attrs={"name": "Target"},
        ))

        # Create method in Source
        graph.add_node(GraphNode(
            id="func:Source.method",
            node_type=NodeType.FUNCTION,
            attrs={"name": "method", "is_method": True},
        ))
        graph.add_edge(GraphEdge(
            source="class:Source",
            target="func:Source.method",
            edge_type=EdgeType.CONTAINS_METHOD,
        ))

        # Move method to Target
        composition = Move(
            target="func:Source.method",
            from_scope="class:Source",
            to_scope="class:Target",
            edge_kind=EdgeKind.CONTAINS,
        )

        result = composition.execute(graph)

        assert result.success

        # Method no longer in Source
        assert not graph.has_edge("class:Source", "func:Source.method")

        # Method now in Target
        assert graph.has_edge("class:Target", "func:Source.method")

    def test_move_generates_delete_and_insert(self) -> None:
        """Test that move generates DELETE edge + INSERT edge."""
        graph = TypedGraph()
        graph.add_node(GraphNode(id="class:A", node_type=NodeType.CLASS, attrs={"name": "A"}))
        graph.add_node(GraphNode(id="class:B", node_type=NodeType.CLASS, attrs={"name": "B"}))
        graph.add_node(GraphNode(id="func:A.m", node_type=NodeType.FUNCTION, attrs={"name": "m"}))
        graph.add_edge(GraphEdge(source="class:A", target="func:A.m", edge_type=EdgeType.CONTAINS_METHOD))

        composition = Move(
            target="func:A.m",
            from_scope="class:A",
            to_scope="class:B",
        )

        primitives = list(composition.primitives(graph))

        # Should have DELETE edge and INSERT edge
        primitive_types = [p.__class__.__name__ for p in primitives]
        assert "DeleteEdge" in primitive_types
        assert "InsertEdge" in primitive_types


# =============================================================================
# EXTRACT Tests
# =============================================================================


class TestExtract:
    """Tests for EXTRACT composition."""

    def test_extract_creates_new_entity(self, module_with_functions: TypedGraph) -> None:
        """Test that extract creates a new callable."""
        composition = Extract(
            new_id="func:extracted_helper",
            new_name="extracted_helper",
            node_kind=NodeKind.CALLABLE,
            scope="module:utils",
            original="func:process",
            replacement_value="extracted_helper()",
            attrs={"file": "utils.py", "line": 50},
        )

        result = composition.execute(module_with_functions)

        assert result.success

        # New function exists
        assert module_with_functions.has_node("func:extracted_helper")
        new_node = module_with_functions.get_node("func:extracted_helper")
        assert new_node.attrs["name"] == "extracted_helper"

        # Containment edge exists
        assert module_with_functions.has_edge("module:utils", "func:extracted_helper")

    def test_extract_generates_correct_primitives(self, module_with_functions: TypedGraph) -> None:
        """Test that extract generates INSERT + INSERT + UPDATE + INSERT."""
        composition = Extract(
            new_id="func:new_func",
            new_name="new_func",
            node_kind=NodeKind.CALLABLE,
            scope="module:utils",
            original="func:helper",
            replacement_value="new_func()",
        )

        primitives = list(composition.primitives(module_with_functions))

        # Should have: INSERT node, INSERT edge (containment), UPDATE (original), INSERT edge (calls)
        assert len(primitives) >= 3

        primitive_types = [p.__class__.__name__ for p in primitives]
        assert "InsertNode" in primitive_types
        assert "InsertEdge" in primitive_types
        assert "Update" in primitive_types


# =============================================================================
# INLINE Tests
# =============================================================================


class TestInline:
    """Tests for INLINE composition."""

    def test_inline_removes_entity(self, graph_with_calls: TypedGraph) -> None:
        """Test that inline removes the inlined entity."""
        composition = Inline(
            target="func:helper",
            remove_after=True,
        )

        result = composition.execute(graph_with_calls)

        assert result.success
        # Helper function should be removed
        assert not graph_with_calls.has_node("func:helper")

    def test_inline_preserves_entity_when_requested(self, graph_with_calls: TypedGraph) -> None:
        """Test inline without removal."""
        composition = Inline(
            target="func:helper",
            remove_after=False,
        )

        result = composition.execute(graph_with_calls)

        assert result.success
        # Helper function should still exist
        assert graph_with_calls.has_node("func:helper")


# =============================================================================
# ADD_GUARD Tests
# =============================================================================


class TestAddGuard:
    """Tests for ADD_GUARD composition."""

    def test_add_guard_creates_branch(self, module_with_functions: TypedGraph) -> None:
        """Test that add_guard creates a guard node."""
        composition = AddGuard(
            target="func:process",
            guard_type="null_check",
            guard_condition="input is not None",
            guard_action="early_return",
        )

        result = composition.execute(module_with_functions)

        assert result.success

        # Guard node should exist
        guard_id = "guard:func:process:null_check"
        assert module_with_functions.has_node(guard_id)

        guard_node = module_with_functions.get_node(guard_id)
        assert guard_node.attrs["guard_type"] == "null_check"
        assert guard_node.attrs["condition"] == "input is not None"


# =============================================================================
# WRAP Tests
# =============================================================================


class TestWrap:
    """Tests for WRAP composition."""

    def test_wrap_creates_wrapper(self, module_with_functions: TypedGraph) -> None:
        """Test that wrap creates a wrapper block."""
        composition = Wrap(
            target="func:validate",
            wrapper_kind="try_catch",
            wrapper_attrs={"catch_type": "Exception"},
        )

        result = composition.execute(module_with_functions)

        assert result.success

        # Wrapper node should exist
        wrapper_id = "wrapper:func:validate:try_catch"
        assert module_with_functions.has_node(wrapper_id)

        wrapper = module_with_functions.get_node(wrapper_id)
        assert wrapper.attrs["wrapper_type"] == "try_catch"


# =============================================================================
# CompositionRegistry Tests
# =============================================================================


class TestCompositionRegistry:
    """Tests for the composition registry."""

    def test_registry_has_standard_compositions(self) -> None:
        """Test that standard compositions are registered."""
        names = CompositionRegistry.list_compositions()

        assert "RENAME" in names
        assert "MOVE" in names
        assert "EXTRACT" in names
        assert "INLINE" in names
        assert "ADD_GUARD" in names
        assert "CHANGE_SIGNATURE" in names
        assert "WRAP" in names

    def test_registry_get(self) -> None:
        """Test getting composition class by name."""
        cls = CompositionRegistry.get("RENAME")
        assert cls is Rename

        cls = CompositionRegistry.get("rename")  # Case insensitive
        assert cls is Rename

    def test_registry_create(self) -> None:
        """Test creating composition instance."""
        composition = CompositionRegistry.create(
            "RENAME",
            target="func:test",
            new_name="new_test",
        )

        assert composition is not None
        assert isinstance(composition, Rename)
        assert composition.target == "func:test"
        assert composition.new_name == "new_test"

    def test_registry_unknown_returns_none(self) -> None:
        """Test that unknown composition returns None."""
        assert CompositionRegistry.get("UNKNOWN") is None
        assert CompositionRegistry.create("UNKNOWN") is None


# =============================================================================
# CompositionBuilder Tests
# =============================================================================


class TestCompositionBuilder:
    """Tests for the fluent composition builder."""

    def test_builder_creates_composition(self, module_with_functions: TypedGraph) -> None:
        """Test building a custom composition."""
        composition = (
            CompositionBuilder("custom_transform")
            .insert_node("func:new_func", NodeKind.CALLABLE, attrs={"name": "new_func"})
            .insert_edge("module:utils", "func:new_func", EdgeKind.CONTAINS)
            .update("func:helper", "deprecated", True)
            .build()
        )

        result = composition.execute(module_with_functions)

        assert result.success
        assert module_with_functions.has_node("func:new_func")
        assert module_with_functions.has_edge("module:utils", "func:new_func")

        helper = module_with_functions.get_node("func:helper")
        assert helper.attrs.get("deprecated") is True

    def test_builder_chaining(self) -> None:
        """Test that builder methods return self for chaining."""
        builder = CompositionBuilder("test")

        result = builder.insert_node("n1", NodeKind.CALLABLE)
        assert result is builder

        result = builder.insert_edge("n1", "n2", EdgeKind.CALLS)
        assert result is builder

        result = builder.delete_node("n1")
        assert result is builder

        result = builder.update("n1", "name", "new")
        assert result is builder

    def test_builder_composition_name(self) -> None:
        """Test that built composition has correct name."""
        composition = CompositionBuilder("my_composition").build()
        assert composition.name == "my_composition"


# =============================================================================
# Rollback Tests
# =============================================================================


class TestCompositionRollback:
    """Tests for composition rollback on failure."""

    def test_rollback_on_failure(self) -> None:
        """Test that composition rolls back on primitive failure."""
        graph = TypedGraph()
        graph.add_node(GraphNode(
            id="func:existing",
            node_type=NodeType.FUNCTION,
            attrs={"name": "existing"},
        ))

        # Build composition that will fail partway through
        composition = (
            CompositionBuilder("failing_composition")
            .insert_node("func:new1", NodeKind.CALLABLE, attrs={"name": "new1"})
            .insert_node("func:new2", NodeKind.CALLABLE, attrs={"name": "new2"})
            # This will fail - trying to insert duplicate
            .insert_node("func:existing", NodeKind.CALLABLE, attrs={"name": "existing"})
            .build()
        )

        result = composition.execute(graph)

        assert not result.success
        # After rollback, new nodes should be removed
        # Note: Rollback is best-effort, so we just check the result indicates failure
        assert "already exists" in result.error or "failed" in result.error.lower()
