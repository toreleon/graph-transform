"""
spec -- Output machine-readable specification of graph-transform capabilities.

Designed for LLM agents: one command gives everything needed to use the tool.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from graph_transform.cli.operator_metadata import (
    CATEGORIES,
    OPERATOR_DESCRIPTIONS,
    OPERATOR_EXAMPLES,
    OPERATOR_PARAMS,
    get_all_operators,
)


def _classify_param(description: str) -> bool:
    """Return True if param is required based on its description."""
    return "(required)" in description.lower()


def _build_operator_spec(op) -> dict[str, Any]:
    """Build spec entry for a single operator."""
    params_raw = OPERATOR_PARAMS.get(op, {})
    params_spec = {}
    for pname, pdesc in params_raw.items():
        # Strip "(required)"/"(optional)" suffix for clean description
        clean = pdesc
        for suffix in (" (required)", " (optional)"):
            clean = clean.replace(suffix, "")
        params_spec[pname] = {
            "description": clean,
            "required": _classify_param(pdesc),
        }

    entry: dict[str, Any] = {
        "name": op.value,
        "category": _get_category(op),
        "description": OPERATOR_DESCRIPTIONS.get(op, ""),
        "params": params_spec,
    }

    example_str = OPERATOR_EXAMPLES.get(op)
    if example_str:
        try:
            entry["example"] = json.loads(example_str)
        except json.JSONDecodeError:
            entry["example"] = example_str

    return entry


def _get_category(op) -> str:
    for cat, ops in CATEGORIES.items():
        if op in ops:
            return cat
    return "other"


def _build_compact_operator(op) -> dict[str, Any]:
    """Build a one-line operator summary for compact mode."""
    params_raw = OPERATOR_PARAMS.get(op, {})
    required = [k for k, v in params_raw.items() if _classify_param(v)]
    optional = [k for k, v in params_raw.items() if not _classify_param(v)]
    entry: dict[str, Any] = {
        "name": op.value,
        "description": OPERATOR_DESCRIPTIONS.get(op, ""),
        "required_params": required,
    }
    if optional:
        entry["optional_params"] = optional
    return entry


def _build_full_spec(compact: bool = False) -> dict[str, Any]:
    """Build the complete spec JSON.

    compact=True returns a much shorter spec (~150 lines) with operators
    grouped by category showing only names and required params.  The agent
    can then call ``graph-transform spec <operator>`` for full details.
    """
    if compact:
        return _build_compact_spec()

    return _build_verbose_spec()


def _build_compact_spec() -> dict[str, Any]:
    """Minimal spec for initial orientation (~100 lines of JSON)."""
    # Group operators: { category: { op_name: [required_params] } }
    operators_by_category: dict[str, dict[str, list[str]]] = {}
    for op in get_all_operators():
        cat = _get_category(op)
        params_raw = OPERATOR_PARAMS.get(op, {})
        required = [k for k, v in params_raw.items() if _classify_param(v)]
        operators_by_category.setdefault(cat, {})[op.value] = required

    return {
        "tool": "graph-transform",
        "usage": "grep -rl 'symbol' | graph-transform plan --stdin -F recipe.yaml",
        "detail_command": "graph-transform spec <operator_name>  # full params & example",
        "operators_by_category (name: [required_params])": operators_by_category,
        "recipe_format": {
            "steps": [{"op": "str", "repeat": "once|all", "params": {}}],
            "notes": "repeat: all for operators that should match every occurrence",
        },
        "common_recipes": {
            "add_param + update callers": [
                {"op": "add_param", "params": {"function_name": "F", "param_name": "P", "default_value": "V"}},
                {"op": "add_arg", "repeat": "all", "params": {"callee": "F", "arg_name": "P", "arg_value": "V"}},
            ],
            "rename_func + update calls": [
                {"op": "rename_func", "params": {"old_name": "O", "new_name": "N"}},
                {"op": "update_call", "repeat": "all", "params": {"old_callee": "O", "new_callee": "N"}},
            ],
            "rename_module + update imports": [
                {"op": "rename_module", "params": {"old_name": "pkg.old", "new_name": "pkg.new"}},
                {"op": "update_import", "repeat": "all", "params": {"old_module": "pkg.old", "new_module": "pkg.new"}},
            ],
        },
        "scoping": "Only files piped via --stdin are visible. Use grep -rl to find ALL files.",
        "limitations": [
            "move_class/move_to_module: no edit generation — handle manually, use update_import for imports",
            "Inline mode (-op/-p): first match only. Use recipe with repeat: all for multiple matches",
        ],
    }


def _build_verbose_spec() -> dict[str, Any]:
    """Full spec with all operator details, examples, and patterns."""
    operators_section = [_build_operator_spec(op) for op in get_all_operators()]

    return {
        "tool": "graph-transform",
        "version": "0.1.0",
        "description": "Algebraic graph rewriting engine for verified code refactoring",
        "commands": {
            "plan": {
                "description": "Generate refactoring edit plan from source code and operators (main command)",
                "usage": "graph-transform plan [SOURCE_PATH] [OPTIONS]",
                "options": {
                    "--stdin": "Read file paths from stdin (one per line, pipe from grep -rl)",
                    "--files/-f": "Specific Python files to include (repeatable)",
                    "--recipe/-F": "YAML recipe file defining refactoring steps",
                    "--operator/-op": "Operator name for inline mode (repeatable)",
                    "--params/-p": "JSON params matching each -op (repeatable)",
                    "--output/-o": "Output file (default: stdout)",
                    "--verbose/-v": "Show detailed progress on stderr",
                },
                "input_modes": {
                    "inline": (
                        "grep -rl 'symbol' | graph-transform plan --stdin "
                        "-op add_param -p '{\"function_name\":\"F\",\"param_name\":\"P\"}'"
                    ),
                    "recipe": (
                        "grep -rl 'symbol' | graph-transform plan --stdin -F recipe.yaml"
                    ),
                },
                "output_schema": {
                    "steps": [{
                        "step": "int",
                        "operator": "str",
                        "params": {},
                        "edits": [{
                            "type": "str (add_parameter|add_argument|rename|update_import|...)",
                            "file": "str",
                            "line": "int|null",
                        }],
                    }],
                    "summary": {"total_steps": "int", "total_edits": "int"},
                },
            },
            "list": {
                "description": "List available operators with descriptions",
                "usage": "graph-transform list [--json] [-v] [-c CATEGORY]",
            },
            "dry-run": {
                "description": "Check if operator is applicable without modifying graph",
                "usage": "graph-transform dry-run GRAPH_FILE -op OPERATOR -p PARAMS [--json]",
            },
            "build": {
                "description": "Build a code graph from Python source files",
                "usage": "graph-transform build [SOURCE_PATH] [--stdin] [-o OUTPUT]",
            },
            "verify": {
                "description": "Run invariant checks on a graph",
                "usage": "graph-transform verify GRAPH_FILE [--json] [--strict]",
            },
        },
        "operators": operators_section,
        "recipe_format": {
            "description": "YAML recipe for multi-step refactoring via graph-transform plan -F",
            "schema": {
                "steps": [{
                    "op": "operator_name (string)",
                    "repeat": "once (default) | all",
                    "params": {"key": "value"},
                }],
            },
            "notes": [
                "Use repeat: all when an operator should match every occurrence (e.g., add_arg to all call sites)",
                "Default repeat is once (first match only)",
                "--stdin expects file PATHS (one per line), NOT file contents",
            ],
        },
        "common_patterns": [
            {
                "name": "Add parameter + update call sites",
                "when": "Adding a new parameter to a function and updating all callers",
                "recipe": {"steps": [
                    {"op": "add_param", "params": {
                        "function_name": "F", "param_name": "P", "default_value": "V",
                    }},
                    {"op": "add_arg", "repeat": "all", "params": {
                        "callee": "F", "arg_name": "P", "arg_value": "V",
                    }},
                ]},
            },
            {
                "name": "Add parameter + update only direct calls",
                "when": "Adding a parameter but skipping method calls like obj.F() that share the name",
                "recipe": {"steps": [
                    {"op": "add_param", "params": {
                        "function_name": "F", "param_name": "P", "default_value": "V",
                    }},
                    {"op": "add_arg", "repeat": "all", "params": {
                        "callee": "F", "arg_name": "P", "arg_value": "V",
                        "call_type": "direct",
                    }},
                ]},
            },
            {
                "name": "Rename function + update calls",
                "when": "Renaming a function and updating all call sites",
                "recipe": {"steps": [
                    {"op": "rename_func", "params": {"old_name": "old", "new_name": "new"}},
                    {"op": "update_call", "repeat": "all", "params": {
                        "old_callee": "old", "new_callee": "new",
                    }},
                ]},
            },
            {
                "name": "Rename module + update imports",
                "when": "Renaming a module and updating all import statements",
                "recipe": {"steps": [
                    {"op": "rename_module", "params": {
                        "old_name": "pkg.old_mod", "new_name": "pkg.new_mod",
                    }},
                    {"op": "update_import", "repeat": "all", "params": {
                        "old_module": "pkg.old_mod", "new_module": "pkg.new_mod",
                    }},
                ]},
            },
            {
                "name": "Move method between classes",
                "when": "Moving a method from one class to another",
                "recipe": {"steps": [
                    {"op": "move_method", "params": {
                        "method_name": "M", "source_class": "A", "target_class": "B",
                    }},
                ]},
            },
            {
                "name": "Add field + encapsulate",
                "when": "Adding a field with getter/setter methods",
                "recipe": {"steps": [
                    {"op": "add_field", "params": {
                        "class_name": "C", "field_name": "F",
                        "field_type": "int", "default_value": "0",
                    }},
                    {"op": "encapsulate_field", "params": {
                        "class_name": "C", "field_name": "F",
                    }},
                ]},
            },
        ],
        "scoping": (
            "The graph only contains files you pipe into graph-transform plan. "
            "Files not provided are invisible. You MUST include ALL files that "
            "contain relevant definitions and usages. "
            "Use 'grep -rl \"symbol\" .' from the repo root to find all files."
        ),
        "limitations": [
            "move_class and move_to_module do not support edit generation — handle those manually after using update_import for imports",
            "Inline mode (-op/-p) applies each operator once (first match only). Use YAML recipe with repeat: all for multiple matches",
            "--stdin expects file PATHS, not file contents. Use: grep -rl 'pattern' | graph-transform plan --stdin",
        ],
        "errors": {
            "No matches found": "Operator target not in graph — check name matches source exactly; broaden grep to include more files",
            "Invariant violation": "Transformation breaks semantic rules — add missing companion operators (e.g., add_arg after add_param)",
            "No Python files provided": "stdin/grep returned no results — broaden search pattern",
            "Mismatch: N operators but M param sets": "Each -op must have a matching -p",
            "not yet supported for edit generation": "Operator modifies graph but can't generate file edits — handle manually (see limitations)",
        },
    }


@click.command("spec")
@click.argument("operator_name", required=False)
@click.option("--json", "as_json", is_flag=True, default=False, hidden=True,
              help="Output as JSON (default behaviour, accepted for compatibility).")
@click.option("--compact", is_flag=True, default=False,
              help="Shorter output: operators grouped by category with only names and required params.")
def spec(operator_name: str | None, as_json: bool, compact: bool) -> None:
    """Output machine-readable specification for LLM agents.

    \b
    Examples:
      graph-transform spec              # full spec (all operators + commands + patterns)
      graph-transform spec --compact    # shorter spec (operators grouped by category)
      graph-transform spec add_param    # spec for a single operator
    """
    if operator_name:
        # Single operator spec
        from graph_transform.cli.operator_metadata import resolve_operator

        try:
            op = resolve_operator(operator_name)
        except ValueError as e:
            sys.stderr.write(f"Error: {e}\n")
            sys.exit(2)

        data = _build_operator_spec(op)
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    else:
        # Full spec
        data = _build_full_spec(compact=compact)
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
