"""
Invariant System — Layered, Schema-Driven Graph Verification

Organizes correctness checks into ordered layers, each backed by
declarative abstractions (GraphSchema, ScopeRule, ReferenceRule)
rather than ad-hoc hand-coded functions.

Layer architecture:
    0  SCHEMA     – type graph conformance (edge types, multiplicity, attrs)
    1  STRUCTURE  – topological integrity (acyclicity, reachability)
    2  SCOPE      – name uniqueness within scopes (parametric)
    3  REFERENCE  – symbol resolution and consistency (parametric)
    4  TYPE_SYSTEM – inheritance DAG, override compatibility
    5  SEMANTIC   – argument/parameter matching
    6  QUALITY    – unused imports, empty containers, hints
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)


# =============================================================================
# Enums
# =============================================================================


class InvariantSeverity(Enum):
    """Severity level for invariant violations."""

    ERROR = "error"  # Blocks transformation
    WARNING = "warning"  # Reports but does not block
    INFO = "info"  # Informational hint


class InvariantLayer(Enum):
    """Ordered verification layers — lower ordinals must pass first."""

    SCHEMA = 0  # Type graph conformance
    STRUCTURE = 1  # Topological integrity
    SCOPE = 2  # Name uniqueness
    REFERENCE = 3  # Symbol resolution
    TYPE_SYSTEM = 4  # Inheritance, overrides
    SEMANTIC = 5  # Arg/param consistency
    QUALITY = 6  # Hints, style


# =============================================================================
# InvariantViolation
# =============================================================================


@dataclass
class InvariantViolation:
    """A violated invariant with rich diagnostic context."""

    invariant_name: str
    message: str
    severity: InvariantSeverity = InvariantSeverity.ERROR
    layer: InvariantLayer = InvariantLayer.STRUCTURE
    node_id: str | None = None
    edge: GraphEdge | None = None
    related_nodes: list[str] = field(default_factory=list)
    fix_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "invariant_name": self.invariant_name,
            "message": self.message,
            "severity": self.severity.value,
            "layer": self.layer.name.lower(),
            "node_id": self.node_id,
        }
        if self.edge:
            result["edge"] = {
                "source": self.edge.source,
                "target": self.edge.target,
                "type": self.edge.edge_type.value,
            }
        if self.related_nodes:
            result["related_nodes"] = self.related_nodes
        if self.fix_hint:
            result["fix_hint"] = self.fix_hint
        return result


# =============================================================================
# Invariant
# =============================================================================


@dataclass
class Invariant:
    """A graph invariant or pre/postcondition.

    Wraps a check function with metadata including severity, layer, and
    an ``enabled`` flag that replaces the old practice of commenting out
    invariants.
    """

    name: str
    description: str
    check: Callable[[TypedGraph], list[InvariantViolation]]
    severity: InvariantSeverity = InvariantSeverity.ERROR
    layer: InvariantLayer = InvariantLayer.STRUCTURE
    enabled: bool = True

    def verify(self, graph: TypedGraph) -> list[InvariantViolation]:
        """Run the invariant check on *graph* (no-op if disabled)."""
        if not self.enabled:
            return []
        return self.check(graph)


# =============================================================================
# Layer 0 — Graph Schema
# =============================================================================


@dataclass(frozen=True)
class EdgeConstraint:
    """Typing constraint for one edge type in the graph schema."""

    edge_type: EdgeType
    source_types: frozenset[NodeType]
    target_types: frozenset[NodeType]
    target_max: int | None = None  # max incoming edges of this type per target
    source_max: int | None = None  # max outgoing edges of this type per source
    allow_external_target: bool = False  # target may be absent (external ref)


class GraphSchema:
    """Declarative type graph defining the code graph structure.

    A single :meth:`validate` call replaces the old ``no_dangling_edges``,
    ``edge_type_correctness``, ``containment_well_formedness``,
    ``node_attribute_completeness``, and ``defined_in_consistency`` checks.
    """

    CONSTRAINTS: dict[EdgeType, EdgeConstraint] = {
        EdgeType.CONTAINS_METHOD: EdgeConstraint(
            edge_type=EdgeType.CONTAINS_METHOD,
            source_types=frozenset({NodeType.CLASS}),
            target_types=frozenset({NodeType.FUNCTION}),
            target_max=1,
        ),
        EdgeType.CONTAINS_FIELD: EdgeConstraint(
            edge_type=EdgeType.CONTAINS_FIELD,
            source_types=frozenset({NodeType.CLASS}),
            target_types=frozenset({NodeType.FIELD}),
            target_max=1,
        ),
        EdgeType.HAS_PARAMETER: EdgeConstraint(
            edge_type=EdgeType.HAS_PARAMETER,
            source_types=frozenset({NodeType.FUNCTION}),
            target_types=frozenset({NodeType.PARAMETER}),
            target_max=1,
        ),
        EdgeType.HAS_ARGUMENT: EdgeConstraint(
            edge_type=EdgeType.HAS_ARGUMENT,
            source_types=frozenset({NodeType.CALL}),
            target_types=frozenset({NodeType.ARGUMENT}),
            target_max=1,
        ),
        EdgeType.CALLS: EdgeConstraint(
            edge_type=EdgeType.CALLS,
            source_types=frozenset({NodeType.CALL}),
            target_types=frozenset({NodeType.FUNCTION}),
        ),
        EdgeType.INHERITS: EdgeConstraint(
            edge_type=EdgeType.INHERITS,
            source_types=frozenset({NodeType.CLASS}),
            target_types=frozenset({NodeType.CLASS}),
            allow_external_target=True,
        ),
        EdgeType.IMPORTS: EdgeConstraint(
            edge_type=EdgeType.IMPORTS,
            source_types=frozenset({NodeType.MODULE}),
            target_types=frozenset({NodeType.IMPORT}),
        ),
        EdgeType.CONTAINS: EdgeConstraint(
            edge_type=EdgeType.CONTAINS,
            source_types=frozenset({NodeType.MODULE}),
            target_types=frozenset({NodeType.CLASS, NodeType.FUNCTION}),
            target_max=1,  # Each function/class can only be in one module
        ),
        EdgeType.EXPORTS: EdgeConstraint(
            edge_type=EdgeType.EXPORTS,
            source_types=frozenset({NodeType.MODULE}),
            target_types=frozenset({NodeType.CLASS, NodeType.FUNCTION}),
            # A module can export multiple symbols, and a symbol can only be exported by its defining module
        ),
        EdgeType.DEFINED_IN: EdgeConstraint(
            edge_type=EdgeType.DEFINED_IN,
            source_types=frozenset({NodeType.CLASS, NodeType.FUNCTION}),
            target_types=frozenset({NodeType.MODULE}),
            source_max=1,
        ),
        EdgeType.CALLER_OF: EdgeConstraint(
            edge_type=EdgeType.CALLER_OF,
            source_types=frozenset({NodeType.FUNCTION}),
            target_types=frozenset({NodeType.CALL}),
        ),
        EdgeType.REFERENCES: EdgeConstraint(
            edge_type=EdgeType.REFERENCES,
            source_types=frozenset(
                {NodeType.FUNCTION, NodeType.CLASS, NodeType.CALL}
            ),
            target_types=frozenset(
                {NodeType.FUNCTION, NodeType.CLASS, NodeType.FIELD, NodeType.IMPORT}
            ),
        ),
    }

    REQUIRED_ATTRS: dict[NodeType, list[str]] = {
        NodeType.FUNCTION: ["name"],
        NodeType.CLASS: ["name"],
        NodeType.PARAMETER: ["name", "position"],
        NodeType.CALL: ["callee"],
        NodeType.ARGUMENT: ["position"],
        NodeType.IMPORT: ["module"],
        NodeType.MODULE: ["name"],
        NodeType.FIELD: ["name"],
        # Control flow nodes (added for primitives)
        NodeType.BLOCK: [],
        NodeType.BRANCH: [],
        NodeType.LOOP: [],
        # Expression nodes (added for primitives)
        NodeType.EXPRESSION: [],
        NodeType.LITERAL: [],
        # Annotation nodes (added for primitives)
        NodeType.ANNOTATION: [],
    }

    def validate(self, graph: TypedGraph) -> list[InvariantViolation]:
        """Validate *graph* against this schema."""
        violations: list[InvariantViolation] = []
        self._check_dangling_and_typing(graph, violations)
        self._check_multiplicity(graph, violations)
        self._check_required_attrs(graph, violations)
        return violations

    # -- internal helpers -----------------------------------------------------

    def _check_dangling_and_typing(
        self,
        graph: TypedGraph,
        violations: list[InvariantViolation],
    ) -> None:
        for edge in graph.edges:
            constraint = self.CONSTRAINTS.get(edge.edge_type)
            src_node = graph.get_node(edge.source)
            tgt_node = graph.get_node(edge.target)

            # Dangling source — always an error
            if src_node is None:
                violations.append(InvariantViolation(
                    invariant_name="schema_conformance",
                    message=(
                        f"Dangling edge source: {edge.source} -> {edge.target} "
                        f"(type={edge.edge_type.value})"
                    ),
                    layer=InvariantLayer.SCHEMA,
                    edge=edge,
                    fix_hint="Add the missing source node or remove the edge",
                ))
                continue

            # Dangling target — WARNING (not error) because partial graphs
            # (subgraph scoping) naturally have edges to external nodes.
            if tgt_node is None:
                if constraint and constraint.allow_external_target:
                    continue  # e.g. INHERITS to stdlib class
                violations.append(InvariantViolation(
                    invariant_name="schema_conformance",
                    message=(
                        f"Dangling edge target: {edge.source} -> {edge.target} "
                        f"(type={edge.edge_type.value})"
                    ),
                    severity=InvariantSeverity.WARNING,
                    layer=InvariantLayer.SCHEMA,
                    edge=edge,
                    fix_hint="Target node missing — may be in a file not included in the graph",
                ))
                continue

            if constraint is None:
                continue  # no constraint registered for this edge type

            # Source type check
            if src_node.node_type not in constraint.source_types:
                violations.append(InvariantViolation(
                    invariant_name="schema_conformance",
                    message=(
                        f"Edge type {edge.edge_type.value}: source {edge.source} "
                        f"has type {src_node.node_type.value}, expected one of "
                        f"{_fmt_types(constraint.source_types)}"
                    ),
                    layer=InvariantLayer.SCHEMA,
                    edge=edge,
                    node_id=edge.source,
                    fix_hint="Change the edge type or fix the source node type",
                ))

            # Target type check
            if tgt_node.node_type not in constraint.target_types:
                violations.append(InvariantViolation(
                    invariant_name="schema_conformance",
                    message=(
                        f"Edge type {edge.edge_type.value}: target {edge.target} "
                        f"has type {tgt_node.node_type.value}, expected one of "
                        f"{_fmt_types(constraint.target_types)}"
                    ),
                    layer=InvariantLayer.SCHEMA,
                    edge=edge,
                    node_id=edge.target,
                    fix_hint="Change the edge type or fix the target node type",
                ))

    def _check_multiplicity(
        self,
        graph: TypedGraph,
        violations: list[InvariantViolation],
    ) -> None:
        # Build counts per (node_id, edge_type) for incoming and outgoing
        incoming: dict[tuple[str, EdgeType], int] = collections.Counter()
        outgoing: dict[tuple[str, EdgeType], int] = collections.Counter()
        for edge in graph.edges:
            incoming[(edge.target, edge.edge_type)] += 1
            outgoing[(edge.source, edge.edge_type)] += 1

        for edge_type, constraint in self.CONSTRAINTS.items():
            # target_max: max incoming edges of this type per target node
            if constraint.target_max is not None:
                seen: set[str] = set()
                for (nid, etype), count in incoming.items():
                    if etype == edge_type and count > constraint.target_max and nid not in seen:
                        seen.add(nid)
                        node = graph.get_node(nid)
                        label = node.attrs.get("name", nid) if node else nid
                        violations.append(InvariantViolation(
                            invariant_name="schema_conformance",
                            message=(
                                f"Multiplicity violation: node '{label}' has "
                                f"{count} incoming {edge_type.value} edges "
                                f"(max {constraint.target_max})"
                            ),
                            layer=InvariantLayer.SCHEMA,
                            node_id=nid,
                            fix_hint=(
                                f"Remove extra {edge_type.value} edges to this node"
                            ),
                        ))

            # source_max: max outgoing edges of this type per source node
            if constraint.source_max is not None:
                seen_src: set[str] = set()
                for (nid, etype), count in outgoing.items():
                    if etype == edge_type and count > constraint.source_max and nid not in seen_src:
                        seen_src.add(nid)
                        node = graph.get_node(nid)
                        label = node.attrs.get("name", nid) if node else nid
                        violations.append(InvariantViolation(
                            invariant_name="schema_conformance",
                            message=(
                                f"Multiplicity violation: node '{label}' has "
                                f"{count} outgoing {edge_type.value} edges "
                                f"(max {constraint.source_max})"
                            ),
                            layer=InvariantLayer.SCHEMA,
                            node_id=nid,
                            fix_hint=(
                                f"Remove extra {edge_type.value} edges from this node"
                            ),
                        ))

    def _check_required_attrs(
        self,
        graph: TypedGraph,
        violations: list[InvariantViolation],
    ) -> None:
        for node_id, node in graph.nodes.items():
            required = self.REQUIRED_ATTRS.get(node.node_type, [])
            for attr in required:
                if attr not in node.attrs:
                    violations.append(InvariantViolation(
                        invariant_name="schema_conformance",
                        message=(
                            f"Node {node_id} ({node.node_type.value}) "
                            f"missing required attribute: '{attr}'"
                        ),
                        layer=InvariantLayer.SCHEMA,
                        node_id=node_id,
                        fix_hint=f"Add the '{attr}' attribute to this node",
                    ))


def _fmt_types(types: frozenset[NodeType]) -> str:
    return "{" + ", ".join(sorted(t.value for t in types)) + "}"


# Default schema instance
_DEFAULT_SCHEMA = GraphSchema()


def _check_schema_conformance(graph: TypedGraph) -> list[InvariantViolation]:
    """Validate graph against the default schema."""
    return _DEFAULT_SCHEMA.validate(graph)


# =============================================================================
# Layer 1 — Structural Integrity
# =============================================================================

_CONTAINMENT_EDGE_TYPES = frozenset({
    EdgeType.CONTAINS,
    EdgeType.CONTAINS_METHOD,
    EdgeType.CONTAINS_FIELD,
    EdgeType.HAS_PARAMETER,
    EdgeType.HAS_ARGUMENT,
})


def _check_containment_acyclicity(graph: TypedGraph) -> list[InvariantViolation]:
    """Containment edges must form a forest (DAG)."""
    violations: list[InvariantViolation] = []

    # Build adjacency for containment edges (parent -> children)
    children: dict[str, list[str]] = collections.defaultdict(list)
    for edge in graph.edges:
        if edge.edge_type in _CONTAINMENT_EDGE_TYPES:
            children[edge.source].append(edge.target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = collections.defaultdict(int)

    def dfs(node_id: str) -> None:
        color[node_id] = GRAY
        for child_id in children.get(node_id, []):
            if color[child_id] == GRAY:
                violations.append(InvariantViolation(
                    invariant_name="containment_acyclicity",
                    message=(
                        f"Cycle in containment hierarchy involving "
                        f"'{node_id}' -> '{child_id}'"
                    ),
                    layer=InvariantLayer.STRUCTURE,
                    node_id=node_id,
                    related_nodes=[child_id],
                    fix_hint="Break the containment cycle",
                ))
            elif color[child_id] == WHITE:
                dfs(child_id)
        color[node_id] = BLACK

    for node_id in graph.nodes:
        if color[node_id] == WHITE:
            dfs(node_id)

    return violations


def _check_no_orphan_nodes(graph: TypedGraph) -> list[InvariantViolation]:
    """Non-MODULE nodes should be reachable from some root."""
    violations: list[InvariantViolation] = []
    if not graph.nodes:
        return violations

    # Build set of all nodes that are targets of containment edges
    # or sources of DEFINED_IN edges (i.e. connected to the hierarchy)
    connected: set[str] = set()
    for edge in graph.edges:
        if edge.edge_type in _CONTAINMENT_EDGE_TYPES:
            connected.add(edge.target)
            connected.add(edge.source)
        elif edge.edge_type == EdgeType.DEFINED_IN:
            connected.add(edge.source)
            connected.add(edge.target)
        elif edge.edge_type == EdgeType.CALLER_OF:
            connected.add(edge.source)
            connected.add(edge.target)

    for node_id, node in graph.nodes.items():
        if node.node_type == NodeType.MODULE:
            continue
        if node_id not in connected:
            violations.append(InvariantViolation(
                invariant_name="no_orphan_nodes",
                message=(
                    f"Orphan {node.node_type.value} node: "
                    f"'{node.attrs.get('name', node_id)}'"
                ),
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.STRUCTURE,
                node_id=node_id,
                fix_hint="Connect this node to its parent via a containment edge",
            ))

    return violations


# =============================================================================
# Layer 2 — Scope Uniqueness (Parametric)
# =============================================================================


@dataclass(frozen=True)
class ScopeRule:
    """Declarative rule for name uniqueness within a scope."""

    container_type: NodeType
    child_type: NodeType
    edge_type: EdgeType
    name_attr: str = "name"
    allow_overload: bool = False
    scope_label: str = ""


SCOPE_RULES: list[ScopeRule] = [
    ScopeRule(
        NodeType.CLASS, NodeType.FUNCTION, EdgeType.CONTAINS_METHOD,
        allow_overload=True, scope_label="class",
    ),
    ScopeRule(
        NodeType.CLASS, NodeType.FIELD, EdgeType.CONTAINS_FIELD,
        scope_label="class",
    ),
    ScopeRule(
        NodeType.FUNCTION, NodeType.PARAMETER, EdgeType.HAS_PARAMETER,
        scope_label="function",
    ),
    ScopeRule(
        NodeType.CALL, NodeType.ARGUMENT, EdgeType.HAS_ARGUMENT,
        name_attr="position", scope_label="call site",
    ),
]


def _check_scope_uniqueness(graph: TypedGraph) -> list[InvariantViolation]:
    """Parametric uniqueness check across all scope rules."""
    violations: list[InvariantViolation] = []

    for rule in SCOPE_RULES:
        for container in graph.get_nodes_by_type(rule.container_type):
            edges = [
                e for e in graph.get_edges_from(container.id)
                if e.edge_type == rule.edge_type
            ]
            seen: dict[str, str] = {}  # attr_value -> first child id
            for edge in edges:
                child = graph.get_node(edge.target)
                if child is None:
                    continue
                key = str(child.attrs.get(rule.name_attr, ""))
                if key in seen:
                    # Check @overload exemption
                    if rule.allow_overload:
                        existing = graph.get_node(seen[key])
                        if (
                            existing
                            and existing.attrs.get("is_overload", False)
                            and child.attrs.get("is_overload", False)
                        ):
                            continue

                    container_name = container.attrs.get("name", container.id)
                    violations.append(InvariantViolation(
                        invariant_name="scope_name_uniqueness",
                        message=(
                            f"Duplicate {child.node_type.value} "
                            f"'{key}' in {rule.scope_label} "
                            f"'{container_name}'"
                        ),
                        layer=InvariantLayer.SCOPE,
                        node_id=child.id,
                        related_nodes=[seen[key]],
                        fix_hint=f"Rename one of the duplicate {child.node_type.value}s",
                    ))
                else:
                    seen[key] = child.id

    return violations


def _check_global_scope_uniqueness(graph: TypedGraph) -> list[InvariantViolation]:
    """Module names globally unique; class/function names unique per module."""
    violations: list[InvariantViolation] = []

    # Module names — globally unique
    module_names: dict[str, str] = {}
    for mod in graph.get_nodes_by_type(NodeType.MODULE):
        name = mod.attrs.get("name", "")
        if name in module_names:
            violations.append(InvariantViolation(
                invariant_name="global_scope_uniqueness",
                message=f"Duplicate module name: '{name}'",
                layer=InvariantLayer.SCOPE,
                node_id=mod.id,
                related_nodes=[module_names[name]],
                fix_hint="Rename one of the duplicate modules",
            ))
        else:
            module_names[name] = mod.id

    # Global functions — unique per module (or global bucket)
    module_funcs: dict[str, dict[str, str]] = {}
    for func in graph.get_nodes_by_type(NodeType.FUNCTION):
        if func.attrs.get("is_method", False):
            continue
        name = func.attrs.get("name", "")
        defined_in = [
            e.target for e in graph.get_edges_from(func.id)
            if e.edge_type == EdgeType.DEFINED_IN
        ]
        mod_key = defined_in[0] if defined_in else "__global__"
        bucket = module_funcs.setdefault(mod_key, {})
        if name in bucket:
            violations.append(InvariantViolation(
                invariant_name="global_scope_uniqueness",
                message=f"Duplicate global function name '{name}' in scope {mod_key}",
                layer=InvariantLayer.SCOPE,
                node_id=func.id,
                related_nodes=[bucket[name]],
                fix_hint="Rename one of the duplicate functions",
            ))
        else:
            bucket[name] = func.id

    # Classes — unique per module (or global bucket)
    module_classes: dict[str, dict[str, str]] = {}
    for cls in graph.get_nodes_by_type(NodeType.CLASS):
        name = cls.attrs.get("name", "")
        defined_in = [
            e.target for e in graph.get_edges_from(cls.id)
            if e.edge_type == EdgeType.DEFINED_IN
        ]
        mod_key = defined_in[0] if defined_in else "__global__"
        bucket = module_classes.setdefault(mod_key, {})
        if name in bucket:
            violations.append(InvariantViolation(
                invariant_name="global_scope_uniqueness",
                message=f"Duplicate class name '{name}' in scope {mod_key}",
                layer=InvariantLayer.SCOPE,
                node_id=cls.id,
                related_nodes=[bucket[name]],
                fix_hint="Rename one of the duplicate classes",
            ))
        else:
            bucket[name] = cls.id

    return violations


# =============================================================================
# Layer 3 — Reference Integrity (Parametric)
# =============================================================================

REFERENCE_EDGE_TYPES: frozenset[EdgeType] = frozenset({
    EdgeType.CALLS,
    EdgeType.REFERENCES,
    EdgeType.IMPORTS,
})

# (edge_type, source_attr, expected_target_type, target_attr)
REFERENCE_CONSISTENCY_RULES: list[tuple[EdgeType, str, NodeType, str]] = [
    (EdgeType.CALLS, "callee", NodeType.FUNCTION, "name"),
]


def _check_reference_integrity(graph: TypedGraph) -> list[InvariantViolation]:
    """All reference edges must point to existing target nodes."""
    violations: list[InvariantViolation] = []
    for edge in graph.edges:
        if edge.edge_type not in REFERENCE_EDGE_TYPES:
            continue
        target = graph.get_node(edge.target)
        if target is None:
            violations.append(InvariantViolation(
                invariant_name="reference_integrity",
                message=(
                    f"Unresolved {edge.edge_type.value} reference: "
                    f"{edge.source} -> {edge.target}"
                ),
                layer=InvariantLayer.REFERENCE,
                edge=edge,
                node_id=edge.source,
                fix_hint="Add the missing target node or remove the reference edge",
            ))
    return violations


def _check_reference_consistency(graph: TypedGraph) -> list[InvariantViolation]:
    """Reference attributes should match their targets (stale reference detection)."""
    violations: list[InvariantViolation] = []
    for edge in graph.edges:
        for rule_etype, src_attr, tgt_type, tgt_attr in REFERENCE_CONSISTENCY_RULES:
            if edge.edge_type != rule_etype:
                continue
            src_node = graph.get_node(edge.source)
            tgt_node = graph.get_node(edge.target)
            if src_node is None or tgt_node is None:
                continue  # caught by reference_integrity
            if tgt_node.node_type != tgt_type:
                continue
            src_val = src_node.attrs.get(src_attr)
            tgt_val = tgt_node.attrs.get(tgt_attr)
            if src_val and tgt_val and src_val != tgt_val:
                violations.append(InvariantViolation(
                    invariant_name="reference_consistency",
                    message=(
                        f"Stale reference: {edge.source} has {src_attr}='{src_val}' "
                        f"but target {edge.target} has {tgt_attr}='{tgt_val}'"
                    ),
                    severity=InvariantSeverity.WARNING,
                    layer=InvariantLayer.REFERENCE,
                    edge=edge,
                    node_id=edge.source,
                    related_nodes=[edge.target],
                    fix_hint=f"Update the '{src_attr}' attribute to match the target",
                ))
    return violations


def _check_import_target_resolution(graph: TypedGraph) -> list[InvariantViolation]:
    """From-imports should resolve to definitions in the source graph.

    For each ``from X import Y`` node whose source module is present in the
    graph, verify that a FUNCTION or CLASS named ``Y`` is actually defined in
    that module.  If the module is **not** in the graph we skip (external dep).

    This catches stale imports left behind after a ``rename_func`` or
    ``rename_class`` that was not paired with an ``update_import`` step.
    """
    violations: list[InvariantViolation] = []

    # 1. Build MODULE file-suffix → module_id mapping
    module_by_suffix: dict[str, str] = {}  # "a/b/utils.py" -> "module:utils"
    for mod_node in graph.get_nodes_by_type(NodeType.MODULE):
        fpath = mod_node.attrs.get("file", "")
        if fpath:
            module_by_suffix[fpath] = mod_node.id

    # 2. Build module_id → {defined names}
    defs_by_module: dict[str, set[str]] = {mid: set() for mid in module_by_suffix.values()}
    for node in (*graph.get_nodes_by_type(NodeType.FUNCTION),
                 *graph.get_nodes_by_type(NodeType.CLASS)):
        for edge in graph.get_edges_from(node.id):
            if edge.edge_type == EdgeType.DEFINED_IN:
                mod_id = edge.target
                name = node.attrs.get("name", "")
                if mod_id in defs_by_module and name:
                    defs_by_module[mod_id].add(name)

    # 3. For each from-import, resolve target module and check name
    for imp_node in graph.get_nodes_by_type(NodeType.IMPORT):
        if not imp_node.attrs.get("is_from_import", False):
            continue
        imported_name = imp_node.attrs.get("name")
        if not imported_name:
            continue
        imp_module = imp_node.attrs.get("module", "")
        if not imp_module:
            continue

        # Convert dotted module to path suffix: "a.b.utils" → "a/b/utils.py"
        mod_path = imp_module.replace(".", "/") + ".py"
        # Also try package __init__: "a.b.utils" → "a/b/utils/__init__.py"
        pkg_path = imp_module.replace(".", "/") + "/__init__.py"

        matched_mod_id: str | None = None
        for suffix, mid in module_by_suffix.items():
            if suffix == mod_path or suffix.endswith("/" + mod_path):
                matched_mod_id = mid
                break
            if suffix == pkg_path or suffix.endswith("/" + pkg_path):
                matched_mod_id = mid
                break

        if matched_mod_id is None:
            continue  # Source module not in graph — external, skip

        defined_names = defs_by_module.get(matched_mod_id, set())
        if imported_name not in defined_names:
            available = sorted(defined_names) if defined_names else ["(none)"]
            violations.append(InvariantViolation(
                invariant_name="import_target_resolution",
                message=(
                    f"Import '{imported_name}' from '{imp_module}' does not "
                    f"match any function/class definition in '{matched_mod_id}'"
                ),
                severity=InvariantSeverity.ERROR,
                layer=InvariantLayer.REFERENCE,
                node_id=imp_node.id,
                fix_hint=(
                    f"Add an update_import operator to rename "
                    f"'{imported_name}', or the import may refer to a "
                    f"variable/re-export not captured in the graph. "
                    f"Definitions found: {available}"
                ),
            ))

    return violations


# =============================================================================
# Layer 4 — Type System
# =============================================================================


def _check_inheritance_dag(graph: TypedGraph) -> list[InvariantViolation]:
    """No circular or self-inheritance.  Follows ALL parents via BFS."""
    violations: list[InvariantViolation] = []

    for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
        # Self-inheritance check
        for edge in graph.get_edges_from(cls_node.id):
            if edge.edge_type == EdgeType.INHERITS and edge.target == cls_node.id:
                violations.append(InvariantViolation(
                    invariant_name="inheritance_dag",
                    message=(
                        f"Self-inheritance: "
                        f"'{cls_node.attrs.get('name', cls_node.id)}'"
                    ),
                    layer=InvariantLayer.TYPE_SYSTEM,
                    node_id=cls_node.id,
                    fix_hint="Remove the self-inheritance edge",
                ))

        # BFS cycle detection following ALL parents
        # Only a true cycle exists if we can reach cls_node.id again.
        # Convergence (diamond inheritance) is valid and must not trigger.
        visited: set[str] = set()
        queue: collections.deque[str] = collections.deque()

        # Seed with direct parents
        for edge in graph.get_edges_from(cls_node.id):
            if edge.edge_type == EdgeType.INHERITS and edge.target != cls_node.id:
                if edge.target in graph.nodes:
                    queue.append(edge.target)

        cycle_found = False
        while queue and not cycle_found:
            current = queue.popleft()
            if current == cls_node.id:
                violations.append(InvariantViolation(
                    invariant_name="inheritance_dag",
                    message=(
                        f"Circular inheritance involving "
                        f"'{cls_node.attrs.get('name', cls_node.id)}'"
                    ),
                    layer=InvariantLayer.TYPE_SYSTEM,
                    node_id=cls_node.id,
                    related_nodes=[current],
                    fix_hint="Break the inheritance cycle",
                ))
                cycle_found = True
                break
            if current in visited:
                continue  # diamond convergence — not a cycle
            visited.add(current)
            for edge in graph.get_edges_from(current):
                if edge.edge_type == EdgeType.INHERITS and edge.target in graph.nodes:
                    queue.append(edge.target)

    return violations


def _check_override_compatibility(graph: TypedGraph) -> list[InvariantViolation]:
    """Methods overriding ancestors should have compatible parameter counts."""
    violations: list[InvariantViolation] = []

    def _get_method_names(cls_id: str) -> dict[str, str]:
        """Return {method_name: func_node_id} for a class."""
        result: dict[str, str] = {}
        for edge in graph.get_edges_from(cls_id):
            if edge.edge_type == EdgeType.CONTAINS_METHOD:
                func = graph.get_node(edge.target)
                if func:
                    name = func.attrs.get("name", "")
                    if name:
                        result[name] = func.id
        return result

    def _param_count(func_id: str) -> int:
        """Count non-self parameters."""
        count = 0
        for edge in graph.get_edges_from(func_id):
            if edge.edge_type == EdgeType.HAS_PARAMETER:
                param = graph.get_node(edge.target)
                if param and param.attrs.get("name") not in ("self", "cls"):
                    count += 1
        return count

    def _ancestors(cls_id: str) -> list[str]:
        """Collect all ancestor class IDs via BFS."""
        result: list[str] = []
        visited: set[str] = {cls_id}
        queue: collections.deque[str] = collections.deque()
        for edge in graph.get_edges_from(cls_id):
            if edge.edge_type == EdgeType.INHERITS and edge.target in graph.nodes:
                queue.append(edge.target)
        while queue:
            cur = queue.popleft()
            if cur in visited:
                continue
            visited.add(cur)
            result.append(cur)
            for edge in graph.get_edges_from(cur):
                if edge.edge_type == EdgeType.INHERITS and edge.target in graph.nodes:
                    queue.append(edge.target)
        return result

    for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
        my_methods = _get_method_names(cls_node.id)
        for ancestor_id in _ancestors(cls_node.id):
            ancestor_methods = _get_method_names(ancestor_id)
            for method_name, my_func_id in my_methods.items():
                if method_name in ancestor_methods:
                    ancestor_func_id = ancestor_methods[method_name]
                    my_count = _param_count(my_func_id)
                    ancestor_count = _param_count(ancestor_func_id)
                    if my_count != ancestor_count:
                        cls_name = cls_node.attrs.get("name", cls_node.id)
                        anc_node = graph.get_node(ancestor_id)
                        anc_name = anc_node.attrs.get("name", ancestor_id) if anc_node else ancestor_id
                        violations.append(InvariantViolation(
                            invariant_name="override_compatibility",
                            message=(
                                f"Method '{method_name}' in '{cls_name}' has "
                                f"{my_count} params but ancestor '{anc_name}' "
                                f"has {ancestor_count}"
                            ),
                            severity=InvariantSeverity.WARNING,
                            layer=InvariantLayer.TYPE_SYSTEM,
                            node_id=my_func_id,
                            related_nodes=[ancestor_func_id],
                            fix_hint="Align parameter counts between override and base method",
                        ))

    return violations


# =============================================================================
# Layer 5 — Semantic Consistency
# =============================================================================


def _check_call_argument_match(graph: TypedGraph) -> list[InvariantViolation]:
    """Call sites should have compatible argument counts with targets.

    Improvements over old ``call_argument_count_match``:
    - Skips variadic functions (``*args``/``**kwargs``)
    - Excludes ``self``/``cls`` from parameter count
    - Uses range check (required <= args <= total) instead of exact match
    - Severity: WARNING (static analysis is imprecise)
    """
    violations: list[InvariantViolation] = []

    for call_node in graph.get_nodes_by_type(NodeType.CALL):
        call_edges = [
            e for e in graph.get_edges_from(call_node.id)
            if e.edge_type == EdgeType.CALLS
        ]
        if not call_edges:
            continue

        target_func_id = call_edges[0].target
        target_func = graph.get_node(target_func_id)
        if not target_func or target_func.node_type != NodeType.FUNCTION:
            continue

        # Count arguments at call site
        arg_count = len([
            e for e in graph.get_edges_from(call_node.id)
            if e.edge_type == EdgeType.HAS_ARGUMENT
        ])

        # Gather parameter info
        param_edges = [
            e for e in graph.get_edges_from(target_func_id)
            if e.edge_type == EdgeType.HAS_PARAMETER
        ]
        params = [graph.get_node(e.target) for e in param_edges]
        params = [p for p in params if p is not None]

        # Skip variadic functions
        has_variadic = any(
            p.attrs.get("name", "").startswith("*")
            or p.attrs.get("is_starred", False)
            or p.attrs.get("is_double_starred", False)
            for p in params
        )
        if has_variadic:
            continue

        # Count required vs total params (excluding self/cls)
        required_count = 0
        total_count = 0
        for p in params:
            name = p.attrs.get("name", "")
            if name in ("self", "cls"):
                continue
            total_count += 1
            if not p.attrs.get("has_default", False):
                required_count += 1

        if arg_count < required_count or arg_count > total_count:
            func_name = target_func.attrs.get("name", target_func_id)
            if required_count == total_count:
                expected = str(required_count)
            else:
                expected = f"{required_count}-{total_count}"
            violations.append(InvariantViolation(
                invariant_name="call_argument_match",
                message=(
                    f"Call to '{func_name}' has {arg_count} arguments, "
                    f"expected {expected} parameters"
                ),
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.SEMANTIC,
                node_id=call_node.id,
                related_nodes=[target_func_id],
                fix_hint="Add or remove arguments to match the function signature",
            ))

    return violations


def _check_parameter_ordering(graph: TypedGraph) -> list[InvariantViolation]:
    """Parameter positions in a function should be 0, 1, 2, ..., n-1."""
    violations: list[InvariantViolation] = []
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
                    invariant_name="parameter_ordering",
                    message=(
                        f"Non-consecutive parameter positions in "
                        f"'{func_node.attrs.get('name', func_node.id)}': "
                        f"got {positions}, expected {expected}"
                    ),
                    severity=InvariantSeverity.WARNING,
                    layer=InvariantLayer.SEMANTIC,
                    node_id=func_node.id,
                    fix_hint="Renumber parameter positions to be consecutive",
                ))
    return violations


# =============================================================================
# Layer 6 — Quality Hints
# =============================================================================


def _check_unused_imports(graph: TypedGraph) -> list[InvariantViolation]:
    """Identify IMPORT nodes that are not referenced by any edge."""
    violations: list[InvariantViolation] = []
    referenced_ids = {edge.target for edge in graph.edges}
    for imp_node in graph.get_nodes_by_type(NodeType.IMPORT):
        if imp_node.id not in referenced_ids:
            violations.append(InvariantViolation(
                invariant_name="unused_imports",
                message=(
                    f"Unused import: {imp_node.attrs.get('module', imp_node.id)}"
                ),
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.QUALITY,
                node_id=imp_node.id,
                fix_hint="Remove the unused import",
            ))
    return violations


def _check_non_empty_container_guard(graph: TypedGraph) -> list[InvariantViolation]:
    """Flag empty classes/modules — informational hint for agents."""
    violations: list[InvariantViolation] = []

    for cls_node in graph.get_nodes_by_type(NodeType.CLASS):
        children = [
            e for e in graph.get_edges_from(cls_node.id)
            if e.edge_type in (EdgeType.CONTAINS_METHOD, EdgeType.CONTAINS_FIELD)
        ]
        if not children:
            violations.append(InvariantViolation(
                invariant_name="non_empty_container_guard",
                message=(
                    f"Class '{cls_node.attrs.get('name', cls_node.id)}' "
                    f"has no methods or fields"
                ),
                severity=InvariantSeverity.INFO,
                layer=InvariantLayer.QUALITY,
                node_id=cls_node.id,
            ))

    for mod_node in graph.get_nodes_by_type(NodeType.MODULE):
        # Count definitions in this module
        defs = [
            e for e in graph.get_edges_to(mod_node.id)
            if e.edge_type == EdgeType.DEFINED_IN
        ]
        # Also count containment from module if such edges exist
        containment = [
            e for e in graph.get_edges_from(mod_node.id)
            if e.edge_type in (EdgeType.CONTAINS_METHOD, EdgeType.CONTAINS_FIELD)
        ]
        if not defs and not containment:
            violations.append(InvariantViolation(
                invariant_name="non_empty_container_guard",
                message=(
                    f"Module '{mod_node.attrs.get('name', mod_node.id)}' "
                    f"has no definitions"
                ),
                severity=InvariantSeverity.INFO,
                layer=InvariantLayer.QUALITY,
                node_id=mod_node.id,
            ))

    return violations


# =============================================================================
# InvariantRegistry
# =============================================================================


class InvariantRegistry:
    """Registry of graph invariants organized by layer.

    Supports enable/disable by name or layer, filtering by layer/severity,
    and layered validation (stop checking higher layers when a lower layer
    has ERROR violations).
    """

    def __init__(
        self,
        *,
        schema: GraphSchema | None = None,
        register_defaults: bool = True,
    ) -> None:
        self._schema = schema or _DEFAULT_SCHEMA
        self._invariants: dict[str, Invariant] = {}
        if register_defaults:
            self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            # Layer 0: Schema
            Invariant(
                name="schema_conformance",
                description="Type graph conformance (edge types, multiplicity, required attrs)",
                check=_check_schema_conformance,
                layer=InvariantLayer.SCHEMA,
            ),
            # Layer 1: Structure
            Invariant(
                name="containment_acyclicity",
                description="Containment edges form a forest (no cycles)",
                check=_check_containment_acyclicity,
                layer=InvariantLayer.STRUCTURE,
            ),
            Invariant(
                name="no_orphan_nodes",
                description="Non-module nodes are connected to the hierarchy",
                check=_check_no_orphan_nodes,
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.STRUCTURE,
                enabled=False,
            ),
            # Layer 2: Scope
            Invariant(
                name="scope_name_uniqueness",
                description="No duplicate names within a scope (parametric)",
                check=_check_scope_uniqueness,
                layer=InvariantLayer.SCOPE,
            ),
            Invariant(
                name="global_scope_uniqueness",
                description="Module/class/function names unique per scope",
                check=_check_global_scope_uniqueness,
                layer=InvariantLayer.SCOPE,
            ),
            # Layer 3: Reference
            Invariant(
                name="reference_integrity",
                description="CALLS/REFERENCES/IMPORTS edges point to existing nodes",
                check=_check_reference_integrity,
                layer=InvariantLayer.REFERENCE,
            ),
            Invariant(
                name="reference_consistency",
                description="Reference attributes match their targets",
                check=_check_reference_consistency,
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.REFERENCE,
            ),
            Invariant(
                name="import_target_resolution",
                description="From-imports resolve to definitions in the source graph",
                check=_check_import_target_resolution,
                layer=InvariantLayer.REFERENCE,
            ),
            # Layer 4: Type System
            Invariant(
                name="inheritance_dag",
                description="No circular or self-inheritance",
                check=_check_inheritance_dag,
                layer=InvariantLayer.TYPE_SYSTEM,
            ),
            Invariant(
                name="override_compatibility",
                description="Method overrides have compatible signatures",
                check=_check_override_compatibility,
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.TYPE_SYSTEM,
            ),
            # Layer 5: Semantic
            Invariant(
                name="call_argument_match",
                description="Call site argument counts match function signatures",
                check=_check_call_argument_match,
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.SEMANTIC,
            ),
            Invariant(
                name="parameter_ordering",
                description="Parameter positions are consecutive 0..n-1",
                check=_check_parameter_ordering,
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.SEMANTIC,
            ),
            # Layer 6: Quality
            Invariant(
                name="unused_imports",
                description="IMPORT nodes not referenced by any edge",
                check=_check_unused_imports,
                severity=InvariantSeverity.WARNING,
                layer=InvariantLayer.QUALITY,
            ),
            Invariant(
                name="non_empty_container_guard",
                description="Flag empty classes and modules",
                check=_check_non_empty_container_guard,
                severity=InvariantSeverity.INFO,
                layer=InvariantLayer.QUALITY,
                enabled=False,
            ),
        ]
        for inv in defaults:
            self._invariants[inv.name] = inv

    # ----- Enable / Disable --------------------------------------------------

    def enable(self, name: str) -> None:
        """Enable an invariant by name."""
        if name in self._invariants:
            self._invariants[name].enabled = True

    def disable(self, name: str) -> None:
        """Disable an invariant by name."""
        if name in self._invariants:
            self._invariants[name].enabled = False

    def enable_layer(self, layer: InvariantLayer) -> None:
        """Enable all invariants in *layer*."""
        for inv in self._invariants.values():
            if inv.layer == layer:
                inv.enabled = True

    def disable_layer(self, layer: InvariantLayer) -> None:
        """Disable all invariants in *layer*."""
        for inv in self._invariants.values():
            if inv.layer == layer:
                inv.enabled = False

    # ----- Query -------------------------------------------------------------

    def get_invariant(self, name: str) -> Invariant | None:
        return self._invariants.get(name)

    def get_by_layer(self, layer: InvariantLayer) -> list[Invariant]:
        return [inv for inv in self._invariants.values() if inv.layer == layer]

    def get_enabled(self) -> list[Invariant]:
        return [inv for inv in self._invariants.values() if inv.enabled]

    @property
    def graph_invariants(self) -> list[Invariant]:
        """Backward-compatible property returning all registered invariants."""
        return list(self._invariants.values())

    # ----- Mutation ----------------------------------------------------------

    def add_invariant(self, invariant: Invariant) -> None:
        """Add or replace a custom invariant."""
        self._invariants[invariant.name] = invariant

    def remove_invariant(self, name: str) -> bool:
        """Remove an invariant by name.  Returns True if it existed."""
        return self._invariants.pop(name, None) is not None

    # ----- Verification ------------------------------------------------------

    def verify_graph(
        self,
        graph: TypedGraph,
        *,
        layers: set[InvariantLayer] | None = None,
        min_severity: InvariantSeverity = InvariantSeverity.INFO,
        stop_on_layer_error: bool = False,
    ) -> list[InvariantViolation]:
        """Run enabled invariants in layer order.

        Args:
            graph: The graph to verify.
            layers: If given, only check invariants in these layers.
            min_severity: Only return violations at or above this severity.
            stop_on_layer_error: If True, stop checking higher layers when
                a lower layer has ERROR violations.

        Returns:
            List of violations sorted by layer then severity.
        """
        severity_rank = {
            InvariantSeverity.INFO: 0,
            InvariantSeverity.WARNING: 1,
            InvariantSeverity.ERROR: 2,
        }
        min_rank = severity_rank[min_severity]

        # Group invariants by layer
        by_layer: dict[InvariantLayer, list[Invariant]] = collections.defaultdict(list)
        for inv in self._invariants.values():
            if not inv.enabled:
                continue
            if layers and inv.layer not in layers:
                continue
            by_layer[inv.layer].append(inv)

        all_violations: list[InvariantViolation] = []

        for layer in sorted(by_layer.keys(), key=lambda l: l.value):
            layer_violations: list[InvariantViolation] = []
            for inv in by_layer[layer]:
                layer_violations.extend(inv.verify(graph))

            # Filter by severity
            for v in layer_violations:
                if severity_rank.get(v.severity, 0) >= min_rank:
                    all_violations.append(v)

            # Stop early if layer has errors
            if stop_on_layer_error:
                has_errors = any(
                    v.severity == InvariantSeverity.ERROR for v in layer_violations
                )
                if has_errors:
                    break

        return all_violations

    def verify_preconditions(
        self,
        preconditions: list[Invariant],
        graph: TypedGraph,
    ) -> list[InvariantViolation]:
        """Verify rule preconditions on *graph*."""
        violations: list[InvariantViolation] = []
        for pre in preconditions:
            violations.extend(pre.verify(graph))
        return violations

    def verify_postconditions(
        self,
        postconditions: list[Invariant],
        graph: TypedGraph,
    ) -> list[InvariantViolation]:
        """Verify rule postconditions on *graph*."""
        violations: list[InvariantViolation] = []
        for post in postconditions:
            violations.extend(post.verify(graph))
        return violations
