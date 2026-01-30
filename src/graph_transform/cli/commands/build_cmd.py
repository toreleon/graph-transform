"""
build -- Build a TypedGraph from Python source code.
"""

from __future__ import annotations

import sys

import click

from graph_transform.cli.formatting import print_error, print_graph_summary, print_success
from graph_transform.io.builder import build_graph_from_source, build_graph_from_files
from graph_transform.io.serialization import save_graph


@click.command("build")
@click.argument("source_path", type=click.Path(exists=True), required=False)
@click.option(
    "--files", "-f",
    multiple=True,
    type=click.Path(exists=True),
    help="Specific Python files to include (can be repeated).",
)
@click.option(
    "--stdin",
    is_flag=True,
    help="Read file list from stdin (one file per line, pipe from grep).",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output JSON file (default: stdout).",
)
@click.option("--verbose", "-v", is_flag=True, help="Show graph summary after building.")
def build(
    source_path: str | None,
    files: tuple[str, ...],
    stdin: bool,
    output: str | None,
    verbose: bool,
) -> None:
    """Build a TypedGraph from Python source code.
    
    Three input modes:
    
    \b
    1. Directory/file path (default):
       graph-transform build src/ -o graph.json
    
    \b
    2. Specific files via --files:
       graph-transform build --files foo.py --files bar.py -o graph.json
    
    \b
    3. Pipe file list from grep via --stdin:
       grep -rl "get_group_vars" src/ | graph-transform build --stdin -o graph.json
    """
    file_list: list[str] = []
    
    # Determine input mode
    if stdin:
        # Read file list from stdin
        if source_path or files:
            print_error("Cannot use --stdin with SOURCE_PATH or --files")
            sys.exit(2)
        for line in sys.stdin:
            line = line.strip()
            if line and line.endswith(".py"):
                file_list.append(line)
        if not file_list:
            print_error("No Python files provided via stdin")
            sys.exit(2)
    elif files:
        # Use explicit file list
        if source_path:
            print_error("Cannot use SOURCE_PATH with --files")
            sys.exit(2)
        file_list = list(files)
    elif source_path:
        # Traditional directory/file mode
        pass
    else:
        print_error("Must provide SOURCE_PATH, --files, or --stdin")
        sys.exit(2)
    
    try:
        if file_list:
            graph = build_graph_from_files(file_list)
            if verbose:
                print_graph_summary(graph, title=f"Built from {len(file_list)} files")
        else:
            graph = build_graph_from_source(source_path)
            if verbose:
                print_graph_summary(graph, title=f"Built from {source_path}")
    except (FileNotFoundError, SyntaxError, ValueError) as e:
        print_error(str(e))
        sys.exit(2)

    save_graph(graph, output)

    if output:
        print_success(f"Graph written to {output}")
