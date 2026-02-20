"""Bulk JSON ingestor for project wisdom entities.

WisdomIngestor loads wisdom entries from JSON files or Python lists
and upserts them into a WisdomStore. Each entry is validated for
required fields (entity_type, title, description) and assigned a
deterministic wisdom_id via _make_wisdom_id().

Usage:
    ingestor = WisdomIngestor(store)
    result = ingestor.ingest_file(Path("data/seed_wisdom.json"))
    print(f"Added {result.added}, updated {result.updated}, skipped {result.skipped}")

Exports:
    IngestResult: Pydantic model tracking ingestion outcomes
    WisdomIngestor: Bulk loader for wisdom entries
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from src.pipeline.wisdom.models import WisdomEntity, _make_wisdom_id
from src.pipeline.wisdom.store import WisdomStore

_VALID_ENTITY_TYPES = frozenset(
    {"breakthrough", "dead_end", "scope_decision", "method_decision"}
)


class IngestResult(BaseModel):
    """Outcome of a bulk wisdom ingestion operation.

    Attributes:
        added: Count of new entities successfully inserted.
        updated: Count of existing entities upserted (same wisdom_id).
        skipped: Count of entries with validation errors.
        errors: List of error messages for skipped entries.
    """

    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


class WisdomIngestor:
    """Bulk loader for wisdom entries from JSON files or lists.

    Validates each entry, generates deterministic wisdom_id, and
    upserts into the WisdomStore. Supports re-running: existing
    entries are updated rather than duplicated.

    Args:
        store: WisdomStore to upsert entries into.
    """

    def __init__(self, store: WisdomStore) -> None:
        self._store = store

    def ingest_file(self, path: Path) -> IngestResult:
        """Load and ingest wisdom entries from a JSON file.

        Accepts either a JSON array at top level or an object with
        an "entries" key containing the array.

        Args:
            path: Path to the JSON file.

        Returns:
            IngestResult with counts and any error messages.
        """
        data = json.loads(path.read_text())
        entries = data if isinstance(data, list) else data.get("entries", [])
        return self.ingest_list(entries)

    def ingest_list(self, entries: list[dict]) -> IngestResult:
        """Ingest a list of wisdom entry dicts.

        Each entry is validated for required fields (entity_type,
        title, description) and entity_type must be one of the
        four valid types. Invalid entries are skipped with an
        error message recorded.

        Args:
            entries: List of dicts, each representing a wisdom entry.

        Returns:
            IngestResult with counts and any error messages.
        """
        result = IngestResult()

        for entry in entries:
            try:
                # Validate entity_type
                entity_type = entry.get("entity_type", "")
                if entity_type not in _VALID_ENTITY_TYPES:
                    result = result.model_copy(
                        update={
                            "skipped": result.skipped + 1,
                            "errors": result.errors
                            + [f"Invalid entity_type: {entity_type!r}"],
                        }
                    )
                    continue

                # Validate required fields
                title = entry.get("title", "").strip()
                description = entry.get("description", "").strip()
                if not title or not description:
                    result = result.model_copy(
                        update={
                            "skipped": result.skipped + 1,
                            "errors": result.errors
                            + ["Missing title or description"],
                        }
                    )
                    continue

                # Generate deterministic ID and check for existing
                wisdom_id = _make_wisdom_id(entity_type, title)
                existing = self._store.get(wisdom_id)

                # Build entity
                entity = WisdomEntity(
                    wisdom_id=wisdom_id,
                    entity_type=entity_type,
                    title=title,
                    description=description,
                    context_tags=entry.get("context_tags", []),
                    scope_paths=entry.get("scope_paths", []),
                    confidence=entry.get("confidence", 1.0),
                    source_document=entry.get("source_document"),
                    source_phase=entry.get("source_phase"),
                )

                # Upsert (insert or replace)
                self._store.upsert(entity)

                if existing:
                    result = result.model_copy(
                        update={"updated": result.updated + 1}
                    )
                else:
                    result = result.model_copy(
                        update={"added": result.added + 1}
                    )

            except Exception as e:
                result = result.model_copy(
                    update={
                        "skipped": result.skipped + 1,
                        "errors": result.errors + [str(e)],
                    }
                )

        return result
