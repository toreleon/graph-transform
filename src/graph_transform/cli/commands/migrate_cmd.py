"""
migrate -- Migrate source code from one language to another.

Uses the transformation pipeline:
  Source → parse() → TypedGraph → MIGRATE composition → TypedGraph → emit() → Target
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from graph_transform.cli.formatting import (
    err_console,
    print_error,
    print_success,
)
from graph_transform.core.primitives import (
    Migrate,
    MigrateNaming,
    MigrateTypes,
    MigrateStructure,
)
from graph_transform.io.builder import build_graph_from_source
from graph_transform.io.serialization import save_graph
from graph_transform.languages import LanguageRegistry
from graph_transform.languages.mappings import LanguageMappings


@click.command("migrate")
@click.argument("source_path", type=click.Path(exists=True))
@click.option(
    "--to", "-t",
    "target_language",
    required=True,
    help="Target language (java, typescript, go, csharp, python).",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    required=True,
    help="Output directory for generated files.",
)
@click.option(
    "--graph-output", "-g",
    type=click.Path(),
    default=None,
    help="Optional: Save intermediate graph to file.",
)
@click.option(
    "--steps",
    type=click.Choice(["all", "naming", "types", "structure"]),
    default="all",
    help="Migration steps to apply (default: all).",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Show detailed output.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output migration report as JSON.",
)
def migrate(
    source_path: str,
    target_language: str,
    output: str,
    graph_output: str | None,
    steps: str,
    verbose: bool,
    as_json: bool,
) -> None:
    """Migrate source code to a different programming language.

    Uses the three-primitive transformation system:
      1. Parse source into TypedGraph
      2. Apply MIGRATE composition (UPDATE primitives)
      3. Emit code in target language

    Examples:

        # Migrate Python to Java
        graph-transform migrate src/models.py --to java -o ./java_output/

        # Migrate with intermediate graph saved
        graph-transform migrate src/ --to typescript -o ./ts/ -g graph.json

        # Only convert naming conventions
        graph-transform migrate src/ --to java -o ./java/ --steps naming

        # Verbose output showing all transformations
        graph-transform migrate src/ --to java -o ./java/ -v
    """
    # Validate target language
    target_lang = target_language.lower()
    if not LanguageMappings.is_registered(target_lang):
        available = ", ".join(LanguageMappings.supported_languages())
        print_error(f"Unknown target language: '{target_language}'. Available: {available}")
        sys.exit(2)

    # Check if we can emit to target language
    if not LanguageRegistry.is_registered(target_lang):
        print_error(
            f"Language '{target_language}' has mapping rules but no emitter. "
            f"Available emitters: {', '.join(LanguageRegistry.supported_languages())}"
        )
        sys.exit(2)

    report = {
        "source": source_path,
        "target_language": target_lang,
        "steps": [],
        "files_generated": [],
    }

    # Step 1: Parse source
    if verbose:
        err_console.print(f"[dim]Step 1: Parsing source...[/dim]")

    try:
        graph = build_graph_from_source(source_path)
        report["parsed"] = {
            "nodes": graph.node_count,
            "edges": graph.edge_count,
        }
        if verbose:
            err_console.print(f"  [dim]Parsed: {graph.node_count} nodes, {graph.edge_count} edges[/dim]")
    except Exception as e:
        print_error(f"Failed to parse source: {e}")
        sys.exit(2)

    # Step 2: Apply MIGRATE composition
    if verbose:
        err_console.print(f"[dim]Step 2: Applying MIGRATE transformations...[/dim]")

    try:
        if steps == "all":
            composition = Migrate(target_language=target_lang)
        elif steps == "naming":
            composition = MigrateNaming(target_language=target_lang)
        elif steps == "types":
            composition = MigrateTypes(target_language=target_lang)
        elif steps == "structure":
            composition = MigrateStructure(target_language=target_lang)

        result = composition.execute(graph)

        if not result.success:
            print_error(f"Migration failed: {result.error}")
            sys.exit(1)

        # Record transformation details
        report["transformations"] = {
            "composition": composition.name,
            "primitives_applied": len(result.primitive_results),
            "affected_nodes": len(result.affected_ids),
        }

        if verbose:
            err_console.print(f"  [dim]Applied {len(result.primitive_results)} UPDATE primitives[/dim]")
            err_console.print(f"  [dim]Affected {len(result.affected_ids)} nodes[/dim]")

            # Show some example transformations
            for i, pr in enumerate(result.primitive_results[:5]):
                if pr.metadata.get("prop") == "name":
                    old = pr.metadata.get("old_value", "?")
                    new = pr.metadata.get("new_value", "?")
                    err_console.print(f"    [dim]- Renamed: {old} → {new}[/dim]")

            if len(result.primitive_results) > 5:
                err_console.print(f"    [dim]... and {len(result.primitive_results) - 5} more[/dim]")

    except Exception as e:
        print_error(f"Migration transformation failed: {e}")
        sys.exit(1)

    # Step 3: Save intermediate graph if requested
    if graph_output:
        try:
            save_graph(graph, graph_output)
            report["graph_file"] = graph_output
            if verbose:
                err_console.print(f"[dim]Saved graph to {graph_output}[/dim]")
        except Exception as e:
            print_error(f"Failed to save graph: {e}")
            # Continue anyway

    # Step 4: Emit target language code
    if verbose:
        err_console.print(f"[dim]Step 3: Emitting {target_lang} code...[/dim]")

    try:
        adapter = LanguageRegistry.get(target_lang)

        out_path = Path(output)
        if hasattr(adapter, "emit_files"):
            files = adapter.emit_files(graph, out_path)
        else:
            content = adapter.emit(graph)
            out_path.mkdir(parents=True, exist_ok=True)
            ext = adapter.extensions[0] if adapter.extensions else ".txt"
            single_file = out_path / f"output{ext}"
            single_file.write_text(content)
            files = {single_file.name: content}

        report["files_generated"] = list(files.keys())

        if verbose:
            for filename in files:
                err_console.print(f"  [dim]Generated: {filename}[/dim]")

    except NotImplementedError as e:
        print_error(str(e))
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to emit code: {e}")
        sys.exit(1)

    # Output report
    if as_json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        print_success(
            f"Migrated to {target_lang}: "
            f"{report['transformations']['primitives_applied']} transformations, "
            f"{len(report['files_generated'])} files generated in {output}"
        )
