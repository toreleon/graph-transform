"""
Derived Operators as Compositions

All higher-level code transformations are compositions of the three primitives:
INSERT, DELETE, UPDATE.

This module defines standard compositions for common operations:
- RENAME: Update name + update references
- MOVE: Delete edge + insert edge
- EXTRACT: Insert new entity + update original
- INLINE: Update call sites + delete entity
- etc.

Compositions can be:
1. Declared statically (templates)
2. Generated dynamically based on graph analysis
3. Combined to form complex transformations
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Iterator

from .base import (
    DeleteEdge,
    DeleteNode,
    InsertEdge,
    InsertNode,
    Primitive,
    PrimitiveKind,
    PrimitiveResult,
    Update,
)
from .node_kinds import EdgeKind, NodeKind
from .position import Position

if TYPE_CHECKING:
    from ..typed_graph import TypedGraph


class CompositionStatus(Enum):
    """Status of composition execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class CompositionResult:
    """Result of executing a composition."""

    success: bool
    composition_name: str
    primitive_results: list[PrimitiveResult] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def affected_ids(self) -> list[str]:
        """All IDs affected by this composition."""
        ids = []
        for pr in self.primitive_results:
            ids.extend(pr.affected_ids)
        return ids

    @classmethod
    def ok(
        cls,
        name: str,
        results: list[PrimitiveResult],
        **metadata: Any,
    ) -> CompositionResult:
        return cls(
            success=True,
            composition_name=name,
            primitive_results=results,
            metadata=metadata,
        )

    @classmethod
    def fail(
        cls,
        name: str,
        error: str,
        partial_results: list[PrimitiveResult] | None = None,
    ) -> CompositionResult:
        return cls(
            success=False,
            composition_name=name,
            primitive_results=partial_results or [],
            error=error,
        )


class Composition(ABC):
    """Base class for derived operators.

    A composition is a sequence of primitives that together
    implement a higher-level transformation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this composition."""
        ...

    @abstractmethod
    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        """Generate the sequence of primitives for this composition.

        This method analyzes the graph and yields the primitives
        needed to implement the transformation.

        Args:
            graph: The graph to transform

        Yields:
            Primitive operations in order of execution
        """
        ...

    def edit_instructions(self, graph: TypedGraph) -> list[dict[str, Any]]:
        """Generate file-level edit instructions for this composition.

        This bridges graph primitives to actionable file edits.
        Override in subclasses to provide specific edit generation.

        Args:
            graph: The graph to analyze

        Returns:
            List of edit instruction dicts with keys:
            - type: "rename_file", "replace_text", "delete_lines", etc.
            - file: Target file path
            - Additional type-specific keys
        """
        return []  # Default: no edits (subclasses override)

    def execute(self, graph: TypedGraph) -> CompositionResult:
        """Execute this composition on the graph.

        Executes primitives in order, rolling back on failure.
        """
        results: list[PrimitiveResult] = []
        executed_primitives: list[tuple[Primitive, PrimitiveResult]] = []

        try:
            for primitive in self.primitives(graph):
                result = primitive.execute(graph)
                results.append(result)
                executed_primitives.append((primitive, result))

                if not result.success:
                    # Rollback previous operations
                    self._rollback(graph, executed_primitives[:-1])
                    return CompositionResult.fail(
                        self.name,
                        f"Primitive failed: {result.error}",
                        partial_results=results,
                    )

            return CompositionResult.ok(self.name, results)

        except Exception as e:
            # Rollback on exception
            self._rollback(graph, executed_primitives)
            return CompositionResult.fail(
                self.name,
                f"Exception during execution: {e}",
                partial_results=results,
            )

    def _rollback(
        self,
        graph: TypedGraph,
        executed: list[tuple[Primitive, PrimitiveResult]],
    ) -> None:
        """Rollback executed primitives in reverse order.

        This is a best-effort rollback - some operations may not
        be perfectly reversible.
        """
        for primitive, result in reversed(executed):
            try:
                self._reverse_primitive(graph, primitive, result)
            except Exception:
                # Log but continue rollback
                pass

    def _reverse_primitive(
        self,
        graph: TypedGraph,
        primitive: Primitive,
        result: PrimitiveResult,
    ) -> None:
        """Reverse a single primitive operation."""
        if isinstance(primitive, InsertNode):
            # Reverse INSERT node -> DELETE node
            DeleteNode(primitive.node_id, cascade=True).execute(graph)

        elif isinstance(primitive, InsertEdge):
            # Reverse INSERT edge -> DELETE edge
            DeleteEdge(primitive.source, primitive.target).execute(graph)

        elif isinstance(primitive, DeleteNode):
            # Cannot easily reverse DELETE node without stored data
            pass

        elif isinstance(primitive, DeleteEdge):
            # Cannot easily reverse DELETE edge without stored data
            pass

        elif isinstance(primitive, Update):
            # Reverse UPDATE -> UPDATE with old values
            old_values = result.metadata.get("old_values", {})
            if old_values:
                Update(primitive.target, properties=old_values).execute(graph)


# =============================================================================
# Standard Compositions
# =============================================================================


@dataclass
class Rename(Composition):
    """Rename an entity and update all references.

    RENAME = UPDATE(name) + UPDATE*(references)

    This is the fundamental "change identity" operation.
    """

    target: str  # Node ID to rename
    new_name: str
    update_references: bool = True  # Also update references

    @property
    def name(self) -> str:
        return "RENAME"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        # 1. Update the entity's name
        yield Update(target=self.target, prop="name", value=self.new_name)

        # 2. Update references if requested
        if self.update_references:
            for ref in self._find_references(graph):
                yield Update(
                    target=ref,
                    prop="callee" if "call:" in ref else "target",
                    value=self.new_name,
                )

    def _find_references(self, graph: TypedGraph) -> list[str]:
        """Find all nodes that reference this entity."""
        refs = []
        node = graph.get_node(self.target)
        if not node:
            return refs

        old_name = node.attrs.get("name")
        if not old_name:
            return refs

        # Find calls to this entity
        for edge in graph.get_edges_to(self.target):
            if edge.source.startswith("call:"):
                refs.append(edge.source)

        # Find other references
        for n in graph.nodes.values():
            if n.id == self.target:
                continue
            # Check for name references in attributes
            for key, value in n.attrs.items():
                if value == old_name and key in ("callee", "target", "receiver"):
                    refs.append(n.id)

        return refs

    def edit_instructions(self, graph: TypedGraph) -> list[dict[str, Any]]:
        """Generate file-level edits for rename operation."""
        edits: list[dict[str, Any]] = []
        node = graph.get_node(self.target)
        if not node:
            return edits

        old_name = node.attrs.get("name", "")
        file_path = node.attrs.get("file", "")

        # Check if this is a module rename
        if self.target.startswith("module:"):
            # Module rename = file rename + import updates
            if file_path:
                # Generate file rename
                old_file = file_path
                # Replace last component of path
                if "/" in old_file:
                    dir_part = old_file.rsplit("/", 1)[0]
                    new_file = f"{dir_part}/{self.new_name}.py"
                else:
                    new_file = f"{self.new_name}.py"

                edits.append({
                    "type": "rename_file",
                    "old_path": old_file,
                    "new_path": new_file,
                })

                # Find all files that import from this module
                old_module = old_name
                new_module = old_module.rsplit(".", 1)[0] + "." + self.new_name if "." in old_module else self.new_name

                # Get the short module name for alias replacement (e.g., "params" -> "param")
                old_short_name = old_module.rsplit(".", 1)[-1]
                new_short_name = self.new_name

                seen_files: set[str] = set()
                for n in graph.nodes.values():
                    if n.node_type.name == "IMPORT":
                        import_module = n.attrs.get("module", "")
                        import_name = n.attrs.get("name", "")

                        # Match: "from fastapi.params import X" (module == old_module)
                        # Match: "from fastapi import params" (module == parent and name == short_name)
                        is_direct_import = import_module == old_module or import_module.startswith(old_module + ".")
                        is_named_import = (
                            import_name == old_short_name and
                            old_module.rsplit(".", 1)[0] == import_module if "." in old_module else import_module == ""
                        )

                        if is_direct_import or is_named_import:
                            import_file = n.attrs.get("file", "")
                            if import_file and import_file != old_file and import_file not in seen_files:
                                seen_files.add(import_file)
                                # Replace module path in import statement
                                edits.append({
                                    "type": "replace_text",
                                    "file": import_file,
                                    "old_text": old_module,
                                    "new_text": new_module,
                                })
                                # Also replace module alias usage (e.g., params.Body -> param.Body)
                                edits.append({
                                    "type": "replace_text",
                                    "file": import_file,
                                    "old_text": f"{old_short_name}.",
                                    "new_text": f"{new_short_name}.",
                                })
        else:
            # Regular symbol rename - replace occurrences in file
            if file_path:
                edits.append({
                    "type": "replace_text",
                    "file": file_path,
                    "pattern": rf"\b{old_name}\b",
                    "replacement": self.new_name,
                })

        return edits


@dataclass
class Move(Composition):
    """Move an entity from one scope to another.

    MOVE = DELETE(containment_edge) + INSERT(new_containment_edge)
           + DELETE(exports_edge)? + UPDATE*(references)

    This changes where an entity "lives" in the code structure.
    When a symbol is moved, any EXPORTS edge from the source scope is removed
    (the symbol is no longer part of the source's public API).
    """

    target: str  # Node ID to move
    from_scope: str  # Source container
    to_scope: str  # Target container
    edge_kind: EdgeKind = EdgeKind.CONTAINS
    update_references: bool = True
    preserve_export: bool = False  # If True, add EXPORTS edge to destination

    @property
    def name(self) -> str:
        return "MOVE"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        from graph_transform.core.typed_graph import EdgeType

        # 1. Remove from old scope (containment)
        yield DeleteEdge(
            source=self.from_scope,
            target=self.target,
            edge_kind=self.edge_kind,
        )

        # 2. Add to new scope (containment)
        yield InsertEdge(
            source=self.to_scope,
            target=self.target,
            edge_kind=self.edge_kind,
        )

        # 3. Handle EXPORTS edge: remove from source if exists
        # This is language-agnostic (Python __all__, JS export, Rust pub, etc.)
        for edge in graph.get_edges_to(self.target):
            if edge.edge_type == EdgeType.EXPORTS and edge.source == self.from_scope:
                yield DeleteEdge(
                    source=self.from_scope,
                    target=self.target,
                    edge_kind=EdgeKind.EXPORTS,
                )
                # Optionally add export to destination
                if self.preserve_export:
                    yield InsertEdge(
                        source=self.to_scope,
                        target=self.target,
                        edge_kind=EdgeKind.EXPORTS,
                    )
                break

        # 4. Update qualified references if needed
        if self.update_references:
            node = graph.get_node(self.target)
            if node:
                old_name = node.attrs.get("name", "")
                # Update any qualified paths
                for ref_id in self._find_qualified_refs(graph, old_name):
                    yield Update(
                        target=ref_id,
                        prop="qualified_path",
                        value=self._compute_new_path(graph, old_name),
                    )

    def _find_qualified_refs(self, graph: TypedGraph, name: str) -> list[str]:
        """Find references using qualified paths."""
        # Simplified - would need more sophisticated analysis
        return []

    def _compute_new_path(self, graph: TypedGraph, name: str) -> str:
        """Compute new qualified path in target scope."""
        to_node = graph.get_node(self.to_scope)
        if to_node:
            scope_name = to_node.attrs.get("name", "")
            return f"{scope_name}.{name}"
        return name


@dataclass
class Extract(Composition):
    """Extract code into a new entity.

    EXTRACT = INSERT(new_entity) + INSERT(containment_edge) + UPDATE(original)

    This is the fundamental "create abstraction" operation.
    """

    new_id: str  # ID for new entity
    new_name: str
    node_kind: NodeKind
    scope: str  # Where to put new entity
    original: str  # Entity being extracted from
    replacement_value: Any  # What replaces extracted code in original

    attrs: dict[str, Any] = field(default_factory=dict)
    position: Position | None = None

    @property
    def name(self) -> str:
        return "EXTRACT"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        # 1. Create new entity
        full_attrs = {"name": self.new_name, **self.attrs}
        yield InsertNode(
            node_id=self.new_id,
            node_kind=self.node_kind,
            attrs=full_attrs,
            position=self.position,
        )

        # 2. Add to scope
        yield InsertEdge(
            source=self.scope,
            target=self.new_id,
            edge_kind=EdgeKind.CONTAINS,
        )

        # 3. Update original to reference new entity
        yield Update(
            target=self.original,
            prop="body",  # or appropriate property
            value=self.replacement_value,
        )

        # 4. Add call/reference edge if applicable
        if self.node_kind == NodeKind.CALLABLE:
            yield InsertEdge(
                source=self.original,
                target=self.new_id,
                edge_kind=EdgeKind.CALLS,
            )


@dataclass
class Inline(Composition):
    """Inline an entity into its call sites.

    INLINE = UPDATE*(call_sites) + DELETE(entity)

    This is the inverse of EXTRACT.
    """

    target: str  # Entity to inline
    remove_after: bool = True  # Delete entity after inlining

    @property
    def name(self) -> str:
        return "INLINE"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        node = graph.get_node(self.target)
        if not node:
            return

        # Get the body/value to inline
        body = node.attrs.get("body", node.attrs.get("value"))

        # 1. Update all call sites
        for edge in graph.get_edges_to(self.target):
            if edge.edge_type.value == "calls":
                yield Update(
                    target=edge.source,
                    prop="inlined_body",
                    value=body,
                )

        # 2. Remove the entity
        if self.remove_after:
            yield DeleteNode(self.target, cascade=True)


@dataclass
class AddGuard(Composition):
    """Add a guard/check before an operation.

    ADD_GUARD = INSERT(guard_node) + UPDATE(control_flow)

    Used for null checks, bounds checks, validation, etc.
    """

    target: str  # Where to add guard
    guard_type: str  # "null_check", "bounds_check", etc.
    guard_condition: str
    guard_action: str = "early_return"  # or "throw", "default_value"

    @property
    def name(self) -> str:
        return "ADD_GUARD"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        guard_id = f"guard:{self.target}:{self.guard_type}"

        # 1. Insert guard node
        yield InsertNode(
            node_id=guard_id,
            node_kind=NodeKind.BRANCH,
            attrs={
                "guard_type": self.guard_type,
                "condition": self.guard_condition,
                "action": self.guard_action,
            },
            position=Position.at_start_of(self.target),
        )

        # 2. Add control flow edge
        yield InsertEdge(
            source=self.target,
            target=guard_id,
            edge_kind=EdgeKind.CONTAINS,
        )


@dataclass
class ChangeSignature(Composition):
    """Change a callable's signature.

    CHANGE_SIGNATURE = UPDATE(signature) + UPDATE*(call_sites)
    """

    target: str  # Callable to modify
    changes: dict[str, Any]  # Signature changes

    @property
    def name(self) -> str:
        return "CHANGE_SIGNATURE"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        # 1. Update the callable's signature
        yield Update(target=self.target, properties=self.changes)

        # 2. Update call sites
        for edge in graph.get_edges_to(self.target):
            if edge.edge_type.value == "calls":
                call_node = graph.get_node(edge.source)
                if call_node:
                    yield Update(
                        target=edge.source,
                        prop="signature_updated",
                        value=True,
                    )


@dataclass
class Wrap(Composition):
    """Wrap code in a construct (try/catch, with, etc).

    WRAP = INSERT(wrapper) + UPDATE(move_body_into_wrapper)
    """

    target: str
    wrapper_kind: str  # "try_catch", "with", "async", etc.
    wrapper_attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return "WRAP"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        wrapper_id = f"wrapper:{self.target}:{self.wrapper_kind}"

        # 1. Insert wrapper
        yield InsertNode(
            node_id=wrapper_id,
            node_kind=NodeKind.BLOCK,
            attrs={
                "wrapper_type": self.wrapper_kind,
                **self.wrapper_attrs,
            },
        )

        # 2. Update target to be wrapped
        yield Update(
            target=self.target,
            prop="wrapped_by",
            value=wrapper_id,
        )

        # 3. Add containment edge
        yield InsertEdge(
            source=wrapper_id,
            target=self.target,
            edge_kind=EdgeKind.CONTAINS,
        )


# =============================================================================
# Composition Registry
# =============================================================================


class CompositionRegistry:
    """Registry of available compositions."""

    _compositions: dict[str, type[Composition]] = {}

    @classmethod
    def register(cls, name: str, composition_class: type[Composition]) -> None:
        """Register a composition class."""
        cls._compositions[name.upper()] = composition_class

    @classmethod
    def get(cls, name: str) -> type[Composition] | None:
        """Get a composition class by name."""
        return cls._compositions.get(name.upper())

    @classmethod
    def list_compositions(cls) -> list[str]:
        """List all registered composition names."""
        return list(cls._compositions.keys())

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Composition | None:
        """Create a composition instance by name.

        Handles type conversion for string params to enums,
        and normalizes parameter aliases for common mistakes.
        """
        comp_class = cls.get(name)
        if comp_class:
            # Convert string params to enums where needed
            converted = kwargs.copy()
            if "node_kind" in converted and isinstance(converted["node_kind"], str):
                try:
                    converted["node_kind"] = NodeKind(converted["node_kind"])
                except ValueError:
                    pass  # Leave as-is if not a valid enum value
            if "edge_kind" in converted and isinstance(converted["edge_kind"], str):
                try:
                    converted["edge_kind"] = EdgeKind(converted["edge_kind"])
                except ValueError:
                    pass

            # Handle MOVE parameter aliases (common LLM mistakes)
            if name.upper() == "MOVE":
                converted = cls._normalize_move_params(converted)

            return comp_class(**converted)
        return None

    @classmethod
    def _normalize_move_params(cls, params: dict[str, Any]) -> dict[str, Any]:
        """Normalize MOVE parameters to handle common LLM mistakes.

        Handles aliases like:
        - destination -> to_scope
        - scope -> to_scope (when no to_scope)
        - position.scope -> to_scope
        """
        result = params.copy()

        # Handle nested position object (common LLM mistake)
        if "position" in result and isinstance(result["position"], dict):
            pos = result.pop("position")
            if "scope" in pos and "to_scope" not in result:
                result["to_scope"] = pos["scope"]

        # Handle destination alias
        if "destination" in result and "to_scope" not in result:
            result["to_scope"] = result.pop("destination")

        # Handle bare scope alias
        if "scope" in result and "to_scope" not in result:
            result["to_scope"] = result.pop("scope")

        return result


@dataclass
class UpdateImport(Composition):
    """Update import statements when a symbol moves between modules.

    UPDATE_IMPORT = UPDATE(import_module)

    Changes import paths when a symbol is moved from one module to another.
    Example: `from old_module import func` -> `from new_module import func`
    """

    symbol: str  # The imported symbol name
    old_module: str  # Original module path
    new_module: str  # New module path
    file: str | None = None  # Optional: specific file to update

    @property
    def name(self) -> str:
        return "UPDATE_IMPORT"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        # Find all import nodes that match the symbol and old module
        for node_id, node in graph.nodes.items():
            if not node_id.startswith("import:"):
                continue

            imp_name = node.attrs.get("name", "")
            imp_module = node.attrs.get("module", "")

            # Check if this import matches
            if imp_name == self.symbol and self.old_module in imp_module:
                # If a specific file is specified, only update that file
                if self.file and node.attrs.get("file") != self.file:
                    continue

                # Calculate new module path
                new_mod = imp_module.replace(self.old_module, self.new_module)
                yield Update(target=node_id, prop="module", value=new_mod)


# Register standard compositions
CompositionRegistry.register("RENAME", Rename)
CompositionRegistry.register("MOVE", Move)
CompositionRegistry.register("EXTRACT", Extract)
CompositionRegistry.register("INLINE", Inline)
CompositionRegistry.register("ADD_GUARD", AddGuard)
CompositionRegistry.register("CHANGE_SIGNATURE", ChangeSignature)
CompositionRegistry.register("WRAP", Wrap)
CompositionRegistry.register("UPDATE_IMPORT", UpdateImport)


# =============================================================================
# Composition Builder (Fluent API)
# =============================================================================


class CompositionBuilder:
    """Fluent API for building compositions from primitives."""

    def __init__(self, name: str = "custom"):
        self._name = name
        self._primitives: list[Primitive] = []

    def insert_node(
        self,
        node_id: str,
        node_kind: NodeKind,
        attrs: dict[str, Any] | None = None,
        position: Position | None = None,
    ) -> CompositionBuilder:
        """Add INSERT node primitive."""
        self._primitives.append(InsertNode(
            node_id=node_id,
            node_kind=node_kind,
            attrs=attrs or {},
            position=position,
        ))
        return self

    def insert_edge(
        self,
        source: str,
        target: str,
        edge_kind: EdgeKind,
        attrs: dict[str, Any] | None = None,
    ) -> CompositionBuilder:
        """Add INSERT edge primitive."""
        self._primitives.append(InsertEdge(
            source=source,
            target=target,
            edge_kind=edge_kind,
            attrs=attrs or {},
        ))
        return self

    def delete_node(self, node_id: str, cascade: bool = True) -> CompositionBuilder:
        """Add DELETE node primitive."""
        self._primitives.append(DeleteNode(node_id=node_id, cascade=cascade))
        return self

    def delete_edge(
        self,
        source: str,
        target: str,
        edge_kind: EdgeKind | None = None,
    ) -> CompositionBuilder:
        """Add DELETE edge primitive."""
        self._primitives.append(DeleteEdge(
            source=source,
            target=target,
            edge_kind=edge_kind,
        ))
        return self

    def update(
        self,
        target: str,
        prop: str | None = None,
        value: Any = None,
        **properties: Any,
    ) -> CompositionBuilder:
        """Add UPDATE primitive."""
        if properties:
            self._primitives.append(Update(target=target, properties=properties))
        else:
            self._primitives.append(Update(target=target, prop=prop, value=value))
        return self

    def build(self) -> _BuiltComposition:
        """Build the composition."""
        return _BuiltComposition(self._name, list(self._primitives))


@dataclass
class _BuiltComposition(Composition):
    """A composition built from explicit primitive list."""

    _name: str
    _primitives: list[Primitive]

    @property
    def name(self) -> str:
        return self._name

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        yield from self._primitives
