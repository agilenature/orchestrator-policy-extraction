"""DuckDB-backed storage for project wisdom entities.

WisdomStore provides CRUD operations, tag-based search, and scope-based
search against the project_wisdom DuckDB table. Manages its own schema
creation for standalone usage.

Usage:
    store = WisdomStore(db_path)
    entity = WisdomEntity.create("breakthrough", "Title", "Description")
    store.add(entity)
    results = store.search_by_tags(["duckdb", "schema"])

Exports:
    WisdomStore: Full CRUD and search for WisdomEntity instances
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.pipeline.wisdom.models import WisdomEntity


class WisdomStore:
    """DuckDB-backed CRUD and search for wisdom entities.

    Creates the project_wisdom table on init if it does not exist.
    All methods operate on WisdomEntity frozen Pydantic models.

    Args:
        db_path: Path to the DuckDB database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn = duckdb.connect(str(db_path))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the project_wisdom table if it does not exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS project_wisdom (
                wisdom_id VARCHAR PRIMARY KEY,
                entity_type VARCHAR NOT NULL CHECK (
                    entity_type IN (
                        'breakthrough', 'dead_end',
                        'scope_decision', 'method_decision'
                    )
                ),
                title VARCHAR NOT NULL,
                description TEXT NOT NULL,
                context_tags VARCHAR[] DEFAULT [],
                scope_paths VARCHAR[] DEFAULT [],
                confidence DOUBLE DEFAULT 1.0,
                source_document VARCHAR,
                source_phase INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                embedding DOUBLE[]
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_wisdom_entity_type "
            "ON project_wisdom(entity_type)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_wisdom_source_phase "
            "ON project_wisdom(source_phase)"
        )

    def add(self, entity: WisdomEntity) -> str:
        """Insert a new wisdom entity.

        Raises ValueError if an entity with the same wisdom_id already exists.

        Args:
            entity: WisdomEntity to insert.

        Returns:
            The wisdom_id of the inserted entity.

        Raises:
            ValueError: If a duplicate wisdom_id exists.
        """
        # Check for existing entry
        existing = self._conn.execute(
            "SELECT wisdom_id FROM project_wisdom WHERE wisdom_id = ?",
            [entity.wisdom_id],
        ).fetchone()
        if existing is not None:
            raise ValueError(
                f"Wisdom entity with id '{entity.wisdom_id}' already exists"
            )

        self._conn.execute(
            """
            INSERT INTO project_wisdom (
                wisdom_id, entity_type, title, description,
                context_tags, scope_paths, confidence,
                source_document, source_phase, embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entity.wisdom_id,
                entity.entity_type,
                entity.title,
                entity.description,
                entity.context_tags,
                entity.scope_paths,
                entity.confidence,
                entity.source_document,
                entity.source_phase,
                entity.embedding,
            ],
        )
        return entity.wisdom_id

    def get(self, wisdom_id: str) -> WisdomEntity | None:
        """Fetch a wisdom entity by ID.

        Args:
            wisdom_id: The wisdom entity ID to look up.

        Returns:
            WisdomEntity if found, None otherwise.
        """
        row = self._conn.execute(
            """
            SELECT wisdom_id, entity_type, title, description,
                   context_tags, scope_paths, confidence,
                   source_document, source_phase, embedding
            FROM project_wisdom
            WHERE wisdom_id = ?
            """,
            [wisdom_id],
        ).fetchone()

        if row is None:
            return None

        return self._row_to_entity(row)

    def update(self, entity: WisdomEntity) -> None:
        """Update an existing wisdom entity.

        Replaces all fields for the given wisdom_id. Updates the
        last_updated timestamp automatically.

        Args:
            entity: WisdomEntity with updated fields.

        Raises:
            ValueError: If no entity with the given wisdom_id exists.
        """
        existing = self._conn.execute(
            "SELECT wisdom_id FROM project_wisdom WHERE wisdom_id = ?",
            [entity.wisdom_id],
        ).fetchone()
        if existing is None:
            raise ValueError(
                f"Wisdom entity with id '{entity.wisdom_id}' not found"
            )

        self._conn.execute(
            """
            UPDATE project_wisdom SET
                entity_type = ?,
                title = ?,
                description = ?,
                context_tags = ?,
                scope_paths = ?,
                confidence = ?,
                source_document = ?,
                source_phase = ?,
                embedding = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE wisdom_id = ?
            """,
            [
                entity.entity_type,
                entity.title,
                entity.description,
                entity.context_tags,
                entity.scope_paths,
                entity.confidence,
                entity.source_document,
                entity.source_phase,
                entity.embedding,
                entity.wisdom_id,
            ],
        )

    def delete(self, wisdom_id: str) -> None:
        """Delete a wisdom entity by ID.

        Idempotent: no error if the entity does not exist.

        Args:
            wisdom_id: The wisdom entity ID to delete.
        """
        self._conn.execute(
            "DELETE FROM project_wisdom WHERE wisdom_id = ?",
            [wisdom_id],
        )

    def list(self, entity_type: str | None = None) -> list[WisdomEntity]:
        """List all wisdom entities, optionally filtered by type.

        Args:
            entity_type: If provided, only return entities of this type.

        Returns:
            List of WisdomEntity instances.
        """
        if entity_type is not None:
            rows = self._conn.execute(
                """
                SELECT wisdom_id, entity_type, title, description,
                       context_tags, scope_paths, confidence,
                       source_document, source_phase, embedding
                FROM project_wisdom
                WHERE entity_type = ?
                ORDER BY wisdom_id
                """,
                [entity_type],
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT wisdom_id, entity_type, title, description,
                       context_tags, scope_paths, confidence,
                       source_document, source_phase, embedding
                FROM project_wisdom
                ORDER BY wisdom_id
                """
            ).fetchall()

        return [self._row_to_entity(row) for row in rows]

    def search_by_tags(self, tags: list[str]) -> list[WisdomEntity]:
        """Find entities matching any of the given context tags.

        Uses DuckDB list_has_any() for efficient array intersection.

        Args:
            tags: Tags to search for (OR semantics: any match counts).

        Returns:
            List of matching WisdomEntity instances.
        """
        if not tags:
            return []

        rows = self._conn.execute(
            """
            SELECT wisdom_id, entity_type, title, description,
                   context_tags, scope_paths, confidence,
                   source_document, source_phase, embedding
            FROM project_wisdom
            WHERE list_has_any(context_tags, ?)
            ORDER BY wisdom_id
            """,
            [tags],
        ).fetchall()

        return [self._row_to_entity(row) for row in rows]

    def search_by_scope(self, scope_path: str) -> list[WisdomEntity]:
        """Find entities matching the given scope path.

        Returns entities that either contain the exact scope_path in
        their scope_paths array, OR have an empty scope_paths array
        (indicating repo-wide applicability).

        Args:
            scope_path: File/directory path to search for.

        Returns:
            List of matching WisdomEntity instances.
        """
        rows = self._conn.execute(
            """
            SELECT wisdom_id, entity_type, title, description,
                   context_tags, scope_paths, confidence,
                   source_document, source_phase, embedding
            FROM project_wisdom
            WHERE list_contains(scope_paths, ?)
               OR len(scope_paths) = 0
            ORDER BY wisdom_id
            """,
            [scope_path],
        ).fetchall()

        return [self._row_to_entity(row) for row in rows]

    def upsert(self, entity: WisdomEntity) -> str:
        """Insert or replace a wisdom entity.

        If an entity with the same wisdom_id exists, it is replaced.
        Otherwise a new entity is inserted.

        Args:
            entity: WisdomEntity to insert or replace.

        Returns:
            The wisdom_id of the upserted entity.
        """
        self._conn.execute(
            """
            INSERT OR REPLACE INTO project_wisdom (
                wisdom_id, entity_type, title, description,
                context_tags, scope_paths, confidence,
                source_document, source_phase, embedding,
                last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                entity.wisdom_id,
                entity.entity_type,
                entity.title,
                entity.description,
                entity.context_tags,
                entity.scope_paths,
                entity.confidence,
                entity.source_document,
                entity.source_phase,
                entity.embedding,
            ],
        )
        return entity.wisdom_id

    @staticmethod
    def _row_to_entity(row: tuple) -> WisdomEntity:
        """Convert a database row tuple to a WisdomEntity.

        Args:
            row: Tuple of (wisdom_id, entity_type, title, description,
                 context_tags, scope_paths, confidence, source_document,
                 source_phase, embedding).

        Returns:
            WisdomEntity instance.
        """
        (
            wisdom_id,
            entity_type,
            title,
            description,
            context_tags,
            scope_paths,
            confidence,
            source_document,
            source_phase,
            embedding,
        ) = row

        return WisdomEntity(
            wisdom_id=wisdom_id,
            entity_type=entity_type,
            title=title,
            description=description,
            context_tags=list(context_tags) if context_tags else [],
            scope_paths=list(scope_paths) if scope_paths else [],
            confidence=confidence if confidence is not None else 1.0,
            source_document=source_document,
            source_phase=source_phase,
            embedding=list(embedding) if embedding else None,
        )
