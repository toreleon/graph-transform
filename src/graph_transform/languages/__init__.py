"""
Multi-Language Support

Provides language adapters for parsing and code generation across multiple
programming languages. The system is designed to be extensible - new languages
can be added by implementing the LanguageAdapter interface.

Currently supported languages:
- Python (.py, .pyw)

Planned languages (requires tree-sitter):
- Java (.java)
- TypeScript (.ts, .tsx)
- Go (.go)

Usage:
    from graph_transform.languages import LanguageRegistry, PythonAdapter

    # Auto-detect from file extension
    adapter = LanguageRegistry.detect("src/main.py")
    graph = adapter.parse_file("src/main.py")

    # Explicit language selection
    adapter = LanguageRegistry.get("python")
    graph = adapter.parse("def hello(): pass", "example.py")

    # List supported languages
    languages = LanguageRegistry.supported_languages()
"""

from .base import EditInstruction, LanguageAdapter
from .registry import LanguageRegistry
from .python import PythonAdapter, PythonEmitter, PythonParser
from .java import JavaAdapter, JavaEmitter


# Register built-in adapters
def _register_builtin_adapters() -> None:
    """Register all built-in language adapters."""
    LanguageRegistry.register(PythonAdapter())
    LanguageRegistry.register(JavaAdapter())


# Auto-register on module import
_register_builtin_adapters()


__all__ = [
    # Base classes
    "LanguageAdapter",
    "EditInstruction",
    "LanguageRegistry",
    # Python
    "PythonAdapter",
    "PythonParser",
    "PythonEmitter",
    # Java
    "JavaAdapter",
    "JavaEmitter",
]
