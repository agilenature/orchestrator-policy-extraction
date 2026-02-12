/**
 * Individual episode API routes.
 *
 * GET   /api/episodes/:id  - Get a single episode by ID
 * PATCH /api/episodes/:id  - Update episode fields or reaction
 *
 * @module api/episodes/[id]
 */

import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getEpisode, updateEpisodeReaction } from "@/lib/db/episodes";

/** Valid reaction labels. */
const VALID_REACTIONS = [
  "approve",
  "correct",
  "redirect",
  "block",
  "question",
  "unknown",
];

/** Valid mode values. */
const VALID_MODES = [
  "Explore",
  "Plan",
  "Implement",
  "Verify",
  "Integrate",
  "Triage",
  "Refactor",
];

/** Valid risk values. */
const VALID_RISKS = ["low", "medium", "high", "critical"];

/** Valid status values. */
const VALID_STATUSES = ["pending", "in_progress", "review", "completed"];

/**
 * GET /api/episodes/:id
 *
 * Returns the episode record or 404 if not found.
 * JSON columns are returned as-is (TEXT strings).
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const db = getDb();
    const { id } = await params;

    const episode = getEpisode(db, id);
    if (!episode) {
      return NextResponse.json(
        { error: "Episode not found" },
        { status: 404 }
      );
    }

    return NextResponse.json(episode, { status: 200 });
  } catch (err) {
    console.error(`[GET /api/episodes/:id] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/episodes/:id
 *
 * Supports two update paths:
 *
 * 1. Reaction update:
 *    { reaction: { label, message, confidence } }
 *    Calls updateEpisodeReaction() and sets status='completed'.
 *
 * 2. General field update:
 *    { mode?, risk?, status?, observation?, orchestrator_action?, outcome? }
 *    Updates specific columns directly.
 *
 * Returns the updated episode with 200, or 404 if not found.
 */
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const db = getDb();
    const { id } = await params;

    // Check episode exists
    const existing = getEpisode(db, id);
    if (!existing) {
      return NextResponse.json(
        { error: "Episode not found" },
        { status: 404 }
      );
    }

    const body = await request.json();

    // --- Path 1: Reaction update ---
    if (body.reaction) {
      const { label, message, confidence } = body.reaction;

      if (!label || typeof label !== "string") {
        return NextResponse.json(
          { error: "reaction.label is required and must be a string" },
          { status: 400 }
        );
      }
      if (!VALID_REACTIONS.includes(label)) {
        return NextResponse.json(
          {
            error: `Invalid reaction.label. Must be one of: ${VALID_REACTIONS.join(", ")}`,
          },
          { status: 400 }
        );
      }
      if (typeof confidence !== "number" || confidence < 0 || confidence > 1) {
        return NextResponse.json(
          {
            error:
              "reaction.confidence is required and must be a number between 0 and 1",
          },
          { status: 400 }
        );
      }

      updateEpisodeReaction(db, id, {
        label,
        message: message ?? "",
        confidence,
      });

      const updated = getEpisode(db, id);
      return NextResponse.json(updated, { status: 200 });
    }

    // --- Path 2: General field update ---
    const allowedFields: Record<string, string[]> = {
      mode: VALID_MODES,
      risk: VALID_RISKS,
      status: VALID_STATUSES,
    };

    const setClauses: string[] = [];
    const values: Record<string, unknown> = { episode_id: id };

    // Validate and collect flat field updates
    for (const [field, validValues] of Object.entries(allowedFields)) {
      if (body[field] !== undefined) {
        if (!validValues.includes(body[field])) {
          return NextResponse.json(
            {
              error: `Invalid ${field}. Must be one of: ${validValues.join(", ")}`,
            },
            { status: 400 }
          );
        }
        setClauses.push(`${field} = @${field}`);
        values[field] = body[field];
      }
    }

    // JSON column updates
    const jsonFields = ["observation", "orchestrator_action", "outcome"];
    for (const field of jsonFields) {
      if (body[field] !== undefined) {
        if (typeof body[field] !== "object") {
          return NextResponse.json(
            { error: `${field} must be an object` },
            { status: 400 }
          );
        }
        setClauses.push(`${field} = @${field}`);
        values[field] = JSON.stringify(body[field]);
      }
    }

    if (setClauses.length === 0) {
      return NextResponse.json(
        { error: "No valid fields to update" },
        { status: 400 }
      );
    }

    setClauses.push("updated_at = datetime('now')");

    const sql = `UPDATE episodes SET ${setClauses.join(", ")} WHERE episode_id = @episode_id`;
    db.prepare(sql).run(values);

    const updated = getEpisode(db, id);
    return NextResponse.json(updated, { status: 200 });
  } catch (err) {
    console.error(`[PATCH /api/episodes/:id] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
