"""
Production Rule Catalog

Factory for creating production rules for all 40+ operator types
from primitive_operators. Each operator is mapped to an L <- K -> R
production rule with preconditions, postconditions, and attr_transfer.
"""

from __future__ import annotations

from typing import Any, Callable

from graph_transform.core.morphism import GraphMorphism
from graph_transform.core.typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph
from graph_transform.rewriting.invariants import (
    Invariant,
    InvariantLayer,
    InvariantSeverity,
    InvariantViolation,
)
from graph_transform.rewriting.production_rule import ProductionRule

from .primitive_operators import OperatorType


# =============================================================================
# Helper: build simple production rules
# =============================================================================


def _normalize_module_name(name: str) -> str:
    """Convert a dotted import path to a file-stem module name.

    The graph builder stores MODULE nodes with ``name = Path(file).stem``,
    e.g. ``params`` for ``fastapi/params.py``.  Callers (especially LLM
    agents) often pass the full dotted import path instead, like
    ``fastapi.params``.  This helper extracts the last component so that
    module operators match correctly regardless of which form is used.
    """
    return name.rsplit(".", 1)[-1] if "." in name else name


def _make_rule(
    name: str,
    op_type: OperatorType,
    lhs_nodes: list[GraphNode],
    lhs_edges: list[GraphEdge],
    interface_nodes: list[GraphNode],
    interface_edges: list[GraphEdge],
    rhs_nodes: list[GraphNode],
    rhs_edges: list[GraphEdge],
    preconditions: list[Invariant] | None = None,
    postconditions: list[Invariant] | None = None,
    attr_transfer: dict[str, Callable] | None = None,
    parameters: dict[str, Any] | None = None,
    description: str | None = None,
    category: str | None = None,
) -> ProductionRule:
    """Build a production rule from node/edge lists."""
    lhs = TypedGraph(
        nodes={n.id: n for n in lhs_nodes},
        edges=lhs_edges,
    )
    interface = TypedGraph(
        nodes={n.id: n for n in interface_nodes},
        edges=interface_edges,
    )
    rhs = TypedGraph(
        nodes={n.id: n for n in rhs_nodes},
        edges=rhs_edges,
    )
    lhs_inclusion = GraphMorphism.inclusion(interface, lhs)
    rhs_inclusion = GraphMorphism.inclusion(interface, rhs)

    return ProductionRule(
        name=name,
        op_type=op_type,
        lhs=lhs,
        interface=interface,
        rhs=rhs,
        lhs_inclusion=lhs_inclusion,
        rhs_inclusion=rhs_inclusion,
        preconditions=preconditions or [],
        postconditions=postconditions or [],
        attr_transfer=attr_transfer or {},
        parameters=parameters or {},
        description=description,
        category=category,
    )


def _node_exists_precondition(
    node_type: NodeType, attr_key: str, attr_value: str, inv_name: str
) -> Invariant:
    """Create a precondition that a node with given attr must exist."""
    def check(graph: TypedGraph) -> list[InvariantViolation]:
        found = graph.get_nodes_by_attr(attr_key, attr_value)
        found = [n for n in found if n.node_type == node_type]
        if not found:
            return [InvariantViolation(
                invariant_name=inv_name,
                message=f"{node_type.value} with {attr_key}='{attr_value}' not found",
            )]
        return []
    return Invariant(name=inv_name, description=f"Requires {node_type.value} '{attr_value}'", check=check)


def _node_absent_precondition(
    node_type: NodeType, attr_key: str, attr_value: str, inv_name: str
) -> Invariant:
    """Create a precondition that a node with given attr must NOT exist."""
    def check(graph: TypedGraph) -> list[InvariantViolation]:
        found = graph.get_nodes_by_attr(attr_key, attr_value)
        found = [n for n in found if n.node_type == node_type]
        if found:
            return [InvariantViolation(
                invariant_name=inv_name,
                message=f"{node_type.value} with {attr_key}='{attr_value}' already exists",
            )]
        return []
    return Invariant(name=inv_name, description=f"Requires no {node_type.value} '{attr_value}'", check=check)


def _node_exists_postcondition(
    node_type: NodeType, attr_key: str, attr_value: str, inv_name: str
) -> Invariant:
    """Create a postcondition that a node with given attr must exist."""
    return _node_exists_precondition(node_type, attr_key, attr_value, inv_name)


def _edge_exists_precondition(
    source_type: NodeType,
    source_attr: str,
    source_val: str,
    target_type: NodeType,
    target_attr: str,
    target_val: str,
    edge_type: EdgeType,
    inv_name: str,
) -> Invariant:
    """Create a precondition that a specific edge must exist."""
    def check(graph: TypedGraph) -> list[InvariantViolation]:
        sources = [
            n for n in graph.get_nodes_by_attr(source_attr, source_val)
            if n.node_type == source_type
        ]
        targets = [
            n for n in graph.get_nodes_by_attr(target_attr, target_val)
            if n.node_type == target_type
        ]
        if not sources or not targets:
            return [InvariantViolation(
                invariant_name=inv_name,
                message=(
                    f"No {edge_type.value} edge from {source_type.value} "
                    f"'{source_val}' to {target_type.value} '{target_val}'"
                ),
                layer=InvariantLayer.REFERENCE,
            )]
        for src in sources:
            for tgt in targets:
                if graph.has_edge(src.id, tgt.id, edge_type):
                    return []
        return [InvariantViolation(
            invariant_name=inv_name,
            message=(
                f"No {edge_type.value} edge from {source_type.value} "
                f"'{source_val}' to {target_type.value} '{target_val}'"
            ),
            layer=InvariantLayer.REFERENCE,
        )]
    return Invariant(
        name=inv_name,
        description=f"Requires {edge_type.value} edge from '{source_val}' to '{target_val}'",
        check=check,
        layer=InvariantLayer.REFERENCE,
    )


def _inheritance_precondition(
    subclass: str, superclass: str, inv_name: str = "inheritance_exists"
) -> Invariant:
    """Create a precondition that subclass INHERITS from superclass."""
    return _edge_exists_precondition(
        source_type=NodeType.CLASS,
        source_attr="name",
        source_val=subclass,
        target_type=NodeType.CLASS,
        target_attr="name",
        target_val=superclass,
        edge_type=EdgeType.INHERITS,
        inv_name=inv_name,
    )


def _no_references_precondition(
    node_type: NodeType, attr_key: str, attr_value: str, inv_name: str
) -> Invariant:
    """Precondition: no CALLS/REFERENCES edges point to this node (safe deletion)."""
    def check(graph: TypedGraph) -> list[InvariantViolation]:
        targets = [
            n for n in graph.get_nodes_by_attr(attr_key, attr_value)
            if n.node_type == node_type
        ]
        for tgt in targets:
            refs = [
                e for e in graph.get_edges_to(tgt.id)
                if e.edge_type in (EdgeType.CALLS, EdgeType.REFERENCES)
            ]
            if refs:
                return [InvariantViolation(
                    invariant_name=inv_name,
                    message=(
                        f"{node_type.value} '{attr_value}' still has "
                        f"{len(refs)} reference(s)"
                    ),
                    severity=InvariantSeverity.WARNING,
                    layer=InvariantLayer.REFERENCE,
                    node_id=tgt.id,
                    related_nodes=[e.source for e in refs],
                    fix_hint="Remove or update all references before deletion",
                )]
        return []
    return Invariant(
        name=inv_name,
        description=f"No references to {node_type.value} '{attr_value}'",
        check=check,
        severity=InvariantSeverity.WARNING,
        layer=InvariantLayer.REFERENCE,
    )


# =============================================================================
# ProductionRuleCatalog
# =============================================================================


class ProductionRuleCatalog:
    """Factory for creating production rules for all operator types.

    Each method creates a ProductionRule with the appropriate L, K, R graphs
    and pre/postconditions. Rules are parameterized: the factory takes
    concrete names/values and builds specific rule instances.
    """

    _DISPATCH: dict[OperatorType, str] = {
        # Method-level
        OperatorType.ADD_METHOD: "_add_method",
        OperatorType.REMOVE_METHOD: "_remove_method",
        OperatorType.RENAME_METHOD: "_rename_method",
        OperatorType.MOVE_METHOD: "_move_method",
        OperatorType.EXTRACT_METHOD: "_extract_method",
        OperatorType.INLINE_METHOD: "_inline_method",
        OperatorType.PULL_UP_METHOD: "_pull_up_method",
        OperatorType.PUSH_DOWN_METHOD: "_push_down_method",
        OperatorType.CHANGE_SIGNATURE: "_change_signature",
        # Field-level
        OperatorType.ADD_FIELD: "_add_field",
        OperatorType.REMOVE_FIELD: "_remove_field",
        OperatorType.RENAME_FIELD: "_rename_field",
        OperatorType.MOVE_FIELD: "_move_field",
        OperatorType.PULL_UP_FIELD: "_pull_up_field",
        OperatorType.PUSH_DOWN_FIELD: "_push_down_field",
        OperatorType.ENCAPSULATE_FIELD: "_encapsulate_field",
        # Class-level
        OperatorType.ADD_CLASS: "_add_class",
        OperatorType.REMOVE_CLASS: "_remove_class",
        OperatorType.RENAME_CLASS: "_rename_class",
        OperatorType.MOVE_CLASS: "_move_class",
        OperatorType.EXTRACT_CLASS: "_extract_class",
        OperatorType.INLINE_CLASS: "_inline_class",
        OperatorType.EXTRACT_SUPERCLASS: "_extract_superclass",
        # Parameter-level
        OperatorType.ADD_PARAM: "_add_param",
        OperatorType.REMOVE_PARAM: "_remove_param",
        OperatorType.RENAME_PARAM: "_rename_param",
        OperatorType.INTRODUCE_PARAM_OBJECT: "_introduce_param_object",
        # Module-level
        OperatorType.CREATE_MODULE: "_create_module",
        OperatorType.DELETE_MODULE: "_delete_module",
        OperatorType.RENAME_MODULE: "_rename_module",
        OperatorType.MOVE_TO_MODULE: "_move_to_module",
        OperatorType.MERGE_MODULES: "_merge_modules",
        # Reference-level
        OperatorType.ADD_IMPORT: "_add_import",
        OperatorType.REMOVE_IMPORT: "_remove_import",
        OperatorType.UPDATE_IMPORT: "_update_import",
        OperatorType.UPDATE_CALL: "_update_call",
        OperatorType.UPDATE_REFERENCE: "_update_reference",
        # Call-site level
        OperatorType.ADD_ARG: "_add_arg",
        OperatorType.REMOVE_ARG: "_remove_arg",
        OperatorType.UPDATE_ARG: "_update_arg",
        # Alias
        OperatorType.RENAME_FUNC: "_rename_method",
    }

    def create_rule(
        self, op_type: OperatorType, params: dict[str, Any]
    ) -> ProductionRule:
        """Create a production rule for the given operator type."""
        rules = self.create_rules(op_type, params)
        return rules[0]

    def create_rules(
        self, op_type: OperatorType, params: dict[str, Any]
    ) -> list[ProductionRule]:
        """Create production rule(s) for the given operator type.

        Most operators produce a single rule. Some (like update_import)
        may produce multiple rules to handle different AST patterns.
        """
        method_name = self._DISPATCH.get(op_type)
        if method_name is None:
            raise ValueError(f"Unsupported operator type: {op_type}")
        method = getattr(self, method_name)
        result = method(params)
        if isinstance(result, list):
            return result
        return [result]

    # =========================================================================
    # Method-Level Rules
    # =========================================================================

    def _add_method(self, p: dict) -> ProductionRule:
        """L: {class}. K: {class}. R: {class, method, CONTAINS_METHOD edge}."""
        cls_name = p["class_name"]
        method_name = p["method_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        method_node = GraphNode("method", NodeType.FUNCTION, {
            "name": method_name,
            "is_method": True,
            "is_async": p.get("is_async", False),
        })
        return _make_rule(
            name=f"add_method:{cls_name}.{method_name}",
            op_type=OperatorType.ADD_METHOD,
            lhs_nodes=[cls_node],
            lhs_edges=[],
            interface_nodes=[cls_node],
            interface_edges=[],
            rhs_nodes=[cls_node, method_node],
            rhs_edges=[GraphEdge("cls", "method", EdgeType.CONTAINS_METHOD)],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists"),
            ],
            postconditions=[
                _node_exists_postcondition(NodeType.FUNCTION, "name", method_name, "method_added"),
            ],
            parameters=p,
            description=f"Add method {method_name} to class {cls_name}",
            category="method",
        )

    def _remove_method(self, p: dict) -> ProductionRule:
        """L: {class, method, edge}. K: {class}. R: {class}."""
        cls_name = p["class_name"]
        method_name = p["method_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        method_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        return _make_rule(
            name=f"remove_method:{cls_name}.{method_name}",
            op_type=OperatorType.REMOVE_METHOD,
            lhs_nodes=[cls_node, method_node],
            lhs_edges=[GraphEdge("cls", "method", EdgeType.CONTAINS_METHOD)],
            interface_nodes=[cls_node],
            interface_edges=[],
            rhs_nodes=[cls_node],
            rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists"),
                _node_exists_precondition(NodeType.FUNCTION, "name", method_name, "method_exists"),
            ],
            parameters=p,
            description=f"Remove method {method_name} from class {cls_name}",
            category="method",
        )

    def _rename_method(self, p: dict) -> ProductionRule:
        """L: {method(old_name)}. K: {method}. R: {method(new_name)}."""
        old_name = p.get("old_name", p.get("method_name", ""))
        new_name = p["new_name"]
        lhs_node = GraphNode("method", NodeType.FUNCTION, {"name": old_name})
        k_node = GraphNode("method", NodeType.FUNCTION, {})
        rhs_node = GraphNode("method", NodeType.FUNCTION, {"name": new_name})
        return _make_rule(
            name=f"rename_method:{old_name}->{new_name}",
            op_type=OperatorType.RENAME_METHOD,
            lhs_nodes=[lhs_node],
            lhs_edges=[],
            interface_nodes=[k_node],
            interface_edges=[],
            rhs_nodes=[rhs_node],
            rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.FUNCTION, "name", old_name, "old_method_exists"),
                _node_absent_precondition(NodeType.FUNCTION, "name", new_name, "new_name_available"),
            ],
            postconditions=[
                _node_exists_postcondition(NodeType.FUNCTION, "name", new_name, "method_renamed"),
            ],
            parameters=p,
            description=f"Rename method {old_name} to {new_name}",
            category="method",
        )

    def _move_method(self, p: dict) -> ProductionRule:
        """L: {src, dst, method, edge(src→method)}. K: {src, dst, method}. R: {src, dst, method, edge(dst→method)}."""
        src_class = p["source_class"]
        dst_class = p["target_class"]
        method_name = p["method_name"]
        src_node = GraphNode("src", NodeType.CLASS, {"name": src_class})
        dst_node = GraphNode("dst", NodeType.CLASS, {"name": dst_class})
        method_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        return _make_rule(
            name=f"move_method:{method_name}:{src_class}->{dst_class}",
            op_type=OperatorType.MOVE_METHOD,
            lhs_nodes=[src_node, dst_node, method_node],
            lhs_edges=[GraphEdge("src", "method", EdgeType.CONTAINS_METHOD)],
            interface_nodes=[src_node, dst_node, method_node],
            interface_edges=[],
            rhs_nodes=[src_node, dst_node, method_node],
            rhs_edges=[GraphEdge("dst", "method", EdgeType.CONTAINS_METHOD)],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", src_class, "src_class_exists"),
                _node_exists_precondition(NodeType.CLASS, "name", dst_class, "dst_class_exists"),
                _node_exists_precondition(NodeType.FUNCTION, "name", method_name, "method_exists"),
            ],
            parameters=p,
            description=f"Move method {method_name} from {src_class} to {dst_class}",
            category="method",
        )

    def _extract_method(self, p: dict) -> ProductionRule:
        """L: {source_method}. K: {source_method}. R: {source_method, new_method, CALLS edge}."""
        source_method = p["source_method"]
        new_method_name = p["new_method_name"]
        src_node = GraphNode("src", NodeType.FUNCTION, {"name": source_method})
        new_node = GraphNode("new", NodeType.FUNCTION, {"name": new_method_name})
        call_node = GraphNode("call", NodeType.CALL, {"callee": new_method_name})
        return _make_rule(
            name=f"extract_method:{source_method}->{new_method_name}",
            op_type=OperatorType.EXTRACT_METHOD,
            lhs_nodes=[src_node],
            lhs_edges=[],
            interface_nodes=[src_node],
            interface_edges=[],
            rhs_nodes=[src_node, new_node, call_node],
            rhs_edges=[
                GraphEdge("call", "new", EdgeType.CALLS),
                GraphEdge("src", "call", EdgeType.CALLER_OF),
            ],
            preconditions=[
                _node_exists_precondition(NodeType.FUNCTION, "name", source_method, "source_exists"),
                _node_absent_precondition(NodeType.FUNCTION, "name", new_method_name, "new_name_available"),
            ],
            parameters=p,
            description=f"Extract method {new_method_name} from {source_method}",
            category="method",
        )

    def _inline_method(self, p: dict) -> ProductionRule:
        """L: {method, call, CALLS edge}. K: {}. R: {}."""
        method_name = p["method_name"]
        method_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        call_node = GraphNode("call", NodeType.CALL, {"callee": method_name})
        return _make_rule(
            name=f"inline_method:{method_name}",
            op_type=OperatorType.INLINE_METHOD,
            lhs_nodes=[method_node, call_node],
            lhs_edges=[GraphEdge("call", "method", EdgeType.CALLS)],
            interface_nodes=[],
            interface_edges=[],
            rhs_nodes=[],
            rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.FUNCTION, "name", method_name, "method_exists"),
            ],
            parameters=p,
            description=f"Inline method {method_name}",
            category="method",
        )

    def _pull_up_method(self, p: dict) -> ProductionRule:
        """L: {subclass, method, edge}. K: {method}. R: {superclass, method, edge}."""
        source = p["source_class"]
        target = p["target_class"]
        method_name = p["method_name"]
        sub_node = GraphNode("sub", NodeType.CLASS, {"name": source})
        super_node = GraphNode("super", NodeType.CLASS, {"name": target})
        method_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        return _make_rule(
            name=f"pull_up_method:{method_name}:{source}->{target}",
            op_type=OperatorType.PULL_UP_METHOD,
            lhs_nodes=[sub_node, method_node],
            lhs_edges=[GraphEdge("sub", "method", EdgeType.CONTAINS_METHOD)],
            interface_nodes=[method_node],
            interface_edges=[],
            rhs_nodes=[super_node, method_node],
            rhs_edges=[GraphEdge("super", "method", EdgeType.CONTAINS_METHOD)],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", source, "subclass_exists"),
                _node_exists_precondition(NodeType.CLASS, "name", target, "superclass_exists"),
                _node_exists_precondition(NodeType.FUNCTION, "name", method_name, "method_exists"),
                _inheritance_precondition(source, target, "inherits_from_target"),
            ],
            parameters=p,
            description=f"Pull up method {method_name} from {source} to {target}",
            category="method",
        )

    def _push_down_method(self, p: dict) -> ProductionRule:
        """L: {superclass, method, edge}. K: {method}. R: {subclass, method, edge}."""
        source = p["source_class"]
        target = p["target_class"]
        method_name = p["method_name"]
        super_node = GraphNode("super", NodeType.CLASS, {"name": source})
        sub_node = GraphNode("sub", NodeType.CLASS, {"name": target})
        method_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        return _make_rule(
            name=f"push_down_method:{method_name}:{source}->{target}",
            op_type=OperatorType.PUSH_DOWN_METHOD,
            lhs_nodes=[super_node, method_node],
            lhs_edges=[GraphEdge("super", "method", EdgeType.CONTAINS_METHOD)],
            interface_nodes=[method_node],
            interface_edges=[],
            rhs_nodes=[sub_node, method_node],
            rhs_edges=[GraphEdge("sub", "method", EdgeType.CONTAINS_METHOD)],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", source, "superclass_exists"),
                _node_exists_precondition(NodeType.CLASS, "name", target, "subclass_exists"),
                _inheritance_precondition(target, source, "inherits_from_source"),
            ],
            parameters=p,
            description=f"Push down method {method_name} from {source} to {target}",
            category="method",
        )

    def _change_signature(self, p: dict) -> ProductionRule:
        """L: {method}. K: {method}. R: {method(new_params)}."""
        method_name = p["method_name"]
        lhs_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        k_node = GraphNode("method", NodeType.FUNCTION, {"name": method_name})
        rhs_node = GraphNode("method", NodeType.FUNCTION, {
            "name": method_name,
            "new_params": p.get("new_params", []),
        })
        return _make_rule(
            name=f"change_signature:{method_name}",
            op_type=OperatorType.CHANGE_SIGNATURE,
            lhs_nodes=[lhs_node],
            lhs_edges=[],
            interface_nodes=[k_node],
            interface_edges=[],
            rhs_nodes=[rhs_node],
            rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.FUNCTION, "name", method_name, "method_exists"),
            ],
            parameters=p,
            description=f"Change signature of {method_name}",
            category="method",
        )

    # =========================================================================
    # Field-Level Rules
    # =========================================================================

    def _add_field(self, p: dict) -> ProductionRule:
        cls_name = p["class_name"]
        field_name = p["field_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        field_node = GraphNode("field", NodeType.FIELD, {
            "name": field_name,
            "class_name": cls_name,
            "field_type": p.get("field_type"),
            "has_default": p.get("default_value") is not None,
            "default_value": p.get("default_value"),
        })
        return _make_rule(
            name=f"add_field:{cls_name}.{field_name}",
            op_type=OperatorType.ADD_FIELD,
            lhs_nodes=[cls_node], lhs_edges=[],
            interface_nodes=[cls_node], interface_edges=[],
            rhs_nodes=[cls_node, field_node],
            rhs_edges=[GraphEdge("cls", "field", EdgeType.CONTAINS_FIELD)],
            preconditions=[_node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists")],
            postconditions=[_node_exists_postcondition(NodeType.FIELD, "name", field_name, "field_added")],
            parameters=p, description=f"Add field {field_name} to {cls_name}", category="field",
        )

    def _remove_field(self, p: dict) -> ProductionRule:
        cls_name = p["class_name"]
        field_name = p["field_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        field_node = GraphNode("field", NodeType.FIELD, {"name": field_name, "class_name": cls_name})
        return _make_rule(
            name=f"remove_field:{cls_name}.{field_name}",
            op_type=OperatorType.REMOVE_FIELD,
            lhs_nodes=[cls_node, field_node],
            lhs_edges=[GraphEdge("cls", "field", EdgeType.CONTAINS_FIELD)],
            interface_nodes=[cls_node], interface_edges=[],
            rhs_nodes=[cls_node], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists"),
                _node_exists_precondition(NodeType.FIELD, "name", field_name, "field_exists"),
            ],
            parameters=p, description=f"Remove field {field_name} from {cls_name}", category="field",
        )

    def _rename_field(self, p: dict) -> ProductionRule:
        old_name = p["old_name"]
        new_name = p["new_name"]
        lhs_node = GraphNode("field", NodeType.FIELD, {"name": old_name})
        k_node = GraphNode("field", NodeType.FIELD, {})
        rhs_node = GraphNode("field", NodeType.FIELD, {"name": new_name})
        return _make_rule(
            name=f"rename_field:{old_name}->{new_name}",
            op_type=OperatorType.RENAME_FIELD,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            preconditions=[_node_exists_precondition(NodeType.FIELD, "name", old_name, "old_field_exists")],
            parameters=p, description=f"Rename field {old_name} to {new_name}", category="field",
        )

    def _move_field(self, p: dict) -> ProductionRule:
        src = p["source_class"]
        dst = p["target_class"]
        field_name = p["field_name"]
        src_node = GraphNode("src", NodeType.CLASS, {"name": src})
        dst_node = GraphNode("dst", NodeType.CLASS, {"name": dst})
        field_node = GraphNode("field", NodeType.FIELD, {"name": field_name})
        return _make_rule(
            name=f"move_field:{field_name}:{src}->{dst}",
            op_type=OperatorType.MOVE_FIELD,
            lhs_nodes=[src_node, dst_node, field_node],
            lhs_edges=[GraphEdge("src", "field", EdgeType.CONTAINS_FIELD)],
            interface_nodes=[src_node, dst_node, field_node], interface_edges=[],
            rhs_nodes=[src_node, dst_node, field_node],
            rhs_edges=[GraphEdge("dst", "field", EdgeType.CONTAINS_FIELD)],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", src, "src_exists"),
                _node_exists_precondition(NodeType.CLASS, "name", dst, "dst_exists"),
            ],
            parameters=p, description=f"Move field {field_name} from {src} to {dst}", category="field",
        )

    def _pull_up_field(self, p: dict) -> ProductionRule:
        return self._move_field({
            "source_class": p["source_class"],
            "target_class": p["target_class"],
            "field_name": p["field_name"],
        })

    def _push_down_field(self, p: dict) -> ProductionRule:
        return self._move_field({
            "source_class": p["source_class"],
            "target_class": p["target_class"],
            "field_name": p["field_name"],
        })

    def _encapsulate_field(self, p: dict) -> ProductionRule:
        """L: {class, field, edge}. K: {class}. R: {class, field, getter, setter, edges}."""
        cls_name = p["class_name"]
        field_name = p["field_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        field_node = GraphNode("field", NodeType.FIELD, {"name": field_name})
        getter = GraphNode("getter", NodeType.FUNCTION, {"name": f"get_{field_name}", "is_method": True})
        setter = GraphNode("setter", NodeType.FUNCTION, {"name": f"set_{field_name}", "is_method": True})
        return _make_rule(
            name=f"encapsulate_field:{cls_name}.{field_name}",
            op_type=OperatorType.ENCAPSULATE_FIELD,
            lhs_nodes=[cls_node, field_node],
            lhs_edges=[GraphEdge("cls", "field", EdgeType.CONTAINS_FIELD)],
            interface_nodes=[cls_node],
            interface_edges=[],
            rhs_nodes=[cls_node, field_node, getter, setter],
            rhs_edges=[
                GraphEdge("cls", "field", EdgeType.CONTAINS_FIELD),
                GraphEdge("cls", "getter", EdgeType.CONTAINS_METHOD),
                GraphEdge("cls", "setter", EdgeType.CONTAINS_METHOD),
            ],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists"),
                _node_exists_precondition(NodeType.FIELD, "name", field_name, "field_exists"),
            ],
            parameters=p, description=f"Encapsulate field {field_name} in {cls_name}", category="field",
        )

    # =========================================================================
    # Class-Level Rules
    # =========================================================================

    def _add_class(self, p: dict) -> ProductionRule:
        cls_name = p["class_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {
            "name": cls_name,
            "file": p.get("file", ""),
            "line": p.get("line", 0),
        })
        return _make_rule(
            name=f"add_class:{cls_name}",
            op_type=OperatorType.ADD_CLASS,
            lhs_nodes=[], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[cls_node], rhs_edges=[],
            preconditions=[_node_absent_precondition(NodeType.CLASS, "name", cls_name, "name_available")],
            postconditions=[_node_exists_postcondition(NodeType.CLASS, "name", cls_name, "class_added")],
            parameters=p, description=f"Add class {cls_name}", category="class",
        )

    def _remove_class(self, p: dict) -> ProductionRule:
        cls_name = p["class_name"]
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        return _make_rule(
            name=f"remove_class:{cls_name}",
            op_type=OperatorType.REMOVE_CLASS,
            lhs_nodes=[cls_node], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists"),
                _no_references_precondition(NodeType.CLASS, "name", cls_name, "no_class_references"),
            ],
            parameters=p, description=f"Remove class {cls_name}", category="class",
        )

    def _rename_class(self, p: dict) -> ProductionRule:
        old_name = p["old_name"]
        new_name = p["new_name"]
        lhs_node = GraphNode("cls", NodeType.CLASS, {"name": old_name})
        k_node = GraphNode("cls", NodeType.CLASS, {})
        rhs_node = GraphNode("cls", NodeType.CLASS, {"name": new_name})
        return _make_rule(
            name=f"rename_class:{old_name}->{new_name}",
            op_type=OperatorType.RENAME_CLASS,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", old_name, "old_exists"),
                _node_absent_precondition(NodeType.CLASS, "name", new_name, "new_available"),
            ],
            parameters=p, description=f"Rename class {old_name} to {new_name}", category="class",
        )

    def _move_class(self, p: dict) -> ProductionRule:
        cls_name = p["class_name"]
        target_mod = _normalize_module_name(p["target_module"])
        cls_node = GraphNode("cls", NodeType.CLASS, {"name": cls_name})
        old_mod_node = GraphNode("old_mod", NodeType.MODULE, {})  # match any module
        new_mod_node = GraphNode("new_mod", NodeType.MODULE, {"name": target_mod})
        # LHS: class defined in old_mod, new_mod exists.
        # The DEFINED_IN edge is in L but NOT in K → gets removed by pushout.
        # RHS adds a new DEFINED_IN edge to new_mod.
        return _make_rule(
            name=f"move_class:{cls_name}->{target_mod}",
            op_type=OperatorType.MOVE_CLASS,
            lhs_nodes=[cls_node, old_mod_node, new_mod_node],
            lhs_edges=[GraphEdge("cls", "old_mod", EdgeType.DEFINED_IN)],
            interface_nodes=[cls_node, old_mod_node, new_mod_node],
            interface_edges=[],  # old edge excluded → deleted
            rhs_nodes=[cls_node, old_mod_node, new_mod_node],
            rhs_edges=[GraphEdge("cls", "new_mod", EdgeType.DEFINED_IN)],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", cls_name, "class_exists"),
                _node_exists_precondition(NodeType.MODULE, "name", target_mod, "module_exists"),
            ],
            parameters=p, description=f"Move class {cls_name} to {target_mod}", category="class",
        )

    def _extract_class(self, p: dict) -> ProductionRule:
        src_name = p["source_class"]
        new_name = p["new_class_name"]
        src_node = GraphNode("src", NodeType.CLASS, {"name": src_name})
        new_node = GraphNode("new", NodeType.CLASS, {"name": new_name})
        return _make_rule(
            name=f"extract_class:{new_name} from {src_name}",
            op_type=OperatorType.EXTRACT_CLASS,
            lhs_nodes=[src_node], lhs_edges=[],
            interface_nodes=[src_node], interface_edges=[],
            rhs_nodes=[src_node, new_node], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", src_name, "source_exists"),
                _node_absent_precondition(NodeType.CLASS, "name", new_name, "name_available"),
            ],
            parameters=p, description=f"Extract class {new_name} from {src_name}", category="class",
        )

    def _inline_class(self, p: dict) -> ProductionRule:
        src_name = p["source_class"]
        target_name = p["target_class"]
        src_node = GraphNode("src", NodeType.CLASS, {"name": src_name})
        tgt_node = GraphNode("tgt", NodeType.CLASS, {"name": target_name})
        return _make_rule(
            name=f"inline_class:{src_name}->{target_name}",
            op_type=OperatorType.INLINE_CLASS,
            lhs_nodes=[src_node, tgt_node], lhs_edges=[],
            interface_nodes=[tgt_node], interface_edges=[],
            rhs_nodes=[tgt_node], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.CLASS, "name", src_name, "source_exists"),
                _node_exists_precondition(NodeType.CLASS, "name", target_name, "target_exists"),
            ],
            parameters=p, description=f"Inline class {src_name} into {target_name}", category="class",
        )

    def _extract_superclass(self, p: dict) -> ProductionRule:
        super_name = p["superclass_name"]
        super_node = GraphNode("super", NodeType.CLASS, {"name": super_name})
        return _make_rule(
            name=f"extract_superclass:{super_name}",
            op_type=OperatorType.EXTRACT_SUPERCLASS,
            lhs_nodes=[], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[super_node], rhs_edges=[],
            preconditions=[_node_absent_precondition(NodeType.CLASS, "name", super_name, "name_available")],
            postconditions=[_node_exists_postcondition(NodeType.CLASS, "name", super_name, "superclass_added")],
            parameters=p, description=f"Extract superclass {super_name}", category="class",
        )

    # =========================================================================
    # Parameter-Level Rules
    # =========================================================================

    def _add_param(self, p: dict) -> ProductionRule:
        func_name = p["function_name"]
        param_name = p["param_name"]
        func_attrs: dict[str, Any] = {"name": func_name}
        if p.get("file"):
            func_attrs["file"] = p["file"]
        func_node = GraphNode("func", NodeType.FUNCTION, func_attrs)
        param_node = GraphNode("param", NodeType.PARAMETER, {
            "name": param_name,
            "has_default": p.get("default_value") is not None,
            "default_value": p.get("default_value"),
            "is_keyword_only": p.get("keyword_only", True),
        })

        def _compute_param_position(match: GraphMorphism, host: TypedGraph) -> dict:
            host_func_id = match.map_node("func")
            if not host_func_id:
                return {"position": 0}
            existing = [
                e for e in host.edges
                if e.source == host_func_id and e.edge_type == EdgeType.HAS_PARAMETER
            ]
            return {"position": len(existing)}

        return _make_rule(
            name=f"add_param:{func_name}.{param_name}",
            op_type=OperatorType.ADD_PARAM,
            lhs_nodes=[func_node], lhs_edges=[],
            interface_nodes=[func_node], interface_edges=[],
            rhs_nodes=[func_node, param_node],
            rhs_edges=[GraphEdge("func", "param", EdgeType.HAS_PARAMETER)],
            preconditions=[_node_exists_precondition(NodeType.FUNCTION, "name", func_name, "func_exists")],
            postconditions=[_node_exists_postcondition(NodeType.PARAMETER, "name", param_name, "param_added")],
            attr_transfer={"param": _compute_param_position},
            parameters=p, description=f"Add parameter {param_name} to {func_name}", category="parameter",
        )

    def _remove_param(self, p: dict) -> ProductionRule:
        func_name = p["function_name"]
        param_name = p["param_name"]
        func_node = GraphNode("func", NodeType.FUNCTION, {"name": func_name})
        param_node = GraphNode("param", NodeType.PARAMETER, {"name": param_name})
        return _make_rule(
            name=f"remove_param:{func_name}.{param_name}",
            op_type=OperatorType.REMOVE_PARAM,
            lhs_nodes=[func_node, param_node],
            lhs_edges=[GraphEdge("func", "param", EdgeType.HAS_PARAMETER)],
            interface_nodes=[func_node], interface_edges=[],
            rhs_nodes=[func_node], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.FUNCTION, "name", func_name, "func_exists"),
                _node_exists_precondition(NodeType.PARAMETER, "name", param_name, "param_exists"),
            ],
            parameters=p, description=f"Remove parameter {param_name} from {func_name}", category="parameter",
        )

    def _rename_param(self, p: dict) -> ProductionRule:
        old_name = p["old_name"]
        new_name = p["new_name"]
        lhs_node = GraphNode("param", NodeType.PARAMETER, {"name": old_name})
        k_node = GraphNode("param", NodeType.PARAMETER, {})
        rhs_node = GraphNode("param", NodeType.PARAMETER, {"name": new_name})
        return _make_rule(
            name=f"rename_param:{old_name}->{new_name}",
            op_type=OperatorType.RENAME_PARAM,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            preconditions=[_node_exists_precondition(NodeType.PARAMETER, "name", old_name, "old_exists")],
            parameters=p, description=f"Rename parameter {old_name} to {new_name}", category="parameter",
        )

    def _introduce_param_object(self, p: dict) -> ProductionRule:
        func_name = p["function_name"]
        obj_name = p["object_name"]
        func_node = GraphNode("func", NodeType.FUNCTION, {"name": func_name})
        obj_param = GraphNode("obj", NodeType.PARAMETER, {"name": obj_name})

        def _compute_param_position(match: GraphMorphism, host: TypedGraph) -> dict:
            host_func_id = match.map_node("func")
            if not host_func_id:
                return {"position": 0}
            existing = [
                e for e in host.edges
                if e.source == host_func_id and e.edge_type == EdgeType.HAS_PARAMETER
            ]
            return {"position": len(existing)}

        return _make_rule(
            name=f"introduce_param_object:{func_name}.{obj_name}",
            op_type=OperatorType.INTRODUCE_PARAM_OBJECT,
            lhs_nodes=[func_node], lhs_edges=[],
            interface_nodes=[func_node], interface_edges=[],
            rhs_nodes=[func_node, obj_param],
            rhs_edges=[GraphEdge("func", "obj", EdgeType.HAS_PARAMETER)],
            preconditions=[_node_exists_precondition(NodeType.FUNCTION, "name", func_name, "func_exists")],
            attr_transfer={"obj": _compute_param_position},
            parameters=p, description=f"Introduce param object {obj_name} in {func_name}", category="parameter",
        )

    # =========================================================================
    # Module-Level Rules
    # =========================================================================

    def _create_module(self, p: dict) -> ProductionRule:
        mod_name = _normalize_module_name(p["module_name"])
        mod_node = GraphNode("mod", NodeType.MODULE, {"name": mod_name, "file": p.get("file", "")})
        return _make_rule(
            name=f"create_module:{mod_name}",
            op_type=OperatorType.CREATE_MODULE,
            lhs_nodes=[], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[mod_node], rhs_edges=[],
            preconditions=[_node_absent_precondition(NodeType.MODULE, "name", mod_name, "name_available")],
            postconditions=[_node_exists_postcondition(NodeType.MODULE, "name", mod_name, "module_created")],
            parameters=p, description=f"Create module {mod_name}", category="module",
        )

    def _delete_module(self, p: dict) -> ProductionRule:
        mod_name = _normalize_module_name(p["module_name"])
        mod_node = GraphNode("mod", NodeType.MODULE, {"name": mod_name})
        return _make_rule(
            name=f"delete_module:{mod_name}",
            op_type=OperatorType.DELETE_MODULE,
            lhs_nodes=[mod_node], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[], rhs_edges=[],
            preconditions=[_node_exists_precondition(NodeType.MODULE, "name", mod_name, "module_exists")],
            parameters=p, description=f"Delete module {mod_name}", category="module",
        )

    def _rename_module(self, p: dict) -> ProductionRule:
        old_name = _normalize_module_name(p["old_name"])
        new_name = _normalize_module_name(p["new_name"])
        lhs_node = GraphNode("mod", NodeType.MODULE, {"name": old_name})
        k_node = GraphNode("mod", NodeType.MODULE, {})
        rhs_node = GraphNode("mod", NodeType.MODULE, {"name": new_name})
        return _make_rule(
            name=f"rename_module:{old_name}->{new_name}",
            op_type=OperatorType.RENAME_MODULE,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            preconditions=[_node_exists_precondition(NodeType.MODULE, "name", old_name, "old_exists")],
            parameters=p, description=f"Rename module {old_name} to {new_name}", category="module",
        )

    def _move_to_module(self, p: dict) -> ProductionRule:
        item_name = p["item_name"]
        target_mod = _normalize_module_name(p["target_module"])
        item_type = NodeType(p.get("item_type", "function"))
        item_node = GraphNode("item", item_type, {"name": item_name})
        mod_node = GraphNode("mod", NodeType.MODULE, {"name": target_mod})
        return _make_rule(
            name=f"move_to_module:{item_name}->{target_mod}",
            op_type=OperatorType.MOVE_TO_MODULE,
            lhs_nodes=[item_node, mod_node], lhs_edges=[],
            interface_nodes=[item_node, mod_node], interface_edges=[],
            rhs_nodes=[item_node, mod_node],
            rhs_edges=[GraphEdge("item", "mod", EdgeType.DEFINED_IN)],
            preconditions=[_node_exists_precondition(NodeType.MODULE, "name", target_mod, "module_exists")],
            parameters=p, description=f"Move {item_name} to module {target_mod}", category="module",
        )

    def _merge_modules(self, p: dict) -> ProductionRule:
        src_name = _normalize_module_name(p["source_module"])
        tgt_name = _normalize_module_name(p["target_module"])
        src_node = GraphNode("src", NodeType.MODULE, {"name": src_name})
        tgt_node = GraphNode("tgt", NodeType.MODULE, {"name": tgt_name})
        return _make_rule(
            name=f"merge_modules:{src_name}->{tgt_name}",
            op_type=OperatorType.MERGE_MODULES,
            lhs_nodes=[src_node, tgt_node], lhs_edges=[],
            interface_nodes=[tgt_node], interface_edges=[],
            rhs_nodes=[tgt_node], rhs_edges=[],
            preconditions=[
                _node_exists_precondition(NodeType.MODULE, "name", src_name, "source_exists"),
                _node_exists_precondition(NodeType.MODULE, "name", tgt_name, "target_exists"),
            ],
            parameters=p, description=f"Merge module {src_name} into {tgt_name}", category="module",
        )

    # =========================================================================
    # Reference-Level Rules
    # =========================================================================

    def _add_import(self, p: dict) -> ProductionRule:
        mod = p["module"]
        name = p.get("name", "")
        imp_node = GraphNode("imp", NodeType.IMPORT, {
            "module": mod,
            "name": name,
            "alias": p.get("alias"),
            "file": p.get("file", ""),
            "is_from_import": p.get("is_from_import", bool(name)),
        })
        return _make_rule(
            name=f"add_import:{mod}.{name}",
            op_type=OperatorType.ADD_IMPORT,
            lhs_nodes=[], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[imp_node], rhs_edges=[],
            parameters=p, description=f"Add import {mod}.{name}", category="reference",
        )

    def _remove_import(self, p: dict) -> ProductionRule:
        mod = p["module"]
        name = p.get("name", "")
        imp_node = GraphNode("imp", NodeType.IMPORT, {"module": mod, "name": name})
        return _make_rule(
            name=f"remove_import:{mod}.{name}",
            op_type=OperatorType.REMOVE_IMPORT,
            lhs_nodes=[imp_node], lhs_edges=[],
            interface_nodes=[], interface_edges=[],
            rhs_nodes=[], rhs_edges=[],
            preconditions=[_node_exists_precondition(NodeType.IMPORT, "module", mod, "import_exists")],
            parameters=p, description=f"Remove import {mod}.{name}", category="reference",
        )

    @staticmethod
    def _split_module_path(module: str) -> tuple[str, str] | None:
        """Split a module path into (parent, child) for submodule matching.

        Handles relative imports where leading dots are part of the parent:
          ".exceptions"      → (".", "exceptions")
          "..pkg.mod"        → ("..pkg", "mod")
          "pkg.mod"          → ("pkg", "mod")
          "os"               → None  (no split possible)
          "."                → None  (no child component)
        """
        # Separate leading dots (relative import markers) from the rest
        i = 0
        while i < len(module) and module[i] == ".":
            i += 1
        dots = module[:i]
        rest = module[i:]

        if "." in rest:
            # "pkg.mod" portion can be split normally
            parent, child = rest.rsplit(".", 1)
            return (dots + parent, child)
        elif dots and rest:
            # Relative import: ".exceptions" → (".", "exceptions")
            return (dots, rest)
        else:
            # Can't split: bare "os" or just "."
            return None

    def _update_import(self, p: dict) -> ProductionRule | list[ProductionRule]:
        old_module = p["old_module"]
        new_module = p["new_module"]
        names = p.get("names")  # Optional: list of specific imported names to move

        if names:
            # Selective mode: only move specific named imports.
            # Creates one rule per name, matching module AND name.
            # No submodule rules — `names` only applies to `from X import Y` pattern.
            rules: list[ProductionRule] = []
            for name in names:
                lhs_node = GraphNode("imp", NodeType.IMPORT, {
                    "module": old_module, "name": name,
                })
                k_node = GraphNode("imp", NodeType.IMPORT, {})
                rhs_node = GraphNode("imp", NodeType.IMPORT, {"module": new_module})

                rules.append(_make_rule(
                    name=f"update_import:{old_module}->{new_module}[{name}]",
                    op_type=OperatorType.UPDATE_IMPORT,
                    lhs_nodes=[lhs_node], lhs_edges=[],
                    interface_nodes=[k_node], interface_edges=[],
                    rhs_nodes=[rhs_node], rhs_edges=[],
                    preconditions=[],
                    parameters=p,
                    description=f"Move import of {name} from {old_module} to {new_module}",
                    category="reference",
                ))
            return rules

        # Rule 1: Match `from old_module import X` pattern
        # e.g., from ansible.module_utils.facts.namespace import PrefixFactNamespace
        # e.g., from .exceptions import FileModeWarning  (relative)
        lhs_node = GraphNode("imp", NodeType.IMPORT, {"module": old_module})
        k_node = GraphNode("imp", NodeType.IMPORT, {})
        rhs_node = GraphNode("imp", NodeType.IMPORT, {"module": new_module})

        rule_direct = _make_rule(
            name=f"update_import:{old_module}->{new_module}",
            op_type=OperatorType.UPDATE_IMPORT,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            preconditions=[_node_exists_precondition(NodeType.IMPORT, "module", old_module, "old_exists")],
            parameters=p,
            description=f"Update import {old_module} to {new_module}",
            category="reference",
        )

        # Rule 2: Match `from parent import submodule` pattern
        # e.g., from ansible.module_utils.facts import namespace
        # e.g., from . import exceptions  (relative)
        old_split = self._split_module_path(old_module)
        new_split = self._split_module_path(new_module)
        if old_split and new_split:
            old_parent, old_child = old_split
            new_parent, new_child = new_split

            lhs_sub = GraphNode("imp", NodeType.IMPORT, {
                "module": old_parent, "name": old_child,
            })
            k_sub = GraphNode("imp", NodeType.IMPORT, {})
            rhs_sub = GraphNode("imp", NodeType.IMPORT, {
                "module": new_parent, "name": new_child,
            })

            rule_submodule = _make_rule(
                name=f"update_import:{old_parent}.{old_child}->{new_parent}.{new_child}(submodule)",
                op_type=OperatorType.UPDATE_IMPORT,
                lhs_nodes=[lhs_sub], lhs_edges=[],
                interface_nodes=[k_sub], interface_edges=[],
                rhs_nodes=[rhs_sub], rhs_edges=[],
                preconditions=[],
                parameters=p,
                description=f"Update submodule import {old_child} to {new_child}",
                category="reference",
            )
            return [rule_direct, rule_submodule]

        return rule_direct

    def _update_call(self, p: dict) -> ProductionRule:
        old_callee = p["old_callee"]
        new_callee = p["new_callee"]
        lhs_node = GraphNode("call", NodeType.CALL, self._call_attrs(old_callee, p))
        k_node = GraphNode("call", NodeType.CALL, {})
        rhs_node = GraphNode("call", NodeType.CALL, {"callee": new_callee})
        return _make_rule(
            name=f"update_call:{old_callee}->{new_callee}",
            op_type=OperatorType.UPDATE_CALL,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            parameters=p, description=f"Update call from {old_callee} to {new_callee}", category="reference",
        )

    def _update_reference(self, p: dict) -> ProductionRule:
        old_ref = p["old_ref"]
        new_ref = p["new_ref"]
        lhs_node = GraphNode("ref", NodeType.CALL, {"callee": old_ref})
        k_node = GraphNode("ref", NodeType.CALL, {})
        rhs_node = GraphNode("ref", NodeType.CALL, {"callee": new_ref})
        return _make_rule(
            name=f"update_reference:{old_ref}->{new_ref}",
            op_type=OperatorType.UPDATE_REFERENCE,
            lhs_nodes=[lhs_node], lhs_edges=[],
            interface_nodes=[k_node], interface_edges=[],
            rhs_nodes=[rhs_node], rhs_edges=[],
            parameters=p, description=f"Update reference {old_ref} to {new_ref}", category="reference",
        )

    # =========================================================================
    # Call-Site Level Rules
    # =========================================================================

    @staticmethod
    def _call_attrs(callee: str, p: dict) -> dict:
        """Build CALL node attrs, optionally filtering by call_type and file."""
        attrs: dict = {"callee": callee}
        call_type = p.get("call_type")
        if call_type in ("direct", "method"):
            attrs["call_type"] = call_type
        if p.get("file"):
            attrs["file"] = p["file"]
        return attrs

    def _add_arg(self, p: dict) -> ProductionRule:
        callee = p["callee"]
        arg_name = p["arg_name"]
        arg_value = p.get("arg_value")
        call_node = GraphNode("call", NodeType.CALL, self._call_attrs(callee, p))
        arg_node = GraphNode("arg", NodeType.ARGUMENT, {
            "name": arg_name,
            "value": arg_value,
            "is_keyword": p.get("is_keyword", True),
        })

        def _compute_arg_position(match: GraphMorphism, host: TypedGraph) -> dict:
            host_call_id = match.map_node("call")
            if not host_call_id:
                return {"position": 0}
            existing = [
                e for e in host.edges
                if e.source == host_call_id and e.edge_type == EdgeType.HAS_ARGUMENT
            ]
            return {"position": len(existing)}

        return _make_rule(
            name=f"add_arg:{callee}.{arg_name}",
            op_type=OperatorType.ADD_ARG,
            lhs_nodes=[call_node], lhs_edges=[],
            interface_nodes=[call_node], interface_edges=[],
            rhs_nodes=[call_node, arg_node],
            rhs_edges=[GraphEdge("call", "arg", EdgeType.HAS_ARGUMENT)],
            attr_transfer={"arg": _compute_arg_position},
            parameters=p, description=f"Add argument {arg_name} to calls of {callee}", category="call_site",
        )

    def _remove_arg(self, p: dict) -> ProductionRule:
        callee = p["callee"]
        arg_name = p["arg_name"]
        call_node = GraphNode("call", NodeType.CALL, self._call_attrs(callee, p))
        arg_node = GraphNode("arg", NodeType.ARGUMENT, {"name": arg_name})
        return _make_rule(
            name=f"remove_arg:{callee}.{arg_name}",
            op_type=OperatorType.REMOVE_ARG,
            lhs_nodes=[call_node, arg_node],
            lhs_edges=[GraphEdge("call", "arg", EdgeType.HAS_ARGUMENT)],
            interface_nodes=[call_node], interface_edges=[],
            rhs_nodes=[call_node], rhs_edges=[],
            parameters=p, description=f"Remove argument {arg_name} from calls of {callee}", category="call_site",
        )

    def _update_arg(self, p: dict) -> ProductionRule:
        callee = p["callee"]
        arg_name = p["arg_name"]
        new_value = p["new_value"]
        call_attrs = self._call_attrs(callee, p)
        lhs_call = GraphNode("call", NodeType.CALL, call_attrs)
        lhs_arg = GraphNode("arg", NodeType.ARGUMENT, {"name": arg_name})
        k_call = GraphNode("call", NodeType.CALL, call_attrs)
        k_arg = GraphNode("arg", NodeType.ARGUMENT, {"name": arg_name})
        rhs_call = GraphNode("call", NodeType.CALL, call_attrs)
        rhs_arg = GraphNode("arg", NodeType.ARGUMENT, {"name": arg_name, "value": new_value})
        return _make_rule(
            name=f"update_arg:{callee}.{arg_name}={new_value}",
            op_type=OperatorType.UPDATE_ARG,
            lhs_nodes=[lhs_call, lhs_arg],
            lhs_edges=[GraphEdge("call", "arg", EdgeType.HAS_ARGUMENT)],
            interface_nodes=[k_call, k_arg],
            interface_edges=[GraphEdge("call", "arg", EdgeType.HAS_ARGUMENT)],
            rhs_nodes=[rhs_call, rhs_arg],
            rhs_edges=[GraphEdge("call", "arg", EdgeType.HAS_ARGUMENT)],
            parameters=p, description=f"Update argument {arg_name}={new_value} in calls of {callee}", category="call_site",
        )
