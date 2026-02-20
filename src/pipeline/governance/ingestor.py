"""Dual-store governance ingestor for ConstraintStore and WisdomStore.

Orchestrates sequential writes: constraints first (from assumptions),
then wisdom entities (from failure stories and decisions). Uses a
forbidden-language heuristic to upgrade constraint severity.

Exports:
    GovIngestResult: Pydantic model with ingestion outcome counts
    GovDocIngestor: Main ingestor class
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from src.pipeline.constraint_store import ConstraintStore
from src.pipeline.governance.parser import GovDocParser
from src.pipeline.wisdom.models import WisdomEntity
from src.pipeline.wisdom.store import WisdomStore


class GovIngestResult(BaseModel):
    """Outcome of a governance document ingestion.

    Attributes:
        constraints_added: New constraints written to ConstraintStore.
        constraints_skipped: Duplicate constraints already in store.
        wisdom_added: New wisdom entities inserted into WisdomStore.
        wisdom_updated: Existing wisdom entities updated in WisdomStore.
        wisdom_skipped: Wisdom entities that could not be written.
        errors: Warning and error messages from ingestion.
        bulk_threshold: Threshold for is_bulk computation.
    """

    constraints_added: int = 0
    constraints_skipped: int = 0
    wisdom_added: int = 0
    wisdom_updated: int = 0
    wisdom_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    bulk_threshold: int = 5

    @property
    def total_entities(self) -> int:
        """Total number of entities processed."""
        return (
            self.constraints_added
            + self.constraints_skipped
            + self.wisdom_added
            + self.wisdom_updated
            + self.wisdom_skipped
        )

    @property
    def is_bulk(self) -> bool:
        """Whether this ingestion qualifies as a bulk operation."""
        return self.total_entities >= self.bulk_threshold


class GovDocIngestor:
    """Dual-store ingestor for governance Markdown documents.

    Reads a Markdown file, parses it via GovDocParser, then writes:
      1. Constraints to ConstraintStore (from assumption entities)
      2. Wisdom to WisdomStore (from dead_end, scope_decision,
         method_decision entities)

    Constraints are always written first, then saved, before wisdom
    entities are written. This ensures constraints are persisted even
    if wisdom writing fails.

    Args:
        constraint_store: ConstraintStore instance for JSON persistence.
        wisdom_store: WisdomStore instance for DuckDB persistence.
        bulk_threshold: Entity count above which is_bulk returns True.
    """

    _FORBIDDEN_RE = re.compile(
        r"\b(must not|never|forbidden|do not|shall not)\b", re.IGNORECASE
    )

    def __init__(
        self,
        constraint_store: ConstraintStore,
        wisdom_store: WisdomStore,
        bulk_threshold: int = 5,
    ) -> None:
        self._constraint_store = constraint_store
        self._wisdom_store = wisdom_store
        self._bulk_threshold = bulk_threshold

    def ingest_file(
        self,
        path: Path,
        source_id: str | None = None,
        dry_run: bool = False,
    ) -> GovIngestResult:
        """Ingest a governance Markdown file into both stores.

        Args:
            path: Path to the Markdown file.
            source_id: Optional identifier; defaults to path.stem.
            dry_run: If True, compute counts but do not write.

        Returns:
            GovIngestResult with counts and any error messages.
        """
        result = GovIngestResult(bulk_threshold=self._bulk_threshold)

        # Read file
        content = path.read_text(encoding="utf-8")
        effective_source_id = source_id or path.stem

        # Parse
        parser = GovDocParser()
        entities = parser.parse_document(content, effective_source_id)

        if not entities:
            result = result.model_copy(
                update={
                    "errors": result.errors
                    + [f"No entities parsed from {path.name}"]
                }
            )
            return result

        # Separate entities by destination
        assumption_entities = [
            e for e in entities if e.entity_type == "assumption"
        ]
        wisdom_entities = [
            e
            for e in entities
            if e.entity_type in ("dead_end", "scope_decision", "method_decision")
        ]

        if dry_run:
            result = result.model_copy(
                update={
                    "constraints_added": len(assumption_entities),
                    "wisdom_added": len(wisdom_entities),
                }
            )
            return result

        # --- Sequential write: constraints FIRST ---
        constraint_ids: list[str] = []
        constraints_added = 0
        constraints_skipped = 0

        for entity in assumption_entities:
            constraint_dict = self._build_constraint(entity)
            cid = constraint_dict["constraint_id"]
            added = self._constraint_store.add(constraint_dict)
            if added:
                constraints_added += 1
                constraint_ids.append(cid)
            else:
                constraints_skipped += 1
                # Still track the ID for co-occurrence linkage
                constraint_ids.append(cid)

        # Persist constraints (CRITICAL)
        self._constraint_store.save()

        # --- Write wisdom SECOND ---
        wisdom_added = 0
        wisdom_updated = 0
        wisdom_skipped = 0

        for entity in wisdom_entities:
            try:
                # Determine context tags
                if entity.entity_type == "dead_end":
                    context_tags = ["governance", "pre-mortem"]
                else:
                    context_tags = ["governance", "decisions"]

                # Build metadata with co-occurrence linkage
                metadata: dict = {}
                if constraint_ids:
                    metadata["related_constraint_ids"] = list(constraint_ids)

                wisdom_entity = WisdomEntity.create(
                    entity_type=entity.entity_type,
                    title=entity.title,
                    description=entity.content,
                    context_tags=context_tags,
                    scope_paths=[],
                    confidence=1.0,
                    source_document=effective_source_id,
                    source_phase=12,
                    metadata=metadata if metadata else None,
                )

                # Check if exists for add/update tracking
                existing = self._wisdom_store.get(wisdom_entity.wisdom_id)
                self._wisdom_store.upsert(wisdom_entity)

                if existing:
                    wisdom_updated += 1
                else:
                    wisdom_added += 1

            except Exception as exc:
                wisdom_skipped += 1
                result = result.model_copy(
                    update={
                        "errors": result.errors
                        + [f"Wisdom write error for '{entity.title}': {exc}"]
                    }
                )

        result = result.model_copy(
            update={
                "constraints_added": constraints_added,
                "constraints_skipped": constraints_skipped,
                "wisdom_added": wisdom_added,
                "wisdom_updated": wisdom_updated,
                "wisdom_skipped": wisdom_skipped,
            }
        )
        return result

    def _build_constraint(self, entity) -> dict:
        """Build a constraint dict matching constraint.schema.json.

        Args:
            entity: ParsedEntity with type 'assumption'.

        Returns:
            Constraint dict ready for ConstraintStore.add().
        """
        text = entity.content
        scope_paths: list[str] = []
        created_at = datetime.now(timezone.utc).isoformat()

        # Deterministic ID: SHA-256(text + JSON(scope_paths))[:16]
        raw = (text + json.dumps(scope_paths)).encode()
        constraint_id = hashlib.sha256(raw).hexdigest()[:16]

        severity = self._determine_severity(text)

        return {
            "constraint_id": constraint_id,
            "text": text,
            "severity": severity,
            "scope": {"paths": scope_paths},
            "detection_hints": [text[:80]],
            "source_episode_id": "",
            "created_at": created_at,
            "examples": [],
            "type": "behavioral_constraint",
            "status": "active",
            "source": "govern_ingest",
            "status_history": [
                {"status": "active", "changed_at": created_at}
            ],
            "bypassed_constraint_id": None,
            "supersedes": None,
            "source_excerpt": text,
        }

    def _determine_severity(self, text: str) -> str:
        """Determine constraint severity from prohibition language.

        Returns "forbidden" if any prohibition keywords are found,
        otherwise "requires_approval".

        Args:
            text: Constraint text to analyze.

        Returns:
            "forbidden" or "requires_approval".
        """
        if self._FORBIDDEN_RE.search(text):
            return "forbidden"
        return "requires_approval"
