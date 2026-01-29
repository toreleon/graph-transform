#!/usr/bin/env python3
"""
Visualize graph transformations on a sample Python repo.

Builds a TypedGraph from sample_repo/models.py, renders it as SVG,
applies operators step-by-step, and renders the result after each step.

Usage:
    python graph_transform/examples/visualize_transform.py

Outputs:
    graph_transform/examples/output/step0_initial.svg
    graph_transform/examples/output/step1_add_param.svg
    graph_transform/examples/output/step2_add_arg.svg
    graph_transform/examples/output/step3_rename_method.svg
"""

from __future__ import annotations

from pathlib import Path

from graph_transform import (
    EdgeType,
    GraphEdge,
    GraphNode,
    ModuleNode,
    NodeType,
    OperatorType,
    TypedGraph,
    create_engine,
)
from graph_transform.visualization import diff_edges, diff_nodes, render_graph


# =============================================================================
# Build sample graph
# =============================================================================


def build_sample_graph() -> TypedGraph:
    """Build a TypedGraph representing sample_repo/models.py."""
    g = TypedGraph()

    # --- Module ---
    g.add_node(GraphNode("module:models", NodeType.MODULE, {
        "name": "models", "file": "models.py",
    }))

    # --- Classes ---
    g.add_node(GraphNode("class:BaseService", NodeType.CLASS, {
        "name": "BaseService", "file": "models.py", "line": 4, "is_abstract": True,
    }))
    g.add_node(GraphNode("class:DataService", NodeType.CLASS, {
        "name": "DataService", "file": "models.py", "line": 14, "is_abstract": False,
    }))

    # Inheritance
    g.add_edge(GraphEdge("class:DataService", "class:BaseService", EdgeType.INHERITS))

    # Defined in module
    g.add_edge(GraphEdge("class:BaseService", "module:models", EdgeType.DEFINED_IN))
    g.add_edge(GraphEdge("class:DataService", "module:models", EdgeType.DEFINED_IN))

    # --- Fields ---
    g.add_node(GraphNode("field:DataService.cache_enabled", NodeType.FIELD, {
        "name": "cache_enabled", "field_type": "bool", "has_default": True,
        "default_value": "True", "is_class_var": True,
    }))
    g.add_edge(GraphEdge("class:DataService", "field:DataService.cache_enabled", EdgeType.CONTAINS_FIELD))

    # --- Methods: BaseService ---
    g.add_node(GraphNode("func:connect", NodeType.FUNCTION, {
        "name": "connect", "file": "models.py", "line": 7, "is_method": True, "is_async": False,
    }))
    g.add_node(GraphNode("param:connect.self", NodeType.PARAMETER, {
        "name": "self", "position": 0, "has_default": False,
    }))
    g.add_node(GraphNode("param:connect.host", NodeType.PARAMETER, {
        "name": "host", "position": 1, "has_default": False,
    }))
    g.add_edge(GraphEdge("class:BaseService", "func:connect", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("func:connect", "param:connect.self", EdgeType.HAS_PARAMETER))
    g.add_edge(GraphEdge("func:connect", "param:connect.host", EdgeType.HAS_PARAMETER))

    g.add_node(GraphNode("func:disconnect", NodeType.FUNCTION, {
        "name": "disconnect", "file": "models.py", "line": 10, "is_method": True, "is_async": False,
    }))
    g.add_node(GraphNode("param:disconnect.self", NodeType.PARAMETER, {
        "name": "self", "position": 0, "has_default": False,
    }))
    g.add_edge(GraphEdge("class:BaseService", "func:disconnect", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("func:disconnect", "param:disconnect.self", EdgeType.HAS_PARAMETER))

    # --- Methods: DataService ---
    g.add_node(GraphNode("func:get_data", NodeType.FUNCTION, {
        "name": "get_data", "file": "models.py", "line": 19, "is_method": True, "is_async": False,
    }))
    g.add_node(GraphNode("param:get_data.self", NodeType.PARAMETER, {
        "name": "self", "position": 0, "has_default": False,
    }))
    g.add_node(GraphNode("param:get_data.query", NodeType.PARAMETER, {
        "name": "query", "position": 1, "has_default": False,
    }))
    g.add_edge(GraphEdge("class:DataService", "func:get_data", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("func:get_data", "param:get_data.self", EdgeType.HAS_PARAMETER))
    g.add_edge(GraphEdge("func:get_data", "param:get_data.query", EdgeType.HAS_PARAMETER))

    g.add_node(GraphNode("func:process", NodeType.FUNCTION, {
        "name": "process", "file": "models.py", "line": 24, "is_method": True, "is_async": False,
    }))
    g.add_node(GraphNode("param:process.self", NodeType.PARAMETER, {
        "name": "self", "position": 0, "has_default": False,
    }))
    g.add_node(GraphNode("param:process.data", NodeType.PARAMETER, {
        "name": "data", "position": 1, "has_default": False,
    }))
    g.add_edge(GraphEdge("class:DataService", "func:process", EdgeType.CONTAINS_METHOD))
    g.add_edge(GraphEdge("func:process", "param:process.self", EdgeType.HAS_PARAMETER))
    g.add_edge(GraphEdge("func:process", "param:process.data", EdgeType.HAS_PARAMETER))

    # --- Standalone function: main ---
    g.add_node(GraphNode("func:main", NodeType.FUNCTION, {
        "name": "main", "file": "models.py", "line": 28, "is_method": False, "is_async": False,
    }))
    g.add_edge(GraphEdge("func:main", "module:models", EdgeType.DEFINED_IN))

    # --- Call sites from main() ---
    g.add_node(GraphNode("call:get_data:30", NodeType.CALL, {
        "callee": "get_data", "file": "models.py", "line": 30, "caller": "main",
    }))
    g.add_node(GraphNode("arg:get_data:30.query", NodeType.ARGUMENT, {
        "name": "query", "value": "SELECT * FROM users", "is_keyword": True,
    }))
    g.add_edge(GraphEdge("call:get_data:30", "func:get_data", EdgeType.CALLS))
    g.add_edge(GraphEdge("func:main", "call:get_data:30", EdgeType.CALLER_OF))
    g.add_edge(GraphEdge("call:get_data:30", "arg:get_data:30.query", EdgeType.HAS_ARGUMENT))

    g.add_node(GraphNode("call:process:31", NodeType.CALL, {
        "callee": "process", "file": "models.py", "line": 31, "caller": "main",
    }))
    g.add_node(GraphNode("arg:process:31.data", NodeType.ARGUMENT, {
        "name": "data", "value": "raw", "is_keyword": True,
    }))
    g.add_edge(GraphEdge("call:process:31", "func:process", EdgeType.CALLS))
    g.add_edge(GraphEdge("func:main", "call:process:31", EdgeType.CALLER_OF))
    g.add_edge(GraphEdge("call:process:31", "arg:process:31.data", EdgeType.HAS_ARGUMENT))

    g.add_node(GraphNode("call:disconnect:32", NodeType.CALL, {
        "callee": "disconnect", "file": "models.py", "line": 32, "caller": "main",
    }))
    g.add_edge(GraphEdge("call:disconnect:32", "func:disconnect", EdgeType.CALLS))
    g.add_edge(GraphEdge("func:main", "call:disconnect:32", EdgeType.CALLER_OF))

    # Internal call: get_data -> connect
    g.add_node(GraphNode("call:connect:20", NodeType.CALL, {
        "callee": "connect", "file": "models.py", "line": 20, "caller": "get_data",
    }))
    g.add_node(GraphNode("arg:connect:20.host", NodeType.ARGUMENT, {
        "name": "host", "value": "db.local", "is_keyword": False,
    }))
    g.add_edge(GraphEdge("call:connect:20", "func:connect", EdgeType.CALLS))
    g.add_edge(GraphEdge("func:get_data", "call:connect:20", EdgeType.CALLER_OF))
    g.add_edge(GraphEdge("call:connect:20", "arg:connect:20.host", EdgeType.HAS_ARGUMENT))

    return g


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    engine = create_engine(mode="dpo", check_invariants=False)
    catalog = engine.catalog

    # Step 0: Initial graph
    graph = build_sample_graph()
    print(f"Step 0  Initial graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    svg0 = render_graph(graph, "Step 0: Initial Graph", str(output_dir / "step0_initial"))
    print(f"        -> {svg0}")

    # -------------------------------------------------------------------------
    # Step 1: ADD_PARAM  —  add 'log' parameter to get_data()
    # -------------------------------------------------------------------------
    rule1 = catalog.create_rule(OperatorType.ADD_PARAM, {
        "function_name": "get_data",
        "param_name": "log",
        "default_value": "True",
    })
    result1 = engine.apply_rule(rule1, graph)
    assert result1.success, f"Step 1 failed: {result1.errors}"
    graph1 = result1.result_graph

    new_nodes_1 = diff_nodes(graph, graph1)
    new_edges_1 = diff_edges(graph, graph1)
    print(f"Step 1  ADD_PARAM get_data(log=True): +{len(new_nodes_1)} nodes, +{len(new_edges_1)} edges")
    svg1 = render_graph(
        graph1,
        "Step 1: ADD_PARAM  get_data(log=True)",
        str(output_dir / "step1_add_param"),
        highlight_nodes=new_nodes_1,
        highlight_edges=new_edges_1,
    )
    print(f"        -> {svg1}")

    # -------------------------------------------------------------------------
    # Step 2: ADD_ARG  —  add log=False argument to call site of get_data
    # -------------------------------------------------------------------------
    rule2 = catalog.create_rule(OperatorType.ADD_ARG, {
        "callee": "get_data",
        "arg_name": "log",
        "arg_value": "False",
    })
    results2 = engine.apply_all_matches(rule2, graph1)
    assert all(r.success for r in results2), f"Step 2 failed: {[r.errors for r in results2]}"
    graph2 = results2[-1].result_graph if results2 else graph1

    new_nodes_2 = diff_nodes(graph1, graph2)
    new_edges_2 = diff_edges(graph1, graph2)
    print(f"Step 2  ADD_ARG get_data(log=False) x{len(results2)}: +{len(new_nodes_2)} nodes, +{len(new_edges_2)} edges")
    svg2 = render_graph(
        graph2,
        "Step 2: ADD_ARG  get_data(log=False)",
        str(output_dir / "step2_add_arg"),
        highlight_nodes=new_nodes_2,
        highlight_edges=new_edges_2,
    )
    print(f"        -> {svg2}")

    # -------------------------------------------------------------------------
    # Step 3: RENAME_METHOD  —  rename process -> transform
    # -------------------------------------------------------------------------
    rule3 = catalog.create_rule(OperatorType.RENAME_METHOD, {
        "old_name": "process",
        "new_name": "transform",
    })
    result3 = engine.apply_rule(rule3, graph2)
    assert result3.success, f"Step 3 failed: {result3.errors}"
    graph3 = result3.result_graph

    # The rename changes an existing node's attrs — find it
    changed_nodes_3: set[str] = set()
    for nid, node in graph3.nodes.items():
        if nid in graph2.nodes:
            old_node = graph2.nodes[nid]
            if node.attrs.get("name") != old_node.attrs.get("name"):
                changed_nodes_3.add(nid)
    changed_nodes_3 |= diff_nodes(graph2, graph3)
    new_edges_3 = diff_edges(graph2, graph3)
    print(f"Step 3  RENAME_METHOD process->transform: {len(changed_nodes_3)} changed nodes")
    svg3 = render_graph(
        graph3,
        "Step 3: RENAME_METHOD  process -> transform",
        str(output_dir / "step3_rename_method"),
        highlight_nodes=changed_nodes_3,
        highlight_edges=new_edges_3,
    )
    print(f"        -> {svg3}")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print()
    print("=== Summary ===")
    print(f"Initial: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"Final:   {len(graph3.nodes)} nodes, {len(graph3.edges)} edges")
    print(f"Operators applied: 3  (ADD_PARAM, ADD_ARG, RENAME_METHOD)")
    print(f"SVGs written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
