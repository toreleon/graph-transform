"""
Position System for INSERT Operations

Defines where elements should be inserted in the code graph.
This is a universal position system that works across languages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Relation(Enum):
    """Relation of new element to anchor point."""

    BEFORE = "before"           # Insert before anchor
    AFTER = "after"             # Insert after anchor
    FIRST_CHILD = "first"       # Insert as first child of scope
    LAST_CHILD = "last"         # Insert as last child of scope
    REPLACE = "replace"         # Replace anchor (DELETE + INSERT)


@dataclass
class Position:
    """Specifies where to insert an element in the graph.

    The position is defined by:
    - scope: The container node (e.g., class, module, function)
    - anchor: Optional reference point within the scope
    - relation: How to position relative to anchor or scope
    - slot: Named slot within scope (e.g., "parameters", "body", "decorators")
    - index: Absolute position index (if applicable)

    Examples:
        # Insert as last method in class
        Position(scope="class:MyClass", relation=Relation.LAST_CHILD)

        # Insert before a specific method
        Position(
            scope="class:MyClass",
            anchor="func:MyClass.existing_method",
            relation=Relation.BEFORE
        )

        # Insert as third parameter
        Position(
            scope="func:my_func",
            slot="parameters",
            index=2
        )
    """

    # The container/scope where the element belongs
    scope: str | None = None

    # Optional anchor element for relative positioning
    anchor: str | None = None

    # Relation to anchor or scope
    relation: Relation = Relation.LAST_CHILD

    # Named slot within scope (for structured elements)
    slot: str | None = None

    # Absolute index position (0-based)
    index: int | None = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate position specification."""
        if self.anchor is not None and self.relation in (
            Relation.FIRST_CHILD,
            Relation.LAST_CHILD,
        ):
            # If anchor is specified, relation should be BEFORE/AFTER
            # FIRST_CHILD/LAST_CHILD are relative to scope, not anchor
            pass  # Allow it, anchor takes precedence

    @classmethod
    def at_end_of(cls, scope: str) -> Position:
        """Create position at end of scope."""
        return cls(scope=scope, relation=Relation.LAST_CHILD)

    @classmethod
    def at_start_of(cls, scope: str) -> Position:
        """Create position at start of scope."""
        return cls(scope=scope, relation=Relation.FIRST_CHILD)

    @classmethod
    def before(cls, anchor: str, scope: str | None = None) -> Position:
        """Create position before anchor."""
        return cls(scope=scope, anchor=anchor, relation=Relation.BEFORE)

    @classmethod
    def after(cls, anchor: str, scope: str | None = None) -> Position:
        """Create position after anchor."""
        return cls(scope=scope, anchor=anchor, relation=Relation.AFTER)

    @classmethod
    def replacing(cls, anchor: str, scope: str | None = None) -> Position:
        """Create position replacing anchor."""
        return cls(scope=scope, anchor=anchor, relation=Relation.REPLACE)

    @classmethod
    def at_index(cls, scope: str, index: int, slot: str | None = None) -> Position:
        """Create position at specific index within scope."""
        return cls(scope=scope, index=index, slot=slot)

    @classmethod
    def in_slot(cls, scope: str, slot: str, relation: Relation = Relation.LAST_CHILD) -> Position:
        """Create position in named slot of scope."""
        return cls(scope=scope, slot=slot, relation=relation)

    def with_metadata(self, **kwargs: Any) -> Position:
        """Return copy with additional metadata."""
        new_meta = {**self.metadata, **kwargs}
        return Position(
            scope=self.scope,
            anchor=self.anchor,
            relation=self.relation,
            slot=self.slot,
            index=self.index,
            metadata=new_meta,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "scope": self.scope,
            "anchor": self.anchor,
            "relation": self.relation.value,
            "slot": self.slot,
            "index": self.index,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        """Deserialize from dictionary."""
        return cls(
            scope=data.get("scope"),
            anchor=data.get("anchor"),
            relation=Relation(data.get("relation", "last")),
            slot=data.get("slot"),
            index=data.get("index"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EdgePosition:
    """Specifies position context for an edge.

    Edges connect two nodes. This class captures additional
    positioning information for the edge itself (not the nodes).
    """

    # Source and target node IDs
    source: str
    target: str

    # Optional ordering among parallel edges
    index: int | None = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "index": self.index,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgePosition:
        return cls(
            source=data["source"],
            target=data["target"],
            index=data.get("index"),
            metadata=data.get("metadata", {}),
        )
