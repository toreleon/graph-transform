"""I/O, visualization, and source parsing."""

from .builder import build_graph_from_source
from .serialization import (
    format_result_json,
    load_graph,
    load_json,
    save_graph,
    validate_graph_json,
)
from .sqlite_storage import SQLiteGraphStore

__all__ = [
    "build_graph_from_source",
    "format_result_json",
    "load_graph",
    "load_json",
    "save_graph",
    "validate_graph_json",
    "SQLiteGraphStore",
]

# Visualization is optional (requires graphviz)
try:
    from .visualization import diff_edges, diff_nodes, render_graph

    __all__ += ["diff_edges", "diff_nodes", "render_graph"]
except ImportError:
    pass
