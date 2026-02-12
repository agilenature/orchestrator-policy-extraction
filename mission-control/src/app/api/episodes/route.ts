/**
 * Episode collection API routes.
 *
 * GET  /api/episodes  - List episodes with optional filters and pagination
 * POST /api/episodes  - Create a new episode
 *
 * @module api/episodes
 */

import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { getDb } from "@/lib/db";
import { createEpisode, listEpisodes } from "@/lib/db/episodes";
import type { EpisodeFilters } from "@/lib/db/episodes";

/** Valid mode values for filtering. */
const VALID_MODES = [
  "Explore",
  "Plan",
  "Implement",
  "Verify",
  "Integrate",
  "Triage",
  "Refactor",
];

/** Valid risk values for filtering. */
const VALID_RISKS = ["low", "medium", "high", "critical"];

/** Valid reaction labels for filtering. */
const VALID_REACTIONS = [
  "approve",
  "correct",
  "redirect",
  "block",
  "question",
  "unknown",
];

/** Valid status values for filtering. */
const VALID_STATUSES = ["pending", "in_progress", "review", "completed"];

/**
 * GET /api/episodes
 *
 * List episodes with optional filters from searchParams:
 *   - mode: Explore|Plan|Implement|Verify|Integrate|Triage|Refactor
 *   - risk: low|medium|high|critical
 *   - reaction_label: approve|correct|redirect|block|question|unknown
 *   - status: pending|in_progress|review|completed
 *   - limit: number (default 50)
 *   - offset: number (default 0)
 *
 * Returns JSON array with 200.
 */
export async function GET(request: NextRequest) {
  try {
    const db = getDb();
    const { searchParams } = new URL(request.url);

    const filters: EpisodeFilters = {};

    // Parse and validate filters
    const mode = searchParams.get("mode");
    if (mode) {
      if (!VALID_MODES.includes(mode)) {
        return NextResponse.json(
          { error: `Invalid mode. Must be one of: ${VALID_MODES.join(", ")}` },
          { status: 400 }
        );
      }
      filters.mode = mode;
    }

    const risk = searchParams.get("risk");
    if (risk) {
      if (!VALID_RISKS.includes(risk)) {
        return NextResponse.json(
          { error: `Invalid risk. Must be one of: ${VALID_RISKS.join(", ")}` },
          { status: 400 }
        );
      }
      filters.risk = risk;
    }

    const reactionLabel = searchParams.get("reaction_label");
    if (reactionLabel) {
      if (!VALID_REACTIONS.includes(reactionLabel)) {
        return NextResponse.json(
          {
            error: `Invalid reaction_label. Must be one of: ${VALID_REACTIONS.join(", ")}`,
          },
          { status: 400 }
        );
      }
      filters.reaction_label = reactionLabel;
    }

    const status = searchParams.get("status");
    if (status) {
      if (!VALID_STATUSES.includes(status)) {
        return NextResponse.json(
          {
            error: `Invalid status. Must be one of: ${VALID_STATUSES.join(", ")}`,
          },
          { status: 400 }
        );
      }
      filters.status = status;
    }

    const limit = searchParams.get("limit");
    filters.limit = limit ? Math.min(Math.max(parseInt(limit, 10) || 50, 1), 500) : 50;

    const offset = searchParams.get("offset");
    filters.offset = offset ? Math.max(parseInt(offset, 10) || 0, 0) : 0;

    const episodes = listEpisodes(db, filters);
    return NextResponse.json(episodes, { status: 200 });
  } catch (err) {
    console.error("[GET /api/episodes] Error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

/**
 * POST /api/episodes
 *
 * Create a new episode. Request body:
 *   - task_id: string (required)
 *   - observation: object (optional)
 *   - orchestrator_action: object (optional)
 *   - mode: string (optional)
 *   - risk: string (optional)
 *   - status: string (optional, defaults to 'pending')
 *
 * Returns created episode with 201.
 */
export async function POST(request: NextRequest) {
  try {
    const db = getDb();
    const body = await request.json();

    // Validate required field
    if (!body.task_id || typeof body.task_id !== "string") {
      return NextResponse.json(
        { error: "task_id is required and must be a string" },
        { status: 400 }
      );
    }

    // Validate optional enum fields
    if (body.mode && !VALID_MODES.includes(body.mode)) {
      return NextResponse.json(
        { error: `Invalid mode. Must be one of: ${VALID_MODES.join(", ")}` },
        { status: 400 }
      );
    }

    if (body.risk && !VALID_RISKS.includes(body.risk)) {
      return NextResponse.json(
        { error: `Invalid risk. Must be one of: ${VALID_RISKS.join(", ")}` },
        { status: 400 }
      );
    }

    if (body.status && !VALID_STATUSES.includes(body.status)) {
      return NextResponse.json(
        {
          error: `Invalid status. Must be one of: ${VALID_STATUSES.join(", ")}`,
        },
        { status: 400 }
      );
    }

    const episodeId = randomUUID();
    const now = new Date().toISOString();

    createEpisode(db, {
      episode_id: episodeId,
      task_id: body.task_id,
      session_id: body.session_id ?? undefined,
      timestamp: now,
      mode: body.mode ?? undefined,
      risk: body.risk ?? undefined,
      status: body.status ?? "pending",
      observation: body.observation ?? undefined,
      orchestrator_action: body.orchestrator_action ?? undefined,
      outcome: body.outcome ?? undefined,
      project: body.project ?? { repo_path: "." },
      phase: body.phase ?? undefined,
    });

    // Return the created episode
    const created = {
      episode_id: episodeId,
      task_id: body.task_id,
      timestamp: now,
      status: body.status ?? "pending",
      mode: body.mode ?? null,
      risk: body.risk ?? null,
    };

    return NextResponse.json(created, { status: 201 });
  } catch (err) {
    console.error("[POST /api/episodes] Error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
