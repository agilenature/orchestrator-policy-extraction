/**
 * CRUD operations for episodes and episode_events in Mission Control's SQLite.
 *
 * All functions use better-sqlite3's synchronous prepared statement API.
 * JSON columns are serialized with JSON.stringify on write and stored as TEXT.
 * The Python analytics pipeline reads these via DuckDB's SQLite extension
 * and parses with json.loads.
 *
 * @module episodes
 */

import type Database from "better-sqlite3";

// Re-export schema init for convenience
export { initEpisodeSchema } from "./schema-episodes";

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

/** Project reference for an episode. */
export interface ProjectRef {
  repo_path: string;
  repo_remote?: string;
  branch?: string;
  commit_head?: string;
}

/** Input for creating a new episode. */
export interface CreateEpisodeInput {
  episode_id: string;
  task_id: string;
  session_id?: string;
  timestamp: string;
  project: ProjectRef;
  phase?: string;

  // Flat queryable fields
  mode?: string;
  risk?: string;
  status?: string;

  // Nested structures (will be JSON.stringified)
  observation?: Record<string, unknown>;
  orchestrator_action?: Record<string, unknown>;
  outcome?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  constraints_extracted?: Record<string, unknown>[];
  labels?: Record<string, unknown>;
}

/** Reaction update payload. */
export interface ReactionUpdate {
  label: string;
  message: string;
  confidence: number;
}

/** Filters for listing episodes. */
export interface EpisodeFilters {
  mode?: string;
  risk?: string;
  reaction_label?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

/** Episode event input. */
export interface EpisodeEventInput {
  event_id: string;
  episode_id: string;
  timestamp: string;
  received_at: string;
  event_type: string;
  payload: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Episode CRUD
// ---------------------------------------------------------------------------

/**
 * Create a new episode record.
 *
 * Inserts flat queryable columns directly and JSON.stringifies nested
 * structures for TEXT columns.
 */
export function createEpisode(
  db: Database.Database,
  episode: CreateEpisodeInput
): Database.RunResult {
  const stmt = db.prepare(`
    INSERT INTO episodes (
      episode_id, task_id, session_id, timestamp,
      mode, risk, status,
      observation, orchestrator_action, outcome,
      provenance, constraints_extracted, labels,
      project_repo_path, project_branch, project_commit_head,
      phase
    ) VALUES (
      @episode_id, @task_id, @session_id, @timestamp,
      @mode, @risk, @status,
      @observation, @orchestrator_action, @outcome,
      @provenance, @constraints_extracted, @labels,
      @project_repo_path, @project_branch, @project_commit_head,
      @phase
    )
  `);

  return stmt.run({
    episode_id: episode.episode_id,
    task_id: episode.task_id,
    session_id: episode.session_id ?? null,
    timestamp: episode.timestamp,
    mode: episode.mode ?? null,
    risk: episode.risk ?? null,
    status: episode.status ?? "in_progress",
    observation: episode.observation
      ? JSON.stringify(episode.observation)
      : null,
    orchestrator_action: episode.orchestrator_action
      ? JSON.stringify(episode.orchestrator_action)
      : null,
    outcome: episode.outcome ? JSON.stringify(episode.outcome) : null,
    provenance: episode.provenance
      ? JSON.stringify(episode.provenance)
      : null,
    constraints_extracted: episode.constraints_extracted
      ? JSON.stringify(episode.constraints_extracted)
      : null,
    labels: episode.labels ? JSON.stringify(episode.labels) : null,
    project_repo_path: episode.project.repo_path,
    project_branch: episode.project.branch ?? null,
    project_commit_head: episode.project.commit_head ?? null,
    phase: episode.phase ?? null,
  });
}

/**
 * Update an episode's reaction label, confidence, and outcome reaction field.
 *
 * Uses json_set to merge the reaction into the existing outcome JSON
 * without overwriting other outcome fields.
 *
 * @param constraintRef - Optional constraint ID to link to this reaction.
 */
export function updateEpisodeReaction(
  db: Database.Database,
  episodeId: string,
  reaction: ReactionUpdate,
  constraintRef?: string
): Database.RunResult {
  const reactionJson = JSON.stringify({
    label: reaction.label,
    message: reaction.message,
    confidence: reaction.confidence,
  });

  const stmt = db.prepare(`
    UPDATE episodes SET
      reaction_label = @reaction_label,
      reaction_confidence = @reaction_confidence,
      outcome = json_set(
        COALESCE(outcome, '{}'),
        '$.reaction',
        json(@reaction_json)
      ),
      status = 'completed',
      updated_at = datetime('now')
    WHERE episode_id = @episode_id
  `);

  return stmt.run({
    reaction_label: reaction.label,
    reaction_confidence: reaction.confidence,
    reaction_json: reactionJson,
    episode_id: episodeId,
  });
}

/**
 * Get a single episode by ID.
 *
 * Returns the raw row with JSON columns as TEXT strings.
 * Caller is responsible for JSON.parse on nested columns.
 */
export function getEpisode(
  db: Database.Database,
  episodeId: string
): Record<string, unknown> | undefined {
  const stmt = db.prepare("SELECT * FROM episodes WHERE episode_id = ?");
  return stmt.get(episodeId) as Record<string, unknown> | undefined;
}

/**
 * List episodes with optional filters.
 *
 * Supports filtering by mode, risk, reaction_label, and status.
 * Results are ordered by timestamp DESC with LIMIT/OFFSET pagination.
 */
export function listEpisodes(
  db: Database.Database,
  filters?: EpisodeFilters
): Record<string, unknown>[] {
  const conditions: string[] = [];
  const params: Record<string, unknown> = {};

  if (filters?.mode) {
    conditions.push("mode = @mode");
    params.mode = filters.mode;
  }
  if (filters?.risk) {
    conditions.push("risk = @risk");
    params.risk = filters.risk;
  }
  if (filters?.reaction_label) {
    conditions.push("reaction_label = @reaction_label");
    params.reaction_label = filters.reaction_label;
  }
  if (filters?.status) {
    conditions.push("status = @status");
    params.status = filters.status;
  }

  const where =
    conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const limit = filters?.limit ?? 100;
  const offset = filters?.offset ?? 0;

  const stmt = db.prepare(
    `SELECT * FROM episodes ${where} ORDER BY timestamp DESC LIMIT @limit OFFSET @offset`
  );

  return stmt.all({ ...params, limit, offset }) as Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Episode Events CRUD
// ---------------------------------------------------------------------------

/**
 * Insert a new episode event (tool provenance, lifecycle transition, etc.).
 *
 * The payload is JSON.stringified before storage.
 */
export function insertEpisodeEvent(
  db: Database.Database,
  event: EpisodeEventInput
): Database.RunResult {
  const stmt = db.prepare(`
    INSERT INTO episode_events (
      event_id, episode_id, timestamp, received_at, event_type, payload
    ) VALUES (
      @event_id, @episode_id, @timestamp, @received_at, @event_type, @payload
    )
  `);

  return stmt.run({
    event_id: event.event_id,
    episode_id: event.episode_id,
    timestamp: event.timestamp,
    received_at: event.received_at,
    event_type: event.event_type,
    payload: JSON.stringify(event.payload),
  });
}

/**
 * Get all events for an episode, ordered by timestamp ASC.
 *
 * Returns raw rows with payload as TEXT (JSON string).
 */
export function getEpisodeEvents(
  db: Database.Database,
  episodeId: string
): Record<string, unknown>[] {
  const stmt = db.prepare(
    "SELECT * FROM episode_events WHERE episode_id = ? ORDER BY timestamp ASC"
  );
  return stmt.all(episodeId) as Record<string, unknown>[];
}
