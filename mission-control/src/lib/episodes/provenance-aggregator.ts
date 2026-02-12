/**
 * ProvenanceAggregator for episode outcome population.
 *
 * Reads raw provenance events from episode_events and aggregates them into
 * structured executor_effects and quality metrics that populate the
 * episode's outcome JSON column.
 *
 * All field names use snake_case to match the Pydantic Episode model
 * (src/pipeline/models/episodes.py) and Python analytics pipeline.
 *
 * @module provenance-aggregator
 */

import type Database from "better-sqlite3";
import { getEpisodeEvents } from "../db/episodes";

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

/**
 * Executor effects aggregated from tool provenance events.
 *
 * Matches the Pydantic ExecutorEffects model field names exactly.
 */
export interface ExecutorEffects {
  tool_calls_count: number;
  files_touched: string[];
  commands_ran: string[];
  git_events: Array<{
    type: string;
    ref?: string;
    message?: string;
  }>;
}

/**
 * Quality metrics derived from provenance events.
 *
 * Matches the Pydantic OutcomeQuality model structure.
 */
export interface OutcomeQuality {
  tests_status: string;
  lint_status: string;
  diff_stat: {
    files: number;
    insertions: number;
    deletions: number;
  };
}

/**
 * Combined aggregation result returned by aggregate().
 */
export interface AggregationResult {
  executor_effects: ExecutorEffects;
  quality: OutcomeQuality;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Safely parse a JSON string, returning null on failure.
 */
function safeJsonParse(text: unknown): Record<string, unknown> | null {
  if (typeof text !== "string") return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * Extract a file path from a tool event payload.
 *
 * Looks in common locations: payload.tool_input.file_path,
 * payload.tool_input.path, payload.files_touched.
 */
function extractFilePaths(payload: Record<string, unknown>): string[] {
  const paths: string[] = [];

  const toolInput = payload.tool_input as Record<string, unknown> | undefined;
  if (toolInput) {
    if (typeof toolInput.file_path === "string") {
      paths.push(toolInput.file_path);
    }
    if (typeof toolInput.path === "string") {
      paths.push(toolInput.path);
    }
  }

  if (Array.isArray(payload.files_touched)) {
    for (const f of payload.files_touched) {
      if (typeof f === "string") {
        paths.push(f);
      }
    }
  }

  return paths;
}

/**
 * Extract a command string from a command_run event payload.
 * Truncates to 200 characters.
 */
function extractCommand(payload: Record<string, unknown>): string | null {
  const toolInput = payload.tool_input as Record<string, unknown> | undefined;
  if (toolInput && typeof toolInput.command === "string") {
    const cmd = toolInput.command;
    return cmd.length > 200 ? cmd.slice(0, 200) + "..." : cmd;
  }
  return null;
}

/**
 * Parse a test_result event payload to determine test status.
 */
function parseTestStatus(
  payload: Record<string, unknown>
): string {
  // Check direct status field
  if (typeof payload.status === "string") {
    return payload.status;
  }

  // Check tool result text for common patterns
  const result = typeof payload.result === "string" ? payload.result : "";
  if (result.includes("passed") || result.includes("PASSED")) return "pass";
  if (result.includes("failed") || result.includes("FAILED")) return "fail";
  if (result.includes("error") || result.includes("ERROR")) return "error";

  return "unknown";
}

/**
 * Parse a lint_result event payload to determine lint status.
 */
function parseLintStatus(
  payload: Record<string, unknown>
): string {
  if (typeof payload.status === "string") {
    return payload.status;
  }

  const result = typeof payload.result === "string" ? payload.result : "";
  if (
    result.includes("no issues") ||
    result.includes("All checks passed") ||
    result.includes("0 errors")
  ) {
    return "pass";
  }
  if (result.includes("error") || result.includes("warning")) {
    return "fail";
  }

  return "unknown";
}

/**
 * Extract diff stats from git event payloads.
 *
 * Looks for structured diff_stat fields or parses common git output
 * patterns like "3 files changed, 10 insertions(+), 2 deletions(-)".
 */
function extractDiffStat(
  payload: Record<string, unknown>
): { files: number; insertions: number; deletions: number } | null {
  // Check for structured diff_stat
  if (
    payload.diff_stat &&
    typeof payload.diff_stat === "object"
  ) {
    const ds = payload.diff_stat as Record<string, unknown>;
    return {
      files: Number(ds.files ?? 0),
      insertions: Number(ds.insertions ?? 0),
      deletions: Number(ds.deletions ?? 0),
    };
  }

  // Try to parse from result text
  const result = typeof payload.result === "string" ? payload.result : "";
  const match = result.match(
    /(\d+)\s+files?\s+changed(?:,\s+(\d+)\s+insertions?\(\+\))?(?:,\s+(\d+)\s+deletions?\(-\))?/
  );
  if (match) {
    return {
      files: parseInt(match[1], 10),
      insertions: parseInt(match[2] ?? "0", 10),
      deletions: parseInt(match[3] ?? "0", 10),
    };
  }

  return null;
}

// ---------------------------------------------------------------------------
// ProvenanceAggregator
// ---------------------------------------------------------------------------

/**
 * Aggregates raw provenance events into episode outcome structures.
 *
 * Usage:
 * ```ts
 * const aggregator = new ProvenanceAggregator(db);
 * const result = aggregator.aggregate(episodeId);
 * // or update the episode directly:
 * aggregator.updateEpisodeOutcome(episodeId);
 * ```
 */
export class ProvenanceAggregator {
  private db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
  }

  /**
   * Aggregate all provenance events for an episode into structured summaries.
   *
   * Returns executor_effects (tool counts, files touched, commands, git events)
   * and quality metrics (test/lint status, diff stats).
   *
   * Null-safe: returns zeroed/empty structures if no events exist.
   */
  aggregate(episodeId: string): AggregationResult {
    const rawEvents = getEpisodeEvents(this.db, episodeId);

    // Initialize aggregation accumulators
    let toolCallsCount = 0;
    const filesSet = new Set<string>();
    const commandsList: string[] = [];
    const gitEventsList: Array<{
      type: string;
      ref?: string;
      message?: string;
    }> = [];
    let latestTestStatus = "unknown";
    let latestLintStatus = "unknown";
    let diffStat: { files: number; insertions: number; deletions: number } | null =
      null;

    for (const rawEvent of rawEvents) {
      const eventType = rawEvent.event_type as string;
      const payload = safeJsonParse(rawEvent.payload) ?? {};

      switch (eventType) {
        case "tool_call": {
          toolCallsCount++;
          break;
        }

        case "file_touch": {
          toolCallsCount++;
          const paths = extractFilePaths(payload);
          for (const p of paths) {
            filesSet.add(p);
          }
          break;
        }

        case "command_run": {
          toolCallsCount++;
          const cmd = extractCommand(payload);
          if (cmd) {
            commandsList.push(cmd);
          }
          break;
        }

        case "git_event": {
          toolCallsCount++;
          const gitPayload: {
            type: string;
            ref?: string;
            message?: string;
          } = {
            type: "unknown",
          };

          // Extract git event details from payload
          const toolInput = payload.tool_input as
            | Record<string, unknown>
            | undefined;
          if (toolInput && typeof toolInput.command === "string") {
            const command = toolInput.command;
            if (command.includes("git commit")) {
              gitPayload.type = "commit";
              // Extract message from -m flag
              const msgMatch = command.match(/-m\s+"([^"]+)"/);
              if (msgMatch) {
                gitPayload.message = msgMatch[1];
              }
            } else if (command.includes("git push")) {
              gitPayload.type = "push";
            } else if (command.includes("git pull")) {
              gitPayload.type = "pull";
            } else if (command.includes("git checkout")) {
              gitPayload.type = "checkout";
              const branchMatch = command.match(
                /git checkout\s+(?:-b\s+)?(\S+)/
              );
              if (branchMatch) {
                gitPayload.ref = branchMatch[1];
              }
            } else if (command.includes("git add")) {
              gitPayload.type = "stage";
            } else if (command.includes("git diff")) {
              gitPayload.type = "diff";
            } else if (command.includes("git status")) {
              gitPayload.type = "status";
            } else if (command.includes("git log")) {
              gitPayload.type = "log";
            }
          }

          // Check for structured git event fields
          if (typeof payload.type === "string") {
            gitPayload.type = payload.type;
          }
          if (typeof payload.ref === "string") {
            gitPayload.ref = payload.ref;
          }
          if (typeof payload.message === "string") {
            gitPayload.message = payload.message;
          }

          gitEventsList.push(gitPayload);

          // Try to extract diff stats from git events
          const ds = extractDiffStat(payload);
          if (ds) {
            diffStat = ds;
          }
          break;
        }

        case "test_result": {
          toolCallsCount++;
          // Use the latest test result (events are ordered by timestamp ASC)
          latestTestStatus = parseTestStatus(payload);
          break;
        }

        case "lint_result": {
          toolCallsCount++;
          latestLintStatus = parseLintStatus(payload);
          break;
        }

        case "build_result": {
          toolCallsCount++;
          break;
        }

        case "tool_result": {
          // Tool results don't count as separate tool calls;
          // they're the response to a preceding tool_call/file_touch/etc.
          break;
        }

        default: {
          // lifecycle or other event types -- count but don't aggregate
          break;
        }
      }
    }

    // Build diff_stat fallback from files_touched if no git diff stats
    const finalDiffStat = diffStat ?? {
      files: filesSet.size,
      insertions: 0,
      deletions: 0,
    };

    return {
      executor_effects: {
        tool_calls_count: toolCallsCount,
        files_touched: Array.from(filesSet),
        commands_ran: commandsList,
        git_events: gitEventsList,
      },
      quality: {
        tests_status: latestTestStatus,
        lint_status: latestLintStatus,
        diff_stat: finalDiffStat,
      },
    };
  }

  /**
   * Aggregate provenance events and merge into the episode's outcome JSON.
   *
   * Reads the current episode outcome, merges executor_effects and quality
   * into it, and writes the updated outcome back to SQLite.
   */
  updateEpisodeOutcome(episodeId: string): void {
    const aggregation = this.aggregate(episodeId);

    // Read current episode outcome
    const episode = this.db
      .prepare("SELECT outcome FROM episodes WHERE episode_id = ?")
      .get(episodeId) as { outcome: string | null } | undefined;

    if (!episode) {
      console.warn(
        `[ProvenanceAggregator] Episode not found: ${episodeId}`
      );
      return;
    }

    // Parse existing outcome or start fresh
    let outcome: Record<string, unknown> = {};
    if (episode.outcome) {
      try {
        outcome = JSON.parse(episode.outcome);
      } catch {
        // Corrupted JSON -- start fresh
        outcome = {};
      }
    }

    // Merge aggregated data into outcome
    outcome.executor_effects = aggregation.executor_effects;
    outcome.quality = aggregation.quality;

    // Write back
    this.db
      .prepare(
        "UPDATE episodes SET outcome = @outcome, updated_at = datetime('now') WHERE episode_id = @episode_id"
      )
      .run({
        outcome: JSON.stringify(outcome),
        episode_id: episodeId,
      });
  }
}
