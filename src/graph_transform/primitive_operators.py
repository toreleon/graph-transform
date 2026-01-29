"""
Primitive Refactoring Operators

Based on Fowler's refactoring catalog, Opdyke's thesis, and established refactoring theory.
This module defines 40+ primitive operators that can be composed into complex refactorings.

Core concepts:
- OperatorType: All primitive refactoring operations (method, field, class, etc.)
- RefactoringPattern: Composite refactoring composed of primitives
- OperatorTemplate: Template for generating operators with variable expansion
- Operator algebra: Dependencies, composition, commutativity, inverses
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# =============================================================================
# Extended Operator Type Enum (40+ primitives)
# =============================================================================


class OperatorType(Enum):
    """
    Primitive refactoring operators based on established catalogs.

    Categories:
    - Method-Level (9): Operations on methods/functions
    - Field-Level (7): Operations on class fields/attributes
    - Class-Level (7): Operations on classes/types
    - Parameter-Level (4): Operations on function parameters
    - Module-Level (5): Operations on modules/files
    - Reference-Level (5): Operations on imports/references
    - Call-Site Level (3): Operations on function call arguments
    """

    # === Method-Level (9 operators) ===
    ADD_METHOD = "add_method"  # Add new method to class
    REMOVE_METHOD = "remove_method"  # Remove method from class
    RENAME_METHOD = "rename_method"  # Rename method
    MOVE_METHOD = "move_method"  # Move method to another class
    EXTRACT_METHOD = "extract_method"  # Extract code block into new method
    INLINE_METHOD = "inline_method"  # Replace method call with body
    PULL_UP_METHOD = "pull_up_method"  # Move method to superclass
    PUSH_DOWN_METHOD = "push_down_method"  # Move method to subclass
    CHANGE_SIGNATURE = "change_signature"  # Modify method signature

    # === Field-Level (7 operators) ===
    ADD_FIELD = "add_field"  # Add field to class
    REMOVE_FIELD = "remove_field"  # Remove field from class
    RENAME_FIELD = "rename_field"  # Rename field
    MOVE_FIELD = "move_field"  # Move field to another class
    PULL_UP_FIELD = "pull_up_field"  # Move field to superclass
    PUSH_DOWN_FIELD = "push_down_field"  # Move field to subclass
    ENCAPSULATE_FIELD = "encapsulate_field"  # Add getter/setter

    # === Class-Level (7 operators) ===
    ADD_CLASS = "add_class"  # Create new class
    REMOVE_CLASS = "remove_class"  # Delete class
    RENAME_CLASS = "rename_class"  # Rename class
    MOVE_CLASS = "move_class"  # Move class to another module
    EXTRACT_CLASS = "extract_class"  # Extract fields/methods to new class
    INLINE_CLASS = "inline_class"  # Merge class into another
    EXTRACT_SUPERCLASS = "extract_superclass"  # Create superclass from common members

    # === Parameter-Level (4 operators) ===
    ADD_PARAM = "add_param"  # Add parameter to function signature
    REMOVE_PARAM = "remove_param"  # Remove parameter from signature
    RENAME_PARAM = "rename_param"  # Rename a parameter
    INTRODUCE_PARAM_OBJECT = "introduce_param_object"  # Group params into object

    # === Module-Level (5 operators) ===
    CREATE_MODULE = "create_module"  # Create new module/file
    DELETE_MODULE = "delete_module"  # Delete module/file
    RENAME_MODULE = "rename_module"  # Rename module/file
    MOVE_TO_MODULE = "move_to_module"  # Move definition to module
    MERGE_MODULES = "merge_modules"  # Merge two modules

    # === Reference-Level (5 operators) ===
    ADD_IMPORT = "add_import"  # Add import statement
    REMOVE_IMPORT = "remove_import"  # Remove import statement
    UPDATE_IMPORT = "update_import"  # Modify import statement
    UPDATE_CALL = "update_call"  # Update function call
    UPDATE_REFERENCE = "update_reference"  # Update code reference

    # === Call-Site Level (3 operators) ===
    ADD_ARG = "add_arg"  # Add argument to call site
    REMOVE_ARG = "remove_arg"  # Remove argument from call
    UPDATE_ARG = "update_arg"  # Change argument value

    # === Composite/Meta (for pattern matching) ===
    RENAME_FUNC = "rename_func"  # Alias for RENAME_METHOD (function-level)

    @classmethod
    def method_operators(cls) -> list["OperatorType"]:
        """Return all method-level operators."""
        return [
            cls.ADD_METHOD, cls.REMOVE_METHOD, cls.RENAME_METHOD,
            cls.MOVE_METHOD, cls.EXTRACT_METHOD, cls.INLINE_METHOD,
            cls.PULL_UP_METHOD, cls.PUSH_DOWN_METHOD, cls.CHANGE_SIGNATURE,
        ]

    @classmethod
    def field_operators(cls) -> list["OperatorType"]:
        """Return all field-level operators."""
        return [
            cls.ADD_FIELD, cls.REMOVE_FIELD, cls.RENAME_FIELD,
            cls.MOVE_FIELD, cls.PULL_UP_FIELD, cls.PUSH_DOWN_FIELD,
            cls.ENCAPSULATE_FIELD,
        ]

    @classmethod
    def class_operators(cls) -> list["OperatorType"]:
        """Return all class-level operators."""
        return [
            cls.ADD_CLASS, cls.REMOVE_CLASS, cls.RENAME_CLASS,
            cls.MOVE_CLASS, cls.EXTRACT_CLASS, cls.INLINE_CLASS,
            cls.EXTRACT_SUPERCLASS,
        ]

    @classmethod
    def param_operators(cls) -> list["OperatorType"]:
        """Return all parameter-level operators."""
        return [
            cls.ADD_PARAM, cls.REMOVE_PARAM, cls.RENAME_PARAM,
            cls.INTRODUCE_PARAM_OBJECT,
        ]

    @classmethod
    def module_operators(cls) -> list["OperatorType"]:
        """Return all module-level operators."""
        return [
            cls.CREATE_MODULE, cls.DELETE_MODULE, cls.RENAME_MODULE,
            cls.MOVE_TO_MODULE, cls.MERGE_MODULES,
        ]

    @classmethod
    def reference_operators(cls) -> list["OperatorType"]:
        """Return all reference-level operators."""
        return [
            cls.ADD_IMPORT, cls.REMOVE_IMPORT, cls.UPDATE_IMPORT,
            cls.UPDATE_CALL, cls.UPDATE_REFERENCE,
        ]

    @classmethod
    def call_site_operators(cls) -> list["OperatorType"]:
        """Return all call-site level operators."""
        return [cls.ADD_ARG, cls.REMOVE_ARG, cls.UPDATE_ARG]


class OperatorStatus(Enum):
    """Status of an operator in the plan."""

    PENDING = "pending"  # Not yet processed
    READY = "ready"  # Dependencies satisfied, can be applied
    BLOCKED = "blocked"  # Waiting on dependencies
    APPLIED = "applied"  # Successfully completed
    FAILED = "failed"  # Error during application
    SKIPPED = "skipped"  # Intentionally skipped (e.g., not applicable)


# =============================================================================
# Operator Algebra
# =============================================================================


@dataclass
class OperatorAlgebra:
    """
    Defines algebraic properties of operators.

    Properties:
    - Commutativity: op1 ∘ op2 = op2 ∘ op1
    - Composition: op2 ∘ op1 (apply op1 then op2)
    - Inverse: op⁻¹ such that op ∘ op⁻¹ = identity
    - Dependencies: op1 must complete before op2
    """

    # Pairs of commutative operator types
    COMMUTATIVE_PAIRS: set[tuple[OperatorType, OperatorType]] = field(
        default_factory=lambda: {
            # Renames on different methods commute
            (OperatorType.RENAME_METHOD, OperatorType.RENAME_METHOD),
            (OperatorType.RENAME_FIELD, OperatorType.RENAME_FIELD),
            (OperatorType.RENAME_CLASS, OperatorType.RENAME_CLASS),
            # Adds on different targets commute
            (OperatorType.ADD_METHOD, OperatorType.ADD_METHOD),
            (OperatorType.ADD_FIELD, OperatorType.ADD_FIELD),
            (OperatorType.ADD_CLASS, OperatorType.ADD_CLASS),
            # Independent call site updates commute
            (OperatorType.ADD_ARG, OperatorType.ADD_ARG),
            (OperatorType.UPDATE_ARG, OperatorType.UPDATE_ARG),
        }
    )

    # Inverse operator mappings
    INVERSE_MAP: dict[OperatorType, OperatorType] = field(
        default_factory=lambda: {
            OperatorType.ADD_METHOD: OperatorType.REMOVE_METHOD,
            OperatorType.REMOVE_METHOD: OperatorType.ADD_METHOD,
            OperatorType.ADD_FIELD: OperatorType.REMOVE_FIELD,
            OperatorType.REMOVE_FIELD: OperatorType.ADD_FIELD,
            OperatorType.ADD_CLASS: OperatorType.REMOVE_CLASS,
            OperatorType.REMOVE_CLASS: OperatorType.ADD_CLASS,
            OperatorType.ADD_PARAM: OperatorType.REMOVE_PARAM,
            OperatorType.REMOVE_PARAM: OperatorType.ADD_PARAM,
            OperatorType.ADD_ARG: OperatorType.REMOVE_ARG,
            OperatorType.REMOVE_ARG: OperatorType.ADD_ARG,
            OperatorType.ADD_IMPORT: OperatorType.REMOVE_IMPORT,
            OperatorType.REMOVE_IMPORT: OperatorType.ADD_IMPORT,
            OperatorType.PULL_UP_METHOD: OperatorType.PUSH_DOWN_METHOD,
            OperatorType.PUSH_DOWN_METHOD: OperatorType.PULL_UP_METHOD,
            OperatorType.PULL_UP_FIELD: OperatorType.PUSH_DOWN_FIELD,
            OperatorType.PUSH_DOWN_FIELD: OperatorType.PULL_UP_FIELD,
            # Renames are self-inverse with swapped names
            OperatorType.RENAME_METHOD: OperatorType.RENAME_METHOD,
            OperatorType.RENAME_FIELD: OperatorType.RENAME_FIELD,
            OperatorType.RENAME_CLASS: OperatorType.RENAME_CLASS,
            OperatorType.RENAME_PARAM: OperatorType.RENAME_PARAM,
        }
    )

    @staticmethod
    def commutes(op1_type: OperatorType, op2_type: OperatorType) -> bool:
        """Check if two operator types can commute (order doesn't matter)."""
        algebra = OperatorAlgebra()
        pair = (op1_type, op2_type)
        reverse = (op2_type, op1_type)
        return pair in algebra.COMMUTATIVE_PAIRS or reverse in algebra.COMMUTATIVE_PAIRS

    @staticmethod
    def inverse_type(op_type: OperatorType) -> OperatorType | None:
        """Get the inverse operator type, if it exists."""
        algebra = OperatorAlgebra()
        return algebra.INVERSE_MAP.get(op_type)

    @staticmethod
    def must_precede(before: OperatorType, after: OperatorType) -> bool:
        """Check if 'before' must execute before 'after'."""
        precedence_rules = [
            # Rename before move
            (OperatorType.RENAME_METHOD, OperatorType.MOVE_METHOD),
            (OperatorType.RENAME_FIELD, OperatorType.MOVE_FIELD),
            (OperatorType.RENAME_CLASS, OperatorType.MOVE_CLASS),
            # Add class before add method/field
            (OperatorType.ADD_CLASS, OperatorType.ADD_METHOD),
            (OperatorType.ADD_CLASS, OperatorType.ADD_FIELD),
            # Add param before add arg
            (OperatorType.ADD_PARAM, OperatorType.ADD_ARG),
            # Extract before pull up
            (OperatorType.EXTRACT_METHOD, OperatorType.PULL_UP_METHOD),
            (OperatorType.EXTRACT_CLASS, OperatorType.EXTRACT_SUPERCLASS),
            # Create module before move to module
            (OperatorType.CREATE_MODULE, OperatorType.MOVE_TO_MODULE),
            (OperatorType.CREATE_MODULE, OperatorType.MOVE_CLASS),
        ]
        return (before, after) in precedence_rules


# =============================================================================
# Pattern & Operator Data Structures
# =============================================================================


@dataclass
class Pattern:
    """
    Pattern for matching nodes in the code graph.

    Patterns define what code elements an operator should target.
    Supports glob-style file filters and receiver filtering for method calls.
    """

    node_type: str  # "function" | "call" | "class" | "field" | "import"
    name: str  # Name to match (supports wildcards with *)
    file_filter: str | None = None  # Glob pattern for files
    receiver_filter: list[str] = field(default_factory=list)  # For method calls
    exclude_receivers: list[str] = field(default_factory=list)  # Receivers to skip
    class_filter: str | None = None  # For class-scoped operations

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"node_type": self.node_type, "name": self.name}
        if self.file_filter:
            result["file_filter"] = self.file_filter
        if self.receiver_filter:
            result["receiver_filter"] = self.receiver_filter
        if self.exclude_receivers:
            result["exclude_receivers"] = self.exclude_receivers
        if self.class_filter:
            result["class_filter"] = self.class_filter
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pattern:
        """Create from dictionary."""
        return cls(
            node_type=data["node_type"],
            name=data["name"],
            file_filter=data.get("file_filter"),
            receiver_filter=data.get("receiver_filter", []),
            exclude_receivers=data.get("exclude_receivers", []),
            class_filter=data.get("class_filter"),
        )

    def matches_name(self, name: str) -> bool:
        """Check if a name matches the pattern (supports * wildcard)."""
        if "*" not in self.name:
            return self.name == name
        # Convert glob to regex
        regex = self.name.replace("*", ".*")
        return bool(re.match(f"^{regex}$", name))


@dataclass
class MatchedSite:
    """A code location matched by an operator's pattern."""

    file: str
    line: int
    is_applied: bool = False
    error: "MatchError | None" = None

    def to_dict(self) -> dict[str, Any]:
        result = {"file": self.file, "line": self.line, "is_applied": self.is_applied}
        if self.error:
            result["error"] = self.error.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchedSite:
        error = MatchError.from_dict(data["error"]) if data.get("error") else None
        return cls(
            file=data["file"],
            line=data["line"],
            is_applied=data.get("is_applied", False),
            error=error,
        )


@dataclass
class MatchError:
    """An error encountered during operator matching/application."""

    file: str
    line: int
    error_type: str
    actual: str
    expected: str
    suggested_fix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "error_type": self.error_type,
            "actual": self.actual,
            "expected": self.expected,
            "suggested_fix": self.suggested_fix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchError:
        return cls(
            file=data["file"],
            line=data["line"],
            error_type=data["error_type"],
            actual=data["actual"],
            expected=data["expected"],
            suggested_fix=data["suggested_fix"],
        )


@dataclass
class GraphOperator:
    """
    A single graph rewrite operator.

    Operators define a pattern to match and a transformation to apply.
    They support dependencies and can be composed into larger refactorings.
    """

    id: str  # Unique identifier
    op_type: OperatorType
    target_pattern: Pattern
    transformation: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)

    # Runtime state
    status: OperatorStatus = OperatorStatus.PENDING
    matched_sites: list[MatchedSite] = field(default_factory=list)
    errors: list[MatchError] = field(default_factory=list)

    # Optional metadata
    description: str | None = None
    priority: int = 0  # Higher = execute earlier among ready operators

    @property
    def matched_count(self) -> int:
        return len(self.matched_sites)

    @property
    def applied_count(self) -> int:
        return sum(1 for s in self.matched_sites if s.is_applied)

    @property
    def remaining_count(self) -> int:
        return self.matched_count - self.applied_count

    @property
    def is_complete(self) -> bool:
        return self.status == OperatorStatus.APPLIED

    @property
    def category(self) -> str:
        """Return the operator category."""
        if self.op_type in OperatorType.method_operators():
            return "method"
        elif self.op_type in OperatorType.field_operators():
            return "field"
        elif self.op_type in OperatorType.class_operators():
            return "class"
        elif self.op_type in OperatorType.param_operators():
            return "param"
        elif self.op_type in OperatorType.module_operators():
            return "module"
        elif self.op_type in OperatorType.reference_operators():
            return "reference"
        elif self.op_type in OperatorType.call_site_operators():
            return "call_site"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "op_type": self.op_type.value,
            "target_pattern": self.target_pattern.to_dict(),
            "transformation": self.transformation,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "matched_sites": [s.to_dict() for s in self.matched_sites],
            "errors": [e.to_dict() for e in self.errors],
            "description": self.description,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphOperator:
        return cls(
            id=data["id"],
            op_type=OperatorType(data["op_type"]),
            target_pattern=Pattern.from_dict(data["target_pattern"]),
            transformation=data["transformation"],
            depends_on=data.get("depends_on", []),
            status=OperatorStatus(data.get("status", "pending")),
            matched_sites=[MatchedSite.from_dict(s) for s in data.get("matched_sites", [])],
            errors=[MatchError.from_dict(e) for e in data.get("errors", [])],
            description=data.get("description"),
            priority=data.get("priority", 0),
        )


# =============================================================================
# Refactor Plan
# =============================================================================


@dataclass
class RefactorPlan:
    """
    A refactoring plan composed of graph rewrite operators with dependencies.

    The plan supports:
    - Multiple operators with explicit IDs
    - Dependency ordering (topological sort)
    - Per-operator status tracking
    - JSON serialization for agent communication
    - Pattern instantiation
    """

    operators: list[GraphOperator]
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_operator(self, op_id: str) -> GraphOperator | None:
        """Get operator by ID."""
        for op in self.operators:
            if op.id == op_id:
                return op
        return None

    def get_execution_order(self) -> list[GraphOperator]:
        """
        Return operators in topological order based on dependencies.
        Uses Kahn's algorithm. Raises ValueError if there's a cycle.
        """
        in_degree: dict[str, int] = {op.id: 0 for op in self.operators}
        adjacency: dict[str, list[str]] = {op.id: [] for op in self.operators}

        for op in self.operators:
            for dep_id in op.depends_on:
                if dep_id in adjacency:
                    adjacency[dep_id].append(op.id)
                    in_degree[op.id] += 1

        queue = deque([op_id for op_id, degree in in_degree.items() if degree == 0])
        result: list[GraphOperator] = []

        while queue:
            op_id = queue.popleft()
            op = self.get_operator(op_id)
            if op:
                result.append(op)
            for dependent_id in adjacency[op_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        if len(result) != len(self.operators):
            raise ValueError("Cycle detected in operator dependencies")

        return result

    def get_ready_operators(self) -> list[GraphOperator]:
        """Return operators whose dependencies are satisfied."""
        ready = [
            op for op in self.operators
            if op.status in (OperatorStatus.PENDING, OperatorStatus.READY)
            and self._dependencies_satisfied(op)
        ]
        # Sort by priority (higher first)
        return sorted(ready, key=lambda op: -op.priority)

    def get_blocked_operators(self) -> list[GraphOperator]:
        """Return operators blocked by incomplete dependencies."""
        return [
            op for op in self.operators
            if op.status in (OperatorStatus.PENDING, OperatorStatus.BLOCKED)
            and not self._dependencies_satisfied(op)
        ]

    def _dependencies_satisfied(self, op: GraphOperator) -> bool:
        """Check if all dependencies of an operator are applied."""
        for dep_id in op.depends_on:
            dep_op = self.get_operator(dep_id)
            if dep_op is None or dep_op.status != OperatorStatus.APPLIED:
                return False
        return True

    def update_statuses(self) -> None:
        """Update operator statuses based on dependencies."""
        for op in self.operators:
            if op.status in (OperatorStatus.APPLIED, OperatorStatus.FAILED, OperatorStatus.SKIPPED):
                continue
            if self._dependencies_satisfied(op):
                if op.status != OperatorStatus.READY:
                    op.status = OperatorStatus.READY
            else:
                op.status = OperatorStatus.BLOCKED

    @property
    def is_complete(self) -> bool:
        """Check if all operators are applied."""
        return all(
            op.status in (OperatorStatus.APPLIED, OperatorStatus.SKIPPED)
            for op in self.operators
        )

    @property
    def total_operators(self) -> int:
        return len(self.operators)

    @property
    def applied_operators(self) -> int:
        return sum(1 for op in self.operators if op.status == OperatorStatus.APPLIED)

    @property
    def ready_operators_count(self) -> int:
        return len(self.get_ready_operators())

    @property
    def blocked_operators_count(self) -> int:
        return len(self.get_blocked_operators())

    @property
    def progress_ratio(self) -> float:
        """Return completion ratio (0.0 to 1.0)."""
        if self.total_operators == 0:
            return 1.0
        return self.applied_operators / self.total_operators

    def by_category(self) -> dict[str, list[GraphOperator]]:
        """Group operators by category."""
        result: dict[str, list[GraphOperator]] = {}
        for op in self.operators:
            cat = op.category
            if cat not in result:
                result[cat] = []
            result[cat].append(op)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "operators": [op.to_dict() for op in self.operators],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RefactorPlan:
        """Create from dictionary."""
        return cls(
            operators=[GraphOperator.from_dict(op) for op in data.get("operators", [])],
            metadata=data.get("metadata", {}),
        )

    def to_agent_feedback(self, max_sites_per_op: int = 5) -> str:
        """Format plan progress as XML for agent observation."""
        self.update_statuses()

        lines = ["<refactor_plan_progress>"]

        # Summary
        lines.append(
            f'  <summary total="{self.total_operators}" '
            f'applied="{self.applied_operators}" '
            f'ready="{self.ready_operators_count}" '
            f'blocked="{self.blocked_operators_count}" '
            f'progress="{int(self.progress_ratio * 100)}%" />'
        )

        # Group by category
        by_cat = self.by_category()
        for cat, ops in by_cat.items():
            lines.append(f'  <category name="{cat}">')
            for op in ops:
                self._format_operator(op, lines, max_sites_per_op, indent=4)
            lines.append("  </category>")

        # Next action guidance
        if self.is_complete:
            lines.append("  <next_action>ALL OPERATORS COMPLETE - ready to submit</next_action>")
        else:
            ready = self.get_ready_operators()
            if ready:
                op = ready[0]
                if op.remaining_count > 0:
                    lines.append(
                        f"  <next_action>Apply {op.id} ({op.op_type.value}) "
                        f"to {op.remaining_count} remaining sites</next_action>"
                    )
                else:
                    lines.append(f"  <next_action>Execute {op.id} ({op.op_type.value})</next_action>")
            else:
                blocked = self.get_blocked_operators()
                if blocked:
                    deps = blocked[0].depends_on
                    lines.append(
                        f"  <next_action>Blocked: complete {deps} first</next_action>"
                    )

        lines.append("</refactor_plan_progress>")
        return "\n".join(lines)

    def _format_operator(
        self,
        op: GraphOperator,
        lines: list[str],
        max_sites: int,
        indent: int = 2
    ) -> None:
        """Format a single operator for feedback."""
        spaces = " " * indent
        status = op.status.value
        attrs = f'id="{op.id}" type="{op.op_type.value}" status="{status}"'

        if op.matched_count > 0:
            attrs += f' matched="{op.matched_count}" applied="{op.applied_count}"'

        lines.append(f"{spaces}<operator {attrs}>")

        # Description if available
        if op.description:
            lines.append(f"{spaces}  <description>{op.description}</description>")

        # Target
        target = f"{op.target_pattern.node_type}:{op.target_pattern.name}"
        lines.append(f"{spaces}  <target>{target}</target>")

        # Dependencies
        if op.depends_on:
            dep_strs = []
            for dep_id in op.depends_on:
                dep_op = self.get_operator(dep_id)
                dep_status = dep_op.status.value if dep_op else "unknown"
                dep_strs.append(f"{dep_id} ({dep_status})")
            lines.append(f"{spaces}  <depends_on>{', '.join(dep_strs)}</depends_on>")

        # Remaining sites
        if op.remaining_count > 0:
            remaining = [s for s in op.matched_sites if not s.is_applied]
            lines.append(f'{spaces}  <remaining count="{len(remaining)}">')
            for site in remaining[:max_sites]:
                if site.error:
                    lines.append(
                        f'{spaces}    <site file="{site.file}" line="{site.line}">'
                        f"{site.error.suggested_fix}</site>"
                    )
                else:
                    lines.append(
                        f'{spaces}    <site file="{site.file}" line="{site.line}">needs update</site>'
                    )
            if len(remaining) > max_sites:
                lines.append(f"{spaces}    <!-- {len(remaining) - max_sites} more sites not shown -->")
            lines.append(f"{spaces}  </remaining>")

        lines.append(f"{spaces}</operator>")
