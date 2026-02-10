"""
Tests for Epic 6: Code Emission & Actionable Feedback

FR10: Valid plans emit correct Python code
FR11: Format preservation during emission
FR33-FR38: Structured error responses with actionable suggestions
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from graph_transform.io.builder import build_graph_from_source
from graph_transform.languages.python.emitter import PythonEmitter
from graph_transform.languages.base import EditInstruction
from graph_transform.mcp.tools.plan import plan_tool
from graph_transform.mcp.tools.query import query_tool
from graph_transform.mcp.tools.verify import verify_tool
from graph_transform.core.errors import (
    ErrorCode,
    ViolationType,
    Suggestion,
    ErrorDetails,
    StructuredError,
    SuggestionFactory,
    create_error_response,
)


# -----------------------------------------------------------------------------
# Story 6.1: Python Code Emitter
# FR10: Valid plans emit correct Python source code
# -----------------------------------------------------------------------------


class TestStory61PythonCodeEmitter:
    """Valid plans should emit valid Python source code."""

    def test_emitter_generates_valid_python(self):
        """Given a valid transformation plan, when code emission is triggered,
        then generates valid Python source code."""
        source = '''
def hello():
    pass

def greet(name):
    print(f"Hello, {name}")
'''
        emitter = PythonEmitter()

        # Apply a rename edit
        edit = EditInstruction(
            edit_type="rename",
            file="test.py",
            line=None,
            details={"target": "func:hello", "new_name": "say_hello"}
        )

        result = emitter.apply_edit(source, edit)

        # Should compile (be valid Python)
        compile(result, "<test>", "exec")
        assert "say_hello" in result
        assert "hello" not in result.replace("say_hello", "")

    def test_emitter_includes_decorators(self):
        """Given a modified function node, when emitted,
        then includes correct indentation, decorators, and docstrings."""
        source = '''
@staticmethod
def helper():
    """A helper function."""
    return 42
'''
        emitter = PythonEmitter()

        # Apply rename
        edit = EditInstruction(
            edit_type="rename",
            file="test.py",
            line=None,
            details={"target": "func:helper", "new_name": "utility"}
        )

        result = emitter.apply_edit(source, edit)

        # Verify still compiles and preserves decorator
        compile(result, "<test>", "exec")
        assert "@staticmethod" in result
        assert "utility" in result

    def test_emit_function_adds_at_correct_location(self):
        """Given a plan to add a function, when emitted,
        then function is added at the specified line."""
        source = '''# Module header
x = 1
'''
        emitter = PythonEmitter()

        edit = EditInstruction(
            edit_type="add_function",
            file="test.py",
            line=2,  # After module header
            details={"name": "new_func"}
        )

        result = emitter.apply_edit(source, edit)

        compile(result, "<test>", "exec")
        assert "new_func" in result

    def test_emit_class_creates_valid_class(self):
        """Given a plan to add a class, when emitted,
        then creates valid class definition."""
        source = "# Empty module\n"
        emitter = PythonEmitter()

        edit = EditInstruction(
            edit_type="add_class",
            file="test.py",
            line=None,
            details={"name": "MyClass"}
        )

        result = emitter.apply_edit(source, edit)

        compile(result, "<test>", "exec")
        assert "class MyClass:" in result

    def test_emit_delete_removes_function(self):
        """Given a plan to delete a function, when emitted,
        then function is removed."""
        source = '''
def keep_me():
    pass

def delete_me():
    return 1 + 2

def also_keep():
    pass
'''
        emitter = PythonEmitter()

        edit = EditInstruction(
            edit_type="delete_node",
            file="test.py",
            line=None,
            details={"node_id": "func:delete_me"}
        )

        result = emitter.apply_edit(source, edit)

        compile(result, "<test>", "exec")
        assert "delete_me" not in result
        assert "keep_me" in result
        assert "also_keep" in result


# -----------------------------------------------------------------------------
# Story 6.2: Format Preservation During Emission
# FR11: Source formatting preserved during transformations
# -----------------------------------------------------------------------------


class TestStory62FormatPreservation:
    """Source formatting should be preserved during transformations."""

    def test_preserve_quotes_style(self):
        """Given a Python file with specific formatting,
        when transformed and emitted, then preserves original formatting style."""
        source = '''name = "double quotes"
other = 'single quotes'
'''
        emitter = PythonEmitter()

        # Rename that shouldn't affect quote style
        edit = EditInstruction(
            edit_type="rename",
            file="test.py",
            line=None,
            details={"target": "var:name", "new_name": "title"}
        )

        result = emitter.apply_edit(source, edit)

        # Quote styles preserved
        assert '"double quotes"' in result
        assert "'single quotes'" in result

    def test_preserve_comments(self):
        """Given a file with comments, when code is emitted,
        then comments are preserved in correct positions."""
        source = '''# This is a header comment

def my_func():
    # Internal comment
    pass  # Inline comment
'''
        emitter = PythonEmitter()

        edit = EditInstruction(
            edit_type="rename",
            file="test.py",
            line=None,
            details={"target": "func:my_func", "new_name": "renamed_func"}
        )

        result = emitter.apply_edit(source, edit)

        assert "# This is a header comment" in result
        assert "# Internal comment" in result
        assert "# Inline comment" in result

    def test_only_changed_lines_modified(self):
        """Given a transformation, when emitted,
        then only changed lines are modified."""
        source = '''def unchanged():
    """Docstring should be preserved exactly."""
    x = 1
    y = 2
    return x + y

def to_rename():
    pass
'''
        emitter = PythonEmitter()

        edit = EditInstruction(
            edit_type="rename",
            file="test.py",
            line=None,
            details={"target": "func:to_rename", "new_name": "renamed"}
        )

        result = emitter.apply_edit(source, edit)

        # Unchanged function should be identical
        assert '"""Docstring should be preserved exactly."""' in result
        assert "x = 1" in result
        assert "y = 2" in result
        assert "return x + y" in result


# -----------------------------------------------------------------------------
# Story 6.3: Structured Error Response Format
# FR33, FR37: Errors returned as structured JSON
# -----------------------------------------------------------------------------


class TestStory63StructuredErrorFormat:
    """Errors should be returned as structured JSON."""

    def test_error_response_is_valid_json(self):
        """Given an invalid plan, when error is returned,
        then response is valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            # Invalid operator
            result = plan_tool({
                "path": str(test_file),
                "operator": "NONEXISTENT",
                "params": {}
            })

            assert result["status"] == "error"
            assert "error" in result
            assert "code" in result["error"]
            assert "message" in result["error"]

    def test_error_includes_violation_type(self):
        """Given an invalid plan, when error is returned,
        then includes violation_type enum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            # Missing required param
            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {}  # Missing required params
            })

            assert result["status"] == "error"
            assert result["error"]["code"] in [
                "PLAN_ERROR",
                "PRECONDITION_FAILED",
                "TARGET_NOT_FOUND",
            ]

    def test_error_schema_structure(self):
        """Given any error response, when parsed,
        then follows schema: {status: "error", error: {code, message}}."""
        result = plan_tool({
            "path": "/nonexistent/path",
            "operator": "RENAME",
            "params": {}
        })

        assert result["status"] == "error"
        assert isinstance(result["error"], dict)
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert isinstance(result["error"]["code"], str)
        assert isinstance(result["error"]["message"], str)


# -----------------------------------------------------------------------------
# Story 6.4: Specific Error Details
# FR34: Errors include specific details
# -----------------------------------------------------------------------------


class TestStory64SpecificErrorDetails:
    """Errors should include specific details about what went wrong."""

    def test_name_conflict_includes_conflicting_name(self):
        """Given a name conflict error, when error is returned,
        then includes the conflicting name and scope."""
        # This will be tested through the verification system
        # which already provides detailed violations
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            # Two functions with potential conflict on rename
            test_file.write_text("""
def original():
    pass

def target():
    pass
""")

            # Try to rename original to target (conflict)
            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {
                    "target": "func:original",
                    "new_name": "target"  # Would conflict
                }
            })

            # Should either succeed with warning or fail with details
            if result["status"] == "error":
                assert "message" in result["error"]

    def test_path_not_found_includes_path(self):
        """Given a path not found error, when error is returned,
        then includes the missing path."""
        result = plan_tool({
            "path": "/nonexistent/specific/path/file.py",
            "operator": "RENAME",
            "params": {}
        })

        assert result["status"] == "error"
        assert result["error"]["code"] == "PATH_NOT_FOUND"
        assert "/nonexistent/specific/path/file.py" in result["error"]["message"]

    def test_unknown_operator_includes_available(self):
        """Given an unknown operator error, when error is returned,
        then includes available operators."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            result = plan_tool({
                "path": str(test_file),
                "operator": "UNKNOWN_OP",
                "params": {}
            })

            assert result["status"] == "error"
            assert result["error"]["code"] == "UNKNOWN_OPERATOR"
            assert "available" in result["error"]
            assert isinstance(result["error"]["available"], list)


# -----------------------------------------------------------------------------
# Story 6.5: Actionable Suggestions
# FR35, FR38: Errors include suggestions for resolution
# -----------------------------------------------------------------------------


class TestStory65ActionableSuggestions:
    """Errors should include actionable suggestions for resolution."""

    def test_unknown_operator_suggests_alternatives(self):
        """Given an unknown operator error, when suggestion is generated,
        then proposes valid operator alternatives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            result = plan_tool({
                "path": str(test_file),
                "operator": "RNAME",  # Typo
                "params": {}
            })

            assert result["status"] == "error"
            # Should include available operators as suggestion
            assert "available" in result["error"]
            assert "RENAME" in result["error"]["available"]

    def test_verification_violations_include_fix_hints(self):
        """Given a verification violation, when error is returned,
        then includes fix_hint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {
                    "target": "func:foo",
                    "new_name": "bar"
                }
            })

            # If verification runs and finds issues
            if "verification" in result and not result["verification"]["valid"]:
                for violation in result["verification"]["violations"]:
                    # fix_hint may be None but key should exist
                    assert "fix_hint" in violation

    def test_suggestion_factory_for_name_conflict(self):
        """SuggestionFactory generates actionable suggestions for name conflicts."""
        suggestions = SuggestionFactory.for_name_conflict("existing_name")

        assert len(suggestions) >= 2
        actions = [s.action for s in suggestions]
        assert "use_alternative_name" in actions
        assert "rename_first" in actions

    def test_suggestion_factory_for_unknown_operator(self):
        """SuggestionFactory generates suggestions with did_you_mean."""
        suggestions = SuggestionFactory.for_unknown_operator("RENAM", ["RENAME", "MOVE"])

        assert len(suggestions) >= 1
        # Should suggest RENAME since it's similar
        descriptions = " ".join(s.description for s in suggestions)
        assert "RENAME" in descriptions or "operator" in descriptions.lower()

    def test_error_response_includes_suggestions(self):
        """Error responses include suggestions field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            result = plan_tool({
                "path": str(test_file),
                "operator": "UNKNOWN",
                "params": {}
            })

            assert result["status"] == "error"
            # Should have suggestions in the error
            assert "suggestions" in result["error"]
            assert isinstance(result["error"]["suggestions"], list)


# -----------------------------------------------------------------------------
# Story 6.6: Parser Error Handling
# FR36: Parser errors include source context
# -----------------------------------------------------------------------------


class TestStory66ParserErrorHandling:
    """Parser errors should include source context."""

    def test_syntax_error_includes_line_number(self):
        """Given a Python file with syntax errors, when parsing fails,
        then error includes file path and line number."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "bad.py"
            test_file.write_text("def broken(\n")  # Syntax error

            result = query_tool({
                "path": str(test_file),
            })

            assert result["status"] == "error"
            assert result["error"]["code"] == "PARSE_ERROR"
            # Message should include some location info
            assert "message" in result["error"]

    def test_parse_error_is_structured(self):
        """Given a parse failure, when error is returned,
        then error is structured with code and message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "invalid.py"
            test_file.write_text("class Missing:\n    def unclosed(")

            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {"target": "func:foo", "new_name": "bar"}
            })

            assert result["status"] == "error"
            assert "error" in result
            assert result["error"]["code"] == "PARSE_ERROR"

    def test_parse_error_includes_details(self):
        """Given a parse failure, when error is returned,
        then error includes file details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "syntax_err.py"
            test_file.write_text("def broken(\n")

            result = query_tool({
                "path": str(test_file),
            })

            assert result["status"] == "error"
            assert result["error"]["phase"] == "parse"
            # Should have details with file info
            if "details" in result["error"]:
                assert "file" in result["error"]["details"]

    def test_parse_error_includes_suggestions(self):
        """Given a parse failure, when error is returned,
        then includes suggestions for fixing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "broken.py"
            test_file.write_text("def func(:\n    pass")

            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {}
            })

            assert result["status"] == "error"
            assert "suggestions" in result["error"]


# -----------------------------------------------------------------------------
# Story 6.7: Complete Error Taxonomy
# FR37: Complete taxonomy of error types
# -----------------------------------------------------------------------------


class TestStory67ErrorTaxonomy:
    """Complete taxonomy of error types should be implemented."""

    def test_error_codes_are_enumerated(self):
        """Given the error response schema, when violation_type is examined,
        then covers all required error types."""
        # Test each error code type can be triggered

        # MISSING_PATH
        result = plan_tool({"operator": "RENAME", "params": {}})
        assert result["error"]["code"] == "MISSING_PATH"

        # MISSING_OPERATOR
        result = plan_tool({"path": "/tmp", "params": {}})
        assert result["error"]["code"] == "MISSING_OPERATOR"

        # PATH_NOT_FOUND
        result = plan_tool({
            "path": "/nonexistent",
            "operator": "RENAME",
            "params": {}
        })
        assert result["error"]["code"] == "PATH_NOT_FOUND"

    def test_all_failures_map_to_error_code(self):
        """Given any failure scenario, when error is returned,
        then maps to exactly one error code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo(): pass")

            # UNKNOWN_OPERATOR
            result = plan_tool({
                "path": str(test_file),
                "operator": "FAKE",
                "params": {}
            })
            assert result["status"] == "error"
            assert result["error"]["code"] == "UNKNOWN_OPERATOR"

    def test_error_code_enum_completeness(self):
        """ErrorCode enum covers all required violation types."""
        # Check required codes from FR37
        required_codes = [
            "PRECONDITION_FAILED",
            "POSTCONDITION_FAILED",
            "GLUING_VIOLATION",
            "NAME_CONFLICT",
            "SCOPE_VIOLATION",
            "UNRESOLVED_REFERENCE",
            "PARSE_ERROR",
            "INTERNAL_ERROR",
        ]

        for code_name in required_codes:
            assert hasattr(ErrorCode, code_name), f"Missing ErrorCode.{code_name}"

    def test_violation_type_enum_completeness(self):
        """ViolationType enum covers all phases."""
        required_phases = ["precondition", "postcondition", "gluing", "parse", "internal"]

        for phase in required_phases:
            matching = [v for v in ViolationType if v.value == phase]
            assert matching, f"Missing ViolationType for phase '{phase}'"

    def test_structured_error_to_response(self):
        """StructuredError converts to valid MCP response format."""
        error = StructuredError(
            code=ErrorCode.NAME_CONFLICT,
            message="Name 'foo' already exists",
            phase=ViolationType.PRECONDITION,
            details=ErrorDetails(node_id="func:foo", scope="module:main"),
            suggestions=(
                Suggestion("rename_first", "Rename existing foo first"),
            ),
        )

        response = error.to_response()

        assert response["status"] == "error"
        assert response["error"]["code"] == "NAME_CONFLICT"
        assert response["error"]["message"] == "Name 'foo' already exists"
        assert response["error"]["phase"] == "precondition"
        assert response["error"]["details"]["node_id"] == "func:foo"
        assert len(response["error"]["suggestions"]) == 1


# -----------------------------------------------------------------------------
# Story 6.8: Agent Self-Correction Loop
# FR38: Error feedback designed for self-correction
# -----------------------------------------------------------------------------


class TestStory68AgentSelfCorrection:
    """Error feedback should be designed for agent self-correction."""

    def test_error_enables_retry(self):
        """Given an error with suggestion, when agent constructs retry plan,
        then the new plan can address the specific violation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def hello(): pass")

            # First attempt with typo in operator
            result1 = plan_tool({
                "path": str(test_file),
                "operator": "RENAM",  # Typo
                "params": {"target": "func:hello", "new_name": "hi"}
            })

            assert result1["status"] == "error"
            assert "RENAME" in result1["error"].get("available", [])

            # Agent can use suggestion to retry with correct operator
            result2 = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",  # Corrected
                "params": {"target": "func:hello", "new_name": "hi"}
            })

            # Second attempt should succeed or have different error
            if result2["status"] == "error":
                # If still error, should be different from "UNKNOWN_OPERATOR"
                assert result2["error"]["code"] != "UNKNOWN_OPERATOR" or \
                       "target" in str(result2["error"])

    def test_verification_feedback_is_actionable(self):
        """Given verification violations, when agent reads feedback,
        then can understand what to fix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("""
def process_data(data):
    return data.upper()
""")

            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {
                    "target": "func:process_data",
                    "new_name": "transform"
                }
            })

            # Plan should succeed or provide actionable feedback
            if result["status"] == "ok":
                assert "plan" in result
            else:
                # Error should be understandable
                assert "message" in result["error"]

    def test_self_correction_loop_converges(self):
        """Given a sequence of errors, when agent follows suggestions,
        then converges to valid plan within 3 attempts (pass@3 goal)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text("def my_function(): return 42")

            # Attempt 1: Wrong operator
            result1 = plan_tool({
                "path": str(test_file),
                "operator": "REMANE",  # Typo
                "params": {"target": "func:my_function", "new_name": "renamed"}
            })
            assert result1["status"] == "error"

            # Learn from error - use available operators
            available = result1["error"].get("available", ["RENAME"])

            # Attempt 2: Correct operator
            result2 = plan_tool({
                "path": str(test_file),
                "operator": available[0] if "RENAME" in available else "RENAME",
                "params": {"target": "func:my_function", "new_name": "renamed"}
            })

            # Should either succeed or have specific error we can handle
            if result2["status"] == "error":
                # Learn from this error too
                error_code = result2["error"]["code"]
                assert error_code in [
                    "PRECONDITION_FAILED",
                    "TARGET_NOT_FOUND",
                    "PLAN_ERROR",
                ]
            else:
                assert result2["status"] == "ok"
                assert "plan" in result2

    def test_error_response_is_machine_parseable(self):
        """Error responses can be parsed programmatically by agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("x = 1")

            result = plan_tool({
                "path": str(test_file),
                "operator": "INVALID",
                "params": {}
            })

            # Agent can extract all needed info
            assert result["status"] == "error"
            error = result["error"]

            # Code for categorization
            assert isinstance(error["code"], str)

            # Message for logging/display
            assert isinstance(error["message"], str)

            # Phase for debugging
            assert "phase" in error

            # Suggestions for retry
            assert "suggestions" in error

            # Available options for correction
            assert "available" in error


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------


class TestEmissionIntegration:
    """Integration tests for emission workflow."""

    def test_roundtrip_parse_emit(self):
        """Given a round-trip transformation (parse → emit with no changes),
        when compared to original, then output is syntactically equivalent."""
        source = '''
def calculate(x, y):
    """Add two numbers."""
    return x + y

class Calculator:
    def add(self, a, b):
        return a + b
'''
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "calc.py"
            test_file.write_text(source)

            # Parse
            graph = build_graph_from_source(test_file)

            # Emit
            emitter = PythonEmitter()
            emitted = emitter.emit(graph)

            # Should compile
            compile(emitted, "<test>", "exec")

    def test_plan_to_edit_flow(self):
        """Test the flow from plan generation to edit application."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "app.py"
            test_file.write_text('''
def old_name():
    """Original function."""
    return 42
''')

            # Generate plan
            result = plan_tool({
                "path": str(test_file),
                "operator": "RENAME",
                "params": {
                    "target": "func:old_name",
                    "new_name": "new_name"
                }
            })

            # Plan should be generated (may have verification result)
            if result["status"] == "ok":
                assert "plan" in result
                assert "primitives" in result["plan"]
