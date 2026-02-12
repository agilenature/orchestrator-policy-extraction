/**
 * SQLite schema for Mission Control episode storage.
 *
 * Creates 5 tables alongside MC's existing task tables:
 *   - episodes: Core episode records with flat queryable columns + JSON nested data
 *   - episode_events: Tool provenance and lifecycle events per episode
 *   - constraints: Durable rules extracted from corrections/blocks
 *   - approvals: Gate decisions during task workflow
 *   - commit_links: Episode-to-commit correlation
 *
 * Column names use snake_case throughout and match the Pydantic Episode model
 * field names from src/pipeline/models/episodes.py exactly.
 *
 * @module schema-episodes
 */

import type Database from "better-sqlite3";

/**
 * Initialize the episode schema in the given SQLite database.
 *
 * Enables WAL mode and sets busy_timeout for concurrent access.
 * Uses CREATE TABLE IF NOT EXISTS so this is safe to call multiple times.
 *
 * @param db - A better-sqlite3 Database instance.
 */
export function initEpisodeSchema(db: Database.Database): void {
  // Enable WAL mode for concurrent reads during writes
  db.pragma("journal_mode = WAL");
  // Set busy timeout to 5 seconds to handle write contention
  db.pragma("busy_timeout = 5000");

  // --- Table 1: episodes ---
  // Core episode table with flat queryable columns and JSON nested structures.
  // Flat columns mirror the DuckDB schema for fast filtering.
  // JSON columns store the full nested Pydantic model structures.
  db.exec(`
    CREATE TABLE IF NOT EXISTS episodes (
      episode_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      session_id TEXT,
      timestamp TEXT NOT NULL,

      -- Flat queryable columns (mirrors Pydantic Episode model)
      mode TEXT CHECK (mode IN ('Explore','Plan','Implement','Verify','Integrate','Triage','Refactor')),
      risk TEXT CHECK (risk IN ('low','medium','high','critical')),
      reaction_label TEXT CHECK (reaction_label IN ('approve','correct','redirect','block','question','unknown')),
      reaction_confidence REAL,
      status TEXT DEFAULT 'in_progress' CHECK (status IN ('pending','in_progress','review','completed')),

      -- JSON columns for nested structures (matches Pydantic Episode model)
      observation TEXT,
      orchestrator_action TEXT,
      outcome TEXT,
      provenance TEXT,
      constraints_extracted TEXT,
      labels TEXT,

      -- Project reference (flat for queryability)
      project_repo_path TEXT,
      project_branch TEXT,
      project_commit_head TEXT,
      phase TEXT,

      -- Metadata
      schema_version INTEGER DEFAULT 1,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now')),

      FOREIGN KEY (task_id) REFERENCES tasks(id)
    )
  `);

  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_episodes_task ON episodes(task_id)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_episodes_mode ON episodes(mode)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_episodes_risk ON episodes(risk)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_episodes_reaction ON episodes(reaction_label)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status)"
  );

  // --- Table 2: episode_events ---
  // Tool provenance events and lifecycle transitions per episode.
  db.exec(`
    CREATE TABLE IF NOT EXISTS episode_events (
      event_id TEXT PRIMARY KEY,
      episode_id TEXT NOT NULL,
      timestamp TEXT NOT NULL,
      received_at TEXT NOT NULL,
      event_type TEXT NOT NULL CHECK (event_type IN (
        'tool_call','tool_result','file_touch','command_run',
        'test_result','git_event','lint_result','build_result',
        'lifecycle'
      )),
      payload TEXT NOT NULL,

      FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
    )
  `);

  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_events_episode ON episode_events(episode_id)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_events_type ON episode_events(event_type)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_events_ts ON episode_events(timestamp)"
  );

  // --- Table 3: constraints ---
  // Durable rules extracted from corrections/blocks. Mirrors
  // data/schemas/constraint.schema.json structure.
  db.exec(`
    CREATE TABLE IF NOT EXISTS constraints (
      constraint_id TEXT PRIMARY KEY,
      text TEXT NOT NULL,
      severity TEXT NOT NULL CHECK (severity IN ('warning','requires_approval','forbidden')),
      scope_paths TEXT NOT NULL,
      detection_hints TEXT,
      source_episode_id TEXT,
      source_reaction_label TEXT,
      examples TEXT,
      created_at TEXT DEFAULT (datetime('now')),

      FOREIGN KEY (source_episode_id) REFERENCES episodes(episode_id)
    )
  `);

  // --- Table 4: approvals ---
  // Gate decisions during the task workflow lifecycle.
  db.exec(`
    CREATE TABLE IF NOT EXISTS approvals (
      approval_id TEXT PRIMARY KEY,
      episode_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      gate_type TEXT NOT NULL,
      decision TEXT NOT NULL CHECK (decision IN ('approved','rejected','waived')),
      decided_by TEXT DEFAULT 'human',
      reason TEXT,
      created_at TEXT DEFAULT (datetime('now')),

      FOREIGN KEY (episode_id) REFERENCES episodes(episode_id),
      FOREIGN KEY (task_id) REFERENCES tasks(id)
    )
  `);

  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_approvals_episode ON approvals(episode_id)"
  );

  // --- Table 5: commit_links ---
  // Episode-to-commit correlation for validation.
  db.exec(`
    CREATE TABLE IF NOT EXISTS commit_links (
      link_id TEXT PRIMARY KEY,
      episode_id TEXT NOT NULL,
      commit_sha TEXT NOT NULL,
      branch TEXT,
      commit_message TEXT,
      files_changed TEXT,
      link_confidence REAL DEFAULT 1.0,
      created_at TEXT DEFAULT (datetime('now')),

      FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
    )
  `);

  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_commits_episode ON commit_links(episode_id)"
  );
  db.exec(
    "CREATE INDEX IF NOT EXISTS idx_commits_sha ON commit_links(commit_sha)"
  );
}
