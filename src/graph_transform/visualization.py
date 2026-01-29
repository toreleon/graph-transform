"""
Graph Visualization

Render TypedGraph instances as SVG/PNG/PDF using Graphviz.
Graphviz is an optional dependency -- import errors are caught
and reported with install instructions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph

if TYPE_CHECKING:
    import graphviz


# =============================================================================
# Styles
# =============================================================================

NODE_STYLES: dict[NodeType, dict[str, str]] = {
    NodeType.MODULE:    {"shape": "folder",        "fillcolor": "#4A90D9", "fontcolor": "white"},
    NodeType.CLASS:     {"shape": "box3d",         "fillcolor": "#E8A838", "fontcolor": "white"},
    NodeType.FUNCTION:  {"shape": "component",     "fillcolor": "#50B86C", "fontcolor": "white"},
    NodeType.FIELD:     {"shape": "note",          "fillcolor": "#9B59B6", "fontcolor": "white"},
    NodeType.PARAMETER: {"shape": "ellipse",       "fillcolor": "#F5F5F5", "fontcolor": "#333333"},
    NodeType.CALL:      {"shape": "cds",           "fillcolor": "#E74C3C", "fontcolor": "white"},
    NodeType.ARGUMENT:  {"shape": "ellipse",       "fillcolor": "#FDE8E8", "fontcolor": "#333333"},
    NodeType.IMPORT:    {"shape": "parallelogram", "fillcolor": "#2C3E50", "fontcolor": "white"},
}

EDGE_STYLES: dict[EdgeType, dict[str, str]] = {
    EdgeType.CONTAINS_METHOD: {"color": "#50B86C", "style": "bold",   "label": "method"},
    EdgeType.CONTAINS_FIELD:  {"color": "#9B59B6", "style": "bold",   "label": "field"},
    EdgeType.HAS_PARAMETER:   {"color": "#888888", "style": "solid",  "label": "param"},
    EdgeType.HAS_ARGUMENT:    {"color": "#888888", "style": "dashed", "label": "arg"},
    EdgeType.CALLS:           {"color": "#E74C3C", "style": "bold",   "label": "calls"},
    EdgeType.INHERITS:        {"color": "#E8A838", "style": "bold",   "label": "inherits"},
    EdgeType.DEFINED_IN:      {"color": "#4A90D9", "style": "dashed", "label": "in"},
    EdgeType.CALLER_OF:       {"color": "#CC6666", "style": "dotted", "label": "caller_of"},
    EdgeType.IMPORTS:         {"color": "#2C3E50", "style": "dashed", "label": "imports"},
    EdgeType.REFERENCES:      {"color": "#666666", "style": "dotted", "label": "refs"},
}


def _ensure_graphviz() -> Any:
    """Lazy-import graphviz; raise a clear error if missing."""
    try:
        import graphviz as gv
        return gv
    except ImportError:
        raise ImportError(
            "graphviz is required for visualization.\n"
            "Install with:  pip install 'graphviz>=0.20'\n"
            "You also need the Graphviz system package:\n"
            "  - macOS:  brew install graphviz\n"
            "  - Ubuntu: sudo apt-get install graphviz\n"
            "  - Fedora: sudo dnf install graphviz"
        )


# =============================================================================
# Node labels
# =============================================================================


def _node_label(node: GraphNode) -> str:
    """Build a short display label for a graph node."""
    name = node.attrs.get("name", "")
    ntype = node.node_type.value

    if node.node_type == NodeType.FUNCTION:
        params = "self, ..." if node.attrs.get("is_method") else ""
        return f"{name}({params})"
    if node.node_type == NodeType.CLASS:
        return f"class {name}"
    if node.node_type == NodeType.MODULE:
        return f"module {name}"
    if node.node_type == NodeType.FIELD:
        ftype = node.attrs.get("field_type", "")
        return f"{name}: {ftype}" if ftype else name
    if node.node_type == NodeType.PARAMETER:
        default = node.attrs.get("default_value")
        return f"{name}={default}" if default else name
    if node.node_type == NodeType.CALL:
        callee = node.attrs.get("callee", "?")
        return f"call {callee}()"
    if node.node_type == NodeType.ARGUMENT:
        val = node.attrs.get("value", "")
        return f"{name}={val}" if name and val else name or val or ntype
    return name or ntype


# =============================================================================
# DOT helpers
# =============================================================================


def _dot_id(node_id: str) -> str:
    """Sanitize a graph node ID for DOT format (colons are port separators)."""
    return node_id.replace(":", "__")


def _add_node(
    dot: graphviz.Digraph,
    node: GraphNode,
    highlight: bool,
) -> None:
    style = NODE_STYLES.get(
        node.node_type,
        {"shape": "box", "fillcolor": "#CCCCCC", "fontcolor": "black"},
    )
    attrs: dict[str, str] = dict(style)
    attrs["label"] = _node_label(node)
    attrs["style"] = "filled"
    if highlight:
        attrs["penwidth"] = "3"
        attrs["color"] = "#FF0000"
    dot.node(_dot_id(node.id), **attrs)


def _add_edge(
    dot: graphviz.Digraph,
    edge: GraphEdge,
    highlight: bool,
) -> None:
    style = EDGE_STYLES.get(
        edge.edge_type,
        {"color": "#999999", "style": "solid", "label": ""},
    )
    attrs = {
        "color": style["color"],
        "style": style["style"],
        "label": f"  {style['label']}  ",
        "fontcolor": style["color"],
    }
    if highlight:
        attrs["penwidth"] = "3"
        attrs["color"] = "#FF0000"
        attrs["fontcolor"] = "#FF0000"
    dot.edge(_dot_id(edge.source), _dot_id(edge.target), **attrs)


# =============================================================================
# Public API
# =============================================================================


def render_graph(
    graph: TypedGraph,
    title: str = "",
    output_path: str | None = None,
    fmt: str = "svg",
    highlight_nodes: set[str] | None = None,
    highlight_edges: set[tuple[str, str]] | None = None,
) -> str:
    """Render a TypedGraph using Graphviz.

    Args:
        graph: The TypedGraph to render.
        title: Title displayed at the top.
        output_path: File path without extension (e.g. "output/graph").
                     If None, uses a temp file.
        fmt: Output format ("svg", "png", "pdf").
        highlight_nodes: Node IDs to highlight.
        highlight_edges: (source, target) pairs to highlight.

    Returns:
        Path to the generated output file.
    """
    gv = _ensure_graphviz()

    highlight_nodes = highlight_nodes or set()
    highlight_edges = highlight_edges or set()

    dot = gv.Digraph(
        name=title,
        format=fmt,
        graph_attr={
            "label": title,
            "labelloc": "t",
            "fontsize": "20",
            "fontname": "Helvetica Bold",
            "bgcolor": "white",
            "rankdir": "TB",
            "nodesep": "0.6",
            "ranksep": "0.8",
            "pad": "0.5",
        },
        node_attr={
            "style": "filled",
            "fontname": "Helvetica",
            "fontsize": "11",
            "margin": "0.15,0.08",
        },
        edge_attr={
            "fontname": "Helvetica",
            "fontsize": "9",
        },
    )

    # Group nodes by type
    type_groups: dict[NodeType, list[GraphNode]] = {}
    for node in graph.nodes.values():
        type_groups.setdefault(node.node_type, []).append(node)

    # Module nodes
    for mod_node in type_groups.get(NodeType.MODULE, []):
        _add_node(dot, mod_node, mod_node.id in highlight_nodes)

    # Class clusters
    class_members: set[str] = set()
    for cls_node in type_groups.get(NodeType.CLASS, []):
        with dot.subgraph(name=f"cluster_{cls_node.id}") as c:
            c.attr(
                style="rounded,dashed",
                color="#E8A838",
                label=f"  {cls_node.attrs.get('name', '')}  ",
                fontname="Helvetica Bold",
                fontsize="13",
                fontcolor="#E8A838",
            )
            _add_node(c, cls_node, cls_node.id in highlight_nodes)

            # Methods
            for edge in graph.get_edges_from(cls_node.id):
                if edge.edge_type == EdgeType.CONTAINS_METHOD:
                    target = graph.get_node(edge.target)
                    if target:
                        _add_node(c, target, target.id in highlight_nodes)
                        class_members.add(target.id)
                        # Parameters of methods
                        for pe in graph.get_edges_from(target.id):
                            if pe.edge_type == EdgeType.HAS_PARAMETER:
                                pn = graph.get_node(pe.target)
                                if pn:
                                    _add_node(c, pn, pn.id in highlight_nodes)
                                    class_members.add(pn.id)

            # Fields
            for edge in graph.get_edges_from(cls_node.id):
                if edge.edge_type == EdgeType.CONTAINS_FIELD:
                    target = graph.get_node(edge.target)
                    if target:
                        _add_node(c, target, target.id in highlight_nodes)
                        class_members.add(target.id)

    # Standalone functions
    for func_node in type_groups.get(NodeType.FUNCTION, []):
        if func_node.id not in class_members:
            _add_node(dot, func_node, func_node.id in highlight_nodes)
            for pe in graph.get_edges_from(func_node.id):
                if pe.edge_type == EdgeType.HAS_PARAMETER:
                    pn = graph.get_node(pe.target)
                    if pn and pn.id not in class_members:
                        _add_node(dot, pn, pn.id in highlight_nodes)

    # Calls, arguments
    for call_node in type_groups.get(NodeType.CALL, []):
        _add_node(dot, call_node, call_node.id in highlight_nodes)
    for arg_node in type_groups.get(NodeType.ARGUMENT, []):
        _add_node(dot, arg_node, arg_node.id in highlight_nodes)

    # Standalone fields
    for field_node in type_groups.get(NodeType.FIELD, []):
        if field_node.id not in class_members:
            _add_node(dot, field_node, field_node.id in highlight_nodes)

    # Import nodes
    for imp_node in type_groups.get(NodeType.IMPORT, []):
        _add_node(dot, imp_node, imp_node.id in highlight_nodes)

    # Edges
    for edge in graph.edges:
        is_hl = (edge.source, edge.target) in highlight_edges
        _add_edge(dot, edge, is_hl)

    # Render
    if output_path:
        path = dot.render(filename=output_path, cleanup=True)
    else:
        path = dot.render(cleanup=True)
    return path


def render_graph_string(
    graph: TypedGraph,
    title: str = "",
    fmt: str = "svg",
    highlight_nodes: set[str] | None = None,
    highlight_edges: set[tuple[str, str]] | None = None,
) -> bytes:
    """Render a TypedGraph and return the output as bytes (for piping).

    Args:
        graph: The TypedGraph to render.
        title: Title displayed at the top.
        fmt: Output format ("svg", "png", "pdf").
        highlight_nodes: Node IDs to highlight.
        highlight_edges: (source, target) pairs to highlight.

    Returns:
        Rendered output as bytes.
    """
    gv = _ensure_graphviz()
    # Reuse render_graph logic by rendering to DOT then piping
    # For simplicity, we build the same dot object
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = os.path.join(tmpdir, "graph")
        render_graph(
            graph, title=title, output_path=tmp_path, fmt=fmt,
            highlight_nodes=highlight_nodes, highlight_edges=highlight_edges,
        )
        # Read the output file
        output_file = f"{tmp_path}.{fmt}"
        if os.path.exists(output_file):
            with open(output_file, "rb") as f:
                return f.read()
        # Graphviz sometimes doesn't add extension
        for candidate in os.listdir(tmpdir):
            with open(os.path.join(tmpdir, candidate), "rb") as f:
                return f.read()
    return b""


# =============================================================================
# Diff helpers
# =============================================================================


def diff_nodes(before: TypedGraph, after: TypedGraph) -> set[str]:
    """Return node IDs that are new in `after`."""
    return set(after.nodes.keys()) - set(before.nodes.keys())


def diff_edges(before: TypedGraph, after: TypedGraph) -> set[tuple[str, str]]:
    """Return (source, target) pairs for edges new in `after`."""
    before_set = {(e.source, e.target) for e in before.edges}
    after_set = {(e.source, e.target) for e in after.edges}
    return after_set - before_set
