"""
Error Codes and Structured Error Response Handling

FR33: Violation types as enumerated codes
FR34: Specific error details (node, scope, conflicting name)
FR35: Actionable suggestions for resolution
FR37: Complete error taxonomy with machine-parseable format
FR38: Feedback designed for agent self-correction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Complete taxonomy of error codes.

    FR37: Covers PRECONDITION_FAILED, POSTCONDITION_FAILED, GLUING_VIOLATION,
    NAME_CONFLICT, SCOPE_VIOLATION, REFERENCE_UNRESOLVABLE, PARSE_ERROR, INTERNAL_ERROR
    """

    # Input validation
    MISSING_PATH = "MISSING_PATH"
    MISSING_OPERATOR = "MISSING_OPERATOR"
    PATH_NOT_FOUND = "PATH_NOT_FOUND"
    UNKNOWN_OPERATOR = "UNKNOWN_OPERATOR"

    # Parse errors
    PARSE_ERROR = "PARSE_ERROR"
    SYNTAX_ERROR = "SYNTAX_ERROR"

    # Target resolution
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    SCOPE_NOT_FOUND = "SCOPE_NOT_FOUND"

    # Conflict errors
    NAME_CONFLICT = "NAME_CONFLICT"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"

    # Graph integrity
    DANGLING_EDGE = "DANGLING_EDGE"
    INVALID_EDGE_TARGET = "INVALID_EDGE_TARGET"
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
    ORPHAN_NODE = "ORPHAN_NODE"

    # Verification phases
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    GLUING_VIOLATION = "GLUING_VIOLATION"

    # Plan/transformation errors
    PLAN_ERROR = "PLAN_ERROR"
    EMIT_ERROR = "EMIT_ERROR"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ViolationType(str, Enum):
    """Violation types for phase tracking.

    FR33: Includes violation_type enum
    """

    PRECONDITION = "precondition"
    POSTCONDITION = "postcondition"
    GLUING = "gluing"
    INPUT_VALIDATION = "input_validation"
    PARSE = "parse"
    INTERNAL = "internal"


@dataclass(frozen=True)
class Suggestion:
    """An actionable suggestion for error resolution.

    FR35: Suggestions enable agent self-correction
    FR38: Following suggestions increases success likelihood
    """

    action: str
    description: str
    example: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "action": self.action,
            "description": self.description,
        }
        if self.example:
            result["example"] = self.example
        return result


@dataclass(frozen=True)
class ErrorDetails:
    """Specific details about an error.

    FR34: Includes which node caused conflict, conflicting name, scope
    """

    node_id: str | None = None
    scope: str | None = None
    conflicting_name: str | None = None
    file: str | None = None
    line: int | None = None
    column: int | None = None
    source_line: str | None = None
    related_nodes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.node_id:
            result["node_id"] = self.node_id
        if self.scope:
            result["scope"] = self.scope
        if self.conflicting_name:
            result["conflicting_name"] = self.conflicting_name
        if self.file:
            result["file"] = self.file
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column
        if self.source_line:
            result["source_line"] = self.source_line
        if self.related_nodes:
            result["related_nodes"] = list(self.related_nodes)
        return result


@dataclass(frozen=True)
class StructuredError:
    """A structured error response for MCP tools.

    FR33: Errors as structured JSON with violation_type
    FR34: Specific details about what went wrong
    FR35: Actionable suggestions for resolution
    FR37: Machine-parseable format

    Schema: {
        status: "error",
        error: {
            code: ErrorCode,
            message: str,
            phase: ViolationType,
            details: ErrorDetails,
            suggestions: list[Suggestion]
        }
    }
    """

    code: ErrorCode
    message: str
    phase: ViolationType = ViolationType.INTERNAL
    details: ErrorDetails | None = None
    suggestions: tuple[Suggestion, ...] = ()

    def to_response(self) -> dict[str, Any]:
        """Convert to MCP response format."""
        error_dict: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "phase": self.phase.value,
        }

        if self.details:
            error_dict["details"] = self.details.to_dict()

        if self.suggestions:
            error_dict["suggestions"] = [s.to_dict() for s in self.suggestions]

        return {
            "status": "error",
            "error": error_dict,
        }


class SuggestionFactory:
    """Factory for creating actionable suggestions.

    FR35: Proposes alternative names, rename-first strategy, different targets
    """

    @staticmethod
    def for_name_conflict(
        conflicting_name: str,
        alternatives: list[str] | None = None,
    ) -> list[Suggestion]:
        """Generate suggestions for name conflict errors."""
        suggestions = [
            Suggestion(
                action="use_alternative_name",
                description=f"Choose a different name that doesn't conflict with '{conflicting_name}'",
                example=f"new_name instead of {conflicting_name}",
            ),
            Suggestion(
                action="rename_first",
                description=f"Rename the existing '{conflicting_name}' before creating a new one",
                example=f"RENAME target='{conflicting_name}' new_name='old_{conflicting_name}'",
            ),
        ]

        if alternatives:
            suggestions.insert(
                0,
                Suggestion(
                    action="suggested_names",
                    description="Use one of these available names",
                    example=", ".join(alternatives[:3]),
                ),
            )

        return suggestions

    @staticmethod
    def for_target_not_found(
        target: str,
        similar: list[str] | None = None,
    ) -> list[Suggestion]:
        """Generate suggestions for target not found errors."""
        suggestions = [
            Suggestion(
                action="verify_target",
                description="Use the query tool to find the correct target ID",
                example=f"query pattern='*' to list all nodes",
            ),
        ]

        if similar:
            suggestions.insert(
                0,
                Suggestion(
                    action="similar_targets",
                    description="Did you mean one of these?",
                    example=", ".join(similar[:3]),
                ),
            )

        return suggestions

    @staticmethod
    def for_scope_violation(
        target: str,
        current_scope: str,
        required_access: str = "public",
    ) -> list[Suggestion]:
        """Generate suggestions for scope violation errors."""
        return [
            Suggestion(
                action="make_public",
                description=f"Make '{target}' public before moving/accessing",
                example=f"UPDATE target='{target}' property='visibility' value='public'",
            ),
            Suggestion(
                action="different_target",
                description=f"Move to a scope where '{target}' is accessible",
                example=f"Choose a scope within '{current_scope}'",
            ),
        ]

    @staticmethod
    def for_unknown_operator(
        attempted: str,
        available: list[str],
    ) -> list[Suggestion]:
        """Generate suggestions for unknown operator errors."""
        # Find similar operators
        similar = [op for op in available if attempted.lower() in op.lower() or op.lower() in attempted.lower()]

        suggestions = [
            Suggestion(
                action="use_valid_operator",
                description="Use one of the available operators",
                example=", ".join(available[:5]),
            ),
        ]

        if similar:
            suggestions.insert(
                0,
                Suggestion(
                    action="did_you_mean",
                    description="Similar operators found",
                    example=similar[0],
                ),
            )

        return suggestions

    @staticmethod
    def for_parse_error(
        file: str,
        line: int | None = None,
    ) -> list[Suggestion]:
        """Generate suggestions for parse errors."""
        return [
            Suggestion(
                action="fix_syntax",
                description="Fix the syntax error in the source file",
                example=f"Check {file}" + (f" around line {line}" if line else ""),
            ),
            Suggestion(
                action="validate_file",
                description="Ensure the file is valid Python",
                example="python -m py_compile <file>",
            ),
        ]


def create_error_response(
    code: ErrorCode,
    message: str,
    phase: ViolationType = ViolationType.INTERNAL,
    details: ErrorDetails | None = None,
    suggestions: list[Suggestion] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Create a structured error response.

    This is the primary factory function for creating error responses
    that meet all FR33-FR38 requirements.

    Args:
        code: The error code (from ErrorCode enum)
        message: Human-readable error message
        phase: The phase where error occurred
        details: Specific error details
        suggestions: Actionable suggestions for resolution
        **extra: Additional fields to include in error dict

    Returns:
        MCP-formatted error response dict
    """
    error = StructuredError(
        code=code,
        message=message,
        phase=phase,
        details=details,
        suggestions=tuple(suggestions) if suggestions else (),
    )

    response = error.to_response()

    # Add extra fields
    if extra:
        response["error"].update(extra)

    return response
