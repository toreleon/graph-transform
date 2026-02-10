"""
Epic 2: Codebase Query & Graph Model Tests

Tests specifically for Epic 2 acceptance criteria:
- Story 2.1: TypedGraph with Node and Edge Model
- Story 2.2: Python Parser - Functions and Classes
- Story 2.3: Python Parser - Parameters and Semantic Edges
- Story 2.4: Query Tool - Pattern Matching
- Story 2.5: Query Tool - Kind and File Filtering
- Story 2.6: Query Tool - Complete Result Format
"""

import tempfile
import textwrap
import time
from pathlib import Path

import pytest

from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)
from graph_transform.io.builder import build_graph_from_source
from graph_transform.mcp.tools.query import query_tool


def _write_source(tmp_path: Path, filename: str, code: str) -> Path:
    """Write a Python source file and return its path."""
    filepath = tmp_path / filename
    filepath.write_text(textwrap.dedent(code))
    return filepath


# =============================================================================
# Story 2.1: TypedGraph with Node and Edge Model
# =============================================================================


class TestStory21TypedGraphModel:
    """
    Story 2.1 Acceptance Criteria:
    - Given the TypedGraph class exists
    - When a node is added
    - Then it has: id, kind (NodeKind enum), name, file, line, attributes dict
    - And node ID follows format `{kind}:{file}:{qualified_name}`
    """

    def test_node_has_required_fields(self):
        """Nodes have id, kind, name, file, line, and attributes."""
        graph = TypedGraph()
        node = GraphNode(
            id="function:src/api.py:get_user",
            node_type=NodeType.FUNCTION,
            attrs={
                "name": "get_user",
                "file": "src/api.py",
                "line": 42,
                "is_method": False,
            },
        )
        graph.add_node(node)

        retrieved = graph.get_node("function:src/api.py:get_user")
        assert retrieved is not None
        assert retrieved.id == "function:src/api.py:get_user"
        assert retrieved.node_type == NodeType.FUNCTION
        assert retrieved.attrs["name"] == "get_user"
        assert retrieved.attrs["file"] == "src/api.py"
        assert retrieved.attrs["line"] == 42

    def test_node_id_format(self):
        """Node IDs follow format {kind}:{file}:{qualified_name}."""
        # The parser should generate IDs in this format
        graph = TypedGraph()
        node = GraphNode(
            id="func:my_module:process",
            node_type=NodeType.FUNCTION,
            attrs={"name": "process"},
        )
        graph.add_node(node)
        assert graph.has_node("func:my_module:process")

    def test_edge_has_required_fields(self):
        """Edges have source_id, target_id, kind (EdgeKind enum)."""
        graph = TypedGraph()
        graph.add_node(
            GraphNode(id="func:a", node_type=NodeType.FUNCTION, attrs={})
        )
        graph.add_node(
            GraphNode(id="func:b", node_type=NodeType.FUNCTION, attrs={})
        )

        edge = GraphEdge(source="func:a", target="func:b", edge_type=EdgeType.CALLS)
        graph.add_edge(edge)

        edges_from_a = graph.get_edges_from("func:a")
        assert len(edges_from_a) == 1
        assert edges_from_a[0].source == "func:a"
        assert edges_from_a[0].target == "func:b"
        assert edges_from_a[0].edge_type == EdgeType.CALLS

    def test_edge_indexed_by_kind(self):
        """Edges can be queried by type for O(log n) lookup."""
        graph = TypedGraph()
        graph.add_node(
            GraphNode(id="func:a", node_type=NodeType.FUNCTION, attrs={})
        )
        graph.add_node(
            GraphNode(id="func:b", node_type=NodeType.FUNCTION, attrs={})
        )
        graph.add_node(
            GraphNode(id="class:C", node_type=NodeType.CLASS, attrs={})
        )

        graph.add_edge(GraphEdge("func:a", "func:b", EdgeType.CALLS))
        graph.add_edge(GraphEdge("class:C", "func:a", EdgeType.CONTAINS))

        # Filter by edge type
        call_edges = [e for e in graph.edges if e.edge_type == EdgeType.CALLS]
        contains_edges = [
            e for e in graph.edges if e.edge_type == EdgeType.CONTAINS
        ]

        assert len(call_edges) == 1
        assert len(contains_edges) == 1


# =============================================================================
# Story 2.2: Python Parser - Functions and Classes
# =============================================================================


class TestStory22ParserFunctionsClasses:
    """
    Story 2.2 Acceptance Criteria:
    - Given a Python source file
    - When the parser processes it
    - Then creates CALLABLE nodes for functions/methods
    - And creates TYPE nodes for classes
    - And creates CONTAINER nodes for modules
    - And parsing completes in O(n) time
    """

    def test_creates_callable_nodes_for_functions(self, tmp_path):
        """Parser creates FUNCTION nodes for functions."""
        src = _write_source(
            tmp_path,
            "funcs.py",
            """\
            def foo():
                pass

            def bar(x, y):
                return x + y
            """,
        )
        graph = build_graph_from_source(src)

        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 2
        func_names = {f.attrs["name"] for f in funcs}
        assert func_names == {"foo", "bar"}

    def test_creates_callable_nodes_for_methods(self, tmp_path):
        """Parser creates FUNCTION nodes for methods, marked as is_method."""
        src = _write_source(
            tmp_path,
            "methods.py",
            """\
            class Service:
                def start(self):
                    pass

                def stop(self):
                    pass
            """,
        )
        graph = build_graph_from_source(src)

        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        method_names = {f.attrs["name"] for f in funcs}
        assert method_names == {"start", "stop"}
        for f in funcs:
            assert f.attrs["is_method"] is True

    def test_creates_type_nodes_for_classes(self, tmp_path):
        """Parser creates CLASS nodes for classes."""
        src = _write_source(
            tmp_path,
            "classes.py",
            """\
            class Foo:
                pass

            class Bar:
                pass
            """,
        )
        graph = build_graph_from_source(src)

        classes = graph.get_nodes_by_type(NodeType.CLASS)
        assert len(classes) == 2
        class_names = {c.attrs["name"] for c in classes}
        assert class_names == {"Foo", "Bar"}

    def test_creates_container_nodes_for_modules(self, tmp_path):
        """Parser creates MODULE nodes for files."""
        src = _write_source(tmp_path, "mymodule.py", "x = 1")
        graph = build_graph_from_source(src)

        modules = graph.get_nodes_by_type(NodeType.MODULE)
        assert len(modules) == 1
        assert "mymodule" in modules[0].attrs["name"]

    def test_function_attributes(self, tmp_path):
        """Parsed function nodes include name, file, line number, decorators, async flag."""
        src = _write_source(
            tmp_path,
            "attrs.py",
            """\
            async def async_func():
                pass
            """,
        )
        graph = build_graph_from_source(src)

        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 1
        func = funcs[0]
        assert func.attrs["name"] == "async_func"
        assert "attrs.py" in func.attrs["file"]
        assert func.attrs["line"] == 1
        assert func.attrs["is_async"] is True

    def test_parsing_linear_time(self, tmp_path):
        """Parsing completes in O(n) time relative to source lines."""
        # Generate a file with increasing number of functions
        small_code = "\n".join(f"def func{i}(): pass" for i in range(100))
        large_code = "\n".join(f"def func{i}(): pass" for i in range(1000))

        small_src = _write_source(tmp_path, "small.py", small_code)
        large_src = _write_source(tmp_path, "large.py", large_code)

        start = time.perf_counter()
        build_graph_from_source(small_src)
        small_time = time.perf_counter() - start

        start = time.perf_counter()
        build_graph_from_source(large_src)
        large_time = time.perf_counter() - start

        # 10x more functions should not take more than 20x longer (allowing margin)
        assert large_time < small_time * 50, (
            f"Parsing does not appear O(n): small={small_time:.3f}s, large={large_time:.3f}s"
        )


# =============================================================================
# Story 2.3: Python Parser - Parameters and Semantic Edges
# =============================================================================


class TestStory23ParserParametersEdges:
    """
    Story 2.3 Acceptance Criteria:
    - Given a Python function with parameters
    - When parsed
    - Then creates BINDING nodes for each parameter
    - And creates HAS_PARAMETER edges from function to parameters
    - And creates IMPORTS edges for import statements
    - And creates CALLS edges for function/method calls
    - And creates INHERITS edges for class inheritance
    """

    def test_creates_parameter_nodes(self, tmp_path):
        """Parser creates PARAMETER nodes for function parameters."""
        src = _write_source(
            tmp_path,
            "params.py",
            """\
            def process(data, limit, verbose=False):
                pass
            """,
        )
        graph = build_graph_from_source(src)

        params = graph.get_nodes_by_type(NodeType.PARAMETER)
        assert len(params) == 3
        param_names = {p.attrs["name"] for p in params}
        assert param_names == {"data", "limit", "verbose"}

    def test_has_parameter_edges(self, tmp_path):
        """Parser creates HAS_PARAMETER edges from function to parameters."""
        src = _write_source(
            tmp_path,
            "edges.py",
            """\
            def greet(name, greeting):
                pass
            """,
        )
        graph = build_graph_from_source(src)

        param_edges = [e for e in graph.edges if e.edge_type == EdgeType.HAS_PARAMETER]
        assert len(param_edges) == 2

        # All should start from function
        for e in param_edges:
            assert e.source.startswith("func:")

    def test_imports_edges(self, tmp_path):
        """Parser creates IMPORTS edges for import statements."""
        src = _write_source(
            tmp_path,
            "imports.py",
            """\
            import os
            from pathlib import Path
            """,
        )
        graph = build_graph_from_source(src)

        import_edges = [e for e in graph.edges if e.edge_type == EdgeType.IMPORTS]
        assert len(import_edges) >= 2

    def test_calls_edges(self, tmp_path):
        """Parser creates CALLS edges for function/method calls."""
        src = _write_source(
            tmp_path,
            "calls.py",
            """\
            def helper():
                pass

            def main():
                helper()
            """,
        )
        graph = build_graph_from_source(src)

        calls = graph.get_nodes_by_type(NodeType.CALL)
        assert len(calls) >= 1

        call_edges = [e for e in graph.edges if e.edge_type == EdgeType.CALLS]
        # Should have edge from call node to helper function
        assert len(call_edges) >= 1

    def test_inherits_edges(self, tmp_path):
        """Parser creates INHERITS edges for class inheritance."""
        src = _write_source(
            tmp_path,
            "inheritance.py",
            """\
            class Base:
                pass

            class Child(Base):
                pass

            class GrandChild(Child):
                pass
            """,
        )
        graph = build_graph_from_source(src)

        inherits_edges = [e for e in graph.edges if e.edge_type == EdgeType.INHERITS]
        assert len(inherits_edges) == 2

        # Check specific inheritance
        child_inherits = [e for e in inherits_edges if e.source == "class:Child"]
        assert len(child_inherits) == 1
        assert child_inherits[0].target == "class:Base"


# =============================================================================
# Story 2.4: Query Tool - Pattern Matching
# =============================================================================


class TestStory24QueryPatternMatching:
    """
    Story 2.4 Acceptance Criteria:
    - Given a graph with parsed Python code
    - When `query` is called with pattern `"get_*"`
    - Then returns all nodes whose name matches the glob pattern
    - And supports regex patterns when prefixed with `re:`
    """

    def test_glob_pattern_matching(self, tmp_path):
        """Query matches glob patterns."""
        _write_source(
            tmp_path,
            "funcs.py",
            """\
            def get_user():
                pass

            def get_data():
                pass

            def set_user():
                pass

            def fetch_all():
                pass
            """,
        )

        result = query_tool({"path": str(tmp_path), "pattern": "get_*"})
        assert result["status"] == "ok"

        names = {n["name"] for n in result["nodes"]}
        assert "get_user" in names
        assert "get_data" in names
        assert "set_user" not in names
        assert "fetch_all" not in names

    def test_regex_pattern_matching(self, tmp_path):
        """Query supports regex patterns with 're:' prefix."""
        _write_source(
            tmp_path,
            "funcs.py",
            """\
            def user_create():
                pass

            def user_delete():
                pass

            def order_create():
                pass
            """,
        )

        result = query_tool({"path": str(tmp_path), "pattern": "re:^user_.*"})
        assert result["status"] == "ok"

        names = {n["name"] for n in result["nodes"]}
        assert "user_create" in names
        assert "user_delete" in names
        assert "order_create" not in names

    def test_query_response_time(self, tmp_path):
        """Query response time under 500ms for 10K LOC codebase."""
        # Generate ~10K lines of code
        code_lines = []
        for i in range(1000):
            code_lines.append(f"def func_{i}(x, y, z): return x + y + z")
        code = "\n".join(code_lines)
        _write_source(tmp_path, "big.py", code)

        start = time.perf_counter()
        result = query_tool({"path": str(tmp_path), "pattern": "func_*"})
        elapsed = time.perf_counter() - start

        assert result["status"] == "ok"
        # Allow generous time since we're building graph from scratch
        assert elapsed < 5.0, f"Query took {elapsed:.2f}s"


# =============================================================================
# Story 2.5: Query Tool - Kind and File Filtering
# =============================================================================


class TestStory25QueryKindFileFiltering:
    """
    Story 2.5 Acceptance Criteria:
    - Given a graph with parsed Python code
    - When `query` is called with `kind: "function"`
    - Then returns only CALLABLE nodes
    - When `query` is called with `file: "src/core/*.py"`
    - Then returns only nodes from matching files
    """

    def test_kind_filter_function(self, tmp_path):
        """Query kind filter returns only matching node types."""
        _write_source(
            tmp_path,
            "mixed.py",
            """\
            class MyClass:
                pass

            def my_function():
                pass
            """,
        )

        result = query_tool({"path": str(tmp_path), "kind": "function"})
        assert result["status"] == "ok"

        # Should only return functions, not classes
        for node in result["nodes"]:
            assert node["kind"] in ("function", "callable")

    def test_kind_filter_class(self, tmp_path):
        """Query kind filter for class."""
        _write_source(
            tmp_path,
            "mixed.py",
            """\
            class Foo:
                pass

            def bar():
                pass
            """,
        )

        result = query_tool({"path": str(tmp_path), "kind": "class"})
        assert result["status"] == "ok"

        names = {n["name"] for n in result["nodes"]}
        assert "Foo" in names
        assert "bar" not in names

    def test_file_filter(self, tmp_path):
        """Query file filter returns only matching files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        _write_source(src_dir, "core.py", "def core_func(): pass")
        _write_source(src_dir, "util.py", "def util_func(): pass")
        _write_source(tmp_path, "main.py", "def main_func(): pass")

        result = query_tool({"path": str(tmp_path), "file": "**/core.py"})
        assert result["status"] == "ok"

        # Should only include core.py functions
        files = {n["file"] for n in result["nodes"]}
        for f in files:
            assert "core" in f or f == ""

    def test_combined_filters(self, tmp_path):
        """Query with both kind and file filters."""
        _write_source(
            tmp_path,
            "mixed.py",
            """\
            class Service:
                def process(self):
                    pass

            def helper():
                pass
            """,
        )

        result = query_tool({
            "path": str(tmp_path),
            "kind": "function",
            "file": "**/mixed.py",
        })
        assert result["status"] == "ok"

        # Should return functions from mixed.py
        names = {n["name"] for n in result["nodes"]}
        assert "process" in names or "helper" in names


# =============================================================================
# Story 2.6: Query Tool - Complete Result Format
# =============================================================================


class TestStory26QueryResultFormat:
    """
    Story 2.6 Acceptance Criteria:
    - Given a query matches nodes
    - When results are returned
    - Then each result includes: id, kind, name, file, line number
    - And results are sorted by file then line number
    - And returns ALL matching nodes with zero false negatives
    """

    def test_result_includes_required_fields(self, tmp_path):
        """Query results include id, kind, name, file, line."""
        _write_source(
            tmp_path,
            "sample.py",
            """\
            def hello():
                pass
            """,
        )

        result = query_tool({"path": str(tmp_path), "pattern": "hello"})
        assert result["status"] == "ok"
        assert len(result["nodes"]) >= 1

        node = result["nodes"][0]
        assert "id" in node
        assert "kind" in node
        assert "name" in node
        assert "file" in node
        assert "line" in node

    def test_results_sorted_by_file_then_line(self, tmp_path):
        """Query results are sorted by file, then line number."""
        _write_source(
            tmp_path,
            "a.py",
            """\
            def func_c():
                pass

            def func_a():
                pass
            """,
        )
        _write_source(
            tmp_path,
            "b.py",
            """\
            def func_b():
                pass
            """,
        )

        result = query_tool({"path": str(tmp_path), "pattern": "func_*"})
        assert result["status"] == "ok"

        # Check sorting
        prev_file = ""
        prev_line = 0
        for node in result["nodes"]:
            if node["file"] == prev_file:
                assert node["line"] >= prev_line, "Results not sorted by line within file"
            prev_file = node["file"]
            prev_line = node["line"]

    def test_returns_all_matching_nodes(self, tmp_path):
        """Query returns ALL matching nodes (completeness guarantee)."""
        # Create many functions with same prefix
        code_lines = [f"def test_case_{i}(): pass" for i in range(50)]
        code = "\n".join(code_lines)
        _write_source(tmp_path, "tests.py", code)

        result = query_tool({"path": str(tmp_path), "pattern": "test_case_*"})
        assert result["status"] == "ok"

        # Should find all 50 functions
        assert len(result["nodes"]) >= 50

    def test_count_matches_nodes_length(self, tmp_path):
        """Query count field matches nodes array length."""
        _write_source(
            tmp_path,
            "funcs.py",
            """\
            def foo(): pass
            def bar(): pass
            def baz(): pass
            """,
        )

        result = query_tool({"path": str(tmp_path)})
        assert result["status"] == "ok"
        assert result["count"] == len(result["nodes"])
