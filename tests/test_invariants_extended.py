import pytest
from graph_transform import (
    TypedGraph, GraphNode, GraphEdge,
    NodeType, EdgeType, verify_graph_invariants,
    InvariantRegistry, InvariantViolation
)

def test_symbol_resolution():
    g = TypedGraph()
    g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": False}))

    # Positive case: valid reference
    g.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo"}))
    g.add_edge(GraphEdge("c1", "f1", EdgeType.CALLS))

    violations = verify_graph_invariants(g)
    assert not any(v.invariant_name == "reference_integrity" for v in violations)

    # Negative case: dangling reference
    g.add_edge(GraphEdge("c1", "nonexistent", EdgeType.CALLS))
    violations = verify_graph_invariants(g)
    assert any(v.invariant_name == "reference_integrity" for v in violations)

def test_no_global_name_clashes():
    g = TypedGraph()
    # Positive case: unique names
    g.add_node(GraphNode("m1", NodeType.MODULE, {"name": "mod1"}))
    g.add_node(GraphNode("m2", NodeType.MODULE, {"name": "mod2"}))
    g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "func1", "is_method": False}))
    g.add_node(GraphNode("f2", NodeType.FUNCTION, {"name": "func2", "is_method": False}))
    # Method names can clash globally
    g.add_node(GraphNode("f3", NodeType.FUNCTION, {"name": "func1", "is_method": True}))

    violations = verify_graph_invariants(g)
    assert not any(v.invariant_name == "global_scope_uniqueness" for v in violations)

    # Negative case: duplicate module name
    g.add_node(GraphNode("m3", NodeType.MODULE, {"name": "mod1"}))
    violations = verify_graph_invariants(g)
    assert any(v.invariant_name == "global_scope_uniqueness" and "module" in v.message.lower() for v in violations)

    # Negative case: duplicate global function name
    g2 = TypedGraph()
    g2.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": False}))
    g2.add_node(GraphNode("f2", NodeType.FUNCTION, {"name": "foo", "is_method": False}))
    violations = verify_graph_invariants(g2)
    assert any(v.invariant_name == "global_scope_uniqueness" and "function" in v.message.lower() for v in violations)

@pytest.mark.skip(reason="schema_conformance invariant disabled by default")
def test_node_attribute_completeness():
    g = TypedGraph()
    # Negative case: missing 'name' for CLASS
    g.add_node(GraphNode("c1", NodeType.CLASS, {}))
    registry = InvariantRegistry()
    registry.enable("schema_conformance")
    violations = registry.verify_graph(g)
    assert any(v.invariant_name == "schema_conformance" and "missing" in v.message for v in violations)

    # Positive case: attributes present
    g2 = TypedGraph()
    g2.add_node(GraphNode("c1", NodeType.CLASS, {"name": "MyClass"}))
    g2.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": False}))
    violations = registry.verify_graph(g2)
    assert not any(v.invariant_name == "schema_conformance" and "missing" in v.message for v in violations)

def test_unused_imports_warning():
    g = TypedGraph()
    g.add_node(GraphNode("imp1", NodeType.IMPORT, {"module": "os"}))

    # Initially unused
    violations = verify_graph_invariants(g)
    assert any(v.invariant_name == "unused_imports" for v in violations)

    # Now used
    g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": False}))
    g.add_edge(GraphEdge("f1", "imp1", EdgeType.REFERENCES))
    violations = verify_graph_invariants(g)
    assert not any(v.invariant_name == "unused_imports" for v in violations)

def test_call_argument_count_match():
    g = TypedGraph()
    # Function with 2 params
    g.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": False}))
    g.add_node(GraphNode("p1", NodeType.PARAMETER, {"name": "a", "position": 0}))
    g.add_node(GraphNode("p2", NodeType.PARAMETER, {"name": "b", "position": 1}))
    g.add_edge(GraphEdge("f1", "p1", EdgeType.HAS_PARAMETER))
    g.add_edge(GraphEdge("f1", "p2", EdgeType.HAS_PARAMETER))

    # Call with 2 args (Correct)
    g.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo"}))
    g.add_edge(GraphEdge("c1", "f1", EdgeType.CALLS))
    g.add_node(GraphNode("a1", NodeType.ARGUMENT, {"position": 0}))
    g.add_node(GraphNode("a2", NodeType.ARGUMENT, {"position": 1}))
    g.add_edge(GraphEdge("c1", "a1", EdgeType.HAS_ARGUMENT))
    g.add_edge(GraphEdge("c1", "a2", EdgeType.HAS_ARGUMENT))

    violations = verify_graph_invariants(g)
    assert not any(v.invariant_name == "call_argument_match" for v in violations)

    # Call with 1 arg (Incorrect)
    g2 = TypedGraph()
    g2.add_node(GraphNode("f1", NodeType.FUNCTION, {"name": "foo", "is_method": False}))
    g2.add_node(GraphNode("p1", NodeType.PARAMETER, {"name": "a", "position": 0}))
    g2.add_edge(GraphEdge("f1", "p1", EdgeType.HAS_PARAMETER))

    g2.add_node(GraphNode("c1", NodeType.CALL, {"callee": "foo"}))
    g2.add_edge(GraphEdge("c1", "f1", EdgeType.CALLS))
    # No arguments added

    violations = verify_graph_invariants(g2)
    assert any(v.invariant_name == "call_argument_match" for v in violations)
