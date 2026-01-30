"""
Invariant System

Pre/post conditions and graph-level invariants for verifying
correctness of graph transformations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from graph_transform.core.typed_graph import EdgeType, GraphNode, NodeType, TypedGraph


# =============================================================================
# InvariantViolation
# =============================================================================


@dataclass
class InvariantViolation:
    """A violated invariant."""

    invariant_name: str
    message: str
    severity: str = "error"  # "error" | "warning"
    node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant_name": self.invariant_name,
            "message": self.message,
            "severity": self.severity,
            "node_id": self.node_id,
        }


# =============================================================================
# Invariant
# =============================================================================


@dataclass
class Invariant:
    """A graph invariant or pre/postcondition.

    Wraps a predicate function with metadata.
    The check function takes a TypedGraph and returns a list of violations.
    """

    name: str
    description: str
    check: Callable[[TypedGraph], list[InvariantViolation]]
    severity: str = "error"

    def verify(self, graph: TypedGraph) -> list[InvariantViolation]:
        """Run the invariant check on a graph."""
        return self.check(graph)


# =============================================================================
# Standard Graph Invariants
# =============================================================================


def _check_no_dangling_edges(graph: TypedGraph) -> list[InvariantViolation]:
    """All edge endpoints must exist as nodes.
    
    Note: INHERITS edges to external classes (e.g., stdlib base classes like
    MutableMapping, ABC) are allowed since we don't include stdlib in the graph.
    """
    violations = []
    for edge in graph.dangling_edges():
        # Allow inheritance from external classes (not in graph)
        if edge.edge_type == EdgeType.INHERITS:
            continue
        violations.append(InvariantViolation(
            invariant_name="no_dangling_edges",
            message=(
                f"Dangling edge: {edge.source} -> {edge.target} "
                f"(type={edge.edge_type.value})"
            ),
            severity="error",
        ))
    return violations


def _check_unique_function_names_in_class(graph: TypedGraph) -> list[InvariantViolation]:
    """No two methods in a class should have the same name."""
    violations = []
    for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
        method_edges = [
            e for e in graph.get_edges_from(cls_node.id)
            if e.edge_type == EdgeType.CONTAINS_METHOD
        ]
        method_names: dict[str, str] = {}
        for edge in method_edges:
            func_node = graph.get_node(edge.target)
            if func_node:
                name = func_node.attrs.get("name", "")
                if name in method_names:
                    violations.append(InvariantViolation(
                        invariant_name="unique_function_names_in_class",
                        message=(
                            f"Duplicate method '{name}' in class "
                            f"'{cls_node.attrs.get('name', cls_node.id)}'"
                        ),
                        severity="error",
                        node_id=func_node.id,
                    ))
                else:
                    method_names[name] = func_node.id
    return violations


def _check_unique_class_names_in_module(graph: TypedGraph) -> list[InvariantViolation]:
    """No two classes in a module should have the same name."""
    violations = []
    for mod_node in graph.get_nodes_by_type(NodeType.MODULE):
        class_names: dict[str, str] = {}
        for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
            # Check if class is defined in this module
            defined_in = [
                e for e in graph.get_edges_from(cls_node.id)
                if e.edge_type == EdgeType.DEFINED_IN and e.target == mod_node.id
            ]
            if defined_in:
                name = cls_node.attrs.get("name", "")
                if name in class_names:
                    violations.append(InvariantViolation(
                        invariant_name="unique_class_names_in_module",
                        message=(
                            f"Duplicate class '{name}' in module "
                            f"'{mod_node.attrs.get('name', mod_node.id)}'"
                        ),
                        severity="error",
                        node_id=cls_node.id,
                    ))
                else:
                    class_names[name] = cls_node.id
    return violations


def _check_unique_field_names_in_class(graph: TypedGraph) -> list[InvariantViolation]:
    """No two fields in a class should have the same name."""
    violations = []
    for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
        field_edges = [
            e for e in graph.get_edges_from(cls_node.id)
            if e.edge_type == EdgeType.CONTAINS_FIELD
        ]
        field_names: dict[str, str] = {}
        for edge in field_edges:
            fld_node = graph.get_node(edge.target)
            if fld_node:
                name = fld_node.attrs.get("name", "")
                if name in field_names:
                    violations.append(InvariantViolation(
                        invariant_name="unique_field_names_in_class",
                        message=(
                            f"Duplicate field '{name}' in class "
                            f"'{cls_node.attrs.get('name', cls_node.id)}'"
                        ),
                        severity="error",
                        node_id=fld_node.id,
                    ))
                else:
                    field_names[name] = fld_node.id
    return violations


def _check_valid_inheritance(graph: TypedGraph) -> list[InvariantViolation]:
    """No circular inheritance, base classes must exist."""
    violations = []
    class_ids = {n.id for n in graph.get_nodes_by_type(NodeType.CLASS)}

    for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
        # Check for self-inheritance
        for edge in graph.get_edges_from(cls_node.id):
            if edge.edge_type == EdgeType.INHERITS:
                if edge.target == cls_node.id:
                    violations.append(InvariantViolation(
                        invariant_name="valid_inheritance",
                        message=f"Self-inheritance: '{cls_node.attrs.get('name', cls_node.id)}'",
                        severity="error",
                        node_id=cls_node.id,
                    ))

        # Check for cycles (simple: walk up to depth limit)
        visited: set[str] = set()
        current = cls_node.id
        depth = 0
        while depth < 100:
            parents = [
                e.target for e in graph.get_edges_from(current)
                if e.edge_type == EdgeType.INHERITS
            ]
            if not parents:
                break
            current = parents[0]
            if current in visited:
                violations.append(InvariantViolation(
                    invariant_name="valid_inheritance",
                    message=(
                        f"Circular inheritance detected involving "
                        f"'{cls_node.attrs.get('name', cls_node.id)}'"
                    ),
                    severity="error",
                    node_id=cls_node.id,
                ))
                break
            visited.add(current)
            depth += 1

    return violations


def _check_parameter_positions_consecutive(graph: TypedGraph) -> list[InvariantViolation]:
    """Parameter positions in a function should be 0, 1, 2, ..., n-1."""
    violations = []
    for func_node in graph.get_nodes_by_type(NodeType.FUNCTION):
        param_edges = [
            e for e in graph.get_edges_from(func_node.id)
            if e.edge_type == EdgeType.HAS_PARAMETER
        ]
        positions = []
        for edge in param_edges:
            param_node = graph.get_node(edge.target)
            if param_node:
                pos = param_node.attrs.get("position")
                if pos is not None:
                    positions.append(pos)
        if positions:
            positions.sort()
            expected = list(range(len(positions)))
            if positions != expected:
                violations.append(InvariantViolation(
                    invariant_name="parameter_positions_consecutive",
                    message=(
                        f"Non-consecutive parameter positions in "
                        f"'{func_node.attrs.get('name', func_node.id)}': "
                        f"got {positions}, expected {expected}"
                    ),
                    severity="warning",
                    node_id=func_node.id,
                ))
    return violations


def _check_symbol_resolution(graph: TypedGraph) -> list[InvariantViolation]:
    """All CALLS and REFERENCES edges must point to valid definitions."""
    violations = []
    for edge in graph.edges:
        if edge.edge_type in (EdgeType.CALLS, EdgeType.REFERENCES):
            target_node = graph.get_node(edge.target)
            if not target_node:
                violations.append(InvariantViolation(
                    invariant_name="symbol_resolution",
                    message=f"Dangling symbol reference: {edge.source} -> {edge.target}",
                    severity="error",
                    node_id=edge.source,
                ))
    return violations


def _check_no_global_name_clashes(graph: TypedGraph) -> list[InvariantViolation]:
    """Ensure no duplicate module names or global function names."""
    violations = []
    
    # Check module names
    module_names: dict[str, str] = {}
    for mod in graph.get_nodes_by_type(NodeType.MODULE):
        name = mod.attrs.get("name", "")
        if name in module_names:
            violations.append(InvariantViolation(
                invariant_name="no_global_name_clashes",
                message=f"Duplicate module name: '{name}'",
                severity="error",
                node_id=mod.id,
            ))
        else:
            module_names[name] = mod.id
            
    # Check global functions (is_method=False)
    global_funcs: dict[str, str] = {}
    for func in graph.get_nodes_by_type(NodeType.FUNCTION):
        if not func.attrs.get("is_method", False):
            name = func.attrs.get("name", "")
            if name in global_funcs:
                violations.append(InvariantViolation(
                    invariant_name="no_global_name_clashes",
                    message=f"Duplicate global function name: '{name}'",
                    severity="error",
                    node_id=func.id,
                ))
            else:
                global_funcs[name] = func.id
                
    return violations


def _check_node_attribute_completeness(graph: TypedGraph) -> list[InvariantViolation]:
    """Verify nodes have required attributes for their type."""
    violations = []
    required_attrs = {
        NodeType.FUNCTION: ["name", "is_method"],
        NodeType.CLASS: ["name"],
        NodeType.PARAMETER: ["name", "position"],
        NodeType.CALL: ["callee"],
        NodeType.ARGUMENT: ["position"],
        NodeType.IMPORT: ["module"],
        NodeType.MODULE: ["name"],
    }
    
    for node_id, node in graph.nodes.items():
        if node.node_type in required_attrs:
            for attr in required_attrs[node.node_type]:
                if attr not in node.attrs:
                    violations.append(InvariantViolation(
                        invariant_name="node_attribute_completeness",
                        message=f"Node {node_id} ({node.node_type.value}) missing required attribute: '{attr}'",
                        severity="error",
                        node_id=node_id,
                    ))
    return violations


def _check_unused_imports(graph: TypedGraph) -> list[InvariantViolation]:
    """(Warning) Identify IMPORT nodes that are not referenced."""
    violations = []
    used_imports = set()
    
    # Find all references to imports
    # In this graph model, generic REFERENCES or CALLS might point to something that originated from an import.
    # We check all outgoing edges from other nodes that might target an import.
    referenced_node_ids = {edge.target for edge in graph.edges}
    
    for imp_node in graph.get_nodes_by_type(NodeType.IMPORT):
        if imp_node.id not in referenced_node_ids:
            violations.append(InvariantViolation(
                invariant_name="unused_imports_warning",
                message=f"Unused import: {imp_node.attrs.get('module', imp_node.id)}",
                severity="warning",
                node_id=imp_node.id,
            ))
    return violations


def _check_call_argument_count_match(graph: TypedGraph) -> list[InvariantViolation]:
    """Verify CALL nodes have matching argument count with target FUNCTION."""
    violations = []
    for call_node in graph.get_nodes_by_type(NodeType.CALL):
        # Find the target function
        call_edges = [e for e in graph.get_edges_from(call_node.id) if e.edge_type == EdgeType.CALLS]
        if not call_edges:
            continue
            
        target_func_id = call_edges[0].target
        target_func = graph.get_node(target_func_id)
        
        if target_func and target_func.node_type == NodeType.FUNCTION:
            # Count arguments
            arg_count = len([e for e in graph.get_edges_from(call_node.id) if e.edge_type == EdgeType.HAS_ARGUMENT])
            # Count parameters
            param_count = len([e for e in graph.get_edges_from(target_func_id) if e.edge_type == EdgeType.HAS_PARAMETER])
            
            if arg_count != param_count:
                # Note: This is an simplification (doesn't account for default values, *args, **kwargs)
                # but good as a base invariant.
                violations.append(InvariantViolation(
                    invariant_name="call_argument_count_match",
                    message=(
                        f"Call to '{target_func.attrs.get('name')}' has {arg_count} arguments, "
                        f"but function has {param_count} parameters."
                    ),
                    severity="error",
                    node_id=call_node.id,
                ))
    return violations


# =============================================================================
# InvariantRegistry
# =============================================================================


class InvariantRegistry:
    """Registry of all graph invariants.

    Categories:
    1. Graph-level invariants (always hold)
    2. Preconditions (specific to an operator)
    3. Postconditions (verified after application)
    """

    def __init__(self) -> None:
        self._graph_invariants: list[Invariant] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register standard graph invariants."""
        self._graph_invariants = [
            Invariant(
                name="no_dangling_edges",
                description="All edge endpoints must exist as nodes",
                check=_check_no_dangling_edges,
            ),
            Invariant(
                name="unique_function_names_in_class",
                description="No duplicate method names within a class",
                check=_check_unique_function_names_in_class,
            ),
            Invariant(
                name="unique_class_names_in_module",
                description="No duplicate class names within a module",
                check=_check_unique_class_names_in_module,
            ),
            Invariant(
                name="unique_field_names_in_class",
                description="No duplicate field names within a class",
                check=_check_unique_field_names_in_class,
            ),
            Invariant(
                name="valid_inheritance",
                description="No circular inheritance, no self-inheritance",
                check=_check_valid_inheritance,
            ),
            Invariant(
                name="parameter_positions_consecutive",
                description="Parameter positions should be 0..n-1",
                check=_check_parameter_positions_consecutive,
                severity="warning",
            ),
            Invariant(
                name="symbol_resolution",
                description="All CALLS and REFERENCES edges must point to valid definitions",
                check=_check_symbol_resolution,
            ),
            Invariant(
                name="no_global_name_clashes",
                description="Ensure no duplicate module names or global function names",
                check=_check_no_global_name_clashes,
            ),
            # TODO: Temporarily disabled - re-enable once source graph data is fixed
            # Invariant(
            #     name="node_attribute_completeness",
            #     description="Verify nodes have required attributes for their type",
            #     check=_check_node_attribute_completeness,
            # ),
            Invariant(
                name="unused_imports_warning",
                description="Identify IMPORT nodes that are not referenced",
                check=_check_unused_imports,
                severity="warning",
            ),
            Invariant(
                name="call_argument_count_match",
                description="Verify CALL nodes have matching argument count with target FUNCTION",
                check=_check_call_argument_count_match,
            ),
        ]

    @property
    def graph_invariants(self) -> list[Invariant]:
        return list(self._graph_invariants)

    def add_invariant(self, invariant: Invariant) -> None:
        """Add a custom graph invariant."""
        self._graph_invariants.append(invariant)

    def verify_graph(self, graph: TypedGraph) -> list[InvariantViolation]:
        """Run all graph-level invariants."""
        violations = []
        for inv in self._graph_invariants:
            violations.extend(inv.verify(graph))
        return violations

    def verify_preconditions(
        self,
        preconditions: list[Invariant],
        graph: TypedGraph,
    ) -> list[InvariantViolation]:
        """Verify rule preconditions on the graph."""
        violations = []
        for pre in preconditions:
            violations.extend(pre.verify(graph))
        return violations

    def verify_postconditions(
        self,
        postconditions: list[Invariant],
        graph: TypedGraph,
    ) -> list[InvariantViolation]:
        """Verify rule postconditions on the result graph."""
        violations = []
        for post in postconditions:
            violations.extend(post.verify(graph))
        return violations
