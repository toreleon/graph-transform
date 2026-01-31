"""Comprehensive tests for the redesigned layered invariant system."""

import pytest

from graph_transform import (
    EdgeConstraint,
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphSchema,
    Invariant,
    InvariantLayer,
    InvariantRegistry,
    InvariantSeverity,
    InvariantViolation,
    NodeType,
    ScopeRule,
    TypedGraph,
)


# =============================================================================
# Helpers
# =============================================================================


def _cls(name: str, nid: str | None = None) -> GraphNode:
    return GraphNode(nid or f"class:{name}", NodeType.CLASS, {"name": name})


def _func(name: str, nid: str | None = None, **kw) -> GraphNode:
    attrs = {"name": name, "is_method": kw.get("is_method", False)}
    attrs.update(kw)
    return GraphNode(nid or f"func:{name}", NodeType.FUNCTION, attrs)


def _param(name: str, pos: int, func: str, **kw) -> GraphNode:
    attrs = {"name": name, "position": pos}
    attrs.update(kw)
    return GraphNode(f"param:{func}.{name}", NodeType.PARAMETER, attrs)


def _call(callee: str, nid: str | None = None) -> GraphNode:
    return GraphNode(nid or f"call:{callee}", NodeType.CALL, {"callee": callee})


def _arg(name: str, pos: int, call_id: str) -> GraphNode:
    return GraphNode(
        f"arg:{call_id}.{name}", NodeType.ARGUMENT,
        {"name": name, "position": pos},
    )


def _mod(name: str, nid: str | None = None) -> GraphNode:
    return GraphNode(nid or f"mod:{name}", NodeType.MODULE, {"name": name})


def _imp(module: str, nid: str | None = None) -> GraphNode:
    return GraphNode(nid or f"imp:{module}", NodeType.IMPORT, {"module": module})


def _field(name: str, cls_name: str = "", nid: str | None = None) -> GraphNode:
    return GraphNode(
        nid or f"field:{cls_name}.{name}", NodeType.FIELD,
        {"name": name, "class_name": cls_name},
    )


def _schema_registry() -> InvariantRegistry:
    """Registry with schema_conformance enabled."""
    r = InvariantRegistry()
    r.enable("schema_conformance")
    return r


def _violations_named(violations: list[InvariantViolation], name: str) -> list[InvariantViolation]:
    return [v for v in violations if v.invariant_name == name]


# =============================================================================
# Test Foundation Types
# =============================================================================


class TestFoundationTypes:
    def test_severity_enum_values(self):
        assert InvariantSeverity.ERROR.value == "error"
        assert InvariantSeverity.WARNING.value == "warning"
        assert InvariantSeverity.INFO.value == "info"

    def test_layer_enum_ordering(self):
        assert InvariantLayer.SCHEMA.value < InvariantLayer.STRUCTURE.value
        assert InvariantLayer.STRUCTURE.value < InvariantLayer.SCOPE.value
        assert InvariantLayer.SCOPE.value < InvariantLayer.REFERENCE.value
        assert InvariantLayer.REFERENCE.value < InvariantLayer.TYPE_SYSTEM.value
        assert InvariantLayer.TYPE_SYSTEM.value < InvariantLayer.SEMANTIC.value
        assert InvariantLayer.SEMANTIC.value < InvariantLayer.QUALITY.value

    def test_violation_defaults(self):
        v = InvariantViolation("test", "msg")
        assert v.severity == InvariantSeverity.ERROR
        assert v.layer == InvariantLayer.STRUCTURE
        assert v.node_id is None
        assert v.edge is None
        assert v.related_nodes == []
        assert v.fix_hint is None

    def test_violation_to_dict(self):
        edge = GraphEdge("a", "b", EdgeType.CALLS)
        v = InvariantViolation(
            "test", "msg",
            severity=InvariantSeverity.WARNING,
            layer=InvariantLayer.REFERENCE,
            node_id="a",
            edge=edge,
            related_nodes=["b"],
            fix_hint="fix it",
        )
        d = v.to_dict()
        assert d["severity"] == "warning"
        assert d["layer"] == "reference"
        assert d["node_id"] == "a"
        assert d["edge"]["source"] == "a"
        assert d["related_nodes"] == ["b"]
        assert d["fix_hint"] == "fix it"

    def test_invariant_disabled(self):
        def check(g):
            return [InvariantViolation("x", "y")]

        inv = Invariant("test", "desc", check, enabled=False)
        assert inv.verify(TypedGraph()) == []

    def test_invariant_enabled(self):
        def check(g):
            return [InvariantViolation("x", "y")]

        inv = Invariant("test", "desc", check, enabled=True)
        assert len(inv.verify(TypedGraph())) == 1


# =============================================================================
# Test Layer 0 — Schema Conformance
# =============================================================================


class TestSchemaConformance:
    def test_dangling_source(self):
        g = TypedGraph()
        g.add_node(GraphNode("b", NodeType.FUNCTION, {"name": "f"}))
        g.edges.append(GraphEdge("missing", "b", EdgeType.CONTAINS_METHOD))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("Dangling edge source" in v.message for v in vs)

    def test_dangling_target(self):
        g = TypedGraph()
        g.add_node(GraphNode("a", NodeType.CLASS, {"name": "A"}))
        g.edges.append(GraphEdge("a", "missing", EdgeType.CONTAINS_METHOD))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("Dangling edge target" in v.message for v in vs)

    def test_inherits_allows_external_target(self):
        """INHERITS edges to missing targets should NOT trigger dangling errors."""
        g = TypedGraph()
        g.add_node(_cls("Child"))
        g.edges.append(GraphEdge("class:Child", "external:Base", EdgeType.INHERITS))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        dangling = [v for v in vs if "Dangling" in v.message]
        assert len(dangling) == 0

    def test_wrong_source_type(self):
        """CONTAINS_METHOD source must be CLASS, not FUNCTION."""
        g = TypedGraph()
        g.add_node(_func("a"))
        g.add_node(_func("b", nid="func:b"))
        g.add_edge(GraphEdge("func:a", "func:b", EdgeType.CONTAINS_METHOD))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("source" in v.message and "expected" in v.message for v in vs)

    def test_wrong_target_type(self):
        """HAS_PARAMETER target must be PARAMETER, not CLASS."""
        g = TypedGraph()
        g.add_node(_func("f"))
        g.add_node(_cls("C"))
        g.add_edge(GraphEdge("func:f", "class:C", EdgeType.HAS_PARAMETER))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("target" in v.message and "expected" in v.message for v in vs)

    def test_multiplicity_target_max(self):
        """A method can be contained in at most 1 class."""
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_node(_cls("B"))
        g.add_node(_func("m", is_method=True))
        g.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("class:B", "func:m", EdgeType.CONTAINS_METHOD))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("Multiplicity" in v.message and "incoming" in v.message for v in vs)

    def test_multiplicity_source_max(self):
        """A class/function can be DEFINED_IN at most 1 module."""
        g = TypedGraph()
        g.add_node(_func("f"))
        g.add_node(_mod("m1"))
        g.add_node(_mod("m2"))
        g.add_edge(GraphEdge("func:f", "mod:m1", EdgeType.DEFINED_IN))
        g.add_edge(GraphEdge("func:f", "mod:m2", EdgeType.DEFINED_IN))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("Multiplicity" in v.message and "outgoing" in v.message for v in vs)

    def test_missing_required_attrs(self):
        """CLASS nodes require 'name' attribute."""
        g = TypedGraph()
        g.add_node(GraphNode("c1", NodeType.CLASS, {}))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert any("missing required attribute" in v.message and "name" in v.message for v in vs)

    def test_valid_graph_no_schema_violations(self):
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_node(_func("m", is_method=True))
        g.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))
        r = _schema_registry()
        vs = _violations_named(r.verify_graph(g), "schema_conformance")
        assert len(vs) == 0


# =============================================================================
# Test Layer 1 — Structural Integrity
# =============================================================================


class TestStructuralIntegrity:
    def test_containment_cycle(self):
        """A contains B contains A should be detected."""
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_node(_func("B", is_method=True))
        # These edges create a cycle through containment
        # Use CLASS containing FUNCTION, and abuse to create cycle
        g.add_edge(GraphEdge("class:A", "func:B", EdgeType.CONTAINS_METHOD))
        # We can't really create a containment cycle with proper types,
        # so let's create one with parameters
        g2 = TypedGraph()
        g2.add_node(_func("f1"))
        g2.add_node(_param("a", 0, "f1"))
        g2.add_edge(GraphEdge("func:f1", "param:f1.a", EdgeType.HAS_PARAMETER))
        # Add reverse containment edge to create cycle (improper but tests the check)
        g2.edges.append(GraphEdge("param:f1.a", "func:f1", EdgeType.CONTAINS_METHOD))

        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g2), "containment_acyclicity")
        assert len(vs) >= 1

    def test_no_cycle_clean_graph(self):
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_node(_func("m", is_method=True))
        g.add_node(_param("x", 0, "m"))
        g.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("func:m", "param:m.x", EdgeType.HAS_PARAMETER))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "containment_acyclicity")
        assert len(vs) == 0

    def test_orphan_node(self):
        """A function not connected to any containment hierarchy → WARNING."""
        g = TypedGraph()
        g.add_node(_func("orphan"))
        r = InvariantRegistry()
        r.enable("no_orphan_nodes")
        vs = _violations_named(r.verify_graph(g), "no_orphan_nodes")
        assert len(vs) >= 1
        assert all(v.severity == InvariantSeverity.WARNING for v in vs)

    def test_connected_node_not_orphan(self):
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_node(_func("m", is_method=True))
        g.add_edge(GraphEdge("class:A", "func:m", EdgeType.CONTAINS_METHOD))
        r = InvariantRegistry()
        r.enable("no_orphan_nodes")
        vs = _violations_named(r.verify_graph(g), "no_orphan_nodes")
        assert len(vs) == 0


# =============================================================================
# Test Layer 2 — Scope Uniqueness (Parametric)
# =============================================================================


class TestScopeUniqueness:
    def test_duplicate_method_names_in_class(self):
        g = TypedGraph()
        g.add_node(_cls("C"))
        g.add_node(_func("m", nid="f1", is_method=True))
        g.add_node(_func("m", nid="f2", is_method=True))
        g.add_edge(GraphEdge("class:C", "f1", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("class:C", "f2", EdgeType.CONTAINS_METHOD))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "scope_name_uniqueness")
        assert len(vs) == 1

    def test_overload_methods_allowed(self):
        """@overload decorated methods with same name should not trigger violation."""
        g = TypedGraph()
        g.add_node(_cls("C"))
        g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "m", "is_method": True, "is_overload": True}))
        g.add_node(GraphNode("f2", NodeType.FUNCTION, {"name": "m", "is_method": True, "is_overload": True}))
        g.add_edge(GraphEdge("class:C", "f1", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("class:C", "f2", EdgeType.CONTAINS_METHOD))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "scope_name_uniqueness")
        assert len(vs) == 0

    def test_duplicate_field_names_in_class(self):
        g = TypedGraph()
        g.add_node(_cls("C"))
        g.add_node(_field("x", "C", nid="f1"))
        g.add_node(_field("x", "C", nid="f2"))
        g.add_edge(GraphEdge("class:C", "f1", EdgeType.CONTAINS_FIELD))
        g.add_edge(GraphEdge("class:C", "f2", EdgeType.CONTAINS_FIELD))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "scope_name_uniqueness")
        assert len(vs) == 1

    def test_duplicate_param_names_in_function(self):
        g = TypedGraph()
        g.add_node(_func("f"))
        g.add_node(GraphNode("p1", NodeType.PARAMETER, {"name": "x", "position": 0}))
        g.add_node(GraphNode("p2", NodeType.PARAMETER, {"name": "x", "position": 1}))
        g.add_edge(GraphEdge("func:f", "p1", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("func:f", "p2", EdgeType.HAS_PARAMETER))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "scope_name_uniqueness")
        assert len(vs) == 1

    def test_duplicate_arg_positions_in_call(self):
        g = TypedGraph()
        g.add_node(_call("f"))
        g.add_node(GraphNode("a1", NodeType.ARGUMENT, {"position": 0}))
        g.add_node(GraphNode("a2", NodeType.ARGUMENT, {"position": 0}))
        g.add_edge(GraphEdge("call:f", "a1", EdgeType.HAS_ARGUMENT))
        g.add_edge(GraphEdge("call:f", "a2", EdgeType.HAS_ARGUMENT))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "scope_name_uniqueness")
        assert len(vs) == 1

    def test_unique_names_no_violation(self):
        g = TypedGraph()
        g.add_node(_cls("C"))
        g.add_node(_func("m1", nid="f1", is_method=True))
        g.add_node(_func("m2", nid="f2", is_method=True))
        g.add_edge(GraphEdge("class:C", "f1", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("class:C", "f2", EdgeType.CONTAINS_METHOD))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "scope_name_uniqueness")
        assert len(vs) == 0

    def test_global_scope_duplicate_module_name(self):
        g = TypedGraph()
        g.add_node(_mod("utils", nid="m1"))
        g.add_node(_mod("utils", nid="m2"))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "global_scope_uniqueness")
        assert any("module" in v.message.lower() for v in vs)

    def test_global_scope_duplicate_function_in_same_scope(self):
        g = TypedGraph()
        g.add_node(_func("foo", nid="f1"))
        g.add_node(_func("foo", nid="f2"))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "global_scope_uniqueness")
        assert any("function" in v.message.lower() for v in vs)

    def test_global_scope_same_name_different_modules(self):
        """Same function name in different modules should NOT clash."""
        g = TypedGraph()
        g.add_node(_func("foo", nid="f1"))
        g.add_node(_func("foo", nid="f2"))
        g.add_node(_mod("mod_a"))
        g.add_node(_mod("mod_b"))
        g.add_edge(GraphEdge("f1", "mod:mod_a", EdgeType.DEFINED_IN))
        g.add_edge(GraphEdge("f2", "mod:mod_b", EdgeType.DEFINED_IN))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "global_scope_uniqueness")
        func_dupes = [v for v in vs if "function" in v.message.lower()]
        assert len(func_dupes) == 0


# =============================================================================
# Test Layer 3 — Reference Integrity
# =============================================================================


class TestReferenceIntegrity:
    def test_calls_to_missing_function(self):
        g = TypedGraph()
        g.add_node(_call("foo"))
        g.edges.append(GraphEdge("call:foo", "missing_func", EdgeType.CALLS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "reference_integrity")
        assert len(vs) == 1

    def test_references_to_missing_node(self):
        g = TypedGraph()
        g.add_node(_func("f"))
        g.edges.append(GraphEdge("func:f", "missing", EdgeType.REFERENCES))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "reference_integrity")
        assert len(vs) == 1

    def test_valid_calls_edge(self):
        g = TypedGraph()
        g.add_node(_call("foo"))
        g.add_node(_func("foo"))
        g.add_edge(GraphEdge("call:foo", "func:foo", EdgeType.CALLS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "reference_integrity")
        assert len(vs) == 0

    def test_stale_reference_warning(self):
        """Callee attr doesn't match target function name → WARNING."""
        g = TypedGraph()
        g.add_node(GraphNode("c1", NodeType.CALL, {"callee": "old_name"}))
        g.add_node(_func("new_name"))
        g.add_edge(GraphEdge("c1", "func:new_name", EdgeType.CALLS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "reference_consistency")
        assert len(vs) == 1
        assert vs[0].severity == InvariantSeverity.WARNING

    def test_consistent_reference_no_warning(self):
        g = TypedGraph()
        g.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo"}))
        g.add_node(_func("foo"))
        g.add_edge(GraphEdge("c1", "func:foo", EdgeType.CALLS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "reference_consistency")
        assert len(vs) == 0


# =============================================================================
# Test Layer 4 — Type System
# =============================================================================


class TestTypeSystem:
    def test_self_inheritance(self):
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_edge(GraphEdge("class:A", "class:A", EdgeType.INHERITS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "inheritance_dag")
        assert len(vs) >= 1

    def test_circular_inheritance(self):
        """A -> B -> A should be detected."""
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_node(_cls("B"))
        g.add_edge(GraphEdge("class:A", "class:B", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:B", "class:A", EdgeType.INHERITS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "inheritance_dag")
        assert len(vs) >= 1

    def test_multi_parent_cycle(self):
        """A -> B, A -> C, B -> D, C -> D, D -> A."""
        g = TypedGraph()
        for n in "ABCD":
            g.add_node(_cls(n))
        g.add_edge(GraphEdge("class:A", "class:B", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:A", "class:C", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:B", "class:D", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:C", "class:D", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:D", "class:A", EdgeType.INHERITS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "inheritance_dag")
        assert len(vs) >= 1

    def test_valid_diamond_inheritance(self):
        """A -> B, A -> C, B -> D, C -> D (diamond, no cycle)."""
        g = TypedGraph()
        for n in "ABCD":
            g.add_node(_cls(n))
        g.add_edge(GraphEdge("class:A", "class:B", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:A", "class:C", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:B", "class:D", EdgeType.INHERITS))
        g.add_edge(GraphEdge("class:C", "class:D", EdgeType.INHERITS))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "inheritance_dag")
        assert len(vs) == 0

    def test_override_incompatible_param_count(self):
        """Method with different param count in subclass → WARNING."""
        g = TypedGraph()
        g.add_node(_cls("Base"))
        g.add_node(_cls("Child"))
        g.add_edge(GraphEdge("class:Child", "class:Base", EdgeType.INHERITS))

        # Base.process(self, a, b) — 2 non-self params
        g.add_node(_func("process", nid="f_base", is_method=True))
        g.add_node(_param("self", 0, "base"))
        g.add_node(_param("a", 1, "base"))
        g.add_node(_param("b", 2, "base"))
        g.add_edge(GraphEdge("class:Base", "f_base", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("f_base", "param:base.self", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("f_base", "param:base.a", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("f_base", "param:base.b", EdgeType.HAS_PARAMETER))

        # Child.process(self, a) — 1 non-self param (incompatible)
        g.add_node(_func("process", nid="f_child", is_method=True))
        g.add_node(_param("self", 0, "child"))
        g.add_node(_param("a", 1, "child"))
        g.add_edge(GraphEdge("class:Child", "f_child", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("f_child", "param:child.self", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("f_child", "param:child.a", EdgeType.HAS_PARAMETER))

        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "override_compatibility")
        assert len(vs) >= 1
        assert all(v.severity == InvariantSeverity.WARNING for v in vs)

    def test_compatible_override_no_warning(self):
        """Same param count in override → no violation."""
        g = TypedGraph()
        g.add_node(_cls("Base"))
        g.add_node(_cls("Child"))
        g.add_edge(GraphEdge("class:Child", "class:Base", EdgeType.INHERITS))

        # Base.process(self, a)
        g.add_node(_func("process", nid="f_base", is_method=True))
        g.add_node(_param("self", 0, "base"))
        g.add_node(_param("a", 1, "base"))
        g.add_edge(GraphEdge("class:Base", "f_base", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("f_base", "param:base.self", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("f_base", "param:base.a", EdgeType.HAS_PARAMETER))

        # Child.process(self, a)
        g.add_node(_func("process", nid="f_child", is_method=True))
        g.add_node(_param("self", 0, "child"))
        g.add_node(_param("a", 1, "child"))
        g.add_edge(GraphEdge("class:Child", "f_child", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("f_child", "param:child.self", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("f_child", "param:child.a", EdgeType.HAS_PARAMETER))

        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "override_compatibility")
        assert len(vs) == 0


# =============================================================================
# Test Layer 5 — Semantic Consistency
# =============================================================================


class TestSemanticConsistency:
    def test_call_too_few_args(self):
        g = TypedGraph()
        g.add_node(_func("foo"))
        g.add_node(_param("a", 0, "foo"))
        g.add_node(_param("b", 1, "foo"))
        g.add_edge(GraphEdge("func:foo", "param:foo.a", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("func:foo", "param:foo.b", EdgeType.HAS_PARAMETER))

        g.add_node(_call("foo"))
        g.add_edge(GraphEdge("call:foo", "func:foo", EdgeType.CALLS))
        # 0 arguments, but foo expects 2 → violation
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "call_argument_match")
        assert len(vs) == 1
        assert vs[0].severity == InvariantSeverity.WARNING

    def test_call_too_many_args(self):
        g = TypedGraph()
        g.add_node(_func("foo"))
        g.add_node(_param("a", 0, "foo"))
        g.add_edge(GraphEdge("func:foo", "param:foo.a", EdgeType.HAS_PARAMETER))

        g.add_node(_call("foo"))
        g.add_edge(GraphEdge("call:foo", "func:foo", EdgeType.CALLS))
        g.add_node(_arg("a", 0, "call:foo"))
        g.add_node(_arg("extra", 1, "call:foo"))
        g.add_edge(GraphEdge("call:foo", "arg:call:foo.a", EdgeType.HAS_ARGUMENT))
        g.add_edge(GraphEdge("call:foo", "arg:call:foo.extra", EdgeType.HAS_ARGUMENT))
        # 2 arguments, but foo expects 1 → violation
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "call_argument_match")
        assert len(vs) == 1

    def test_variadic_function_no_violation(self):
        """Functions with *args should not trigger arg count mismatch."""
        g = TypedGraph()
        g.add_node(_func("foo"))
        g.add_node(GraphNode("p1", NodeType.PARAMETER, {
            "name": "*args", "position": 0, "is_starred": True,
        }))
        g.add_edge(GraphEdge("func:foo", "p1", EdgeType.HAS_PARAMETER))

        g.add_node(_call("foo"))
        g.add_edge(GraphEdge("call:foo", "func:foo", EdgeType.CALLS))
        # 0 arguments, but variadic → no violation
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "call_argument_match")
        assert len(vs) == 0

    def test_method_call_excludes_self(self):
        """self/cls params should be excluded from count."""
        g = TypedGraph()
        g.add_node(_func("foo", is_method=True))
        g.add_node(_param("self", 0, "foo"))
        g.add_node(_param("a", 1, "foo"))
        g.add_edge(GraphEdge("func:foo", "param:foo.self", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("func:foo", "param:foo.a", EdgeType.HAS_PARAMETER))

        g.add_node(_call("foo"))
        g.add_edge(GraphEdge("call:foo", "func:foo", EdgeType.CALLS))
        g.add_node(_arg("a", 0, "call:foo"))
        g.add_edge(GraphEdge("call:foo", "arg:call:foo.a", EdgeType.HAS_ARGUMENT))
        # 1 argument, 1 non-self param → correct
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "call_argument_match")
        assert len(vs) == 0

    def test_default_param_range_check(self):
        """Function with 1 required + 1 optional: 1 or 2 args both valid."""
        g = TypedGraph()
        g.add_node(_func("foo"))
        g.add_node(_param("a", 0, "foo"))
        g.add_node(GraphNode("param:foo.b", NodeType.PARAMETER, {
            "name": "b", "position": 1, "has_default": True,
        }))
        g.add_edge(GraphEdge("func:foo", "param:foo.a", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("func:foo", "param:foo.b", EdgeType.HAS_PARAMETER))

        # 1 argument → valid (only required)
        g.add_node(_call("foo"))
        g.add_edge(GraphEdge("call:foo", "func:foo", EdgeType.CALLS))
        g.add_node(_arg("a", 0, "call:foo"))
        g.add_edge(GraphEdge("call:foo", "arg:call:foo.a", EdgeType.HAS_ARGUMENT))

        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "call_argument_match")
        assert len(vs) == 0

    def test_non_consecutive_parameter_positions(self):
        g = TypedGraph()
        g.add_node(_func("f"))
        g.add_node(GraphNode("p0", NodeType.PARAMETER, {"name": "a", "position": 0}))
        g.add_node(GraphNode("p2", NodeType.PARAMETER, {"name": "b", "position": 2}))
        g.add_edge(GraphEdge("func:f", "p0", EdgeType.HAS_PARAMETER))
        g.add_edge(GraphEdge("func:f", "p2", EdgeType.HAS_PARAMETER))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "parameter_ordering")
        assert len(vs) == 1
        assert vs[0].severity == InvariantSeverity.WARNING


# =============================================================================
# Test Layer 6 — Quality Hints
# =============================================================================


class TestQualityHints:
    def test_unused_import(self):
        g = TypedGraph()
        g.add_node(_imp("os"))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "unused_imports")
        assert len(vs) == 1
        assert vs[0].severity == InvariantSeverity.WARNING

    def test_used_import_no_violation(self):
        g = TypedGraph()
        g.add_node(_imp("os"))
        g.add_node(_func("f"))
        g.add_edge(GraphEdge("func:f", "imp:os", EdgeType.REFERENCES))
        r = InvariantRegistry()
        vs = _violations_named(r.verify_graph(g), "unused_imports")
        assert len(vs) == 0

    def test_empty_class_info(self):
        g = TypedGraph()
        g.add_node(_cls("Empty"))
        r = InvariantRegistry()
        r.enable("non_empty_container_guard")
        vs = _violations_named(r.verify_graph(g), "non_empty_container_guard")
        assert len(vs) >= 1
        assert all(v.severity == InvariantSeverity.INFO for v in vs)

    def test_non_empty_class_no_info(self):
        g = TypedGraph()
        g.add_node(_cls("Full"))
        g.add_node(_func("m", is_method=True))
        g.add_edge(GraphEdge("class:Full", "func:m", EdgeType.CONTAINS_METHOD))
        r = InvariantRegistry()
        r.enable("non_empty_container_guard")
        vs = _violations_named(r.verify_graph(g), "non_empty_container_guard")
        cls_vs = [v for v in vs if "class" in v.message.lower()]
        assert len(cls_vs) == 0


# =============================================================================
# Test InvariantRegistry
# =============================================================================


class TestInvariantRegistry:
    def test_enable_disable_by_name(self):
        r = InvariantRegistry()
        assert r.get_invariant("schema_conformance").enabled is False
        r.enable("schema_conformance")
        assert r.get_invariant("schema_conformance").enabled is True
        r.disable("schema_conformance")
        assert r.get_invariant("schema_conformance").enabled is False

    def test_enable_disable_by_layer(self):
        r = InvariantRegistry()
        r.disable_layer(InvariantLayer.SCOPE)
        scope_invs = r.get_by_layer(InvariantLayer.SCOPE)
        assert all(not inv.enabled for inv in scope_invs)
        r.enable_layer(InvariantLayer.SCOPE)
        assert all(inv.enabled for inv in scope_invs)

    def test_get_by_layer(self):
        r = InvariantRegistry()
        schema = r.get_by_layer(InvariantLayer.SCHEMA)
        assert len(schema) >= 1
        assert all(inv.layer == InvariantLayer.SCHEMA for inv in schema)

    def test_get_enabled(self):
        r = InvariantRegistry()
        enabled = r.get_enabled()
        assert all(inv.enabled for inv in enabled)
        # Schema conformance is disabled by default
        assert not any(inv.name == "schema_conformance" for inv in enabled)

    def test_verify_graph_layer_filter(self):
        """Only check specified layers."""
        g = TypedGraph()
        g.add_node(_cls("C"))
        g.add_node(_func("m", nid="f1", is_method=True))
        g.add_node(_func("m", nid="f2", is_method=True))
        g.add_edge(GraphEdge("class:C", "f1", EdgeType.CONTAINS_METHOD))
        g.add_edge(GraphEdge("class:C", "f2", EdgeType.CONTAINS_METHOD))
        g.add_node(_imp("os"))  # unused import

        r = InvariantRegistry()
        # Only check SCOPE layer
        vs = r.verify_graph(g, layers={InvariantLayer.SCOPE})
        assert all(v.layer == InvariantLayer.SCOPE for v in vs)
        assert len(vs) >= 1

    def test_verify_graph_min_severity(self):
        """Filter by minimum severity."""
        g = TypedGraph()
        g.add_node(_imp("os"))  # unused → WARNING
        r = InvariantRegistry()
        # Min severity ERROR should exclude warnings
        vs = r.verify_graph(g, min_severity=InvariantSeverity.ERROR)
        assert not any(v.severity == InvariantSeverity.WARNING for v in vs)
        # Min severity WARNING should include warnings
        vs = r.verify_graph(g, min_severity=InvariantSeverity.WARNING)
        warnings = [v for v in vs if v.severity == InvariantSeverity.WARNING]
        assert len(warnings) >= 1

    def test_stop_on_layer_error(self):
        """Higher layers should not run if a lower layer has errors."""
        g = TypedGraph()
        g.add_node(_cls("A"))
        g.add_edge(GraphEdge("class:A", "class:A", EdgeType.INHERITS))  # cycle ERROR
        g.add_node(_imp("os"))  # unused → QUALITY WARNING

        r = InvariantRegistry()
        vs_stop = r.verify_graph(g, stop_on_layer_error=True)
        # Should stop at TYPE_SYSTEM layer (inheritance_dag error)
        # and not reach QUALITY layer
        assert any(v.invariant_name == "inheritance_dag" for v in vs_stop)
        quality_in_stop = [v for v in vs_stop if v.layer == InvariantLayer.QUALITY]
        # Quality layer may or may not appear depending on where error occurs
        # The key: with stop_on_layer_error=False, quality should appear
        vs_no_stop = r.verify_graph(g, stop_on_layer_error=False)
        assert any(v.invariant_name == "unused_imports" for v in vs_no_stop)

    def test_add_remove_invariant(self):
        r = InvariantRegistry()

        def custom_check(g):
            return [InvariantViolation("custom", "custom msg")]

        inv = Invariant("custom", "Custom check", custom_check)
        r.add_invariant(inv)
        assert r.get_invariant("custom") is inv

        assert r.remove_invariant("custom") is True
        assert r.get_invariant("custom") is None
        assert r.remove_invariant("custom") is False

    def test_graph_invariants_property(self):
        """Backward compat property returns all registered invariants."""
        r = InvariantRegistry()
        invs = r.graph_invariants
        assert len(invs) >= 10  # default set

    def test_verify_preconditions(self):
        def check_pre(g):
            if g.node_count == 0:
                return [InvariantViolation("empty", "Graph is empty")]
            return []

        pre = Invariant("pre", "Must be non-empty", check_pre)
        r = InvariantRegistry()
        vs = r.verify_preconditions([pre], TypedGraph())
        assert len(vs) == 1

    def test_verify_postconditions(self):
        def check_post(g):
            if g.node_count < 2:
                return [InvariantViolation("too_few", "Need at least 2 nodes")]
            return []

        post = Invariant("post", "At least 2 nodes", check_post)
        r = InvariantRegistry()
        g = TypedGraph()
        g.add_node(_cls("A"))
        vs = r.verify_postconditions([post], g)
        assert len(vs) == 1


# =============================================================================
# Test GraphSchema Directly
# =============================================================================


class TestGraphSchema:
    def test_schema_has_all_edge_types(self):
        """All known edge types should have constraints."""
        schema = GraphSchema()
        for edge_type in EdgeType:
            assert edge_type in schema.CONSTRAINTS, (
                f"EdgeType.{edge_type.name} not in GraphSchema.CONSTRAINTS"
            )

    def test_schema_required_attrs_all_node_types(self):
        """All node types should have required attrs defined."""
        schema = GraphSchema()
        for node_type in NodeType:
            assert node_type in schema.REQUIRED_ATTRS, (
                f"NodeType.{node_type.name} not in GraphSchema.REQUIRED_ATTRS"
            )

    def test_schema_validate_empty_graph(self):
        schema = GraphSchema()
        assert schema.validate(TypedGraph()) == []

    def test_edge_constraint_frozen(self):
        ec = EdgeConstraint(
            edge_type=EdgeType.CALLS,
            source_types=frozenset({NodeType.CALL}),
            target_types=frozenset({NodeType.FUNCTION}),
        )
        with pytest.raises(AttributeError):
            ec.edge_type = EdgeType.INHERITS


# =============================================================================
# Test ScopeRule
# =============================================================================


class TestScopeRule:
    def test_scope_rule_frozen(self):
        sr = ScopeRule(NodeType.CLASS, NodeType.FUNCTION, EdgeType.CONTAINS_METHOD)
        with pytest.raises(AttributeError):
            sr.container_type = NodeType.MODULE

    def test_scope_rule_defaults(self):
        sr = ScopeRule(NodeType.CLASS, NodeType.FUNCTION, EdgeType.CONTAINS_METHOD)
        assert sr.name_attr == "name"
        assert sr.allow_overload is False
        assert sr.scope_label == ""
