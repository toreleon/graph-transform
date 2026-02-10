"""
Epic 3: Transformation Primitives & Reference Tracking - Acceptance Tests

Stories:
- 3.1: INSERT Primitive
- 3.2: DELETE Primitive
- 3.3: UPDATE Primitive
- 3.4: Primitive Composition Framework
- 3.5: Find All Call Sites
- 3.6: Find All Import References
- 3.7: Update All References
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)
from graph_transform.core.primitives.base import (
    DeleteEdge,
    DeleteNode,
    InsertEdge,
    InsertNode,
    PrimitiveKind,
    PrimitiveResult,
    Update,
)
from graph_transform.core.primitives.node_kinds import EdgeKind, NodeKind


# =============================================================================
# Story 3.1: INSERT Primitive
# =============================================================================


class TestStory31InsertPrimitive:
    """Tests for INSERT primitive (FR39)."""

    def test_insert_node_returns_new_graph(self):
        """Given a TypedGraph, When INSERT is called with a new node,
        Then returns a new graph with the node added AND original graph unchanged.
        """
        original = TypedGraph()
        original.add_node(GraphNode(id="existing", node_type=NodeType.FUNCTION, attrs={}))

        insert = InsertNode(
            node_id="func:new_helper",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "new_helper", "file": "utils.py", "line": 10},
        )

        # Execute returns result and new graph
        result, new_graph = insert.apply(original)

        # Result should be success
        assert result.success is True
        assert result.primitive_kind == PrimitiveKind.INSERT
        assert "func:new_helper" in result.affected_ids

        # New graph should have the node
        assert new_graph.has_node("func:new_helper")
        new_node = new_graph.get_node("func:new_helper")
        assert new_node is not None
        assert new_node.attrs["name"] == "new_helper"

        # Original graph should be unchanged
        assert not original.has_node("func:new_helper")
        assert original.node_count == 1

    def test_insert_edge_validates_endpoints(self):
        """Given a TypedGraph, When INSERT is called with a new edge,
        Then validates both source and target nodes exist.
        """
        graph = TypedGraph()
        graph.add_node(GraphNode(id="source_node", node_type=NodeType.CLASS, attrs={}))
        graph.add_node(GraphNode(id="target_node", node_type=NodeType.FUNCTION, attrs={}))

        insert = InsertEdge(
            source="source_node",
            target="target_node",
            edge_kind=EdgeKind.CONTAINS,
        )

        result, new_graph = insert.apply(graph)

        assert result.success is True
        assert new_graph.has_edge("source_node", "target_node")

    def test_insert_edge_fails_if_source_missing(self):
        """INSERT edge should fail if source node doesn't exist."""
        graph = TypedGraph()
        graph.add_node(GraphNode(id="target_node", node_type=NodeType.FUNCTION, attrs={}))

        insert = InsertEdge(
            source="missing_source",
            target="target_node",
            edge_kind=EdgeKind.CONTAINS,
        )

        result, new_graph = insert.apply(graph)

        assert result.success is False
        assert "missing_source" in result.error.lower() or "source" in result.error.lower()

    def test_insert_edge_fails_if_target_missing(self):
        """INSERT edge should fail if target node doesn't exist."""
        graph = TypedGraph()
        graph.add_node(GraphNode(id="source_node", node_type=NodeType.CLASS, attrs={}))

        insert = InsertEdge(
            source="source_node",
            target="missing_target",
            edge_kind=EdgeKind.CONTAINS,
        )

        result, new_graph = insert.apply(graph)

        assert result.success is False
        assert "missing_target" in result.error.lower() or "target" in result.error.lower()

    def test_insert_primitive_is_immutable(self):
        """INSERT primitive must be an immutable dataclass (frozen=True)."""
        insert = InsertNode(
            node_id="test",
            node_kind=NodeKind.CALLABLE,
            attrs={"name": "test"},
        )

        with pytest.raises(FrozenInstanceError):
            insert.node_id = "changed"

    def test_insert_is_language_agnostic(self):
        """INSERT primitive should be language-agnostic (FR43)."""
        # The primitive uses NodeKind/EdgeKind (universal) not NodeType/EdgeType (Python-specific)
        insert = InsertNode(
            node_id="callable:my_func",
            node_kind=NodeKind.CALLABLE,  # Universal, not "function"
            attrs={"name": "my_func"},
        )

        assert insert.node_kind == NodeKind.CALLABLE
        # Should work with any language's graph representation


# =============================================================================
# Story 3.2: DELETE Primitive
# =============================================================================


class TestStory32DeletePrimitive:
    """Tests for DELETE primitive (FR40)."""

    def test_delete_node_returns_new_graph(self):
        """Given a TypedGraph with nodes and edges,
        When DELETE is called on a node,
        Then returns new graph with node removed AND removes all connected edges.
        """
        original = TypedGraph()
        original.add_node(GraphNode(id="node1", node_type=NodeType.FUNCTION, attrs={}))
        original.add_node(GraphNode(id="node2", node_type=NodeType.CALL, attrs={}))
        original.add_edge(GraphEdge(source="node2", target="node1", edge_type=EdgeType.CALLS))

        delete = DeleteNode(node_id="node1")

        result, new_graph = delete.apply(original)

        # Result should be success
        assert result.success is True
        assert result.primitive_kind == PrimitiveKind.DELETE
        assert "node1" in result.affected_ids

        # New graph should not have the node
        assert not new_graph.has_node("node1")

        # Connected edges should be removed
        assert not new_graph.has_edge("node2", "node1")

        # Original graph unchanged
        assert original.has_node("node1")
        assert original.has_edge("node2", "node1")

    def test_delete_edge_returns_new_graph(self):
        """Given a TypedGraph with edges,
        When DELETE is called on an edge,
        Then returns new graph with edge removed AND nodes remain intact.
        """
        original = TypedGraph()
        original.add_node(GraphNode(id="node1", node_type=NodeType.FUNCTION, attrs={}))
        original.add_node(GraphNode(id="node2", node_type=NodeType.CALL, attrs={}))
        original.add_edge(GraphEdge(source="node2", target="node1", edge_type=EdgeType.CALLS))

        delete = DeleteEdge(source="node2", target="node1", edge_kind=EdgeKind.CALLS)

        result, new_graph = delete.apply(original)

        # Result should be success
        assert result.success is True

        # Edge should be removed
        assert not new_graph.has_edge("node2", "node1")

        # Nodes remain intact
        assert new_graph.has_node("node1")
        assert new_graph.has_node("node2")

        # Original unchanged
        assert original.has_edge("node2", "node1")

    def test_delete_primitive_is_immutable(self):
        """DELETE primitive must be an immutable dataclass (frozen=True)."""
        delete = DeleteNode(node_id="test")

        with pytest.raises(FrozenInstanceError):
            delete.node_id = "changed"

    def test_delete_is_language_agnostic(self):
        """DELETE primitive should be language-agnostic (FR43)."""
        delete = DeleteEdge(
            source="callable:foo",
            target="callable:bar",
            edge_kind=EdgeKind.CALLS,  # Universal, not "calls"
        )

        assert delete.edge_kind == EdgeKind.CALLS


# =============================================================================
# Story 3.3: UPDATE Primitive
# =============================================================================


class TestStory33UpdatePrimitive:
    """Tests for UPDATE primitive (FR41)."""

    def test_update_node_returns_new_graph(self):
        """Given a TypedGraph with a node,
        When UPDATE is called with attribute changes,
        Then returns new graph with updated node attributes.
        """
        original = TypedGraph()
        original.add_node(GraphNode(
            id="func:old_name",
            node_type=NodeType.FUNCTION,
            attrs={"name": "old_name", "file": "test.py", "line": 1},
        ))

        update = Update(
            target="func:old_name",
            prop="name",
            value="new_name",
        )

        result, new_graph = update.apply(original)

        # Result should be success
        assert result.success is True
        assert result.primitive_kind == PrimitiveKind.UPDATE
        assert "func:old_name" in result.affected_ids

        # New graph should have updated attribute
        updated_node = new_graph.get_node("func:old_name")
        assert updated_node is not None
        assert updated_node.attrs["name"] == "new_name"

        # Original unchanged
        original_node = original.get_node("func:old_name")
        assert original_node is not None
        assert original_node.attrs["name"] == "old_name"

    def test_update_recalculates_node_id_if_name_changes(self):
        """Given a TypedGraph with a node,
        When UPDATE changes the name attribute,
        Then node ID is recalculated if name changes.

        Note: This is tracked in metadata for the composition to handle.
        """
        original = TypedGraph()
        original.add_node(GraphNode(
            id="func:old_name",
            node_type=NodeType.FUNCTION,
            attrs={"name": "old_name"},
        ))

        update = Update(
            target="func:old_name",
            prop="name",
            value="new_name",
        )

        result, new_graph = update.apply(original)

        assert result.success is True
        # The result should indicate name changed (for ID recalculation by composition)
        assert result.metadata.get("old_values", {}).get("name") == "old_name"
        assert result.metadata.get("new_values", {}).get("name") == "new_name"

    def test_update_primitive_is_immutable(self):
        """UPDATE primitive must be an immutable dataclass (frozen=True)."""
        update = Update(target="test", prop="name", value="new")

        with pytest.raises(FrozenInstanceError):
            update.target = "changed"

    def test_update_is_language_agnostic(self):
        """UPDATE primitive should be language-agnostic (FR43)."""
        # Works on generic attributes, not language-specific properties
        update = Update(
            target="callable:my_func",
            properties={"visibility": "public", "async": True},
        )

        assert update.properties_dict == {"visibility": "public", "async": True}


# =============================================================================
# Story 3.4: Primitive Composition Framework
# =============================================================================


class TestStory34CompositionFramework:
    """Tests for primitive composition framework (FR42)."""

    def test_sequence_of_primitives_applied_in_order(self):
        """Given a sequence of primitives [INSERT, UPDATE, DELETE],
        When composed and applied to a graph,
        Then each primitive is applied in order.
        """
        from graph_transform.core.primitives.compositions import CompositionBuilder

        graph = TypedGraph()
        graph.add_node(GraphNode(id="existing", node_type=NodeType.MODULE, attrs={"name": "mod"}))

        # Build a composition: INSERT node, UPDATE it, then verify
        composition = (
            CompositionBuilder("test_sequence")
            .insert_node("new_node", NodeKind.CALLABLE, {"name": "func1"})
            .insert_edge("existing", "new_node", EdgeKind.CONTAINS)
            .update("new_node", "name", "func1_renamed")
            .build()
        )

        result = composition.execute(graph)

        # All primitives should execute in order
        assert result.success is True
        assert len(result.primitive_results) == 3

        # Final state should reflect all changes
        assert graph.has_node("new_node")
        node = graph.get_node("new_node")
        assert node.attrs["name"] == "func1_renamed"
        assert graph.has_edge("existing", "new_node")

    def test_intermediate_graphs_passed_through_chain(self):
        """Each primitive should receive the graph state from previous primitive."""
        from graph_transform.core.primitives.compositions import CompositionBuilder

        graph = TypedGraph()

        # Build composition that depends on previous step
        composition = (
            CompositionBuilder("chain_test")
            .insert_node("step1", NodeKind.CALLABLE, {"name": "step1"})
            .insert_node("step2", NodeKind.CALLABLE, {"name": "step2"})
            # This edge requires both nodes to exist
            .insert_edge("step1", "step2", EdgeKind.CALLS)
            .build()
        )

        result = composition.execute(graph)

        assert result.success is True
        assert graph.has_edge("step1", "step2")

    def test_any_composition_expressible_as_primitives(self):
        """Any composition operator should be expressible as INSERT, DELETE, UPDATE (FR42)."""
        from graph_transform.core.primitives.compositions import Rename

        graph = TypedGraph()
        graph.add_node(GraphNode(
            id="func:old",
            node_type=NodeType.FUNCTION,
            attrs={"name": "old"},
        ))

        rename = Rename(target="func:old", new_name="new", update_references=False)

        # Get the primitives generated by this composition
        primitives = list(rename.primitives(graph))

        # Should only use INSERT, DELETE, UPDATE
        for p in primitives:
            assert p.kind in (PrimitiveKind.INSERT, PrimitiveKind.DELETE, PrimitiveKind.UPDATE)

        # Rename should generate an UPDATE primitive
        assert any(p.kind == PrimitiveKind.UPDATE for p in primitives)

    def test_new_operators_addable_via_composition(self):
        """New operators can be added via composition of primitives (NFR-M4)."""
        from graph_transform.core.primitives.compositions import (
            Composition,
            CompositionRegistry,
        )
        from typing import Iterator

        # Define a custom composition
        class CustomSwap(Composition):
            """Custom operator that swaps two function names."""

            def __init__(self, node_a: str, node_b: str):
                self.node_a = node_a
                self.node_b = node_b

            @property
            def name(self) -> str:
                return "CUSTOM_SWAP"

            def primitives(self, graph: TypedGraph) -> Iterator:
                name_a = graph.get_node(self.node_a).attrs.get("name")
                name_b = graph.get_node(self.node_b).attrs.get("name")

                yield Update(target=self.node_a, prop="name", value=name_b)
                yield Update(target=self.node_b, prop="name", value=name_a)

        # Register it
        CompositionRegistry.register("CUSTOM_SWAP", CustomSwap)

        # Use it
        created = CompositionRegistry.create("CUSTOM_SWAP", node_a="a", node_b="b")
        assert created is not None
        assert created.name == "CUSTOM_SWAP"


# =============================================================================
# Story 3.5: Find All Call Sites
# =============================================================================


class TestStory35FindAllCallSites:
    """Tests for finding all call sites (FR49)."""

    def test_find_all_call_sites_for_function(self):
        """Given a function node in the graph,
        When call sites are queried,
        Then returns ALL nodes with CALLS edges to that function (FR49).
        """
        from graph_transform.core.references import find_all_call_sites

        graph = TypedGraph()
        # Target function
        graph.add_node(GraphNode(id="func:target", node_type=NodeType.FUNCTION, attrs={"name": "target"}))

        # Call sites
        graph.add_node(GraphNode(id="call:site1", node_type=NodeType.CALL, attrs={"callee": "target"}))
        graph.add_node(GraphNode(id="call:site2", node_type=NodeType.CALL, attrs={"callee": "target"}))
        graph.add_node(GraphNode(id="call:site3", node_type=NodeType.CALL, attrs={"callee": "other"}))

        graph.add_edge(GraphEdge(source="call:site1", target="func:target", edge_type=EdgeType.CALLS))
        graph.add_edge(GraphEdge(source="call:site2", target="func:target", edge_type=EdgeType.CALLS))
        # site3 doesn't call target

        call_sites = find_all_call_sites(graph, "func:target")

        assert len(call_sites) == 2
        assert "call:site1" in call_sites
        assert "call:site2" in call_sites
        assert "call:site3" not in call_sites

    def test_find_direct_and_method_calls(self):
        """Call sites should include both direct calls and method calls."""
        from graph_transform.core.references import find_all_call_sites

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:MyClass.method", node_type=NodeType.FUNCTION, attrs={"name": "method"}))

        # Direct call
        graph.add_node(GraphNode(id="call:direct", node_type=NodeType.CALL, attrs={"callee": "method"}))
        graph.add_edge(GraphEdge(source="call:direct", target="func:MyClass.method", edge_type=EdgeType.CALLS))

        # Method call via self
        graph.add_node(GraphNode(id="call:self_method", node_type=NodeType.CALL, attrs={"callee": "method", "receiver": "self"}))
        graph.add_edge(GraphEdge(source="call:self_method", target="func:MyClass.method", edge_type=EdgeType.CALLS))

        # Method call via instance
        graph.add_node(GraphNode(id="call:instance", node_type=NodeType.CALL, attrs={"callee": "method", "receiver": "obj"}))
        graph.add_edge(GraphEdge(source="call:instance", target="func:MyClass.method", edge_type=EdgeType.CALLS))

        call_sites = find_all_call_sites(graph, "func:MyClass.method")

        assert len(call_sites) == 3
        assert "call:direct" in call_sites
        assert "call:self_method" in call_sites
        assert "call:instance" in call_sites

    def test_zero_false_negatives_completeness(self):
        """Call site finder must have zero false negatives (completeness guarantee)."""
        from graph_transform.core.references import find_all_call_sites

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:target", node_type=NodeType.FUNCTION, attrs={}))

        # Add many call sites
        expected_calls = set()
        for i in range(100):
            call_id = f"call:site_{i}"
            graph.add_node(GraphNode(id=call_id, node_type=NodeType.CALL, attrs={}))
            graph.add_edge(GraphEdge(source=call_id, target="func:target", edge_type=EdgeType.CALLS))
            expected_calls.add(call_id)

        found = find_all_call_sites(graph, "func:target")

        assert set(found) == expected_calls  # All found, none missed


# =============================================================================
# Story 3.6: Find All Import References
# =============================================================================


class TestStory36FindAllImportReferences:
    """Tests for finding all import references (FR50)."""

    def test_find_all_import_references(self):
        """Given a function/class exported from a module,
        When import references are queried,
        Then returns ALL nodes with IMPORTS edges to that member (FR50).
        """
        from graph_transform.core.references import find_all_import_references

        graph = TypedGraph()
        # Exported function
        graph.add_node(GraphNode(id="func:module.helper", node_type=NodeType.FUNCTION, attrs={"name": "helper"}))

        # Import nodes
        graph.add_node(GraphNode(id="import:file1:helper", node_type=NodeType.IMPORT, attrs={"name": "helper", "module": "module"}))
        graph.add_node(GraphNode(id="import:file2:helper", node_type=NodeType.IMPORT, attrs={"name": "helper", "module": "module"}))
        graph.add_node(GraphNode(id="import:file3:other", node_type=NodeType.IMPORT, attrs={"name": "other", "module": "module"}))

        graph.add_edge(GraphEdge(source="import:file1:helper", target="func:module.helper", edge_type=EdgeType.IMPORTS))
        graph.add_edge(GraphEdge(source="import:file2:helper", target="func:module.helper", edge_type=EdgeType.IMPORTS))

        imports = find_all_import_references(graph, "func:module.helper")

        assert len(imports) == 2
        assert "import:file1:helper" in imports
        assert "import:file2:helper" in imports

    def test_find_from_import_style(self):
        """Should find `from module import name` style imports."""
        from graph_transform.core.references import find_all_import_references

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:mymodule.myfunc", node_type=NodeType.FUNCTION, attrs={"name": "myfunc"}))

        # from mymodule import myfunc
        graph.add_node(GraphNode(
            id="import:test.py:myfunc",
            node_type=NodeType.IMPORT,
            attrs={"name": "myfunc", "module": "mymodule", "is_from_import": True},
        ))
        graph.add_edge(GraphEdge(source="import:test.py:myfunc", target="func:mymodule.myfunc", edge_type=EdgeType.IMPORTS))

        imports = find_all_import_references(graph, "func:mymodule.myfunc")

        assert "import:test.py:myfunc" in imports

    def test_find_module_import_with_qualified_usage(self):
        """Should find `import module` with `module.name` usage."""
        from graph_transform.core.references import find_all_import_references

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:utils.helper", node_type=NodeType.FUNCTION, attrs={"name": "helper"}))

        # import utils (then utils.helper is used)
        graph.add_node(GraphNode(
            id="import:test.py:utils",
            node_type=NodeType.IMPORT,
            attrs={"module": "utils", "name": None, "is_from_import": False},
        ))
        # This import references the module, but qualifies access to helper
        graph.add_edge(GraphEdge(source="import:test.py:utils", target="func:utils.helper", edge_type=EdgeType.REFERENCES))

        imports = find_all_import_references(graph, "func:utils.helper")

        # Should include both direct imports and qualified references
        assert "import:test.py:utils" in imports


# =============================================================================
# Story 3.7: Update All References
# =============================================================================


class TestStory37UpdateAllReferences:
    """Tests for updating all references (FR51)."""

    def test_update_all_call_sites_on_rename(self):
        """Given a function is renamed via UPDATE primitive,
        When reference update is triggered,
        Then ALL call sites are updated with new name (FR51).
        """
        from graph_transform.core.references import update_all_references

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:old_name", node_type=NodeType.FUNCTION, attrs={"name": "old_name"}))

        # Call sites
        graph.add_node(GraphNode(id="call:site1", node_type=NodeType.CALL, attrs={"callee": "old_name"}))
        graph.add_node(GraphNode(id="call:site2", node_type=NodeType.CALL, attrs={"callee": "old_name"}))
        graph.add_edge(GraphEdge(source="call:site1", target="func:old_name", edge_type=EdgeType.CALLS))
        graph.add_edge(GraphEdge(source="call:site2", target="func:old_name", edge_type=EdgeType.CALLS))

        result, new_graph = update_all_references(
            graph,
            target="func:old_name",
            old_name="old_name",
            new_name="new_name",
        )

        assert result.success is True

        # All call sites should have updated callee
        site1 = new_graph.get_node("call:site1")
        site2 = new_graph.get_node("call:site2")
        assert site1.attrs["callee"] == "new_name"
        assert site2.attrs["callee"] == "new_name"

        # Original unchanged
        assert graph.get_node("call:site1").attrs["callee"] == "old_name"

    def test_update_all_import_statements_on_rename(self):
        """When a function is renamed,
        Then ALL import statements are updated.
        """
        from graph_transform.core.references import update_all_references

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:old_name", node_type=NodeType.FUNCTION, attrs={"name": "old_name"}))

        # Import that references this function
        graph.add_node(GraphNode(
            id="import:file.py:old_name",
            node_type=NodeType.IMPORT,
            attrs={"name": "old_name", "module": "mymod"},
        ))
        graph.add_edge(GraphEdge(source="import:file.py:old_name", target="func:old_name", edge_type=EdgeType.IMPORTS))

        result, new_graph = update_all_references(
            graph,
            target="func:old_name",
            old_name="old_name",
            new_name="new_name",
        )

        assert result.success is True

        # Import should be updated
        imp = new_graph.get_node("import:file.py:old_name")
        assert imp.attrs["name"] == "new_name"

    def test_update_import_paths_on_move(self):
        """Given a function is moved to another module,
        When reference update is triggered,
        Then ALL import paths are updated.
        """
        from graph_transform.core.references import update_references_for_move

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:old_mod.helper", node_type=NodeType.FUNCTION, attrs={"name": "helper"}))

        # Import from old module
        graph.add_node(GraphNode(
            id="import:consumer.py:helper",
            node_type=NodeType.IMPORT,
            attrs={"name": "helper", "module": "old_mod"},
        ))
        graph.add_edge(GraphEdge(source="import:consumer.py:helper", target="func:old_mod.helper", edge_type=EdgeType.IMPORTS))

        result, new_graph = update_references_for_move(
            graph,
            target="func:old_mod.helper",
            old_module="old_mod",
            new_module="new_mod",
        )

        assert result.success is True

        # Import module path should be updated
        imp = new_graph.get_node("import:consumer.py:helper")
        assert imp.attrs["module"] == "new_mod"

    def test_update_qualified_references_on_move(self):
        """Given a function is moved,
        Then ALL qualified references are updated.
        """
        from graph_transform.core.references import update_references_for_move

        graph = TypedGraph()
        graph.add_node(GraphNode(id="func:old_mod.helper", node_type=NodeType.FUNCTION, attrs={"name": "helper"}))

        # Call with qualified name
        graph.add_node(GraphNode(
            id="call:qualified",
            node_type=NodeType.CALL,
            attrs={"callee": "old_mod.helper", "is_qualified": True},
        ))
        graph.add_edge(GraphEdge(source="call:qualified", target="func:old_mod.helper", edge_type=EdgeType.CALLS))

        result, new_graph = update_references_for_move(
            graph,
            target="func:old_mod.helper",
            old_module="old_mod",
            new_module="new_mod",
        )

        assert result.success is True

        # Qualified callee should be updated
        call = new_graph.get_node("call:qualified")
        assert call.attrs["callee"] == "new_mod.helper"
