"""
SQLite Storage for TypedGraph

Persistent storage for code graphs using SQLite.
No external dependencies -- uses only the stdlib sqlite3 module.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from graph_transform.core.typed_graph import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
    TypedGraph,
)


# =============================================================================
# Schema
# =============================================================================

_SCHEMA = """
-- Metadata table for graph-level info
CREATE TABLE IF NOT EXISTS graphs (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    node_count INTEGER,
    edge_count INTEGER
);

-- Nodes table
CREATE TABLE IF NOT EXISTS nodes (
    graph_name TEXT NOT NULL,
    id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    attrs TEXT NOT NULL,
    PRIMARY KEY (graph_name, id),
    FOREIGN KEY (graph_name) REFERENCES graphs(name) ON DELETE CASCADE
);

-- Edges table
CREATE TABLE IF NOT EXISTS edges (
    graph_name TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    attrs TEXT NOT NULL,
    FOREIGN KEY (graph_name) REFERENCES graphs(name) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_edges_graph ON edges(graph_name);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(graph_name, node_type);
"""


# =============================================================================
# SQLiteGraphStore
# =============================================================================


class SQLiteGraphStore:
    """Persistent storage for TypedGraph using SQLite.

    Example:
        >>> store = SQLiteGraphStore("/tmp/my_graphs.db")
        >>> store.save_graph(graph, "my_project")
        >>> loaded = store.load_graph("my_project")
    """

    def __init__(self, db_path: str | Path = "/tmp/graph_transform.db") -> None:
        """Initialize the store, creating tables if needed.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_graph(self, graph: TypedGraph, name: str) -> None:
        """Save a TypedGraph with the given name.

        If a graph with this name already exists, it will be overwritten.

        Args:
            graph: The TypedGraph to save.
            name: Unique name for this graph.
        """
        with self._connect() as conn:
            # Delete existing graph if present (cascade deletes nodes/edges)
            conn.execute("DELETE FROM graphs WHERE name = ?", (name,))

            # Insert graph metadata
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO graphs (name, created_at, node_count, edge_count) VALUES (?, ?, ?, ?)",
                (name, now, graph.node_count, graph.edge_count),
            )

            # Insert nodes
            for node in graph.nodes.values():
                conn.execute(
                    "INSERT INTO nodes (graph_name, id, node_type, attrs) VALUES (?, ?, ?, ?)",
                    (name, node.id, node.node_type.value, json.dumps(node.attrs)),
                )

            # Insert edges
            for edge in graph.edges:
                conn.execute(
                    "INSERT INTO edges (graph_name, source, target, edge_type, attrs) VALUES (?, ?, ?, ?, ?)",
                    (name, edge.source, edge.target, edge.edge_type.value, json.dumps(edge.attrs)),
                )

    def load_graph(self, name: str) -> TypedGraph:
        """Load a TypedGraph by name.

        Args:
            name: Name of the graph to load.

        Returns:
            The loaded TypedGraph.

        Raises:
            KeyError: If no graph with this name exists.
        """
        with self._connect() as conn:
            # Check if graph exists
            row = conn.execute(
                "SELECT name FROM graphs WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Graph not found: {name}")

            # Load nodes
            nodes: dict[str, GraphNode] = {}
            for row in conn.execute(
                "SELECT id, node_type, attrs FROM nodes WHERE graph_name = ?", (name,)
            ):
                nodes[row["id"]] = GraphNode(
                    id=row["id"],
                    node_type=NodeType(row["node_type"]),
                    attrs=json.loads(row["attrs"]),
                )

            # Load edges
            edges: list[GraphEdge] = []
            for row in conn.execute(
                "SELECT source, target, edge_type, attrs FROM edges WHERE graph_name = ?",
                (name,),
            ):
                edges.append(
                    GraphEdge(
                        source=row["source"],
                        target=row["target"],
                        edge_type=EdgeType(row["edge_type"]),
                        attrs=json.loads(row["attrs"]),
                    )
                )

            return TypedGraph(nodes=nodes, edges=edges)

    def list_graphs(self) -> list[str]:
        """Return names of all stored graphs.

        Returns:
            List of graph names, sorted alphabetically.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM graphs ORDER BY name").fetchall()
            return [row["name"] for row in rows]

    def delete_graph(self, name: str) -> bool:
        """Delete a graph by name.

        Args:
            name: Name of the graph to delete.

        Returns:
            True if a graph was deleted, False if no graph with that name existed.
        """
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM graphs WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def graph_exists(self, name: str) -> bool:
        """Check if a graph with the given name exists.

        Args:
            name: Name to check.

        Returns:
            True if the graph exists, False otherwise.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM graphs WHERE name = ?", (name,)
            ).fetchone()
            return row is not None

    def get_graph_info(self, name: str) -> dict[str, str | int] | None:
        """Get metadata about a stored graph.

        Args:
            name: Name of the graph.

        Returns:
            Dict with 'name', 'created_at', 'node_count', 'edge_count',
            or None if not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, created_at, node_count, edge_count FROM graphs WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
