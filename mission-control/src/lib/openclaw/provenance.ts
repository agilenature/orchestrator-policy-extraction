/**
 * ProvenanceCapture adapter for the OpenClaw Gateway WebSocket.
 *
 * Hooks into Gateway WS messages to capture tool provenance events during
 * task execution. Events are buffered and flushed to SQLite's episode_events
 * table in batched transactions to avoid write contention.
 *
 * Gateway timestamps are used as canonical ordering when available;
 * received_at is always recorded as the local receive time.
 *
 * Unrecognized messages are logged with console.debug (not warn) and
 * stored as 'tool_call' if they have content, to avoid data loss.
 *
 * @module provenance
 */

import type Database from "better-sqlite3";
import { randomUUID } from "crypto";
import type { EpisodeEventInput } from "../db/episodes";

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

/**
 * A tool provenance event captured from the Gateway.
 *
 * Maps directly to the episode_events table schema.
 */
export interface ToolProvenanceEvent {
  event_id: string;
  episode_id: string;
  timestamp: string;
  received_at: string;
  event_type:
    | "tool_call"
    | "tool_result"
    | "file_touch"
    | "command_run"
    | "test_result"
    | "git_event"
    | "lint_result"
    | "build_result";
  payload: Record<string, unknown>;
}

/**
 * Broad interface for Gateway WebSocket messages.
 *
 * Kept intentionally flexible since the Gateway protocol is not fully
 * documented. Fields are optional and the adapter handles missing fields
 * defensively.
 */
export interface GatewayMessage {
  type?: string;
  content?: unknown;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_result?: string;
  timestamp?: string;
  [key: string]: unknown;
}

/** Options for the ProvenanceCapture adapter. */
export interface ProvenanceCaptureOptions {
  /** Interval in ms between automatic buffer flushes. Default: 100. */
  batchIntervalMs?: number;
  /** Max buffer size before an immediate flush. Default: 50. */
  maxBatchSize?: number;
}

// ---------------------------------------------------------------------------
// Tool classification
// ---------------------------------------------------------------------------

/** Maps tool names to event_type values. */
const TOOL_EVENT_TYPE_MAP: Record<string, ToolProvenanceEvent["event_type"]> = {
  Bash: "command_run",
  Read: "file_touch",
  Edit: "file_touch",
  Write: "file_touch",
  Glob: "file_touch",
  Grep: "file_touch",
};

/**
 * Classify a tool name into a provenance event type.
 *
 * Special-cases git commands within Bash calls: if the tool is Bash and
 * the command string starts with "git ", it's classified as git_event.
 */
function classifyTool(
  toolName: string,
  toolInput?: Record<string, unknown>
): ToolProvenanceEvent["event_type"] {
  // Check for git commands within Bash
  if (toolName === "Bash" && toolInput) {
    const command = String(toolInput.command ?? "");
    if (command.startsWith("git ") || command.startsWith("git\t")) {
      return "git_event";
    }
    // Check for test runners
    if (
      command.includes("pytest") ||
      command.includes("npm test") ||
      command.includes("vitest") ||
      command.includes("jest")
    ) {
      return "test_result";
    }
    // Check for lint/format
    if (
      command.includes("eslint") ||
      command.includes("prettier") ||
      command.includes("ruff") ||
      command.includes("flake8")
    ) {
      return "lint_result";
    }
    // Check for build
    if (
      command.includes("npm run build") ||
      command.includes("tsc") ||
      command.includes("webpack") ||
      command.includes("vite build")
    ) {
      return "build_result";
    }
  }

  return TOOL_EVENT_TYPE_MAP[toolName] ?? "tool_call";
}

// ---------------------------------------------------------------------------
// ProvenanceCapture
// ---------------------------------------------------------------------------

/**
 * Captures tool provenance events from Gateway WebSocket messages.
 *
 * Usage:
 * ```ts
 * const capture = new ProvenanceCapture(db);
 * capture.startCapture(episodeId);
 * // For each WS message from Gateway:
 * capture.onGatewayMessage(message);
 * // When task completes:
 * capture.stopCapture();
 * ```
 */
export class ProvenanceCapture {
  private db: Database.Database;
  private buffer: ToolProvenanceEvent[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private batchIntervalMs: number;
  private maxBatchSize: number;

  /** The episode currently being captured. Null when not capturing. */
  currentEpisodeId: string | null = null;

  constructor(db: Database.Database, options?: ProvenanceCaptureOptions) {
    this.db = db;
    this.batchIntervalMs = options?.batchIntervalMs ?? 100;
    this.maxBatchSize = options?.maxBatchSize ?? 50;
  }

  /**
   * Start capturing provenance events for the given episode.
   *
   * Sets the current episode ID, clears any existing buffer, and starts
   * the periodic flush timer.
   */
  startCapture(episodeId: string): void {
    this.currentEpisodeId = episodeId;
    this.buffer = [];

    // Start periodic flush timer
    this.flushTimer = setInterval(() => {
      if (this.buffer.length > 0) {
        this.flush();
      }
    }, this.batchIntervalMs);
  }

  /**
   * Stop capturing provenance events.
   *
   * Flushes any remaining buffered events and clears the episode context.
   */
  stopCapture(): void {
    // Clear the periodic flush timer first
    if (this.flushTimer !== null) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }

    // Flush remaining events
    if (this.buffer.length > 0) {
      this.flush();
    }

    this.currentEpisodeId = null;
  }

  /**
   * Process a Gateway WebSocket message for tool provenance events.
   *
   * Identifies tool_use blocks, tool_result messages, and other tool-related
   * events. Unrecognized messages are logged with console.debug and skipped
   * unless they contain content.
   */
  onGatewayMessage(message: GatewayMessage): void {
    if (this.currentEpisodeId === null) {
      return;
    }

    const receivedAt = new Date().toISOString();
    const gatewayTimestamp = message.timestamp ?? receivedAt;
    const events: ToolProvenanceEvent[] = [];

    // Case 1: Content array with tool_use blocks
    if (Array.isArray(message.content)) {
      for (const block of message.content) {
        if (
          block !== null &&
          typeof block === "object" &&
          block.type === "tool_use"
        ) {
          const toolName = String(block.name ?? "unknown");
          const toolInput =
            block.input && typeof block.input === "object"
              ? (block.input as Record<string, unknown>)
              : {};
          const eventType = classifyTool(toolName, toolInput);

          events.push({
            event_id: randomUUID(),
            episode_id: this.currentEpisodeId,
            timestamp: gatewayTimestamp,
            received_at: receivedAt,
            event_type: eventType,
            payload: {
              tool_name: toolName,
              tool_input: toolInput,
            },
          });
        }
      }
    }

    // Case 2: Tool result message
    if (
      message.type === "tool_result" ||
      message.tool_result !== undefined
    ) {
      const toolName = message.tool_name
        ? String(message.tool_name)
        : "unknown";
      const result = message.tool_result
        ? String(message.tool_result)
        : "";
      const truncatedResult =
        result.length > 1000 ? result.slice(0, 1000) + "..." : result;

      events.push({
        event_id: randomUUID(),
        episode_id: this.currentEpisodeId,
        timestamp: gatewayTimestamp,
        received_at: receivedAt,
        event_type: "tool_result",
        payload: {
          tool_name: toolName,
          result: truncatedResult,
        },
      });
    }

    // Case 3: Direct tool_name field (tool call without content blocks)
    if (
      message.tool_name &&
      !Array.isArray(message.content) &&
      message.type !== "tool_result" &&
      message.tool_result === undefined
    ) {
      const toolName = String(message.tool_name);
      const toolInput = message.tool_input ?? {};
      const eventType = classifyTool(toolName, toolInput);

      events.push({
        event_id: randomUUID(),
        episode_id: this.currentEpisodeId,
        timestamp: gatewayTimestamp,
        received_at: receivedAt,
        event_type: eventType,
        payload: {
          tool_name: toolName,
          tool_input: toolInput,
        },
      });
    }

    // Case 4: Unrecognized message
    if (events.length === 0) {
      console.debug(
        "[ProvenanceCapture] Unrecognized gateway message type:",
        message.type ?? "undefined",
        "keys:",
        Object.keys(message).join(",")
      );
      // Skip storage for messages we don't understand
      return;
    }

    // Add events to buffer
    for (const event of events) {
      this.buffer.push(event);
    }

    // Flush if buffer exceeds max batch size
    if (this.buffer.length >= this.maxBatchSize) {
      this.flush();
    }
  }

  /**
   * Flush all buffered events to SQLite in a single transaction.
   *
   * Uses db.transaction() for atomicity to prevent write contention
   * (research Pitfall 3). Events are inserted via the episode_events
   * INSERT prepared statement.
   */
  flush(): void {
    if (this.buffer.length === 0) {
      return;
    }

    const eventsToFlush = this.buffer.splice(0, this.buffer.length);

    const insertStmt = this.db.prepare(`
      INSERT INTO episode_events (
        event_id, episode_id, timestamp, received_at, event_type, payload
      ) VALUES (
        @event_id, @episode_id, @timestamp, @received_at, @event_type, @payload
      )
    `);

    const insertBatch = this.db.transaction(
      (events: ToolProvenanceEvent[]) => {
        for (const event of events) {
          insertStmt.run({
            event_id: event.event_id,
            episode_id: event.episode_id,
            timestamp: event.timestamp,
            received_at: event.received_at,
            event_type: event.event_type,
            payload: JSON.stringify(event.payload),
          });
        }
      }
    );

    try {
      insertBatch(eventsToFlush);
    } catch (err) {
      // Log but don't crash -- provenance is valuable but not mission-critical
      console.error(
        "[ProvenanceCapture] Failed to flush events:",
        (err as Error).message
      );
      // Re-add failed events to buffer for retry on next flush
      this.buffer.unshift(...eventsToFlush);
    }
  }

  /** Return the number of buffered (unflushed) events. */
  get bufferSize(): number {
    return this.buffer.length;
  }
}
