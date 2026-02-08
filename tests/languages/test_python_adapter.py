"""Tests for PythonAdapter."""

import pytest

from graph_transform.languages import PythonAdapter, EditInstruction
from graph_transform.core.typed_graph import NodeType


class TestPythonParser:
    """Tests for Python parsing."""

    def test_parse_simple_function(self):
        """Should parse a simple function definition."""
        adapter = PythonAdapter()
        source = """
def hello():
    pass
"""
        graph = adapter.parse(source, "test.py")

        # Should have module node
        assert graph.has_node("module:test")

        # Should have function node
        assert graph.has_node("func:hello")
        func_node = graph.nodes["func:hello"]
        assert func_node.node_type == NodeType.FUNCTION
        assert func_node.attrs["name"] == "hello"

    def test_parse_class_with_method(self):
        """Should parse a class with method."""
        adapter = PythonAdapter()
        source = """
class MyClass:
    def my_method(self):
        pass
"""
        graph = adapter.parse(source, "test.py")

        assert graph.has_node("class:MyClass")
        assert graph.has_node("func:MyClass.my_method")

        # Check the method has parameter 'self'
        assert graph.has_node("param:MyClass.my_method.self")

    def test_parse_class_field(self):
        """Should parse class fields."""
        adapter = PythonAdapter()
        source = """
class Config:
    timeout: int = 30
    host: str = "localhost"
"""
        graph = adapter.parse(source, "test.py")

        assert graph.has_node("class:Config")
        assert graph.has_node("field:Config.timeout")
        assert graph.has_node("field:Config.host")

        timeout_node = graph.nodes["field:Config.timeout"]
        assert timeout_node.attrs["field_type"] == "int"
        assert timeout_node.attrs["default_value"] == "30"

    def test_parse_inheritance(self):
        """Should parse class inheritance."""
        adapter = PythonAdapter()
        source = """
class Base:
    pass

class Child(Base):
    pass
"""
        graph = adapter.parse(source, "test.py")

        assert graph.has_node("class:Base")
        assert graph.has_node("class:Child")

        # Check inheritance edge
        found = False
        for edge in graph.edges:
            if edge.source == "class:Child" and edge.target == "class:Base":
                found = True
                break
        assert found, "Inheritance edge not found"

    def test_parse_async_function(self):
        """Should parse async function."""
        adapter = PythonAdapter()
        source = """
async def fetch_data():
    pass
"""
        graph = adapter.parse(source, "test.py")

        assert graph.has_node("func:fetch_data")
        func_node = graph.nodes["func:fetch_data"]
        assert func_node.attrs["is_async"] is True

    def test_parse_import(self):
        """Should parse import statements."""
        adapter = PythonAdapter()
        source = """
import os
from pathlib import Path
"""
        graph = adapter.parse(source, "test.py")

        # Check for import nodes
        import_nodes = [
            n for n in graph.nodes.values()
            if n.node_type == NodeType.IMPORT
        ]
        assert len(import_nodes) == 2

    def test_parse_file(self, tmp_path):
        """Should parse a Python file."""
        adapter = PythonAdapter()

        source_file = tmp_path / "module.py"
        source_file.write_text("def greet(name): pass")

        graph = adapter.parse_file(source_file)

        assert graph.has_node("func:greet")
        assert graph.has_node("param:greet.name")

    def test_parse_file_not_found(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        adapter = PythonAdapter()

        with pytest.raises(FileNotFoundError):
            adapter.parse_file(tmp_path / "nonexistent.py")

    def test_parse_syntax_error(self):
        """Should raise SyntaxError for invalid Python."""
        adapter = PythonAdapter()

        with pytest.raises(SyntaxError):
            adapter.parse("def broken(", "test.py")


class TestPythonEmitter:
    """Tests for Python code emission."""

    def test_emit_simple_graph(self):
        """Should emit basic Python code from graph."""
        adapter = PythonAdapter()
        source = "def hello(): pass\n"
        graph = adapter.parse(source, "test.py")

        emitted = adapter.emit(graph)
        assert "def hello" in emitted

    def test_apply_edit_rename(self):
        """Should apply rename edit."""
        adapter = PythonAdapter()
        source = """
def old_name():
    pass

old_name()
"""
        edit = EditInstruction(
            edit_type="rename",
            file="test.py",
            line=None,
            details={
                "target": "func:old_name",
                "new_name": "new_name",
            },
        )

        result = adapter.apply_edit(source, edit)

        assert "new_name" in result
        assert "old_name" not in result

    def test_apply_edit_add_function(self):
        """Should add a new function."""
        adapter = PythonAdapter()
        source = "# existing code\n"

        edit = EditInstruction(
            edit_type="add_callable",
            file="test.py",
            line=None,
            details={"name": "new_function"},
        )

        result = adapter.apply_edit(source, edit)

        assert "def new_function" in result

    def test_apply_edit_add_class(self):
        """Should add a new class."""
        adapter = PythonAdapter()
        source = "# existing code\n"

        edit = EditInstruction(
            edit_type="add_class",
            file="test.py",
            line=None,
            details={"name": "NewClass"},
        )

        result = adapter.apply_edit(source, edit)

        assert "class NewClass" in result

    def test_apply_edits_multiple(self):
        """Should apply multiple edits."""
        adapter = PythonAdapter()
        source = """
def foo():
    pass

def bar():
    pass
"""
        edits = [
            EditInstruction(
                edit_type="rename",
                file="test.py",
                line=None,
                details={"target": "func:foo", "new_name": "foo_renamed"},
            ),
            EditInstruction(
                edit_type="rename",
                file="test.py",
                line=None,
                details={"target": "func:bar", "new_name": "bar_renamed"},
            ),
        ]

        result = adapter.apply_edits(source, edits)

        assert "foo_renamed" in result
        assert "bar_renamed" in result
        assert "def foo(" not in result
        assert "def bar(" not in result


class TestPythonAdapterProperties:
    """Tests for adapter properties."""

    def test_name(self):
        """Should return 'python'."""
        adapter = PythonAdapter()
        assert adapter.name == "python"

    def test_extensions(self):
        """Should return Python extensions."""
        adapter = PythonAdapter()
        assert ".py" in adapter.extensions
        assert ".pyw" in adapter.extensions
