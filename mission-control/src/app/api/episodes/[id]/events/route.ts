/**
 * Episode events API routes.
 *
 * GET  /api/episodes/:id/events  - List events for an episode
 * POST /api/episodes/:id/events  - Append a new event to an episode
 *
 * @module api/episodes/[id]/events
 */

import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { getDb } from "@/lib/db";
import {
  getEpisode,
  getEpisodeEvents,
  insertEpisodeEvent,
} from "@/lib/db/episodes";

/** Valid event types matching the schema CHECK constraint. */
const VALID_EVENT_TYPES = [
  "tool_call",
  "tool_result",
  "file_touch",
  "command_run",
  "test_result",
  "git_event",
  "lint_result",
  "build_result",
  "lifecycle",
];

/**
 * GET /api/episodes/:id/events
 *
 * Returns all events for the given episode, ordered by timestamp ASC.
 * Returns 404 if the episode does not exist.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const db = getDb();
    const { id } = await params;

    // Verify episode exists
    const episode = getEpisode(db, id);
    if (!episode) {
      return NextResponse.json(
        { error: "Episode not found" },
        { status: 404 }
      );
    }

    const events = getEpisodeEvents(db, id);
    return NextResponse.json(events, { status: 200 });
  } catch (err) {
    console.error(`[GET /api/episodes/:id/events] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

/**
 * POST /api/episodes/:id/events
 *
 * Append a new event to an episode. Request body:
 *   - event_type: string (required, one of VALID_EVENT_TYPES)
 *   - payload: object (required)
 *   - timestamp: string (optional, defaults to now)
 *
 * Generates event_id via crypto.randomUUID().
 * Sets received_at to current time.
 *
 * Returns 404 if the episode does not exist.
 * Returns created event with 201.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const db = getDb();
    const { id } = await params;

    // Verify episode exists
    const episode = getEpisode(db, id);
    if (!episode) {
      return NextResponse.json(
        { error: "Episode not found" },
        { status: 404 }
      );
    }

    const body = await request.json();

    // Validate event_type
    if (!body.event_type || typeof body.event_type !== "string") {
      return NextResponse.json(
        { error: "event_type is required and must be a string" },
        { status: 400 }
      );
    }
    if (!VALID_EVENT_TYPES.includes(body.event_type)) {
      return NextResponse.json(
        {
          error: `Invalid event_type. Must be one of: ${VALID_EVENT_TYPES.join(", ")}`,
        },
        { status: 400 }
      );
    }

    // Validate payload
    if (!body.payload || typeof body.payload !== "object") {
      return NextResponse.json(
        { error: "payload is required and must be an object" },
        { status: 400 }
      );
    }

    const eventId = randomUUID();
    const now = new Date().toISOString();
    const timestamp = body.timestamp ?? now;

    insertEpisodeEvent(db, {
      event_id: eventId,
      episode_id: id,
      timestamp,
      received_at: now,
      event_type: body.event_type,
      payload: body.payload,
    });

    const created = {
      event_id: eventId,
      episode_id: id,
      timestamp,
      received_at: now,
      event_type: body.event_type,
    };

    return NextResponse.json(created, { status: 201 });
  } catch (err) {
    console.error(`[POST /api/episodes/:id/events] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
