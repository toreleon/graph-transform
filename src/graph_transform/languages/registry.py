"""
Language Registry

Central registry for language adapters with auto-detection from file extensions.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import LanguageAdapter


class LanguageRegistry:
    """Registry for language adapters with auto-detection.

    This singleton-like class provides central registration and lookup
    of language adapters. It supports:

    1. Registration of language adapters
    2. Lookup by language name
    3. Auto-detection from file extensions

    Usage:
        # Register an adapter
        LanguageRegistry.register(PythonAdapter())

        # Get by name
        adapter = LanguageRegistry.get("python")

        # Auto-detect from file
        adapter = LanguageRegistry.detect("src/main.py")  # Returns Python adapter
        adapter = LanguageRegistry.detect("Main.java")    # Returns Java adapter

        # List supported languages
        languages = LanguageRegistry.supported_languages()
    """

    _adapters: dict[str, LanguageAdapter] = {}
    _extension_map: dict[str, str] = {}

    @classmethod
    def register(cls, adapter: LanguageAdapter) -> None:
        """Register a language adapter.

        Args:
            adapter: The language adapter to register.

        Note:
            Registering an adapter with the same name will replace
            the previous registration.
        """
        cls._adapters[adapter.name] = adapter
        for ext in adapter.extensions:
            cls._extension_map[ext.lower()] = adapter.name

    @classmethod
    def unregister(cls, language: str) -> bool:
        """Unregister a language adapter.

        Args:
            language: The language name to unregister.

        Returns:
            True if the adapter was found and removed, False otherwise.
        """
        if language not in cls._adapters:
            return False

        adapter = cls._adapters[language]
        del cls._adapters[language]

        # Remove extension mappings
        for ext in adapter.extensions:
            if cls._extension_map.get(ext.lower()) == language:
                del cls._extension_map[ext.lower()]

        return True

    @classmethod
    def get(cls, language: str) -> LanguageAdapter:
        """Get an adapter by language name.

        Args:
            language: The language name (e.g., 'python', 'java').

        Returns:
            The registered language adapter.

        Raises:
            KeyError: If no adapter is registered for the language.
        """
        if language not in cls._adapters:
            available = ", ".join(sorted(cls._adapters.keys())) or "none"
            raise KeyError(
                f"Unknown language: '{language}'. Available: {available}"
            )
        return cls._adapters[language]

    @classmethod
    def detect(cls, filename: str | Path) -> LanguageAdapter:
        """Auto-detect language from file extension.

        Args:
            filename: The filename or path to detect language from.

        Returns:
            The detected language adapter.

        Raises:
            ValueError: If the file extension is not recognized.
        """
        path = Path(filename)
        ext = path.suffix.lower()

        if not ext:
            raise ValueError(f"No file extension found: {filename}")

        if ext not in cls._extension_map:
            available = ", ".join(sorted(cls._extension_map.keys())) or "none"
            raise ValueError(
                f"Unknown file extension: '{ext}'. Supported: {available}"
            )

        language = cls._extension_map[ext]
        return cls._adapters[language]

    @classmethod
    def can_detect(cls, filename: str | Path) -> bool:
        """Check if a file's language can be detected.

        Args:
            filename: The filename or path to check.

        Returns:
            True if the file extension is recognized, False otherwise.
        """
        path = Path(filename)
        ext = path.suffix.lower()
        return ext in cls._extension_map

    @classmethod
    def supported_languages(cls) -> list[str]:
        """List all registered language names.

        Returns:
            Sorted list of registered language names.
        """
        return sorted(cls._adapters.keys())

    @classmethod
    def supported_extensions(cls) -> dict[str, str]:
        """Get mapping of extensions to language names.

        Returns:
            Dictionary mapping file extensions to language names.
        """
        return dict(cls._extension_map)

    @classmethod
    def is_registered(cls, language: str) -> bool:
        """Check if a language is registered.

        Args:
            language: The language name to check.

        Returns:
            True if the language is registered, False otherwise.
        """
        return language in cls._adapters

    @classmethod
    def clear(cls) -> None:
        """Clear all registered adapters.

        Useful for testing.
        """
        cls._adapters.clear()
        cls._extension_map.clear()
