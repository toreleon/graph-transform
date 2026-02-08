"""
emit -- Generate source code from a TypedGraph.

Supports emitting to different languages (Python, Java, etc.)
for code migration and transformation workflows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from graph_transform.cli.formatting import err_console, print_error, print_success
from graph_transform.io.serialization import load_graph
from graph_transform.languages import LanguageRegistry


@click.command("emit")
@click.argument("graph_file", type=click.Path(exists=True))
@click.option(
    "--language", "-l",
    required=True,
    help="Target language (python, java, etc.).",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Output directory for generated files. If not specified, prints to stdout.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Show detailed output.",
)
def emit(
    graph_file: str,
    language: str,
    output: str | None,
    verbose: bool,
) -> None:
    """Generate source code from a TypedGraph.

    Reads a graph JSON file and emits source code in the target language.
    Useful for code migration (e.g., Python -> Java).

    Examples:

        # Emit Java code to directory
        graph-transform emit graph.json --language java -o ./java_output/

        # Emit Python code to stdout
        graph-transform emit graph.json --language python

        # Migrate Python to Java
        graph-transform build src/models.py -o graph.json
        graph-transform emit graph.json --language java -o ./java/
    """
    # Validate language
    if not LanguageRegistry.is_registered(language):
        available = ", ".join(LanguageRegistry.supported_languages())
        print_error(f"Unknown language: '{language}'. Available: {available}")
        sys.exit(2)

    # Load graph
    try:
        graph = load_graph(graph_file)
    except Exception as e:
        print_error(f"Failed to load graph: {e}")
        sys.exit(2)

    if verbose:
        err_console.print(
            f"[dim]Loaded graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges[/dim]"
        )

    # Get adapter
    adapter = LanguageRegistry.get(language)

    # Emit code
    try:
        if output:
            # Emit to files
            out_path = Path(output)

            # Check if adapter supports emit_files
            if hasattr(adapter, "emit_files"):
                files = adapter.emit_files(graph, out_path)
            else:
                # Fallback: emit single file
                content = adapter.emit(graph)
                out_path.mkdir(parents=True, exist_ok=True)
                ext = adapter.extensions[0] if adapter.extensions else ".txt"
                single_file = out_path / f"output{ext}"
                single_file.write_text(content)
                files = {single_file.name: content}

            if verbose:
                for filename in files:
                    err_console.print(f"  [dim]Generated: {filename}[/dim]")

            print_success(
                f"Generated {len(files)} file(s) in {output}"
            )

        else:
            # Emit to stdout
            content = adapter.emit(graph)
            sys.stdout.write(content)
            if not content.endswith("\n"):
                sys.stdout.write("\n")

    except NotImplementedError as e:
        print_error(str(e))
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to emit code: {e}")
        sys.exit(1)
