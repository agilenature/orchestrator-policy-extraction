/**
 * Constraint CRUD operations for Mission Control's SQLite.
 *
 * Mirrors the Python ConstraintStore format (data/schemas/constraint.schema.json).
 * Uses the same deduplication pattern: SHA-256 of (text + scope_paths JSON)
 * generates a deterministic constraint_id. On duplicate, the existing
 * constraint's examples array is enriched with the new episode reference.
 *
 * @module constraints
 */

import type Database from "better-sqlite3";
import { createHash } from "crypto";

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

/** Example entry linking a constraint to an episode where it was learned. */
export interface ConstraintExample {
  episode_id: string;
  violation_description: string;
}

/** Input for inserting a new constraint. */
export interface ConstraintInput {
  /** Deterministic ID. If omitted, generated from text + scope_paths. */
  constraint_id?: string;
  text: string;
  severity: "warning" | "requires_approval" | "forbidden";
  scope_paths: string[];
  detection_hints?: string[];
  source_episode_id?: string;
  source_reaction_label?: string;
  examples?: ConstraintExample[];
}

/** A constraint record as stored in the database. */
export interface ConstraintRow {
  constraint_id: string;
  text: string;
  severity: string;
  scope_paths: string;
  detection_hints: string | null;
  source_episode_id: string | null;
  source_reaction_label: string | null;
  examples: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Generate a deterministic constraint ID from text and scope paths.
 *
 * Uses SHA-256 of (text + JSON-serialized scope_paths), matching the
 * Python ConstraintStore pattern in src/pipeline/constraint_store.py.
 */
function generateConstraintId(text: string, scopePaths: string[]): string {
  const hash = createHash("sha256");
  hash.update(text);
  hash.update(JSON.stringify(scopePaths));
  return hash.digest("hex");
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

/**
 * Insert a constraint into the store.
 *
 * If the constraint_id already exists (duplicate), enriches the existing
 * constraint's examples array with new episode references (same dedup
 * pattern as the Python ConstraintStore).
 *
 * @returns true if newly inserted, false if duplicate (enriched).
 */
export function insertConstraint(
  db: Database.Database,
  constraint: ConstraintInput
): boolean {
  const constraintId =
    constraint.constraint_id ??
    generateConstraintId(constraint.text, constraint.scope_paths);

  // Check for existing constraint
  const existing = db
    .prepare("SELECT constraint_id, examples FROM constraints WHERE constraint_id = ?")
    .get(constraintId) as ConstraintRow | undefined;

  if (existing) {
    // Enrich examples array with new episode references
    const existingExamples: ConstraintExample[] = existing.examples
      ? JSON.parse(existing.examples)
      : [];
    const existingEpisodeIds = new Set(
      existingExamples.map((ex) => ex.episode_id)
    );

    const newExamples = constraint.examples ?? [];
    let enriched = false;
    for (const example of newExamples) {
      if (!existingEpisodeIds.has(example.episode_id)) {
        existingExamples.push(example);
        enriched = true;
      }
    }

    if (enriched) {
      db.prepare(
        "UPDATE constraints SET examples = ? WHERE constraint_id = ?"
      ).run(JSON.stringify(existingExamples), constraintId);
    }

    return false;
  }

  // Insert new constraint
  const stmt = db.prepare(`
    INSERT INTO constraints (
      constraint_id, text, severity, scope_paths,
      detection_hints, source_episode_id, source_reaction_label, examples
    ) VALUES (
      @constraint_id, @text, @severity, @scope_paths,
      @detection_hints, @source_episode_id, @source_reaction_label, @examples
    )
  `);

  stmt.run({
    constraint_id: constraintId,
    text: constraint.text,
    severity: constraint.severity,
    scope_paths: JSON.stringify(constraint.scope_paths),
    detection_hints: constraint.detection_hints
      ? JSON.stringify(constraint.detection_hints)
      : null,
    source_episode_id: constraint.source_episode_id ?? null,
    source_reaction_label: constraint.source_reaction_label ?? null,
    examples: constraint.examples
      ? JSON.stringify(constraint.examples)
      : null,
  });

  return true;
}

/**
 * List all constraints in the store.
 *
 * Returns raw rows with JSON columns as TEXT strings.
 */
export function listConstraints(
  db: Database.Database
): ConstraintRow[] {
  return db
    .prepare("SELECT * FROM constraints ORDER BY created_at DESC")
    .all() as ConstraintRow[];
}

/**
 * Get a single constraint by its deterministic ID.
 */
export function getConstraintById(
  db: Database.Database,
  id: string
): ConstraintRow | undefined {
  return db
    .prepare("SELECT * FROM constraints WHERE constraint_id = ?")
    .get(id) as ConstraintRow | undefined;
}
