"""
Primitive and Composition Metadata

Static metadata for CLI help, validation, and documentation of the
three-primitive system (INSERT, DELETE, UPDATE) and compositions.
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Primitives
# =============================================================================

PRIMITIVE_TYPES = [
    "insert_node",
    "insert_edge",
    "delete_node",
    "delete_edge",
    "update",
]

PRIMITIVE_DESCRIPTIONS: dict[str, str] = {
    "insert_node": "Insert a new node into the graph (function, class, variable, etc.)",
    "insert_edge": "Insert a new edge between two nodes (containment, calls, inherits, etc.)",
    "delete_node": "Delete a node from the graph with optional cascade",
    "delete_edge": "Delete an edge between two nodes",
    "update": "Update properties of an existing node or edge",
}

PRIMITIVE_PARAMS: dict[str, dict[str, str]] = {
    "insert_node": {
        "node_id": "Unique identifier for the new node (required)",
        "node_kind": "Node kind: callable, type, binding, container, reference, call, access, block, branch, loop, literal, expression, argument, annotation (required)",
        "attrs": "JSON object of node attributes like name, file, line (optional)",
        "position": "Position specification for where to insert (optional)",
    },
    "insert_edge": {
        "source": "Source node ID (required)",
        "target": "Target node ID (required)",
        "edge_kind": "Edge kind: contains, defines, references, calls, accesses, imports, inherits, implements, type_of, flows_to, depends_on, has_parameter, has_argument, binds_to (required)",
        "attrs": "JSON object of edge attributes (optional)",
    },
    "delete_node": {
        "node_id": "ID of the node to delete (required)",
        "cascade": "If true, also delete connected edges (default: true)",
    },
    "delete_edge": {
        "source": "Source node ID (required)",
        "target": "Target node ID (required)",
        "edge_kind": "Edge kind to delete; if omitted, deletes all edges between source and target (optional)",
    },
    "update": {
        "target": "ID of the node or edge to update (required)",
        "prop": "Property name to update (use with 'value')",
        "value": "New value for the property (use with 'prop')",
        "properties": "JSON object of multiple properties to update (alternative to prop/value)",
    },
}

PRIMITIVE_EXAMPLES: dict[str, dict[str, Any]] = {
    "insert_node": {
        "node_id": "func:new_helper",
        "node_kind": "callable",
        "attrs": {"name": "new_helper", "file": "utils.py", "line": 10},
    },
    "insert_edge": {
        "source": "class:MyClass",
        "target": "func:MyClass.method",
        "edge_kind": "contains",
    },
    "delete_node": {
        "node_id": "func:old_helper",
        "cascade": True,
    },
    "delete_edge": {
        "source": "class:MyClass",
        "target": "func:MyClass.old_method",
        "edge_kind": "contains",
    },
    "update": {
        "target": "func:my_func",
        "prop": "name",
        "value": "new_name",
    },
}

# Node and edge kinds for validation
NODE_KINDS = [
    "callable",     # function, method, lambda
    "type",         # class, struct, interface
    "binding",      # variable, parameter, field
    "container",    # module, package, namespace
    "reference",    # import, use, require
    "call",         # function/method invocation
    "access",       # field/property access
    "block",        # scope block, compound statement
    "branch",       # if, match, switch
    "loop",         # for, while, loop
    "literal",      # string, number, boolean
    "expression",   # general expression
    "argument",     # call argument
    "annotation",   # decorator, attribute
]

EDGE_KINDS = [
    "contains",      # parent contains child
    "defines",       # container defines entity
    "references",    # generic reference
    "calls",         # call invokes callable
    "accesses",      # access reads/writes binding
    "imports",       # reference imports from container
    "inherits",      # type inheritance
    "implements",    # interface implementation
    "type_of",       # entity has type
    "flows_to",      # data flow
    "depends_on",    # dependency
    "has_parameter", # callable has parameter
    "has_argument",  # call has argument
    "binds_to",      # argument binds to parameter
]


# =============================================================================
# Compositions
# =============================================================================

COMPOSITION_TYPES = [
    "RENAME",
    "MOVE",
    "EXTRACT",
    "INLINE",
    "ADD_GUARD",
    "CHANGE_SIGNATURE",
    "WRAP",
    "UPDATE_IMPORT",
]

COMPOSITION_DESCRIPTIONS: dict[str, str] = {
    "RENAME": "Rename an entity and update all references",
    "MOVE": "Move an entity from one scope to another",
    "EXTRACT": "Extract code into a new entity (function, class, etc.)",
    "INLINE": "Inline an entity into its call sites",
    "ADD_GUARD": "Add a guard/check before an operation (null check, bounds check, etc.)",
    "CHANGE_SIGNATURE": "Change a callable's signature and update all call sites",
    "WRAP": "Wrap code in a construct (try/catch, with, async, etc.)",
    "UPDATE_IMPORT": "Update import statements when a symbol moves between modules",
}

COMPOSITION_PARAMS: dict[str, dict[str, str]] = {
    "RENAME": {
        "target": "Node ID to rename (required)",
        "new_name": "New name for the entity (required)",
        "update_references": "Also update all references (default: true)",
    },
    "MOVE": {
        "target": "Node ID to move (required)",
        "from_scope": "Source container ID (required)",
        "to_scope": "Target container ID (required)",
        "edge_kind": "Edge kind for containment (default: contains)",
        "update_references": "Also update references (default: true)",
    },
    "EXTRACT": {
        "new_id": "ID for the new entity (required)",
        "new_name": "Name for the new entity (required)",
        "node_kind": "Kind of entity to create: callable, type, etc. (required)",
        "scope": "Container for the new entity (required)",
        "original": "Entity being extracted from (required)",
        "replacement_value": "What replaces extracted code in original (required)",
        "attrs": "Additional attributes for the new entity (optional)",
        "position": "Position within scope (optional)",
    },
    "INLINE": {
        "target": "Node ID of entity to inline (required)",
        "remove_after": "Delete entity after inlining (default: true)",
    },
    "ADD_GUARD": {
        "target": "Where to add the guard (required)",
        "guard_type": "Type of guard: null_check, bounds_check, type_check, etc. (required)",
        "guard_condition": "Condition expression for the guard (required)",
        "guard_action": "Action on guard failure: early_return, throw, default_value (default: early_return)",
    },
    "CHANGE_SIGNATURE": {
        "target": "Callable node ID to modify (required)",
        "changes": "JSON object describing signature changes (required)",
    },
    "WRAP": {
        "target": "Node ID to wrap (required)",
        "wrapper_kind": "Kind of wrapper: try_catch, with, async, loop, etc. (required)",
        "wrapper_attrs": "Attributes for the wrapper (optional)",
    },
    "UPDATE_IMPORT": {
        "symbol": "The imported symbol name (required)",
        "old_module": "Original module path (required)",
        "new_module": "New module path (required)",
        "file": "Specific file to update (optional, updates all if omitted)",
    },
}

COMPOSITION_EXAMPLES: dict[str, dict[str, Any]] = {
    "RENAME": {
        "target": "func:old_name",
        "new_name": "new_name",
        "update_references": True,
    },
    "MOVE": {
        "target": "func:Source.method",
        "from_scope": "class:Source",
        "to_scope": "class:Target",
    },
    "EXTRACT": {
        "new_id": "func:extracted_helper",
        "new_name": "extracted_helper",
        "node_kind": "callable",
        "scope": "module:utils",
        "original": "func:process",
        "replacement_value": "extracted_helper()",
    },
    "INLINE": {
        "target": "func:small_helper",
        "remove_after": True,
    },
    "ADD_GUARD": {
        "target": "func:process",
        "guard_type": "null_check",
        "guard_condition": "x is not None",
        "guard_action": "early_return",
    },
    "CHANGE_SIGNATURE": {
        "target": "func:my_func",
        "changes": {"add_param": {"name": "logger", "default": "None"}},
    },
    "WRAP": {
        "target": "func:risky_operation",
        "wrapper_kind": "try_catch",
        "wrapper_attrs": {"catch_type": "Exception"},
    },
}


# =============================================================================
# Helpers
# =============================================================================


def resolve_primitive(name: str) -> str:
    """Resolve a primitive name to its canonical form.

    Args:
        name: Primitive name (e.g., 'insert_node', 'INSERT_NODE', 'insertNode')

    Returns:
        Canonical primitive name in lowercase with underscores

    Raises:
        ValueError: If the primitive name is not recognized
    """
    # Normalize to lowercase with underscores
    normalized = name.lower().replace("-", "_")

    if normalized in PRIMITIVE_TYPES:
        return normalized

    # Try camelCase conversion
    import re
    snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    if snake_case in PRIMITIVE_TYPES:
        return snake_case

    raise ValueError(
        f"Unknown primitive: '{name}'. "
        f"Available primitives: {', '.join(PRIMITIVE_TYPES)}"
    )


def resolve_composition(name: str) -> str:
    """Resolve a composition name to its canonical form.

    Args:
        name: Composition name (e.g., 'RENAME', 'rename', 'Rename')

    Returns:
        Canonical composition name in uppercase

    Raises:
        ValueError: If the composition name is not recognized
    """
    normalized = name.upper().replace("-", "_")

    if normalized in COMPOSITION_TYPES:
        return normalized

    raise ValueError(
        f"Unknown composition: '{name}'. "
        f"Available compositions: {', '.join(COMPOSITION_TYPES)}"
    )


def get_primitive_info(name: str) -> dict[str, Any]:
    """Get full information about a primitive.

    Returns:
        Dict with description, params, and example
    """
    canonical = resolve_primitive(name)
    return {
        "name": canonical,
        "description": PRIMITIVE_DESCRIPTIONS.get(canonical, ""),
        "params": PRIMITIVE_PARAMS.get(canonical, {}),
        "example": PRIMITIVE_EXAMPLES.get(canonical, {}),
    }


def get_composition_info(name: str) -> dict[str, Any]:
    """Get full information about a composition.

    Returns:
        Dict with description, params, and example
    """
    canonical = resolve_composition(name)
    return {
        "name": canonical,
        "description": COMPOSITION_DESCRIPTIONS.get(canonical, ""),
        "params": COMPOSITION_PARAMS.get(canonical, {}),
        "example": COMPOSITION_EXAMPLES.get(canonical, {}),
    }


def validate_node_kind(kind: str) -> bool:
    """Check if a node kind is valid."""
    return kind.lower() in NODE_KINDS


def validate_edge_kind(kind: str) -> bool:
    """Check if an edge kind is valid."""
    return kind.lower() in EDGE_KINDS
