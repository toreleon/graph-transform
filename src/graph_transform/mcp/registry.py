"""
Operator Registry with Metadata

Story 1.2: AI agents can discover operators with full metadata including:
- Name and description
- Required and optional parameters with types
- Preconditions for each operator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParameterDef:
    """Definition of an operator parameter."""
    name: str
    param_type: str
    description: str
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = {
            "name": self.name,
            "type": self.param_type,
            "description": self.description,
        }
        if self.default is not None:
            d["default"] = str(self.default)
        return d


@dataclass
class Precondition:
    """Definition of an operator precondition."""
    name: str
    description: str

    def to_dict(self) -> dict[str, str]:
        """Convert to JSON-serializable dict."""
        return {"name": self.name, "description": self.description}


@dataclass
class OperatorMeta:
    """Complete metadata for an operator."""
    name: str
    description: str
    operator_type: str  # "primitive" or "composition"
    required_params: list[ParameterDef] = field(default_factory=list)
    optional_params: list[ParameterDef] = field(default_factory=list)
    preconditions: list[Precondition] = field(default_factory=list)
    example: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.operator_type,
            "required_params": [p.to_dict() for p in self.required_params],
            "optional_params": [p.to_dict() for p in self.optional_params],
            "preconditions": [p.to_dict() for p in self.preconditions],
            "example": self.example,
        }


class OperatorRegistry:
    """Registry of all transformation operators.

    Provides full metadata for each operator including:
    - Name and description
    - Required and optional parameters with types and descriptions
    - Preconditions that must be satisfied
    - Usage examples
    """

    def __init__(self) -> None:
        self._operators: dict[str, OperatorMeta] = {}
        self._register_primitives()
        self._register_compositions()

    def _register_primitives(self) -> None:
        """Register primitive operators."""
        self._operators["insert_node"] = OperatorMeta(
            name="insert_node",
            description="Insert a new node into the graph (function, class, variable, etc.)",
            operator_type="primitive",
            required_params=[
                ParameterDef("node_id", "string", "Unique identifier for the new node"),
                ParameterDef("node_kind", "NodeKind", "Node kind: callable, type, binding, container, etc."),
            ],
            optional_params=[
                ParameterDef("attrs", "object", "Node attributes like name, file, line", {}),
                ParameterDef("position", "Position", "Position specification for insertion", None),
            ],
            preconditions=[
                Precondition("node_not_exists", "Node with node_id must not already exist"),
            ],
            example={
                "node_id": "func:new_helper",
                "node_kind": "callable",
                "attrs": {"name": "new_helper", "file": "utils.py", "line": 10}
            }
        )

        self._operators["insert_edge"] = OperatorMeta(
            name="insert_edge",
            description="Insert a new edge between two nodes",
            operator_type="primitive",
            required_params=[
                ParameterDef("source", "string", "Source node ID"),
                ParameterDef("target", "string", "Target node ID"),
                ParameterDef("edge_kind", "EdgeKind", "Edge kind: contains, calls, inherits, etc."),
            ],
            optional_params=[
                ParameterDef("attrs", "object", "Edge attributes", {}),
            ],
            preconditions=[
                Precondition("source_exists", "Source node must exist"),
                Precondition("target_exists", "Target node must exist"),
            ],
            example={
                "source": "class:MyClass",
                "target": "func:MyClass.method",
                "edge_kind": "contains"
            }
        )

        self._operators["delete_node"] = OperatorMeta(
            name="delete_node",
            description="Delete a node from the graph with optional cascade",
            operator_type="primitive",
            required_params=[
                ParameterDef("node_id", "string", "ID of the node to delete"),
            ],
            optional_params=[
                ParameterDef("cascade", "boolean", "Delete connected edges", True),
            ],
            preconditions=[
                Precondition("node_exists", "Node must exist"),
            ],
            example={
                "node_id": "func:old_helper",
                "cascade": True
            }
        )

        self._operators["delete_edge"] = OperatorMeta(
            name="delete_edge",
            description="Delete an edge between two nodes",
            operator_type="primitive",
            required_params=[
                ParameterDef("source", "string", "Source node ID"),
                ParameterDef("target", "string", "Target node ID"),
            ],
            optional_params=[
                ParameterDef("edge_kind", "EdgeKind", "Edge kind to delete; if omitted deletes all", None),
            ],
            preconditions=[
                Precondition("edge_exists", "At least one edge must exist between source and target"),
            ],
            example={
                "source": "class:MyClass",
                "target": "func:MyClass.old_method",
                "edge_kind": "contains"
            }
        )

        self._operators["update"] = OperatorMeta(
            name="update",
            description="Update properties of an existing node or edge",
            operator_type="primitive",
            required_params=[
                ParameterDef("target", "string", "ID of the node or edge to update"),
            ],
            optional_params=[
                ParameterDef("prop", "string", "Property name to update", None),
                ParameterDef("value", "any", "New value for the property", None),
                ParameterDef("properties", "object", "Multiple properties to update", None),
            ],
            preconditions=[
                Precondition("target_exists", "Target node or edge must exist"),
            ],
            example={
                "target": "func:my_func",
                "prop": "name",
                "value": "new_name"
            }
        )

    def _register_compositions(self) -> None:
        """Register composition operators."""
        self._operators["RENAME"] = OperatorMeta(
            name="RENAME",
            description="Rename an entity and update all references",
            operator_type="composition",
            required_params=[
                ParameterDef("target", "string", "Node ID to rename"),
                ParameterDef("new_name", "string", "New name for the entity"),
            ],
            optional_params=[
                ParameterDef("update_references", "boolean", "Also update all references", True),
            ],
            preconditions=[
                Precondition("target_exists", "Target node must exist"),
                Precondition("name_valid", "New name must be a valid identifier"),
                Precondition("no_conflict", "New name must not conflict in target scope"),
            ],
            example={
                "target": "func:old_name",
                "new_name": "new_name"
            }
        )

        self._operators["MOVE"] = OperatorMeta(
            name="MOVE",
            description="Move an entity from one scope to another",
            operator_type="composition",
            required_params=[
                ParameterDef("target", "string", "Node ID to move"),
                ParameterDef("from_scope", "string", "Source container ID"),
                ParameterDef("to_scope", "string", "Target container ID"),
            ],
            optional_params=[
                ParameterDef("edge_kind", "EdgeKind", "Edge kind for containment", "contains"),
                ParameterDef("update_references", "boolean", "Also update references", True),
            ],
            preconditions=[
                Precondition("target_exists", "Target node must exist"),
                Precondition("from_scope_exists", "Source container must exist"),
                Precondition("to_scope_exists", "Target container must exist"),
                Precondition("contained_in_from", "Target must be in source container"),
                Precondition("no_conflict", "Name must not conflict in target scope"),
            ],
            example={
                "target": "func:Source.method",
                "from_scope": "class:Source",
                "to_scope": "class:Target"
            }
        )

        self._operators["EXTRACT"] = OperatorMeta(
            name="EXTRACT",
            description="Extract code into a new entity (function, class, etc.)",
            operator_type="composition",
            required_params=[
                ParameterDef("new_id", "string", "ID for the new entity"),
                ParameterDef("new_name", "string", "Name for the new entity"),
                ParameterDef("node_kind", "NodeKind", "Kind of entity to create"),
                ParameterDef("scope", "string", "Container for the new entity"),
                ParameterDef("original", "string", "Entity being extracted from"),
                ParameterDef("replacement_value", "string", "What replaces extracted code"),
            ],
            optional_params=[
                ParameterDef("attrs", "object", "Additional attributes", {}),
                ParameterDef("position", "Position", "Position within scope", None),
            ],
            preconditions=[
                Precondition("original_exists", "Source entity must exist"),
                Precondition("scope_exists", "Target container must exist"),
                Precondition("id_unique", "New ID must not already exist"),
            ],
            example={
                "new_id": "func:extracted_helper",
                "new_name": "extracted_helper",
                "node_kind": "callable",
                "scope": "module:utils",
                "original": "func:process",
                "replacement_value": "extracted_helper()"
            }
        )

        self._operators["INLINE"] = OperatorMeta(
            name="INLINE",
            description="Inline an entity into its call sites",
            operator_type="composition",
            required_params=[
                ParameterDef("target", "string", "Node ID of entity to inline"),
            ],
            optional_params=[
                ParameterDef("remove_after", "boolean", "Delete entity after inlining", True),
            ],
            preconditions=[
                Precondition("target_exists", "Target entity must exist"),
                Precondition("has_body", "Target must have inlineable body"),
            ],
            example={
                "target": "func:small_helper",
                "remove_after": True
            }
        )

        self._operators["ADD_GUARD"] = OperatorMeta(
            name="ADD_GUARD",
            description="Add a guard/check before an operation",
            operator_type="composition",
            required_params=[
                ParameterDef("target", "string", "Where to add the guard"),
                ParameterDef("guard_type", "string", "Type: null_check, bounds_check, type_check"),
                ParameterDef("guard_condition", "string", "Condition expression"),
            ],
            optional_params=[
                ParameterDef("guard_action", "string", "Action on failure: early_return, throw", "early_return"),
            ],
            preconditions=[
                Precondition("target_exists", "Target entity must exist"),
                Precondition("target_is_callable", "Target must be a callable"),
            ],
            example={
                "target": "func:process",
                "guard_type": "null_check",
                "guard_condition": "x is not None",
                "guard_action": "early_return"
            }
        )

        self._operators["CHANGE_SIGNATURE"] = OperatorMeta(
            name="CHANGE_SIGNATURE",
            description="Change a callable's signature and update all call sites",
            operator_type="composition",
            required_params=[
                ParameterDef("target", "string", "Callable node ID to modify"),
                ParameterDef("changes", "object", "Signature changes"),
            ],
            optional_params=[],
            preconditions=[
                Precondition("target_exists", "Target callable must exist"),
                Precondition("target_is_callable", "Target must be a callable"),
                Precondition("changes_valid", "Changes must be well-formed"),
            ],
            example={
                "target": "func:my_func",
                "changes": {"add_param": {"name": "logger", "default": "None"}}
            }
        )

        self._operators["WRAP"] = OperatorMeta(
            name="WRAP",
            description="Wrap code in a construct (try/catch, with, async, etc.)",
            operator_type="composition",
            required_params=[
                ParameterDef("target", "string", "Node ID to wrap"),
                ParameterDef("wrapper_kind", "string", "Kind: try_catch, with, async, loop"),
            ],
            optional_params=[
                ParameterDef("wrapper_attrs", "object", "Wrapper attributes", {}),
            ],
            preconditions=[
                Precondition("target_exists", "Target entity must exist"),
            ],
            example={
                "target": "func:risky_operation",
                "wrapper_kind": "try_catch",
                "wrapper_attrs": {"catch_type": "Exception"}
            }
        )

        self._operators["UPDATE_IMPORT"] = OperatorMeta(
            name="UPDATE_IMPORT",
            description="Update import statements when a symbol moves between modules",
            operator_type="composition",
            required_params=[
                ParameterDef("symbol", "string", "The imported symbol name"),
                ParameterDef("old_module", "string", "Original module path"),
                ParameterDef("new_module", "string", "New module path"),
            ],
            optional_params=[
                ParameterDef("file", "string", "Specific file to update (all if omitted)", None),
            ],
            preconditions=[
                Precondition("import_exists", "At least one import of symbol from old_module must exist"),
            ],
            example={
                "symbol": "helper_func",
                "old_module": "old_utils",
                "new_module": "new_utils"
            }
        )

    def get(self, name: str) -> OperatorMeta | None:
        """Get operator metadata by name.

        Args:
            name: Operator name (case-insensitive)

        Returns:
            OperatorMeta if found, None otherwise
        """
        if not name:
            return None

        # Try exact match first
        if name in self._operators:
            return self._operators[name]

        # Try uppercase (for compositions)
        upper = name.upper()
        if upper in self._operators:
            return self._operators[upper]

        # Try lowercase (for primitives)
        lower = name.lower()
        if lower in self._operators:
            return self._operators[lower]

        return None

    def list_operators(self) -> list[OperatorMeta]:
        """List all registered operators."""
        return list(self._operators.values())

    def list_primitives(self) -> list[OperatorMeta]:
        """List primitive operators."""
        return [op for op in self._operators.values() if op.operator_type == "primitive"]

    def list_compositions(self) -> list[OperatorMeta]:
        """List composition operators."""
        return [op for op in self._operators.values() if op.operator_type == "composition"]

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to JSON-serializable dict."""
        return {
            "primitives": [op.to_dict() for op in self.list_primitives()],
            "compositions": [op.to_dict() for op in self.list_compositions()],
        }
