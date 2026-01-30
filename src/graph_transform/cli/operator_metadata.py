"""
Operator Metadata

Static descriptions, parameter schemas, and examples for all 41 operators.
Used by the CLI for help text, listing, and validation.
"""

from __future__ import annotations

from graph_transform.operators.primitive_operators import OperatorType


# =============================================================================
# Descriptions (derived from enum comments in primitive_operators.py)
# =============================================================================

OPERATOR_DESCRIPTIONS: dict[OperatorType, str] = {
    # Method-level
    OperatorType.ADD_METHOD: "Add a new method to a class",
    OperatorType.REMOVE_METHOD: "Remove a method from a class",
    OperatorType.RENAME_METHOD: "Rename a method",
    OperatorType.MOVE_METHOD: "Move a method to another class",
    OperatorType.EXTRACT_METHOD: "Extract code block into a new method",
    OperatorType.INLINE_METHOD: "Inline a method (replace calls with body)",
    OperatorType.PULL_UP_METHOD: "Move a method to the superclass",
    OperatorType.PUSH_DOWN_METHOD: "Move a method to a subclass",
    OperatorType.CHANGE_SIGNATURE: "Modify a method's signature",
    # Field-level
    OperatorType.ADD_FIELD: "Add a field to a class",
    OperatorType.REMOVE_FIELD: "Remove a field from a class",
    OperatorType.RENAME_FIELD: "Rename a field",
    OperatorType.MOVE_FIELD: "Move a field to another class",
    OperatorType.PULL_UP_FIELD: "Move a field to the superclass",
    OperatorType.PUSH_DOWN_FIELD: "Move a field to a subclass",
    OperatorType.ENCAPSULATE_FIELD: "Add getter/setter methods for a field",
    # Class-level
    OperatorType.ADD_CLASS: "Create a new class",
    OperatorType.REMOVE_CLASS: "Delete a class",
    OperatorType.RENAME_CLASS: "Rename a class",
    OperatorType.MOVE_CLASS: "Move a class to another module",
    OperatorType.EXTRACT_CLASS: "Extract fields/methods into a new class",
    OperatorType.INLINE_CLASS: "Merge a class into another",
    OperatorType.EXTRACT_SUPERCLASS: "Create a superclass from common members",
    # Parameter-level
    OperatorType.ADD_PARAM: "Add a parameter to a function signature",
    OperatorType.REMOVE_PARAM: "Remove a parameter from a function signature",
    OperatorType.RENAME_PARAM: "Rename a parameter",
    OperatorType.INTRODUCE_PARAM_OBJECT: "Group parameters into an object parameter",
    # Module-level
    OperatorType.CREATE_MODULE: "Create a new module/file",
    OperatorType.DELETE_MODULE: "Delete a module/file",
    OperatorType.RENAME_MODULE: "Rename a module/file",
    OperatorType.MOVE_TO_MODULE: "Move a definition to another module",
    OperatorType.MERGE_MODULES: "Merge two modules into one",
    # Reference-level
    OperatorType.ADD_IMPORT: "Add an import statement",
    OperatorType.REMOVE_IMPORT: "Remove an import statement",
    OperatorType.UPDATE_IMPORT: "Modify an import statement",
    OperatorType.UPDATE_CALL: "Update a function call target",
    OperatorType.UPDATE_REFERENCE: "Update a code reference",
    # Call-site level
    OperatorType.ADD_ARG: "Add an argument to a call site",
    OperatorType.REMOVE_ARG: "Remove an argument from a call site",
    OperatorType.UPDATE_ARG: "Change an argument value at a call site",
    # Meta
    OperatorType.RENAME_FUNC: "Rename a function (alias for rename_method)",
}


# =============================================================================
# Parameter schemas (required + optional params for each operator)
# =============================================================================

OPERATOR_PARAMS: dict[OperatorType, dict[str, str]] = {
    # Method-level
    OperatorType.ADD_METHOD: {
        "class_name": "Target class name (required)",
        "method_name": "New method name (required)",
    },
    OperatorType.REMOVE_METHOD: {
        "class_name": "Target class name (required)",
        "method_name": "Method to remove (required)",
    },
    OperatorType.RENAME_METHOD: {
        "old_name": "Current method name (required)",
        "new_name": "New method name (required)",
    },
    OperatorType.MOVE_METHOD: {
        "method_name": "Method to move (required)",
        "source_class": "Source class name (required)",
        "target_class": "Target class name (required)",
    },
    OperatorType.EXTRACT_METHOD: {
        "source_method": "Source method name (required)",
        "new_method": "New extracted method name (required)",
    },
    OperatorType.INLINE_METHOD: {
        "method_name": "Method to inline (required)",
    },
    OperatorType.PULL_UP_METHOD: {
        "method_name": "Method to pull up (required)",
        "source_class": "Source subclass name (required)",
        "target_class": "Target superclass name (required)",
    },
    OperatorType.PUSH_DOWN_METHOD: {
        "method_name": "Method to push down (required)",
        "source_class": "Source superclass name (required)",
        "target_class": "Target subclass name (required)",
    },
    OperatorType.CHANGE_SIGNATURE: {
        "method_name": "Method name (required)",
        "new_params": "New parameter list as JSON string (required)",
    },
    # Field-level
    OperatorType.ADD_FIELD: {
        "class_name": "Target class name (required)",
        "field_name": "New field name (required)",
        "field_type": "Field type annotation (optional)",
        "default_value": "Default value (optional)",
    },
    OperatorType.REMOVE_FIELD: {
        "class_name": "Target class name (required)",
        "field_name": "Field to remove (required)",
    },
    OperatorType.RENAME_FIELD: {
        "old_name": "Current field name (required)",
        "new_name": "New field name (required)",
    },
    OperatorType.MOVE_FIELD: {
        "field_name": "Field to move (required)",
        "source_class": "Source class name (required)",
        "target_class": "Target class name (required)",
    },
    OperatorType.PULL_UP_FIELD: {
        "field_name": "Field to pull up (required)",
        "source_class": "Source subclass name (required)",
        "target_class": "Target superclass name (required)",
    },
    OperatorType.PUSH_DOWN_FIELD: {
        "field_name": "Field to push down (required)",
        "source_class": "Source superclass name (required)",
        "target_class": "Target subclass name (required)",
    },
    OperatorType.ENCAPSULATE_FIELD: {
        "class_name": "Target class name (required)",
        "field_name": "Field to encapsulate (required)",
    },
    # Class-level
    OperatorType.ADD_CLASS: {
        "class_name": "New class name (required)",
    },
    OperatorType.REMOVE_CLASS: {
        "class_name": "Class to remove (required)",
    },
    OperatorType.RENAME_CLASS: {
        "old_name": "Current class name (required)",
        "new_name": "New class name (required)",
    },
    OperatorType.MOVE_CLASS: {
        "class_name": "Class to move (required)",
        "target_module": "Target module name (required)",
    },
    OperatorType.EXTRACT_CLASS: {
        "source_class": "Source class name (required)",
        "new_class": "New class name (required)",
    },
    OperatorType.INLINE_CLASS: {
        "source_class": "Class to inline (required)",
        "target_class": "Target class (required)",
    },
    OperatorType.EXTRACT_SUPERCLASS: {
        "superclass_name": "New superclass name (required)",
    },
    # Parameter-level
    OperatorType.ADD_PARAM: {
        "function_name": "Target function name (required)",
        "param_name": "New parameter name (required)",
        "default_value": "Default value (optional)",
    },
    OperatorType.REMOVE_PARAM: {
        "function_name": "Target function name (required)",
        "param_name": "Parameter to remove (required)",
    },
    OperatorType.RENAME_PARAM: {
        "old_name": "Current parameter name (required)",
        "new_name": "New parameter name (required)",
    },
    OperatorType.INTRODUCE_PARAM_OBJECT: {
        "function_name": "Target function name (required)",
        "object_name": "Parameter object name (required)",
    },
    # Module-level
    OperatorType.CREATE_MODULE: {
        "module_name": "New module name (required)",
    },
    OperatorType.DELETE_MODULE: {
        "module_name": "Module to delete (required)",
    },
    OperatorType.RENAME_MODULE: {
        "old_name": "Current module name (required)",
        "new_name": "New module name (required)",
    },
    OperatorType.MOVE_TO_MODULE: {
        "item_name": "Item to move (required)",
        "target_module": "Target module name (required)",
        "item_type": "Item type: function or class (optional, default: function)",
    },
    OperatorType.MERGE_MODULES: {
        "source_module": "Module to merge from (required)",
        "target_module": "Module to merge into (required)",
    },
    # Reference-level
    OperatorType.ADD_IMPORT: {
        "module": "Module to import from (required)",
        "name": "Name to import (optional)",
        "alias": "Import alias (optional)",
        "is_from_import": "Use from-import style (optional, default: true)",
    },
    OperatorType.REMOVE_IMPORT: {
        "module": "Module of import to remove (required)",
        "name": "Name of import to remove (optional)",
    },
    OperatorType.UPDATE_IMPORT: {
        "old_module": "Current module path (required)",
        "new_module": "New module path (required)",
    },
    OperatorType.UPDATE_CALL: {
        "old_callee": "Current callee name (required)",
        "new_callee": "New callee name (required)",
    },
    OperatorType.UPDATE_REFERENCE: {
        "old_ref": "Current reference name (required)",
        "new_ref": "New reference name (required)",
    },
    # Call-site level
    OperatorType.ADD_ARG: {
        "callee": "Target function callee name (required)",
        "arg_name": "Argument name (required)",
        "arg_value": "Argument value (required)",
    },
    OperatorType.REMOVE_ARG: {
        "callee": "Target function callee name (required)",
        "arg_name": "Argument name to remove (required)",
    },
    OperatorType.UPDATE_ARG: {
        "callee": "Target function callee name (required)",
        "arg_name": "Argument name (required)",
        "old_value": "Current argument value (required)",
        "new_value": "New argument value (required)",
    },
    # Meta
    OperatorType.RENAME_FUNC: {
        "old_name": "Current function name (required)",
        "new_name": "New function name (required)",
    },
}


# =============================================================================
# Examples (JSON parameter strings)
# =============================================================================

OPERATOR_EXAMPLES: dict[OperatorType, str] = {
    OperatorType.ADD_METHOD: '{"class_name": "MyClass", "method_name": "process"}',
    OperatorType.REMOVE_METHOD: '{"class_name": "MyClass", "method_name": "old_method"}',
    OperatorType.RENAME_METHOD: '{"old_name": "process", "new_name": "transform"}',
    OperatorType.MOVE_METHOD: '{"method_name": "process", "source_class": "A", "target_class": "B"}',
    OperatorType.ADD_FIELD: '{"class_name": "MyClass", "field_name": "count", "field_type": "int"}',
    OperatorType.RENAME_CLASS: '{"old_name": "OldName", "new_name": "NewName"}',
    OperatorType.ADD_PARAM: '{"function_name": "get_data", "param_name": "log", "default_value": "True"}',
    OperatorType.ADD_ARG: '{"callee": "get_data", "arg_name": "log", "arg_value": "False"}',
    OperatorType.ADD_IMPORT: '{"module": "os.path", "name": "join", "is_from_import": true}',
    OperatorType.CREATE_MODULE: '{"module_name": "utils"}',
}


# =============================================================================
# Category helpers
# =============================================================================

CATEGORIES: dict[str, list[OperatorType]] = {
    "method": OperatorType.method_operators(),
    "field": OperatorType.field_operators(),
    "class": OperatorType.class_operators(),
    "param": OperatorType.param_operators(),
    "module": OperatorType.module_operators(),
    "reference": OperatorType.reference_operators(),
    "call_site": OperatorType.call_site_operators(),
}


def get_all_operators() -> list[OperatorType]:
    """Return all operators in category order."""
    result: list[OperatorType] = []
    for ops in CATEGORIES.values():
        result.extend(ops)
    # Add meta operators not in categories
    for op in OperatorType:
        if op not in result:
            result.append(op)
    return result


def resolve_operator(name: str) -> OperatorType:
    """Resolve an operator name string to an OperatorType enum.

    Accepts both the enum name (ADD_METHOD) and the value (add_method).

    Raises:
        ValueError: If the name doesn't match any operator.
    """
    # Try by value first (e.g. "add_method")
    for op in OperatorType:
        if op.value == name:
            return op
    # Try by name (e.g. "ADD_METHOD")
    name_upper = name.upper()
    for op in OperatorType:
        if op.name == name_upper:
            return op
    raise ValueError(
        f"Unknown operator: '{name}'. "
        f"Run 'graph-transform list' to see all available operators."
    )
