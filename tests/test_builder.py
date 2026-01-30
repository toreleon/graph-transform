"""Tests for graph_transform.builder."""

import textwrap
import tempfile
from pathlib import Path

import pytest

from graph_transform.core.typed_graph import EdgeType, NodeType
from graph_transform.io.builder import build_graph_from_source


# =============================================================================
# Fixtures
# =============================================================================


def _write_source(tmp_path: Path, filename: str, code: str) -> Path:
    """Write a Python source file and return its path."""
    filepath = tmp_path / filename
    filepath.write_text(textwrap.dedent(code))
    return filepath


# =============================================================================
# Tests: single file
# =============================================================================


class TestBuildFromFile:
    def test_simple_function(self, tmp_path):
        src = _write_source(tmp_path, "mod.py", """\
            def hello(name: str) -> str:
                return f"Hello, {name}"
        """)
        graph = build_graph_from_source(src)

        # Module node
        modules = graph.get_nodes_by_type(NodeType.MODULE)
        assert len(modules) == 1
        assert modules[0].attrs["name"] == "mod"

        # Function node
        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 1
        assert funcs[0].attrs["name"] == "hello"
        assert funcs[0].attrs["is_method"] is False

        # Parameter nodes
        params = graph.get_nodes_by_type(NodeType.PARAMETER)
        assert len(params) == 1
        assert params[0].attrs["name"] == "name"

    def test_class_with_methods(self, tmp_path):
        src = _write_source(tmp_path, "models.py", """\
            class MyClass:
                def method_a(self, x: int) -> None:
                    pass

                def method_b(self) -> str:
                    return "b"
        """)
        graph = build_graph_from_source(src)

        classes = graph.get_nodes_by_type(NodeType.CLASS)
        assert len(classes) == 1
        assert classes[0].attrs["name"] == "MyClass"

        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 2
        func_names = {f.attrs["name"] for f in funcs}
        assert func_names == {"method_a", "method_b"}

        # All methods should be marked as methods
        for f in funcs:
            assert f.attrs["is_method"] is True

        # CONTAINS_METHOD edges
        method_edges = [
            e for e in graph.edges if e.edge_type == EdgeType.CONTAINS_METHOD
        ]
        assert len(method_edges) == 2

    def test_inheritance(self, tmp_path):
        src = _write_source(tmp_path, "hierarchy.py", """\
            class Base:
                pass

            class Child(Base):
                pass
        """)
        graph = build_graph_from_source(src)

        classes = graph.get_nodes_by_type(NodeType.CLASS)
        assert len(classes) == 2

        inherits = [e for e in graph.edges if e.edge_type == EdgeType.INHERITS]
        assert len(inherits) == 1
        assert inherits[0].source == "class:Child"
        assert inherits[0].target == "class:Base"

    def test_class_fields(self, tmp_path):
        src = _write_source(tmp_path, "fields.py", """\
            class Config:
                debug: bool = True
                name: str = "default"
        """)
        graph = build_graph_from_source(src)

        fields = graph.get_nodes_by_type(NodeType.FIELD)
        assert len(fields) == 2
        field_names = {f.attrs["name"] for f in fields}
        assert field_names == {"debug", "name"}

        # Check field attributes
        for f in fields:
            assert f.attrs["is_class_var"] is True
            assert f.attrs["has_default"] is True

    def test_init_fields(self, tmp_path):
        src = _write_source(tmp_path, "init_fields.py", """\
            class Foo:
                def __init__(self, x):
                    self.x = x
                    self.y = 10
        """)
        graph = build_graph_from_source(src)

        fields = graph.get_nodes_by_type(NodeType.FIELD)
        field_names = {f.attrs["name"] for f in fields}
        assert "x" in field_names
        assert "y" in field_names

    def test_imports(self, tmp_path):
        src = _write_source(tmp_path, "imports.py", """\
            import os
            from pathlib import Path
            from typing import Any, Optional
        """)
        graph = build_graph_from_source(src)

        imports = graph.get_nodes_by_type(NodeType.IMPORT)
        assert len(imports) >= 3  # os, Path, Any, Optional
        import_names = {i.attrs.get("name") or i.attrs.get("module") for i in imports}
        assert "os" in import_names or any(
            i.attrs.get("module") == "os" for i in imports
        )

    def test_call_sites(self, tmp_path):
        src = _write_source(tmp_path, "calls.py", """\
            def greet(name):
                print(name)

            def main():
                greet("world")
        """)
        graph = build_graph_from_source(src)

        calls = graph.get_nodes_by_type(NodeType.CALL)
        assert len(calls) >= 1

    def test_async_function(self, tmp_path):
        src = _write_source(tmp_path, "async_mod.py", """\
            async def fetch(url: str) -> str:
                return ""
        """)
        graph = build_graph_from_source(src)

        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        assert len(funcs) == 1
        assert funcs[0].attrs["is_async"] is True

    def test_default_parameters(self, tmp_path):
        src = _write_source(tmp_path, "defaults.py", """\
            def process(data, verbose=False, limit=100):
                pass
        """)
        graph = build_graph_from_source(src)

        params = graph.get_nodes_by_type(NodeType.PARAMETER)
        param_map = {p.attrs["name"]: p for p in params}

        assert param_map["data"].attrs["has_default"] is False
        assert param_map["verbose"].attrs["has_default"] is True
        assert param_map["verbose"].attrs["default_value"] == "False"
        assert param_map["limit"].attrs["has_default"] is True


# =============================================================================
# Tests: directory
# =============================================================================


class TestBuildFromDirectory:
    def test_multiple_files(self, tmp_path):
        _write_source(tmp_path, "a.py", "class A: pass")
        _write_source(tmp_path, "b.py", "class B: pass")

        graph = build_graph_from_source(tmp_path)

        classes = graph.get_nodes_by_type(NodeType.CLASS)
        class_names = {c.attrs["name"] for c in classes}
        assert class_names == {"A", "B"}

        modules = graph.get_nodes_by_type(NodeType.MODULE)
        assert len(modules) == 2

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No .py files"):
            build_graph_from_source(empty)

    def test_nonexistent_path(self):
        with pytest.raises(FileNotFoundError):
            build_graph_from_source("/nonexistent/path")


# =============================================================================
# Tests: sample_repo
# =============================================================================


class TestBuildSampleRepo:
    def test_build_sample_models(self):
        """Build graph from the bundled sample_repo/models.py."""
        sample = Path(__file__).parent.parent / "src" / "graph_transform" / "examples" / "sample_repo" / "models.py"
        if not sample.exists():
            pytest.skip("sample_repo/models.py not found")

        graph = build_graph_from_source(sample)

        classes = graph.get_nodes_by_type(NodeType.CLASS)
        class_names = {c.attrs["name"] for c in classes}
        assert "BaseService" in class_names
        assert "DataService" in class_names

        funcs = graph.get_nodes_by_type(NodeType.FUNCTION)
        func_names = {f.attrs["name"] for f in funcs}
        assert "connect" in func_names
        assert "get_data" in func_names

        assert graph.node_count > 0
        assert graph.edge_count > 0
