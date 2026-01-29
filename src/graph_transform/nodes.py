"""
Extended Node Types

Additional code graph node types beyond FunctionNode/CallNode:
ClassNode, FieldNode, ImportNode, ModuleNode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# ClassNode
# =============================================================================


@dataclass
class ClassNode:
    """A class definition in the code graph."""

    name: str
    file: str
    line: int
    end_line: int | None = None
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    is_abstract: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "bases": self.bases,
            "methods": self.methods,
            "fields": self.fields,
            "is_abstract": self.is_abstract,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClassNode:
        return cls(
            name=data["name"],
            file=data["file"],
            line=data["line"],
            end_line=data.get("end_line"),
            bases=data.get("bases", []),
            methods=data.get("methods", []),
            fields=data.get("fields", []),
            is_abstract=data.get("is_abstract", False),
        )


# =============================================================================
# FieldNode
# =============================================================================


@dataclass
class FieldNode:
    """A field/attribute in a class."""

    name: str
    file: str
    line: int
    class_name: str | None = None
    field_type: str | None = None
    has_default: bool = False
    default_value: str | None = None
    is_class_var: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "class_name": self.class_name,
            "field_type": self.field_type,
            "has_default": self.has_default,
            "default_value": self.default_value,
            "is_class_var": self.is_class_var,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldNode:
        return cls(
            name=data["name"],
            file=data["file"],
            line=data["line"],
            class_name=data.get("class_name"),
            field_type=data.get("field_type"),
            has_default=data.get("has_default", False),
            default_value=data.get("default_value"),
            is_class_var=data.get("is_class_var", False),
        )


# =============================================================================
# ImportNode
# =============================================================================


@dataclass
class ImportNode:
    """An import statement in the code graph."""

    module: str
    name: str | None = None
    alias: str | None = None
    file: str = ""
    line: int = 0
    is_from_import: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "name": self.name,
            "alias": self.alias,
            "file": self.file,
            "line": self.line,
            "is_from_import": self.is_from_import,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportNode:
        return cls(
            module=data["module"],
            name=data.get("name"),
            alias=data.get("alias"),
            file=data.get("file", ""),
            line=data.get("line", 0),
            is_from_import=data.get("is_from_import", False),
        )


# =============================================================================
# ModuleNode
# =============================================================================


@dataclass
class ModuleNode:
    """A module/file in the code graph."""

    name: str
    file: str
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "functions": self.functions,
            "classes": self.classes,
            "imports": self.imports,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModuleNode:
        return cls(
            name=data["name"],
            file=data["file"],
            functions=data.get("functions", []),
            classes=data.get("classes", []),
            imports=data.get("imports", []),
        )
