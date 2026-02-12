"""
CLI wrapper for graph-transform MCP tools.

Usage:
    gt spec [OPERATOR]           Show operator specifications
    gt query PATH [OPTIONS]      Query nodes in the code graph
    gt plan PATH -o OP -p PARAMS Create a transformation plan
    gt verify PATH               Verify graph invariants

This CLI wraps the MCP tool functions for use in bash-based agents.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from graph_transform.mcp.tools.spec import spec_tool
from graph_transform.mcp.tools.query import query_tool
from graph_transform.mcp.tools.plan import plan_tool
from graph_transform.mcp.tools.verify import verify_tool


def format_output(result: dict[str, Any], compact: bool = False) -> str:
    """Format result as JSON string."""
    if compact:
        return json.dumps(result, separators=(",", ":"))
    return json.dumps(result, indent=2)


def cmd_spec(args: argparse.Namespace) -> int:
    """Handle spec command."""
    params = {}
    if args.operator:
        params["operator"] = args.operator

    result = spec_tool(params)

    if args.compact and not args.operator:
        # Compact human-readable format for agent consumption
        lines = []

        def format_op(op: dict) -> str:
            name = op["name"]
            desc = op.get("description", "")[:50]
            req_params = [p["name"] for p in op.get("required_params", [])]
            opt_params = [p["name"] for p in op.get("optional_params", [])]
            params_str = ", ".join(req_params + [f"[{p}]" for p in opt_params])
            return f"  {name}: {desc}... ({params_str})"

        if "primitives" in result:
            lines.append("PRIMITIVES:")
            for op in result["primitives"]:
                lines.append(format_op(op))

        if "compositions" in result:
            lines.append("\nCOMPOSITIONS:")
            for op in result["compositions"]:
                lines.append(format_op(op))

        print("\n".join(lines))
    else:
        print(format_output(result, args.compact))

    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Handle query command."""
    params: dict[str, Any] = {"path": args.path}
    if args.pattern:
        params["pattern"] = args.pattern
    if args.kind:
        params["kind"] = args.kind
    if args.file:
        params["file"] = args.file

    result = query_tool(params)
    print(format_output(result, args.compact))

    return 0 if result.get("status") == "ok" else 1


def cmd_plan(args: argparse.Namespace) -> int:
    """Handle plan command."""
    # Parse params from JSON string
    try:
        params_dict = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        print(json.dumps({
            "status": "error",
            "error": {
                "code": "INVALID_JSON",
                "message": f"Failed to parse --params: {e}",
            }
        }))
        return 1

    params = {
        "path": args.path,
        "operator": args.operator,
        "params": params_dict,
    }

    if args.no_verify:
        params["verify"] = False

    result = plan_tool(params)
    print(format_output(result, args.compact))

    return 0 if result.get("status") == "ok" else 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Handle verify command."""
    params: dict[str, Any] = {}
    if args.path:
        params["path"] = args.path
    if args.graph:
        params["graph"] = args.graph
    if args.layer:
        params["layer"] = args.layer

    result = verify_tool(params)
    print(format_output(result, args.compact))

    return 0 if result.get("valid", False) else 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    # Parent parser for common arguments
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--compact", "-c",
        action="store_true",
        help="Compact output format",
    )

    parser = argparse.ArgumentParser(
        prog="gt",
        description="Graph-transform CLI for verified code transformations",
        parents=[parent_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # spec command
    spec_parser = subparsers.add_parser(
        "spec",
        help="Show operator specifications",
        parents=[parent_parser],
    )
    spec_parser.add_argument(
        "operator",
        nargs="?",
        help="Specific operator to show details for",
    )
    spec_parser.set_defaults(func=cmd_spec)

    # query command
    query_parser = subparsers.add_parser(
        "query",
        help="Query nodes in the code graph",
        parents=[parent_parser],
    )
    query_parser.add_argument(
        "path",
        help="File or directory path to query",
    )
    query_parser.add_argument(
        "--pattern", "-p",
        help="Name pattern to match (glob or re: prefix for regex)",
    )
    query_parser.add_argument(
        "--kind", "-k",
        help="Node kind filter (function, class, module, etc.)",
    )
    query_parser.add_argument(
        "--file", "-f",
        help="File path filter (glob pattern)",
    )
    query_parser.set_defaults(func=cmd_query)

    # plan command
    plan_parser = subparsers.add_parser(
        "plan",
        help="Create a transformation plan",
        parents=[parent_parser],
    )
    plan_parser.add_argument(
        "path",
        help="File or directory path to transform",
    )
    plan_parser.add_argument(
        "--operator", "-o",
        required=True,
        help="Operator name (RENAME, MOVE, EXTRACT, etc.)",
    )
    plan_parser.add_argument(
        "--params", "-p",
        default="{}",
        help="Operator parameters as JSON string",
    )
    plan_parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip verification after planning",
    )
    plan_parser.set_defaults(func=cmd_plan)

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify graph invariants",
        parents=[parent_parser],
    )
    verify_parser.add_argument(
        "path",
        nargs="?",
        help="File or directory path to verify",
    )
    verify_parser.add_argument(
        "--graph", "-g",
        help="Path to graph JSON file to verify",
    )
    verify_parser.add_argument(
        "--layer", "-l",
        help="Specific layer to verify (SCHEMA, SCOPE, REFERENCE, etc.)",
    )
    verify_parser.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)

    # Add compact flag to args if not set by subparser
    if not hasattr(args, "compact"):
        args.compact = False

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
