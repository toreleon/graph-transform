"""Tests for LanguageRegistry."""

import pytest

from graph_transform.languages import LanguageRegistry, PythonAdapter
from graph_transform.languages.base import LanguageAdapter
from graph_transform.core.typed_graph import TypedGraph


class MockAdapter(LanguageAdapter):
    """Mock adapter for testing."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def extensions(self) -> list[str]:
        return [".mock", ".mk"]

    def parse(self, source: str, filename: str = "<source>") -> TypedGraph:
        return TypedGraph()

    def parse_file(self, file_path) -> TypedGraph:
        return TypedGraph()

    def emit(self, graph: TypedGraph, original_source: str | None = None) -> str:
        return ""

    def apply_edit(self, source: str, edit) -> str:
        return source


class TestLanguageRegistry:
    """Tests for LanguageRegistry."""

    def test_python_is_registered(self):
        """Python adapter should be registered by default."""
        assert LanguageRegistry.is_registered("python")
        adapter = LanguageRegistry.get("python")
        assert isinstance(adapter, PythonAdapter)

    def test_supported_languages(self):
        """Should list supported languages."""
        languages = LanguageRegistry.supported_languages()
        assert "python" in languages

    def test_supported_extensions(self):
        """Should list supported extensions."""
        extensions = LanguageRegistry.supported_extensions()
        assert ".py" in extensions
        assert extensions[".py"] == "python"

    def test_detect_python(self):
        """Should detect Python from file extension."""
        adapter = LanguageRegistry.detect("main.py")
        assert adapter.name == "python"

        adapter = LanguageRegistry.detect("script.pyw")
        assert adapter.name == "python"

    def test_detect_with_path(self):
        """Should detect from full path."""
        adapter = LanguageRegistry.detect("/home/user/project/src/main.py")
        assert adapter.name == "python"

    def test_detect_unknown_extension(self):
        """Should raise ValueError for unknown extension."""
        with pytest.raises(ValueError, match="Unknown file extension"):
            LanguageRegistry.detect("main.rs")

    def test_detect_no_extension(self):
        """Should raise ValueError for no extension."""
        with pytest.raises(ValueError, match="No file extension"):
            LanguageRegistry.detect("Makefile")

    def test_get_unknown_language(self):
        """Should raise KeyError for unknown language."""
        with pytest.raises(KeyError, match="Unknown language"):
            LanguageRegistry.get("rust")

    def test_can_detect(self):
        """Should return True for known extensions."""
        assert LanguageRegistry.can_detect("main.py")
        assert LanguageRegistry.can_detect("script.pyw")
        assert not LanguageRegistry.can_detect("main.rs")
        assert not LanguageRegistry.can_detect("Makefile")

    def test_case_insensitive_extension(self):
        """Extension matching should be case insensitive."""
        adapter = LanguageRegistry.detect("main.PY")
        assert adapter.name == "python"

        adapter = LanguageRegistry.detect("main.Py")
        assert adapter.name == "python"


class TestRegistration:
    """Tests for adapter registration."""

    def test_register_adapter(self):
        """Should register a new adapter."""
        mock = MockAdapter()
        LanguageRegistry.register(mock)

        assert LanguageRegistry.is_registered("mock")
        assert LanguageRegistry.get("mock") is mock

        # Cleanup
        LanguageRegistry.unregister("mock")

    def test_detect_registered_adapter(self):
        """Should detect registered adapter from extension."""
        mock = MockAdapter()
        LanguageRegistry.register(mock)

        adapter = LanguageRegistry.detect("file.mock")
        assert adapter.name == "mock"

        adapter = LanguageRegistry.detect("file.mk")
        assert adapter.name == "mock"

        # Cleanup
        LanguageRegistry.unregister("mock")

    def test_unregister_adapter(self):
        """Should unregister an adapter."""
        mock = MockAdapter()
        LanguageRegistry.register(mock)
        assert LanguageRegistry.is_registered("mock")

        result = LanguageRegistry.unregister("mock")
        assert result is True
        assert not LanguageRegistry.is_registered("mock")

    def test_unregister_unknown(self):
        """Unregistering unknown language returns False."""
        result = LanguageRegistry.unregister("unknown_language")
        assert result is False

    def test_register_replaces_existing(self):
        """Registering same name replaces existing adapter."""
        mock1 = MockAdapter()
        mock2 = MockAdapter()

        LanguageRegistry.register(mock1)
        LanguageRegistry.register(mock2)

        assert LanguageRegistry.get("mock") is mock2

        # Cleanup
        LanguageRegistry.unregister("mock")
