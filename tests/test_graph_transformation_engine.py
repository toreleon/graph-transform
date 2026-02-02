"""Unit tests for the algebraic graph transformation engine."""

import pytest

from graph_transform import (
    ClassNode,
    EdgeType,
    FieldNode,
    GraphEdge,
    GraphMorphism,
    GraphNode,
    GraphTransformationEngine,
    ImportNode,
    Invariant,
    InvariantLayer,
    InvariantRegistry,
    InvariantSeverity,
    InvariantViolation,
    MatchFinder,
    ModuleNode,
    NodeType,
    OperatorType,
    ProductionRule,
    ProductionRuleCatalog,
    PushoutEngine,
    RewriteMode,
    RewriteResult,
    RuleApplication,
    TransformationPath,
    TypedGraph,
    apply_operator,
    create_engine,
    verify_graph_invariants,
)


# =============================================================================
# Test Fixtures / Helpers
# =============================================================================


def make_func_node(name: str, nid: str | None = None) -> GraphNode:
    return GraphNode(
        id=nid or f"func:{name}",
        node_type=NodeType.FUNCTION,
        attrs={"name": name, "is_method": False, "is_async": False},
    )


def make_class_node(name: str, nid: str | None = None) -> GraphNode:
    return GraphNode(
        id=nid or f"class:{name}",
        node_type=NodeType.CLASS,
        attrs={"name": name},
    )


def make_param_node(name: str, func_name: str, position: int = 0) -> GraphNode:
    return GraphNode(
        id=f"param:{func_name}.{name}",
        node_type=NodeType.PARAMETER,
        attrs={"name": name, "position": position, "has_default": False},
    )


def make_simple_graph() -> TypedGraph:
    """A graph with one class, one method, one parameter."""
    g = TypedGraph()
    g.add_node(make_class_node("MyClass"))
    g.add_node(make_func_node("my_method"))
    g.add_node(make_param_node("self", "my_method", 0))
    g.add_edge(GraphEdge("class:MyClass", "func:my_method", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("func:my_method", "param:my_method.self", EdgeType.HAS_PARAMETER))
    return g


def make_two_class_graph() -> TypedGraph:
    """A graph with two classes and an inheritance relationship."""
    g = TypedGraph()
    g.add_node(make_class_node("Base"))
    g.add_node(make_class_node("Child"))
    g.add_node(make_func_node("process"))
    g.add_edge(GraphEdge("class:Child", "class:Base", EdgeType.INHERITS))
    g.add_edge(GraphEdge("class:Child", "func:process", EdgeType.CONTAINS_METHOD))
    return g


def make_call_graph() -> TypedGraph:
    """A graph with a function and a call site."""
    g = TypedGraph()
    g.add_node(make_func_node("target_func"))
    g.add_node(make_param_node("x", "target_func", 0))
    g.add_edge(GraphEdge("func:target_func", "param:target_func.x", EdgeType.HAS_PARAMETER))

    call_node = GraphNode("call:main.py:10:0", NodeType.CALL, {
        "callee": "target_func", "file": "main.py", "line": 10,
    })
    g.add_node(call_node)
    g.add_edge(GraphEdge("call:main.py:10:0", "func:target_func", EdgeType.CALLS))

    arg_node = GraphNode("arg:call:main.py:10:0.x", NodeType.ARGUMENT, {
        "name": "x", "value": "42", "is_keyword": True, "position": 0,
    })
    g.add_node(arg_node)
    g.add_edge(GraphEdge("call:main.py:10:0", "arg:call:main.py:10:0.x", EdgeType.HAS_ARGUMENT))
    return g


# =============================================================================
# TestExtendedNodes
# =============================================================================


class TestExtendedNodes:
    def test_class_node_creation(self):
        n = ClassNode("Foo", "foo.py", 1, bases=["Bar"])
        assert n.name == "Foo"
        assert n.bases == ["Bar"]

    def test_class_node_roundtrip(self):
        n = ClassNode("Foo", "foo.py", 1, bases=["Bar"], methods=["m1"])
        d = n.to_dict()
        n2 = ClassNode.from_dict(d)
        assert n2.name == n.name
        assert n2.bases == n.bases
        assert n2.methods == n.methods

    def test_field_node_creation(self):
        n = FieldNode("count", "foo.py", 5, class_name="Foo", has_default=True, default_value="0")
        assert n.name == "count"
        assert n.default_value == "0"

    def test_field_node_roundtrip(self):
        n = FieldNode("count", "foo.py", 5, class_name="Foo")
        d = n.to_dict()
        n2 = FieldNode.from_dict(d)
        assert n2.name == n.name
        assert n2.class_name == n.class_name

    def test_import_node_roundtrip(self):
        n = ImportNode("os.path", name="join", is_from_import=True)
        d = n.to_dict()
        n2 = ImportNode.from_dict(d)
        assert n2.module == "os.path"
        assert n2.name == "join"
        assert n2.is_from_import is True

    def test_module_node_roundtrip(self):
        n = ModuleNode("utils", "utils.py", functions=["f1"], classes=["C1"])
        d = n.to_dict()
        n2 = ModuleNode.from_dict(d)
        assert n2.name == "utils"
        assert n2.functions == ["f1"]


# =============================================================================
# TestTypedGraph
# =============================================================================


class TestTypedGraph:
    def test_empty_graph(self):
        g = TypedGraph()
        assert g.node_count == 0
        assert g.edge_count == 0
        assert g.is_empty()
        assert g.is_valid()

    def test_add_remove_node(self):
        g = TypedGraph()
        n = GraphNode("n1", NodeType.FUNCTION, {"name": "foo"})
        g.add_node(n)
        assert g.node_count == 1
        assert g.has_node("n1")
        g.remove_node("n1")
        assert g.node_count == 0

    def test_add_remove_edge(self):
        g = TypedGraph()
        g.add_node(GraphNode("a", NodeType.CLASS, {}))
        g.add_node(GraphNode("b", NodeType.FUNCTION, {}))
        g.add_edge(GraphEdge("a", "b", EdgeType.CONTAINS_METHOD))
        assert g.edge_count == 1
        assert g.has_edge("a", "b", EdgeType.CONTAINS_METHOD)
        g.remove_edge("a", "b", EdgeType.CONTAINS_METHOD)
        assert g.edge_count == 0

    def test_remove_node_removes_edges(self):
        g = TypedGraph()
        g.add_node(GraphNode("a", NodeType.CLASS, {}))
        g.add_node(GraphNode("b", NodeType.FUNCTION, {}))
        g.add_edge(GraphEdge("a", "b", EdgeType.CONTAINS_METHOD))
        g.remove_node("b")
        assert g.edge_count == 0

    def test_get_nodes_by_type(self):
        g = TypedGraph()
        g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "a"}))
        g.add_node(GraphNode("f2", NodeType.FUNCTION, {"name": "b"}))
        g.add_node(GraphNode("c1", NodeType.CLASS, {"name": "C"}))
        funcs = g.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 2

    def test_dangling_edges(self):
        g = TypedGraph()
        g.add_node(GraphNode("a", NodeType.CLASS, {}))
        g.edges.append(GraphEdge("a", "nonexist", EdgeType.CONTAINS_METHOD))
        assert len(g.dangling_edges()) == 1
        assert not g.is_valid()

    def test_subgraph(self):
        g = make_simple_graph()
        sub = g.subgraph({"class:MyClass", "func:my_method"})
        assert sub.node_count == 2
        assert sub.edge_count == 1  # CONTAINS_METHOD edge

    def test_copy_independence(self):
        g = make_simple_graph()
        g2 = g.copy()
        g2.remove_node("class:MyClass")
        assert g.has_node("class:MyClass")  # original unchanged

    def test_serialization_roundtrip(self):
        g = make_simple_graph()
        d = g.to_dict()
        g2 = TypedGraph.from_dict(d)
        assert g2.node_count == g.node_count
        assert g2.edge_count == g.edge_count

    def test_node_matches_wildcard(self):
        n = GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": True})
        pattern = GraphNode("p1", NodeType.FUNCTION, {"name": "foo"})
        assert n.matches(pattern)

    def test_node_matches_none_wildcard(self):
        n = GraphNode("f1", NodeType.FUNCTION, {"name": "foo"})
        pattern = GraphNode("p1", NodeType.FUNCTION, {"name": None})
        assert n.matches(pattern)

    def test_node_no_match_wrong_type(self):
        n = GraphNode("f1", NodeType.FUNCTION, {"name": "foo"})
        pattern = GraphNode("p1", NodeType.CLASS, {"name": "foo"})
        assert not n.matches(pattern)

    def test_node_no_match_wrong_attr(self):
        n = GraphNode("f1", NodeType.FUNCTION, {"name": "foo"})
        pattern = GraphNode("p1", NodeType.FUNCTION, {"name": "bar"})
        assert not n.matches(pattern)


# =============================================================================
# TestGraphMorphism
# =============================================================================


class TestGraphMorphism:
    def test_identity_morphism(self):
        g = make_simple_graph()
        m = GraphMorphism.identity(g)
        assert m.is_valid()
        assert m.is_injective()
        assert m.is_total()

    def test_inclusion_morphism(self):
        g = make_simple_graph()
        sub = g.subgraph({"class:MyClass", "func:my_method"})
        m = GraphMorphism.inclusion(sub, g)
        assert m.is_valid()
        assert m.is_injective()

    def test_non_injective(self):
        g = TypedGraph()
        g.add_node(GraphNode("a", NodeType.FUNCTION, {}))
        g.add_node(GraphNode("b", NodeType.FUNCTION, {}))
        m = GraphMorphism(
            node_map={"a": "x", "b": "x"},
            source=g,
            target=TypedGraph(nodes={"x": GraphNode("x", NodeType.FUNCTION, {})}),
        )
        assert not m.is_injective()

    def test_compose(self):
        a = TypedGraph(nodes={"n1": GraphNode("n1", NodeType.FUNCTION, {})})
        b = TypedGraph(nodes={"n2": GraphNode("n2", NodeType.FUNCTION, {})})
        c = TypedGraph(nodes={"n3": GraphNode("n3", NodeType.FUNCTION, {})})
        m1 = GraphMorphism(node_map={"n1": "n2"}, source=a, target=b)
        m2 = GraphMorphism(node_map={"n2": "n3"}, source=b, target=c)
        composed = m1.compose(m2)
        assert composed.node_map == {"n1": "n3"}

    def test_image(self):
        a = TypedGraph(nodes={"a1": GraphNode("a1", NodeType.CLASS, {})})
        b = TypedGraph(nodes={
            "b1": GraphNode("b1", NodeType.CLASS, {}),
            "b2": GraphNode("b2", NodeType.FUNCTION, {}),
        })
        m = GraphMorphism(node_map={"a1": "b1"}, source=a, target=b)
        assert m.image() == {"b1"}


# =============================================================================
# TestMatchFinder
# =============================================================================


class TestMatchFinder:
    def test_empty_pattern_matches(self):
        g = make_simple_graph()
        finder = MatchFinder(g)
        matches = finder.find_matches(TypedGraph())
        assert len(matches) == 1
        assert matches[0].node_map == {}

    def test_single_node_pattern(self):
        g = make_simple_graph()
        pattern = TypedGraph()
        pattern.add_node(GraphNode("p", NodeType.CLASS, {"name": "MyClass"}))
        finder = MatchFinder(g)
        matches = finder.find_matches(pattern)
        assert len(matches) == 1
        assert matches[0].node_map["p"] == "class:MyClass"

    def test_no_match(self):
        g = make_simple_graph()
        pattern = TypedGraph()
        pattern.add_node(GraphNode("p", NodeType.CLASS, {"name": "NonExistent"}))
        finder = MatchFinder(g)
        matches = finder.find_matches(pattern)
        assert len(matches) == 0

    def test_pattern_with_edge(self):
        g = make_simple_graph()
        pattern = TypedGraph()
        pattern.add_node(GraphNode("c", NodeType.CLASS, {"name": "MyClass"}))
        pattern.add_node(GraphNode("m", NodeType.FUNCTION, {"name": "my_method"}))
        pattern.add_edge(GraphEdge("c", "m", EdgeType.CONTAINS_METHOD))
        finder = MatchFinder(g)
        matches = finder.find_matches(pattern)
        assert len(matches) == 1
        assert matches[0].node_map["c"] == "class:MyClass"
        assert matches[0].node_map["m"] == "func:my_method"

    def test_multiple_matches(self):
        g = TypedGraph()
        g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "a"}))
        g.add_node(GraphNode("f2", NodeType.FUNCTION, {"name": "b"}))
        pattern = TypedGraph()
        pattern.add_node(GraphNode("p", NodeType.FUNCTION, {}))  # matches any function
        finder = MatchFinder(g)
        matches = finder.find_matches(pattern)
        assert len(matches) == 2

    def test_max_matches(self):
        g = TypedGraph()
        for i in range(10):
            g.add_node(GraphNode(f"f{i}", NodeType.FUNCTION, {"name": f"func{i}"}))
        pattern = TypedGraph()
        pattern.add_node(GraphNode("p", NodeType.FUNCTION, {}))
        finder = MatchFinder(g)
        matches = finder.find_matches(pattern, max_matches=3)
        assert len(matches) == 3

    def test_wildcard_attr(self):
        g = TypedGraph()
        g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_async": True}))
        pattern = TypedGraph()
        pattern.add_node(GraphNode("p", NodeType.FUNCTION, {"name": None}))  # wildcard
        finder = MatchFinder(g)
        matches = finder.find_matches(pattern)
        assert len(matches) == 1


# =============================================================================
# TestProductionRule
# =============================================================================


class TestProductionRule:
    def test_deleted_nodes(self):
        # Rule: remove a method node (in L but not in K)
        lhs = TypedGraph()
        lhs.add_node(GraphNode("cls", NodeType.CLASS, {}))
        lhs.add_node(GraphNode("method", NodeType.FUNCTION, {}))
        interface = TypedGraph()
        interface.add_node(GraphNode("cls", NodeType.CLASS, {}))
        rhs = TypedGraph()
        rhs.add_node(GraphNode("cls", NodeType.CLASS, {}))

        rule = ProductionRule(
            name="test", op_type=OperatorType.REMOVE_METHOD,
            lhs=lhs, interface=interface, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(interface, lhs),
            rhs_inclusion=GraphMorphism.inclusion(interface, rhs),
        )
        assert rule.deleted_nodes() == {"method"}
        assert rule.created_nodes() == set()
        assert rule.preserved_nodes() == {"cls"}

    def test_created_nodes(self):
        # Rule: add a param node (in R but not in K)
        lhs = TypedGraph()
        lhs.add_node(GraphNode("func", NodeType.FUNCTION, {}))
        interface = TypedGraph()
        interface.add_node(GraphNode("func", NodeType.FUNCTION, {}))
        rhs = TypedGraph()
        rhs.add_node(GraphNode("func", NodeType.FUNCTION, {}))
        rhs.add_node(GraphNode("param", NodeType.PARAMETER, {}))

        rule = ProductionRule(
            name="test", op_type=OperatorType.ADD_PARAM,
            lhs=lhs, interface=interface, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(interface, lhs),
            rhs_inclusion=GraphMorphism.inclusion(interface, rhs),
        )
        assert rule.deleted_nodes() == set()
        assert rule.created_nodes() == {"param"}
        assert rule.preserved_nodes() == {"func"}

    def test_validate_well_formed(self):
        lhs = TypedGraph(nodes={"n": GraphNode("n", NodeType.FUNCTION, {})})
        k = TypedGraph(nodes={"n": GraphNode("n", NodeType.FUNCTION, {})})
        rhs = TypedGraph(nodes={"n": GraphNode("n", NodeType.FUNCTION, {})})
        rule = ProductionRule(
            name="test", op_type=OperatorType.RENAME_METHOD,
            lhs=lhs, interface=k, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(k, lhs),
            rhs_inclusion=GraphMorphism.inclusion(k, rhs),
        )
        assert rule.validate() == []


# =============================================================================
# TestPushoutEngine (DPO)
# =============================================================================


class TestDPORewriting:
    def test_add_node_dpo(self):
        """DPO: add a node (empty deletion, add parameter)."""
        host = TypedGraph()
        host.add_node(GraphNode("func:foo", NodeType.FUNCTION, {"name": "foo"}))

        # Rule: L={func}, K={func}, R={func, param, HAS_PARAMETER edge}
        lhs = TypedGraph()
        lhs.add_node(GraphNode("func", NodeType.FUNCTION, {"name": "foo"}))
        k = TypedGraph()
        k.add_node(GraphNode("func", NodeType.FUNCTION, {"name": "foo"}))
        rhs = TypedGraph()
        rhs.add_node(GraphNode("func", NodeType.FUNCTION, {"name": "foo"}))
        rhs.add_node(GraphNode("param", NodeType.PARAMETER, {"name": "log"}))
        rhs.add_edge(GraphEdge("func", "param", EdgeType.HAS_PARAMETER))

        rule = ProductionRule(
            name="add_param", op_type=OperatorType.ADD_PARAM,
            lhs=lhs, interface=k, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(k, lhs),
            rhs_inclusion=GraphMorphism.inclusion(k, rhs),
        )

        match = GraphMorphism(
            node_map={"func": "func:foo"},
            source=lhs, target=host,
        )

        engine = PushoutEngine(RewriteMode.DPO)
        result = engine.apply(rule, match, host)

        assert result.success
        assert result.result_graph is not None
        # Original function preserved + new param added
        funcs = result.result_graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 1
        params = result.result_graph.get_nodes_by_type(NodeType.PARAMETER)
        assert len(params) == 1
        assert params[0].attrs["name"] == "log"

    def test_delete_node_dpo(self):
        """DPO: delete a node (method removed from class)."""
        host = TypedGraph()
        host.add_node(GraphNode("class:A", NodeType.CLASS, {"name": "A"}))
        host.add_node(GraphNode("func:m", NodeType.FUNCTION, {"name": "m"}))
        host.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))

        # Rule: L={cls, method, edge}, K={cls}, R={cls}
        lhs = TypedGraph()
        lhs.add_node(GraphNode("cls", NodeType.CLASS, {"name": "A"}))
        lhs.add_node(GraphNode("method", NodeType.FUNCTION, {"name": "m"}))
        lhs.add_edge(GraphEdge("cls", "method", EdgeType.CONTAINS_METHOD))
        k = TypedGraph()
        k.add_node(GraphNode("cls", NodeType.CLASS, {"name": "A"}))
        rhs = TypedGraph()
        rhs.add_node(GraphNode("cls", NodeType.CLASS, {"name": "A"}))

        rule = ProductionRule(
            name="remove_method", op_type=OperatorType.REMOVE_METHOD,
            lhs=lhs, interface=k, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(k, lhs),
            rhs_inclusion=GraphMorphism.inclusion(k, rhs),
        )

        match = GraphMorphism(
            node_map={"cls": "class:A", "method": "func:m"},
            source=lhs, target=host,
        )

        engine = PushoutEngine(RewriteMode.DPO)
        result = engine.apply(rule, match, host)

        assert result.success
        assert result.result_graph.node_count == 1
        assert result.result_graph.has_node("class:A")
        assert not result.result_graph.has_node("func:m")

    def test_dpo_gluing_condition_violation(self):
        """DPO should fail if deleting a node with external edges."""
        host = TypedGraph()
        host.add_node(GraphNode("class:A", NodeType.CLASS, {"name": "A"}))
        host.add_node(GraphNode("func:m", NodeType.FUNCTION, {"name": "m"}))
        host.add_node(GraphNode("call:x", NodeType.CALL, {"callee": "m"}))
        host.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))
        host.add_edge(GraphEdge("call:x", "func:m", EdgeType.CALLS))  # external edge

        # Rule: delete method (but call:x -> func:m is not in the match)
        lhs = TypedGraph()
        lhs.add_node(GraphNode("cls", NodeType.CLASS, {"name": "A"}))
        lhs.add_node(GraphNode("method", NodeType.FUNCTION, {"name": "m"}))
        lhs.add_edge(GraphEdge("cls", "method", EdgeType.CONTAINS_METHOD))
        k = TypedGraph()
        k.add_node(GraphNode("cls", NodeType.CLASS, {"name": "A"}))
        rhs = TypedGraph()
        rhs.add_node(GraphNode("cls", NodeType.CLASS, {"name": "A"}))

        rule = ProductionRule(
            name="remove_method", op_type=OperatorType.REMOVE_METHOD,
            lhs=lhs, interface=k, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(k, lhs),
            rhs_inclusion=GraphMorphism.inclusion(k, rhs),
        )

        match = GraphMorphism(
            node_map={"cls": "class:A", "method": "func:m"},
            source=lhs, target=host,
        )

        engine = PushoutEngine(RewriteMode.DPO)
        result = engine.apply(rule, match, host)

        assert not result.success
        assert any("Dangling" in e or "dangling" in e.lower() for e in result.errors)

    def test_attr_update_on_preserved_node(self):
        """DPO: rename (attribute update on preserved node)."""
        host = TypedGraph()
        host.add_node(GraphNode("func:old", NodeType.FUNCTION, {"name": "old"}))

        lhs = TypedGraph()
        lhs.add_node(GraphNode("f", NodeType.FUNCTION, {"name": "old"}))
        k = TypedGraph()
        k.add_node(GraphNode("f", NodeType.FUNCTION, {}))
        rhs = TypedGraph()
        rhs.add_node(GraphNode("f", NodeType.FUNCTION, {"name": "new"}))

        rule = ProductionRule(
            name="rename", op_type=OperatorType.RENAME_METHOD,
            lhs=lhs, interface=k, rhs=rhs,
            lhs_inclusion=GraphMorphism.inclusion(k, lhs),
            rhs_inclusion=GraphMorphism.inclusion(k, rhs),
        )

        match = GraphMorphism(
            node_map={"f": "func:old"},
            source=lhs, target=host,
        )

        engine = PushoutEngine(RewriteMode.DPO)
        result = engine.apply(rule, match, host)

        assert result.success
        assert result.result_graph.nodes["func:old"].attrs["name"] == "new"


# =============================================================================
# TestSPORewriting
# =============================================================================


class TestSPORewriting:
    def test_spo_auto_removes_dangling(self):
        """SPO should succeed even with dangling edges (auto-remove)."""
        host = TypedGraph()
        host.add_node(GraphNode("func:m", NodeType.FUNCTION, {"name": "m"}))
        host.add_node(GraphNode("call:x", NodeType.CALL, {"callee": "m"}))
        host.add_edge(GraphEdge("call:x", "func:m", EdgeType.CALLS))

        # Delete the function (SPO should auto-remove the CALLS edge)
        lhs = TypedGraph()
        lhs.add_node(GraphNode("method", NodeType.FUNCTION, {"name": "m"}))
        k = TypedGraph()
        rhs = TypedGraph()

        rule = ProductionRule(
            name="remove", op_type=OperatorType.REMOVE_METHOD,
            lhs=lhs, interface=k, rhs=rhs,
            lhs_inclusion=GraphMorphism(node_map={}, source=k, target=lhs),
            rhs_inclusion=GraphMorphism(node_map={}, source=k, target=rhs),
        )

        match = GraphMorphism(
            node_map={"method": "func:m"},
            source=lhs, target=host,
        )

        engine = PushoutEngine(RewriteMode.SPO)
        result = engine.apply(rule, match, host)

        assert result.success
        assert not result.result_graph.has_node("func:m")
        # Dangling edge auto-removed
        assert result.result_graph.edge_count == 0


# =============================================================================
# TestInvariants
# =============================================================================


class TestInvariants:
    def test_no_dangling_edges_pass(self):
        g = make_simple_graph()
        registry = InvariantRegistry()
        registry.enable("schema_conformance")
        violations = registry.verify_graph(g)
        dangling = [v for v in violations if v.invariant_name == "schema_conformance"]
        assert len(dangling) == 0

    def test_no_dangling_edges_fail(self):
        g = TypedGraph()
        g.add_node(GraphNode("a", NodeType.CLASS, {}))
        g.edges.append(GraphEdge("a", "missing", EdgeType.CONTAINS_METHOD))
        registry = InvariantRegistry()
        registry.enable("schema_conformance")
        violations = registry.verify_graph(g)
        dangling = [
            v for v in violations
            if v.invariant_name == "schema_conformance" and "Dangling" in v.message
        ]
        assert len(dangling) == 1

    def test_unique_method_names_pass(self):
        g = make_simple_graph()
        violations = verify_graph_invariants(g)
        dupes = [v for v in violations if v.invariant_name == "scope_name_uniqueness"]
        assert len(dupes) == 0

    def test_unique_method_names_fail(self):
        g = TypedGraph()
        g.add_node(make_class_node("C"))
        g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "dup"}))
        g.add_node(GraphNode("f2", NodeType.FUNCTION, {"name": "dup"}))
        g.add_edge(GraphEdge("class:C", "f1", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("class:C", "f2", EdgeType.CONTAINS_METHOD))
        violations = verify_graph_invariants(g)
        dupes = [v for v in violations if v.invariant_name == "scope_name_uniqueness"]
        assert len(dupes) == 1

    def test_valid_inheritance_self_loop(self):
        g = TypedGraph()
        g.add_node(make_class_node("A"))
        g.add_edge(GraphEdge("class:A", "class:A", EdgeType.INHERITS))
        violations = verify_graph_invariants(g)
        inh = [v for v in violations if v.invariant_name == "inheritance_dag"]
        assert len(inh) >= 1

    def test_custom_invariant(self):
        registry = InvariantRegistry()

        def check_custom(graph: TypedGraph) -> list[InvariantViolation]:
            if graph.node_count > 5:
                return [InvariantViolation("too_many_nodes", "Graph has too many nodes")]
            return []

        registry.add_invariant(Invariant("custom", "test", check_custom))
        g = TypedGraph()
        for i in range(6):
            g.add_node(GraphNode(f"n{i}", NodeType.FUNCTION, {}))
        violations = registry.verify_graph(g)
        custom = [v for v in violations if v.invariant_name == "too_many_nodes"]
        assert len(custom) == 1


# =============================================================================
# TestProductionRuleCatalog
# =============================================================================


class TestProductionRuleCatalog:
    def setup_method(self):
        self.catalog = ProductionRuleCatalog()

    def test_add_method_rule(self):
        rule = self.catalog.create_rule(OperatorType.ADD_METHOD, {
            "class_name": "Foo", "method_name": "bar",
        })
        assert rule.name == "add_method:Foo.bar"
        assert rule.created_nodes()  # should have created nodes
        assert rule.deleted_nodes() == set()

    def test_remove_method_rule(self):
        rule = self.catalog.create_rule(OperatorType.REMOVE_METHOD, {
            "class_name": "Foo", "method_name": "bar",
        })
        assert "method" in rule.deleted_nodes()

    def test_rename_method_rule(self):
        rule = self.catalog.create_rule(OperatorType.RENAME_METHOD, {
            "old_name": "foo", "new_name": "bar",
        })
        assert rule.deleted_nodes() == set()
        assert rule.created_nodes() == set()  # rename is attr update

    def test_add_field_rule(self):
        rule = self.catalog.create_rule(OperatorType.ADD_FIELD, {
            "class_name": "Foo", "field_name": "count",
        })
        assert rule.created_nodes()

    def test_add_class_rule(self):
        rule = self.catalog.create_rule(OperatorType.ADD_CLASS, {
            "class_name": "NewClass",
        })
        assert "cls" in rule.created_nodes()

    def test_add_param_rule(self):
        rule = self.catalog.create_rule(OperatorType.ADD_PARAM, {
            "function_name": "process", "param_name": "verbose",
            "default_value": "False",
        })
        assert rule.created_nodes()

    def test_create_module_rule(self):
        rule = self.catalog.create_rule(OperatorType.CREATE_MODULE, {
            "module_name": "utils",
        })
        assert rule.created_nodes()

    def test_add_import_rule(self):
        rule = self.catalog.create_rule(OperatorType.ADD_IMPORT, {
            "module": "os.path", "name": "join",
        })
        assert rule.created_nodes()

    def test_add_arg_rule(self):
        rule = self.catalog.create_rule(OperatorType.ADD_ARG, {
            "callee": "process", "arg_name": "verbose", "arg_value": "False",
        })
        assert rule.created_nodes()

    def test_all_operator_types_supported(self):
        """Every OperatorType should be in the catalog dispatch table."""
        for op_type in OperatorType:
            assert op_type in ProductionRuleCatalog._DISPATCH, f"{op_type} not in catalog"


# =============================================================================
# TestTransformationPath
# =============================================================================


class TestTransformationPath:
    def test_empty_path(self):
        path = TransformationPath()
        assert path.is_empty
        assert path.length == 0
        assert path.all_succeeded

    def test_add_step(self):
        path = TransformationPath()
        catalog = ProductionRuleCatalog()
        rule = catalog.create_rule(OperatorType.ADD_CLASS, {"class_name": "Foo"})
        app = RuleApplication(rule=rule)
        app.result = RewriteResult(success=True)
        path.add_step(app)
        assert path.length == 1
        assert path.success_count == 1

    def test_serialization(self):
        path = TransformationPath(metadata={"task": "test"})
        d = path.to_dict()
        assert d["length"] == 0
        assert d["metadata"]["task"] == "test"


# =============================================================================
# TestGraphTransformationEngine
# =============================================================================


class TestGraphTransformationEngine:
    def test_create_engine(self):
        engine = create_engine()
        assert engine.mode == RewriteMode.DPO

    def test_apply_add_param(self):
        """End-to-end: add parameter to a function."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(GraphNode("func:get_data", NodeType.FUNCTION, {"name": "get_data"}))

        rule = engine.catalog.create_rule(OperatorType.ADD_PARAM, {
            "function_name": "get_data",
            "param_name": "log",
            "default_value": "True",
        })
        result = engine.apply_rule(rule, graph)

        assert result.success
        params = result.result_graph.get_nodes_by_type(NodeType.PARAMETER)
        assert len(params) == 1
        assert params[0].attrs["name"] == "log"

    def test_apply_add_method(self):
        """End-to-end: add method to a class."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(make_class_node("MyClass"))

        rule = engine.catalog.create_rule(OperatorType.ADD_METHOD, {
            "class_name": "MyClass", "method_name": "process",
        })
        result = engine.apply_rule(rule, graph)

        assert result.success
        funcs = result.result_graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 1
        assert funcs[0].attrs["name"] == "process"

    def test_apply_remove_method(self):
        """End-to-end: remove method from a class."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(make_class_node("MyClass"))
        graph.add_node(make_func_node("process"))
        graph.add_edge(GraphEdge("class:MyClass", "func:process", EdgeType.CONTAINS_METHOD))

        rule = engine.catalog.create_rule(OperatorType.REMOVE_METHOD, {
            "class_name": "MyClass", "method_name": "process",
        })
        result = engine.apply_rule(rule, graph)

        assert result.success
        assert result.result_graph.get_nodes_by_type(NodeType.FUNCTION) == []

    def test_apply_rename_method(self):
        """End-to-end: rename a method."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(make_func_node("old_name"))

        rule = engine.catalog.create_rule(OperatorType.RENAME_METHOD, {
            "old_name": "old_name", "new_name": "new_name",
        })
        result = engine.apply_rule(rule, graph)

        assert result.success
        func = result.result_graph.get_nodes_by_type(NodeType.FUNCTION)[0]
        assert func.attrs["name"] == "new_name"

    def test_no_match_returns_failure(self):
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()  # empty graph

        rule = engine.catalog.create_rule(OperatorType.ADD_PARAM, {
            "function_name": "nonexistent", "param_name": "x",
        })
        result = engine.apply_rule(rule, graph)

        assert not result.success
        assert "No match" in result.errors[0]

    def test_precondition_failure(self):
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()  # no class "Missing"

        rule = engine.catalog.create_rule(OperatorType.ADD_METHOD, {
            "class_name": "Missing", "method_name": "foo",
        })
        result = engine.apply_rule(rule, graph)

        # Should fail: either no match or precondition failure
        assert not result.success

    def test_apply_all_matches(self):
        """Apply rule at all matching call sites."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(GraphNode("c1", NodeType.CALL, {"callee": "func"}))
        graph.add_node(GraphNode("c2", NodeType.CALL, {"callee": "func"}))

        rule = engine.catalog.create_rule(OperatorType.ADD_ARG, {
            "callee": "func", "arg_name": "verbose", "arg_value": "True",
        })
        results = engine.apply_all_matches(rule, graph)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_add_arg_call_type_direct(self):
        """call_type='direct' should only match direct calls, not method calls."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo", "call_type": "direct"}))
        graph.add_node(GraphNode("c2", NodeType.CALL, {"callee": "foo", "call_type": "method"}))

        rule = engine.catalog.create_rule(OperatorType.ADD_ARG, {
            "callee": "foo", "arg_name": "log", "arg_value": "True",
            "call_type": "direct",
        })
        results = engine.apply_all_matches(rule, graph)

        assert len(results) == 1
        assert results[0].success

    def test_add_arg_call_type_method(self):
        """call_type='method' should only match method calls, not direct calls."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo", "call_type": "direct"}))
        graph.add_node(GraphNode("c2", NodeType.CALL, {"callee": "foo", "call_type": "method"}))

        rule = engine.catalog.create_rule(OperatorType.ADD_ARG, {
            "callee": "foo", "arg_name": "log", "arg_value": "True",
            "call_type": "method",
        })
        results = engine.apply_all_matches(rule, graph)

        assert len(results) == 1
        assert results[0].success

    def test_add_arg_no_call_type_matches_both(self):
        """Without call_type, add_arg should match both direct and method calls."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo", "call_type": "direct"}))
        graph.add_node(GraphNode("c2", NodeType.CALL, {"callee": "foo", "call_type": "method"}))

        rule = engine.catalog.create_rule(OperatorType.ADD_ARG, {
            "callee": "foo", "arg_name": "log", "arg_value": "True",
        })
        results = engine.apply_all_matches(rule, graph)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_update_call_call_type_direct(self):
        """call_type='direct' on update_call should only match direct calls."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(GraphNode("c1", NodeType.CALL, {"callee": "old", "call_type": "direct"}))
        graph.add_node(GraphNode("c2", NodeType.CALL, {"callee": "old", "call_type": "method"}))

        rule = engine.catalog.create_rule(OperatorType.UPDATE_CALL, {
            "old_callee": "old", "new_callee": "new",
            "call_type": "direct",
        })
        results = engine.apply_all_matches(rule, graph)

        assert len(results) == 1
        assert results[0].success

    def test_update_import_submodule_pattern(self):
        """update_import should also match 'from parent import child' pattern."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        # Pattern 1: from pkg.old_mod import Foo  (module="pkg.old_mod", name="Foo")
        graph.add_node(GraphNode("i1", NodeType.IMPORT, {
            "module": "pkg.old_mod", "name": "Foo",
        }))
        # Pattern 2: from pkg import old_mod  (module="pkg", name="old_mod")
        graph.add_node(GraphNode("i2", NodeType.IMPORT, {
            "module": "pkg", "name": "old_mod",
        }))

        rules = engine.catalog.create_rules(OperatorType.UPDATE_IMPORT, {
            "old_module": "pkg.old_mod", "new_module": "pkg.new_mod",
        })
        assert len(rules) == 2  # direct + submodule rules

        current = graph
        for rule in rules:
            results = engine.apply_all_matches(rule, current)
            for r in results:
                assert r.success
                current = r.result_graph

        # i1: module changed from pkg.old_mod to pkg.new_mod
        i1 = current.get_node("i1")
        assert i1.attrs["module"] == "pkg.new_mod"
        assert i1.attrs["name"] == "Foo"  # unchanged

        # i2: name changed from old_mod to new_mod
        i2 = current.get_node("i2")
        assert i2.attrs["module"] == "pkg"  # unchanged
        assert i2.attrs["name"] == "new_mod"

    def test_apply_path(self):
        """Apply a sequence of rules as a transformation path."""
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(make_class_node("Foo"))

        catalog = engine.catalog
        rule1 = catalog.create_rule(OperatorType.ADD_METHOD, {
            "class_name": "Foo", "method_name": "bar",
        })
        rule2 = catalog.create_rule(OperatorType.ADD_FIELD, {
            "class_name": "Foo", "field_name": "count",
        })

        path = TransformationPath(steps=[
            RuleApplication(rule=rule1),
            RuleApplication(rule=rule2),
        ])

        result_path = engine.apply_path(path, graph)

        assert result_path.all_succeeded
        assert result_path.length == 2
        final = result_path.current_graph
        assert final.get_nodes_by_type(NodeType.FUNCTION)
        assert final.get_nodes_by_type(NodeType.FIELD)

    def test_dry_run(self):
        engine = create_engine(check_invariants=False)
        graph = TypedGraph()
        graph.add_node(make_func_node("foo"))

        rule = engine.catalog.create_rule(OperatorType.ADD_PARAM, {
            "function_name": "foo", "param_name": "x",
        })
        result = engine.dry_run(rule, graph)

        assert result.success
        # Original graph unchanged
        assert graph.get_nodes_by_type(NodeType.PARAMETER) == []

    def test_find_matches(self):
        engine = create_engine()
        graph = TypedGraph()
        graph.add_node(make_func_node("a"))
        graph.add_node(make_func_node("b"))

        rule = engine.catalog.create_rule(OperatorType.RENAME_METHOD, {
            "old_name": "a", "new_name": "c",
        })
        matches = engine.find_matches(rule, graph)
        assert len(matches) == 1

    def test_verify_graph(self):
        engine = create_engine()
        graph = make_simple_graph()
        violations = engine.verify_graph(graph)
        errors = [v for v in violations if v.severity == InvariantSeverity.ERROR]
        assert len(errors) == 0


# =============================================================================
# TestRealWorldScenarios
# =============================================================================


class TestRealWorldScenarios:
    def test_add_param_and_update_call_sites(self):
        """Simulate: add parameter to function + update all call sites."""
        engine = create_engine(check_invariants=False)

        # Build a graph with a function and two call sites
        graph = TypedGraph()
        graph.add_node(GraphNode("func:get_data", NodeType.FUNCTION, {"name": "get_data"}))
        graph.add_node(GraphNode("call:a.py:5:0", NodeType.CALL, {"callee": "get_data"}))
        graph.add_node(GraphNode("call:b.py:10:0", NodeType.CALL, {"callee": "get_data"}))
        graph.add_edge(GraphEdge("call:a.py:5:0", "func:get_data", EdgeType.CALLS))
        graph.add_edge(GraphEdge("call:b.py:10:0", "func:get_data", EdgeType.CALLS))

        catalog = engine.catalog

        # Step 1: Add parameter
        rule1 = catalog.create_rule(OperatorType.ADD_PARAM, {
            "function_name": "get_data", "param_name": "log",
            "default_value": "True",
        })
        result1 = engine.apply_rule(rule1, graph)
        assert result1.success

        # Step 2: Add argument to all call sites
        rule2 = catalog.create_rule(OperatorType.ADD_ARG, {
            "callee": "get_data", "arg_name": "log", "arg_value": "False",
        })
        results = engine.apply_all_matches(rule2, result1.result_graph)
        assert len(results) == 2
        assert all(r.success for r in results)

        final = results[-1].result_graph
        args = final.get_nodes_by_type(NodeType.ARGUMENT)
        assert len(args) == 2
        for arg in args:
            assert arg.attrs["name"] == "log"
            assert arg.attrs["value"] == "False"

    def test_move_method_between_classes(self):
        """Simulate: move method from one class to another."""
        engine = create_engine(check_invariants=False)

        graph = TypedGraph()
        graph.add_node(make_class_node("Source"))
        graph.add_node(make_class_node("Target"))
        graph.add_node(make_func_node("helper"))
        graph.add_edge(GraphEdge("class:Source", "func:helper", EdgeType.CONTAINS_METHOD))

        rule = engine.catalog.create_rule(OperatorType.MOVE_METHOD, {
            "source_class": "Source",
            "target_class": "Target",
            "method_name": "helper",
        })
        result = engine.apply_rule(rule, graph)

        assert result.success
        final = result.result_graph
        # Method should not be in Source anymore (edge deleted)
        src_methods = [
            e for e in final.get_edges_from("class:Source")
            if e.edge_type == EdgeType.CONTAINS_METHOD
        ]
        assert len(src_methods) == 0
        # Method should be in Target
        assert final.has_node("func:helper")

    def test_sequential_refactoring_path(self):
        """Full path: create class -> add method -> add field -> add param."""
        engine = create_engine(check_invariants=False)
        catalog = engine.catalog

        graph = TypedGraph()

        rules = [
            catalog.create_rule(OperatorType.ADD_CLASS, {"class_name": "Config"}),
            catalog.create_rule(OperatorType.ADD_METHOD, {"class_name": "Config", "method_name": "load"}),
            catalog.create_rule(OperatorType.ADD_FIELD, {"class_name": "Config", "field_name": "path"}),
            catalog.create_rule(OperatorType.ADD_PARAM, {"function_name": "load", "param_name": "verbose"}),
        ]

        path = TransformationPath(
            steps=[RuleApplication(rule=r) for r in rules]
        )

        result_path = engine.apply_path(path, graph)

        assert result_path.all_succeeded
        final = result_path.current_graph
        assert len(final.get_nodes_by_type(NodeType.CLASS)) == 1
        assert len(final.get_nodes_by_type(NodeType.FUNCTION)) == 1
        assert len(final.get_nodes_by_type(NodeType.FIELD)) == 1
        assert len(final.get_nodes_by_type(NodeType.PARAMETER)) == 1
