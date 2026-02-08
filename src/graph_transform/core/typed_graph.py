"""
Typed Graph Infrastructure

Uniform typed attributed graph representation for algebraic operations.
Nodes and edges are typed, enabling structure-preserving morphisms and
pushout constructions.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Type Enums
# =============================================================================


class NodeType(Enum):
    """Types of nodes in the code graph."""

    # Definitions
    FUNCTION = "function"
    CLASS = "class"
    FIELD = "field"
    PARAMETER = "parameter"
    MODULE = "module"

    # References
    IMPORT = "import"
    CALL = "call"
    ARGUMENT = "argument"

    # Control flow (added for primitives)
    BLOCK = "block"
    BRANCH = "branch"
    LOOP = "loop"

    # Expressions (added for primitives)
    EXPRESSION = "expression"
    LITERAL = "literal"

    # Annotations (added for primitives)
    ANNOTATION = "annotation"


class EdgeType(Enum):
    """Types of edges in the code graph."""

    CONTAINS_METHOD = "contains_method"
    CONTAINS_FIELD = "contains_field"
    HAS_PARAMETER = "has_parameter"
    HAS_ARGUMENT = "has_argument"
    CALLS = "calls"
    INHERITS = "inherits"
    IMPORTS = "imports"
    DEFINED_IN = "defined_in"
    CALLER_OF = "caller_of"
    REFERENCES = "references"


# =============================================================================
# GraphNode
# =============================================================================


@dataclass
class GraphNode:
    """A typed node in the graph with attribute dictionary."""

    id: str
    node_type: NodeType
    attrs: dict[str, Any] = field(default_factory=dict)

    def matches(self, pattern: GraphNode, strict: bool = False) -> bool:
        """Check if this node matches a pattern node.

        Pattern attrs with value None are treated as wildcards (match anything).
        If strict=True, all attrs must be present and match exactly.
        """
        if self.node_type != pattern.node_type:
            return False
        for key, value in pattern.attrs.items():
            if value is None:
                continue
            if key not in self.attrs:
                if strict:
                    return False
                continue
            if self.attrs[key] != value:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "attrs": self.attrs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphNode:
        return cls(
            id=data["id"],
            node_type=NodeType(data["node_type"]),
            attrs=data.get("attrs", {}),
        )


# =============================================================================
# GraphEdge
# =============================================================================


@dataclass
class GraphEdge:
    """A typed directed edge in the graph."""

    source: str
    target: str
    edge_type: EdgeType
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "attrs": self.attrs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphEdge:
        return cls(
            source=data["source"],
            target=data["target"],
            edge_type=EdgeType(data["edge_type"]),
            attrs=data.get("attrs", {}),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GraphEdge):
            return False
        return (
            self.source == other.source
            and self.target == other.target
            and self.edge_type == other.edge_type
        )

    def __hash__(self) -> int:
        return hash((self.source, self.target, self.edge_type))


# =============================================================================
# TypedGraph
# =============================================================================


@dataclass
class TypedGraph:
    """A typed attributed graph for algebraic rewriting.

    Nodes and edges are typed. This is the uniform representation
    that morphisms, production rules, and pushout constructions operate on.
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    # --- Node operations ---

    def add_node(self, node: GraphNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all incident edges."""
        self.nodes.pop(node_id, None)
        self.edges = [
            e for e in self.edges
            if e.source != node_id and e.target != node_id
        ]

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def get_nodes_by_type(self, node_type: NodeType) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def get_nodes_by_attr(self, key: str, value: Any) -> list[GraphNode]:
        """Find nodes with a specific attribute value."""
        return [
            n for n in self.nodes.values()
            if n.attrs.get(key) == value
        ]

    # --- Edge operations ---

    def add_edge(self, edge: GraphEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)

    def remove_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType | None = None,
    ) -> None:
        """Remove edge(s) matching source, target, and optionally edge_type."""
        self.edges = [
            e for e in self.edges
            if not (
                e.source == source
                and e.target == target
                and (edge_type is None or e.edge_type == edge_type)
            )
        ]

    def remove_edges_involving(self, node_id: str) -> list[GraphEdge]:
        """Remove and return all edges incident to a node."""
        removed = [
            e for e in self.edges
            if e.source == node_id or e.target == node_id
        ]
        self.edges = [
            e for e in self.edges
            if e.source != node_id and e.target != node_id
        ]
        return removed

    def get_edges_from(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source == node_id]

    def get_edges_to(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.target == node_id]

    def get_edges_between(
        self, source: str, target: str, edge_type: EdgeType | None = None
    ) -> list[GraphEdge]:
        return [
            e for e in self.edges
            if e.source == source
            and e.target == target
            and (edge_type is None or e.edge_type == edge_type)
        ]

    def has_edge(
        self, source: str, target: str, edge_type: EdgeType | None = None
    ) -> bool:
        return len(self.get_edges_between(source, target, edge_type)) > 0

    # --- Graph queries ---

    def neighbors(self, node_id: str) -> list[str]:
        """Return IDs of all adjacent nodes (via outgoing edges)."""
        return list({e.target for e in self.edges if e.source == node_id})

    def predecessors(self, node_id: str) -> list[str]:
        """Return IDs of all nodes with edges pointing to this node."""
        return list({e.source for e in self.edges if e.target == node_id})

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def is_empty(self) -> bool:
        return self.node_count == 0

    # --- Subgraph and copy ---

    def subgraph(self, node_ids: set[str]) -> TypedGraph:
        """Extract a subgraph containing only the given nodes and edges between them."""
        sub_nodes = {nid: self.nodes[nid] for nid in node_ids if nid in self.nodes}
        sub_edges = [
            e for e in self.edges
            if e.source in node_ids and e.target in node_ids
        ]
        return TypedGraph(nodes=sub_nodes, edges=sub_edges)

    def copy(self) -> TypedGraph:
        """Deep copy of the graph."""
        return copy.deepcopy(self)

    # --- Validation ---

    def dangling_edges(self) -> list[GraphEdge]:
        """Return edges where source or target node does not exist."""
        return [
            e for e in self.edges
            if e.source not in self.nodes or e.target not in self.nodes
        ]

    def is_valid(self) -> bool:
        """Check that there are no dangling edges."""
        return len(self.dangling_edges()) == 0

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TypedGraph:
        nodes = {
            nid: GraphNode.from_dict(ndata)
            for nid, ndata in data.get("nodes", {}).items()
        }
        edges = [GraphEdge.from_dict(edata) for edata in data.get("edges", [])]
        return cls(nodes=nodes, edges=edges)

    # --- Factory from existing CodeGraph ---

    @classmethod
    def from_code_graph(
        cls,
        code_graph: Any,
        classes: list[Any] | None = None,
        fields: list[Any] | None = None,
        imports: list[Any] | None = None,
        modules: list[Any] | None = None,
    ) -> TypedGraph:
        """Convert an existing CodeGraph (+ extensions) into a TypedGraph.

        Args:
            code_graph: A CodeGraph instance from graph_transform.py
            classes: Optional list of ClassNode instances
            fields: Optional list of FieldNode instances
            imports: Optional list of ImportNode instances
            modules: Optional list of ModuleNode instances
        """
        graph = cls()

        # Convert FunctionNodes
        for name, func in code_graph.functions.items():
            func_id = f"func:{name}"
            graph.add_node(GraphNode(
                id=func_id,
                node_type=NodeType.FUNCTION,
                attrs={
                    "name": func.name,
                    "file": func.file,
                    "line": func.line,
                    "end_line": getattr(func, "end_line", None),
                    "is_method": func.is_method,
                    "is_async": func.is_async,
                },
            ))
            # Convert parameters
            for param in func.parameters:
                param_id = f"param:{name}.{param.name}"
                graph.add_node(GraphNode(
                    id=param_id,
                    node_type=NodeType.PARAMETER,
                    attrs={
                        "name": param.name,
                        "position": param.position,
                        "has_default": param.has_default,
                        "default_value": param.default_value,
                        "is_keyword_only": param.is_keyword_only,
                    },
                ))
                graph.add_edge(GraphEdge(
                    source=func_id,
                    target=param_id,
                    edge_type=EdgeType.HAS_PARAMETER,
                ))

        # Convert CallNodes
        for i, call in enumerate(code_graph.calls):
            call_id = f"call:{call.file}:{call.line}:{i}"
            graph.add_node(GraphNode(
                id=call_id,
                node_type=NodeType.CALL,
                attrs={
                    "callee": call.callee,
                    "file": call.file,
                    "line": call.line,
                    "caller": call.caller,
                    "call_type": "method" if getattr(call, "is_method_call", False) else "direct",
                    "receiver": call.receiver,
                },
            ))
            # Edge to the called function
            callee_id = f"func:{call.callee}"
            if callee_id in graph.nodes:
                graph.add_edge(GraphEdge(
                    source=call_id,
                    target=callee_id,
                    edge_type=EdgeType.CALLS,
                ))
            # Edge from caller function
            if call.caller:
                caller_id = f"func:{call.caller}"
                if caller_id in graph.nodes:
                    graph.add_edge(GraphEdge(
                        source=caller_id,
                        target=call_id,
                        edge_type=EdgeType.CALLER_OF,
                    ))
            # Convert arguments
            for arg in call.arguments:
                arg_name = arg.name or f"pos{arg.position}"
                arg_id = f"arg:{call_id}.{arg_name}"
                graph.add_node(GraphNode(
                    id=arg_id,
                    node_type=NodeType.ARGUMENT,
                    attrs={
                        "position": arg.position,
                        "name": arg.name,
                        "value": arg.value,
                        "is_keyword": arg.is_keyword,
                        "is_starred": arg.is_starred,
                        "is_double_starred": arg.is_double_starred,
                    },
                ))
                graph.add_edge(GraphEdge(
                    source=call_id,
                    target=arg_id,
                    edge_type=EdgeType.HAS_ARGUMENT,
                ))

        # Convert ClassNodes
        if classes:
            for cls_node in classes:
                cls_id = f"class:{cls_node.name}"
                graph.add_node(GraphNode(
                    id=cls_id,
                    node_type=NodeType.CLASS,
                    attrs={
                        "name": cls_node.name,
                        "file": cls_node.file,
                        "line": cls_node.line,
                        "end_line": cls_node.end_line,
                        "is_abstract": cls_node.is_abstract,
                    },
                ))
                # Inheritance edges
                for base in cls_node.bases:
                    base_id = f"class:{base}"
                    if base_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=cls_id,
                            target=base_id,
                            edge_type=EdgeType.INHERITS,
                        ))
                # Method containment edges
                for method in cls_node.methods:
                    method_id = f"func:{method}"
                    if method_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=cls_id,
                            target=method_id,
                            edge_type=EdgeType.CONTAINS_METHOD,
                        ))
                # Field containment edges
                for fld in cls_node.fields:
                    fld_id = f"field:{cls_node.name}.{fld}"
                    if fld_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=cls_id,
                            target=fld_id,
                            edge_type=EdgeType.CONTAINS_FIELD,
                        ))

        # Convert FieldNodes
        if fields:
            for fld_node in fields:
                fld_key = f"{fld_node.class_name}.{fld_node.name}" if fld_node.class_name else fld_node.name
                fld_id = f"field:{fld_key}"
                graph.add_node(GraphNode(
                    id=fld_id,
                    node_type=NodeType.FIELD,
                    attrs={
                        "name": fld_node.name,
                        "file": fld_node.file,
                        "line": fld_node.line,
                        "class_name": fld_node.class_name,
                        "field_type": fld_node.field_type,
                        "has_default": fld_node.has_default,
                        "default_value": fld_node.default_value,
                        "is_class_var": fld_node.is_class_var,
                    },
                ))

        # Convert ImportNodes
        if imports:
            for imp_node in imports:
                imp_name = imp_node.name or imp_node.module
                imp_id = f"import:{imp_node.file}:{imp_name}"
                graph.add_node(GraphNode(
                    id=imp_id,
                    node_type=NodeType.IMPORT,
                    attrs={
                        "module": imp_node.module,
                        "name": imp_node.name,
                        "alias": imp_node.alias,
                        "file": imp_node.file,
                        "line": imp_node.line,
                        "is_from_import": imp_node.is_from_import,
                    },
                ))

        # Convert ModuleNodes
        if modules:
            for mod_node in modules:
                mod_id = f"module:{mod_node.name}"
                graph.add_node(GraphNode(
                    id=mod_id,
                    node_type=NodeType.MODULE,
                    attrs={
                        "name": mod_node.name,
                        "file": mod_node.file,
                    },
                ))
                # Edges to contained functions
                for func_name in mod_node.functions:
                    func_id = f"func:{func_name}"
                    if func_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=func_id,
                            target=mod_id,
                            edge_type=EdgeType.DEFINED_IN,
                        ))
                # Edges to contained classes
                for cls_name in mod_node.classes:
                    cls_id = f"class:{cls_name}"
                    if cls_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=cls_id,
                            target=mod_id,
                            edge_type=EdgeType.DEFINED_IN,
                        ))
                # Edges to imports
                for imp_key in mod_node.imports:
                    imp_id = f"import:{imp_key}"
                    if imp_id in graph.nodes:
                        graph.add_edge(GraphEdge(
                            source=mod_id,
                            target=imp_id,
                            edge_type=EdgeType.IMPORTS,
                        ))

        return graph
