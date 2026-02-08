"""
Language Mappings

Defines type mappings, naming conventions, and transformation rules
for cross-language migration. Used by migration compositions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class NamingConvention(Enum):
    """Naming conventions for identifiers."""

    SNAKE_CASE = "snake_case"      # python_style
    CAMEL_CASE = "camelCase"       # javaStyle
    PASCAL_CASE = "PascalCase"     # CSharpStyle
    KEBAB_CASE = "kebab-case"      # lisp-style
    SCREAMING_SNAKE = "SCREAMING_SNAKE_CASE"  # CONSTANT_STYLE


def to_snake_case(name: str) -> str:
    """Convert any naming convention to snake_case."""
    # Handle camelCase and PascalCase
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    # Handle kebab-case
    s3 = s2.replace('-', '_')
    return s3.lower()


def to_camel_case(name: str) -> str:
    """Convert any naming convention to camelCase."""
    snake = to_snake_case(name)
    components = snake.split('_')
    return components[0].lower() + ''.join(x.title() for x in components[1:])


def to_pascal_case(name: str) -> str:
    """Convert any naming convention to PascalCase."""
    snake = to_snake_case(name)
    return ''.join(x.title() for x in snake.split('_'))


def to_kebab_case(name: str) -> str:
    """Convert any naming convention to kebab-case."""
    return to_snake_case(name).replace('_', '-')


def to_screaming_snake(name: str) -> str:
    """Convert any naming convention to SCREAMING_SNAKE_CASE."""
    return to_snake_case(name).upper()


# Conversion functions by convention
NAMING_CONVERTERS: dict[NamingConvention, Callable[[str], str]] = {
    NamingConvention.SNAKE_CASE: to_snake_case,
    NamingConvention.CAMEL_CASE: to_camel_case,
    NamingConvention.PASCAL_CASE: to_pascal_case,
    NamingConvention.KEBAB_CASE: to_kebab_case,
    NamingConvention.SCREAMING_SNAKE: to_screaming_snake,
}


@dataclass
class LanguageRules:
    """Rules for a specific programming language."""

    name: str

    # Naming conventions
    function_naming: NamingConvention = NamingConvention.SNAKE_CASE
    method_naming: NamingConvention = NamingConvention.SNAKE_CASE
    class_naming: NamingConvention = NamingConvention.PASCAL_CASE
    field_naming: NamingConvention = NamingConvention.SNAKE_CASE
    constant_naming: NamingConvention = NamingConvention.SCREAMING_SNAKE
    parameter_naming: NamingConvention = NamingConvention.SNAKE_CASE

    # Type mappings (source type -> this language's type)
    type_mappings: dict[str, str] = field(default_factory=dict)

    # Special rules
    self_keyword: str = "self"  # Python: self, Java/C#: this, etc.
    null_keyword: str = "None"  # Python: None, Java: null, etc.
    bool_true: str = "True"
    bool_false: str = "False"


# Pre-defined language rules
PYTHON_RULES = LanguageRules(
    name="python",
    function_naming=NamingConvention.SNAKE_CASE,
    method_naming=NamingConvention.SNAKE_CASE,
    class_naming=NamingConvention.PASCAL_CASE,
    field_naming=NamingConvention.SNAKE_CASE,
    parameter_naming=NamingConvention.SNAKE_CASE,
    constant_naming=NamingConvention.SCREAMING_SNAKE,
    type_mappings={
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "list": "list",
        "dict": "dict",
        "None": "None",
        "Any": "Any",
    },
    self_keyword="self",
    null_keyword="None",
    bool_true="True",
    bool_false="False",
)

JAVA_RULES = LanguageRules(
    name="java",
    function_naming=NamingConvention.CAMEL_CASE,
    method_naming=NamingConvention.CAMEL_CASE,
    class_naming=NamingConvention.PASCAL_CASE,
    field_naming=NamingConvention.CAMEL_CASE,
    parameter_naming=NamingConvention.CAMEL_CASE,
    constant_naming=NamingConvention.SCREAMING_SNAKE,
    type_mappings={
        "str": "String",
        "int": "int",
        "float": "double",
        "bool": "boolean",
        "list": "List<Object>",
        "dict": "Map<String, Object>",
        "None": "void",
        "Any": "Object",
        "bytes": "byte[]",
    },
    self_keyword="this",
    null_keyword="null",
    bool_true="true",
    bool_false="false",
)

TYPESCRIPT_RULES = LanguageRules(
    name="typescript",
    function_naming=NamingConvention.CAMEL_CASE,
    method_naming=NamingConvention.CAMEL_CASE,
    class_naming=NamingConvention.PASCAL_CASE,
    field_naming=NamingConvention.CAMEL_CASE,
    parameter_naming=NamingConvention.CAMEL_CASE,
    constant_naming=NamingConvention.SCREAMING_SNAKE,
    type_mappings={
        "str": "string",
        "int": "number",
        "float": "number",
        "bool": "boolean",
        "list": "Array<any>",
        "dict": "Record<string, any>",
        "None": "void",
        "Any": "any",
        "bytes": "Uint8Array",
    },
    self_keyword="this",
    null_keyword="null",
    bool_true="true",
    bool_false="false",
)

GO_RULES = LanguageRules(
    name="go",
    function_naming=NamingConvention.CAMEL_CASE,  # unexported
    method_naming=NamingConvention.CAMEL_CASE,
    class_naming=NamingConvention.PASCAL_CASE,  # exported structs
    field_naming=NamingConvention.PASCAL_CASE,  # exported fields
    parameter_naming=NamingConvention.CAMEL_CASE,
    constant_naming=NamingConvention.PASCAL_CASE,  # exported constants
    type_mappings={
        "str": "string",
        "int": "int",
        "float": "float64",
        "bool": "bool",
        "list": "[]interface{}",
        "dict": "map[string]interface{}",
        "None": "",  # Go uses multiple returns
        "Any": "interface{}",
        "bytes": "[]byte",
    },
    self_keyword="",  # Go uses receiver name
    null_keyword="nil",
    bool_true="true",
    bool_false="false",
)

CSHARP_RULES = LanguageRules(
    name="csharp",
    function_naming=NamingConvention.PASCAL_CASE,
    method_naming=NamingConvention.PASCAL_CASE,
    class_naming=NamingConvention.PASCAL_CASE,
    field_naming=NamingConvention.CAMEL_CASE,  # private: _camelCase
    parameter_naming=NamingConvention.CAMEL_CASE,
    constant_naming=NamingConvention.PASCAL_CASE,
    type_mappings={
        "str": "string",
        "int": "int",
        "float": "double",
        "bool": "bool",
        "list": "List<object>",
        "dict": "Dictionary<string, object>",
        "None": "void",
        "Any": "object",
        "bytes": "byte[]",
    },
    self_keyword="this",
    null_keyword="null",
    bool_true="true",
    bool_false="false",
)


class LanguageMappings:
    """Registry for language transformation rules."""

    _rules: dict[str, LanguageRules] = {}

    @classmethod
    def register(cls, rules: LanguageRules) -> None:
        """Register language rules."""
        cls._rules[rules.name.lower()] = rules

    @classmethod
    def get(cls, language: str) -> LanguageRules:
        """Get rules for a language."""
        lang = language.lower()
        if lang not in cls._rules:
            available = ", ".join(sorted(cls._rules.keys()))
            raise KeyError(f"Unknown language: '{language}'. Available: {available}")
        return cls._rules[lang]

    @classmethod
    def is_registered(cls, language: str) -> bool:
        """Check if language rules are registered."""
        return language.lower() in cls._rules

    @classmethod
    def supported_languages(cls) -> list[str]:
        """List registered languages."""
        return sorted(cls._rules.keys())

    @classmethod
    def convert_name(
        cls,
        name: str,
        target_language: str,
        name_type: str = "function",
    ) -> str:
        """Convert a name to target language convention.

        Args:
            name: The identifier name to convert
            target_language: Target language (e.g., 'java', 'python')
            name_type: One of 'function', 'method', 'class', 'field', 'constant', 'parameter'

        Returns:
            Converted name following target language conventions
        """
        rules = cls.get(target_language)

        convention_map = {
            "function": rules.function_naming,
            "method": rules.method_naming,
            "class": rules.class_naming,
            "field": rules.field_naming,
            "constant": rules.constant_naming,
            "parameter": rules.parameter_naming,
        }

        convention = convention_map.get(name_type, rules.function_naming)
        converter = NAMING_CONVERTERS[convention]
        return converter(name)

    @classmethod
    def convert_type(
        cls,
        source_type: str,
        target_language: str,
    ) -> str:
        """Convert a type annotation to target language.

        Args:
            source_type: The source type (e.g., 'str', 'list[int]')
            target_language: Target language

        Returns:
            Equivalent type in target language
        """
        rules = cls.get(target_language)

        # Handle None/null
        if source_type is None:
            return rules.type_mappings.get("None", "void")

        source_lower = source_type.lower().strip()

        # Direct mapping
        if source_lower in rules.type_mappings:
            return rules.type_mappings[source_lower]

        # Handle generic types like list[str], dict[str, int]
        # list[X] -> List<X> for Java, Array<X> for TypeScript, etc.
        import re

        list_match = re.match(r'list\[(\w+)\]', source_lower)
        if list_match:
            inner = list_match.group(1)
            inner_mapped = rules.type_mappings.get(inner, inner.title())
            base = rules.type_mappings.get("list", "List<Object>")
            # Replace Object/any with actual type
            return re.sub(r'<[^>]+>|\[\]|<any>', f'<{inner_mapped}>', base)

        dict_match = re.match(r'dict\[(\w+),\s*(\w+)\]', source_lower)
        if dict_match:
            key = rules.type_mappings.get(dict_match.group(1), dict_match.group(1).title())
            val = rules.type_mappings.get(dict_match.group(2), dict_match.group(2).title())
            base = rules.type_mappings.get("dict", "Map<String, Object>")
            return re.sub(r'<[^>]+>', f'<{key}, {val}>', base)

        # Return as-is if no mapping found
        return source_type


# Register built-in language rules
def _register_builtin_rules() -> None:
    LanguageMappings.register(PYTHON_RULES)
    LanguageMappings.register(JAVA_RULES)
    LanguageMappings.register(TYPESCRIPT_RULES)
    LanguageMappings.register(GO_RULES)
    LanguageMappings.register(CSHARP_RULES)


_register_builtin_rules()


__all__ = [
    "NamingConvention",
    "LanguageRules",
    "LanguageMappings",
    "to_snake_case",
    "to_camel_case",
    "to_pascal_case",
    "to_kebab_case",
    "to_screaming_snake",
    "PYTHON_RULES",
    "JAVA_RULES",
    "TYPESCRIPT_RULES",
    "GO_RULES",
    "CSHARP_RULES",
]
