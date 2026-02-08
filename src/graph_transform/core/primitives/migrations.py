"""
Migration Compositions

Compositions for cross-language migration that transform a TypedGraph
from one language's conventions to another.

These compositions use UPDATE primitives to:
- Convert naming conventions (snake_case → camelCase)
- Convert type annotations (str → String)
- Update language-specific keywords (self → this, None → null)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from graph_transform.languages.mappings import LanguageMappings

from .base import Primitive, Update
from .compositions import Composition, CompositionResult

if TYPE_CHECKING:
    from graph_transform.core.typed_graph import TypedGraph


@dataclass
class MigrateNaming(Composition):
    """Convert naming conventions to target language style.

    Uses UPDATE primitives to rename all identifiers according
    to the target language's naming conventions.

    Example:
        # Python → Java: get_user_data → getUserData
        migrate = MigrateNaming(target_language="java")
        result = migrate.execute(graph)
    """

    target_language: str

    @property
    def name(self) -> str:
        return "MIGRATE_NAMING"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        """Generate UPDATE primitives for naming migration."""
        from graph_transform.core.typed_graph import NodeType

        for node_id, node in graph.nodes.items():
            current_name = node.attrs.get("name")
            if not current_name:
                continue

            # Determine name type based on node type
            if node.node_type == NodeType.CLASS:
                name_type = "class"
            elif node.node_type == NodeType.FUNCTION:
                if node.attrs.get("is_method"):
                    name_type = "method"
                else:
                    name_type = "function"
            elif node.node_type == NodeType.FIELD:
                # Check if it's a constant (all uppercase in source)
                if current_name.isupper():
                    name_type = "constant"
                else:
                    name_type = "field"
            elif node.node_type == NodeType.PARAMETER:
                param_name = current_name
                # Skip 'self' parameter - it will be removed in structure migration
                if param_name == "self":
                    continue
                name_type = "parameter"
            else:
                continue

            # Convert name
            new_name = LanguageMappings.convert_name(
                current_name,
                self.target_language,
                name_type,
            )

            # Only yield UPDATE if name changed
            if new_name != current_name:
                yield Update(
                    target=node_id,
                    prop="name",
                    value=new_name,
                )


@dataclass
class MigrateTypes(Composition):
    """Convert type annotations to target language types.

    Uses UPDATE primitives to convert all type annotations
    according to the target language's type system.

    Example:
        # Python → Java: str → String, list[int] → List<Integer>
        migrate = MigrateTypes(target_language="java")
        result = migrate.execute(graph)
    """

    target_language: str

    @property
    def name(self) -> str:
        return "MIGRATE_TYPES"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        """Generate UPDATE primitives for type migration."""
        from graph_transform.core.typed_graph import NodeType

        for node_id, node in graph.nodes.items():
            # Migrate field types
            if node.node_type == NodeType.FIELD:
                field_type = node.attrs.get("field_type")
                if field_type:
                    new_type = LanguageMappings.convert_type(
                        field_type,
                        self.target_language,
                    )
                    if new_type != field_type:
                        yield Update(
                            target=node_id,
                            prop="field_type",
                            value=new_type,
                        )

                # Also convert default values (True → true, None → null)
                default_value = node.attrs.get("default_value")
                if default_value:
                    new_default = self._convert_literal(default_value)
                    if new_default != default_value:
                        yield Update(
                            target=node_id,
                            prop="default_value",
                            value=new_default,
                        )

            # Migrate parameter types (if annotated)
            elif node.node_type == NodeType.PARAMETER:
                param_type = node.attrs.get("type_annotation")
                if param_type:
                    new_type = LanguageMappings.convert_type(
                        param_type,
                        self.target_language,
                    )
                    if new_type != param_type:
                        yield Update(
                            target=node_id,
                            prop="type_annotation",
                            value=new_type,
                        )

    def _convert_literal(self, value: str) -> str:
        """Convert Python literals to target language."""
        rules = LanguageMappings.get(self.target_language)

        if value == "True":
            return rules.bool_true
        elif value == "False":
            return rules.bool_false
        elif value == "None":
            return rules.null_keyword
        return value


@dataclass
class MigrateStructure(Composition):
    """Migrate language-specific structural elements.

    Handles:
    - Removing 'self' parameters (Python → Java/C#)
    - Converting instance field access patterns
    - Other structural transformations

    Example:
        migrate = MigrateStructure(target_language="java")
        result = migrate.execute(graph)
    """

    target_language: str

    @property
    def name(self) -> str:
        return "MIGRATE_STRUCTURE"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        """Generate primitives for structural migration."""
        from graph_transform.core.typed_graph import NodeType

        target_rules = LanguageMappings.get(self.target_language)

        # If target language doesn't use explicit self, mark self params for removal
        if target_rules.self_keyword != "self":
            for node_id, node in graph.nodes.items():
                if node.node_type == NodeType.PARAMETER:
                    if node.attrs.get("name") == "self":
                        # Mark as "remove" - the emitter will handle this
                        yield Update(
                            target=node_id,
                            prop="migrate_action",
                            value="remove",
                        )

        # Add target language metadata
        for node_id, node in graph.nodes.items():
            if node.node_type in (NodeType.CLASS, NodeType.FUNCTION, NodeType.MODULE):
                yield Update(
                    target=node_id,
                    prop="target_language",
                    value=self.target_language,
                )


@dataclass
class Migrate(Composition):
    """Complete migration from source to target language.

    Combines all migration steps:
    1. MIGRATE_NAMING - Convert naming conventions
    2. MIGRATE_TYPES - Convert type annotations
    3. MIGRATE_STRUCTURE - Handle structural differences

    Example:
        migrate = Migrate(target_language="java")
        result = migrate.execute(graph)
        # Graph is now transformed for Java emission
    """

    target_language: str

    @property
    def name(self) -> str:
        return "MIGRATE"

    def primitives(self, graph: TypedGraph) -> Iterator[Primitive]:
        """Generate all migration primitives in order."""
        # Step 1: Naming conventions
        naming = MigrateNaming(target_language=self.target_language)
        yield from naming.primitives(graph)

        # Step 2: Type annotations
        types = MigrateTypes(target_language=self.target_language)
        yield from types.primitives(graph)

        # Step 3: Structural changes
        structure = MigrateStructure(target_language=self.target_language)
        yield from structure.primitives(graph)

    def execute(self, graph: TypedGraph) -> CompositionResult:
        """Execute complete migration."""
        # Execute sub-compositions in order for better error reporting
        results = []

        naming = MigrateNaming(target_language=self.target_language)
        naming_result = naming.execute(graph)
        results.extend(naming_result.primitive_results)
        if not naming_result.success:
            return CompositionResult.fail(
                self.name,
                f"Naming migration failed: {naming_result.error}",
                results,
            )

        types = MigrateTypes(target_language=self.target_language)
        types_result = types.execute(graph)
        results.extend(types_result.primitive_results)
        if not types_result.success:
            return CompositionResult.fail(
                self.name,
                f"Types migration failed: {types_result.error}",
                results,
            )

        structure = MigrateStructure(target_language=self.target_language)
        structure_result = structure.execute(graph)
        results.extend(structure_result.primitive_results)
        if not structure_result.success:
            return CompositionResult.fail(
                self.name,
                f"Structure migration failed: {structure_result.error}",
                results,
            )

        return CompositionResult.ok(
            self.name,
            results,
            target_language=self.target_language,
            naming_updates=len(naming_result.primitive_results),
            type_updates=len(types_result.primitive_results),
            structure_updates=len(structure_result.primitive_results),
        )


__all__ = [
    "MigrateNaming",
    "MigrateTypes",
    "MigrateStructure",
    "Migrate",
]


# Register migration compositions
def _register_migrations() -> None:
    from .compositions import CompositionRegistry

    CompositionRegistry.register("MIGRATE", Migrate)
    CompositionRegistry.register("MIGRATE_NAMING", MigrateNaming)
    CompositionRegistry.register("MIGRATE_TYPES", MigrateTypes)
    CompositionRegistry.register("MIGRATE_STRUCTURE", MigrateStructure)


_register_migrations()
