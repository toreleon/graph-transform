"""
Universal Node and Edge Kinds

Language-agnostic node and edge types that can represent code structures
from any programming language. These map to language-specific constructs
via language adapters.
"""

from __future__ import annotations

from enum import Enum


class NodeKind(Enum):
    """Universal node types for any programming language.

    These are semantic categories that exist across languages,
    not syntax-specific constructs.
    """

    # === Definitions ===
    CALLABLE = "callable"       # function, method, lambda, closure, procedure
    TYPE = "type"               # class, struct, interface, enum, trait, type alias
    BINDING = "binding"         # variable, constant, parameter, field, property
    CONTAINER = "container"     # module, package, namespace, file, crate

    # === References ===
    REFERENCE = "reference"     # import, use, require, include
    CALL = "call"               # function/method invocation
    ACCESS = "access"           # field/property/member access

    # === Control Flow ===
    BLOCK = "block"             # scope block, compound statement, body
    BRANCH = "branch"           # if, match, switch, ternary
    LOOP = "loop"               # for, while, loop, do-while

    # === Literals and Expressions ===
    LITERAL = "literal"         # string, number, boolean, null/nil/None
    EXPRESSION = "expression"   # general expression node

    # === Special ===
    ARGUMENT = "argument"       # call argument (positional or keyword)
    ANNOTATION = "annotation"   # decorator, attribute, annotation


class EdgeKind(Enum):
    """Universal edge types for code relationships.

    These represent semantic relationships that exist across languages.
    """

    # === Containment ===
    CONTAINS = "contains"           # Parent contains child (scope)
    DEFINES = "defines"             # Container defines entity

    # === References ===
    REFERENCES = "references"       # Generic reference relationship
    CALLS = "calls"                 # Call invokes callable
    ACCESSES = "accesses"           # Access reads/writes binding
    IMPORTS = "imports"             # Reference imports from container

    # === Type Relationships ===
    INHERITS = "inherits"           # Type inheritance (extends)
    IMPLEMENTS = "implements"       # Interface implementation
    TYPE_OF = "type_of"             # Entity has type

    # === Data Flow ===
    FLOWS_TO = "flows_to"           # Data flows from source to target
    DEPENDS_ON = "depends_on"       # Dependency relationship

    # === Parameters/Arguments ===
    HAS_PARAMETER = "has_parameter"  # Callable has parameter
    HAS_ARGUMENT = "has_argument"    # Call has argument
    BINDS_TO = "binds_to"            # Argument binds to parameter


# Mapping from universal kinds to existing NodeType/EdgeType
# This allows the primitives to work with the existing TypedGraph

def map_node_kind_to_node_type(kind: NodeKind) -> str:
    """Map universal NodeKind to existing NodeType value.

    Returns the string value that can be used with NodeType enum.
    """
    mapping = {
        NodeKind.CALLABLE: "function",
        NodeKind.TYPE: "class",
        NodeKind.BINDING: "field",  # or parameter depending on context
        NodeKind.CONTAINER: "module",
        NodeKind.REFERENCE: "import",
        NodeKind.CALL: "call",
        NodeKind.ARGUMENT: "argument",
    }
    return mapping.get(kind, kind.value)


def map_edge_kind_to_edge_type(kind: EdgeKind) -> str:
    """Map universal EdgeKind to existing EdgeType value.

    Returns the string value that can be used with EdgeType enum.
    """
    mapping = {
        EdgeKind.CONTAINS: "contains_method",  # or contains_field
        EdgeKind.CALLS: "calls",
        EdgeKind.INHERITS: "inherits",
        EdgeKind.IMPORTS: "imports",
        EdgeKind.DEFINES: "defined_in",
        EdgeKind.REFERENCES: "references",
        EdgeKind.HAS_PARAMETER: "has_parameter",
        EdgeKind.HAS_ARGUMENT: "has_argument",
    }
    return mapping.get(kind, kind.value)
