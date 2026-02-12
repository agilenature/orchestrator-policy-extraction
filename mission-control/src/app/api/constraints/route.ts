/**
 * Constraint CRUD API routes.
 *
 * GET  /api/constraints  - List all constraints
 * POST /api/constraints  - Create a new constraint (with SHA-256 dedup)
 *
 * The POST handler generates a deterministic constraint_id via SHA-256
 * of (text + JSON.stringify(scope_paths)), matching the Python
 * ConstraintStore dedup pattern. Duplicate constraints enrich the
 * existing examples array.
 *
 * @module api/constraints
 */

import { NextRequest, NextResponse } from 'next/server';
import { createHash } from 'crypto';
import { getDb } from '@/lib/db';
import { insertConstraint, listConstraints } from '@/lib/db/constraints';
import { broadcastEpisodeEvent } from '@/app/api/episodes/stream/route';

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

const VALID_SEVERITIES = ['warning', 'requires_approval', 'forbidden'] as const;

// ---------------------------------------------------------------------------
// GET /api/constraints
// ---------------------------------------------------------------------------

/**
 * List all constraints in the store.
 *
 * Returns JSON array of constraint records ordered by created_at DESC.
 */
export async function GET() {
  try {
    const db = getDb();
    const constraints = listConstraints(db);
    return NextResponse.json(constraints, { status: 200 });
  } catch (err) {
    console.error('[GET /api/constraints] Error:', err);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

// ---------------------------------------------------------------------------
// POST /api/constraints
// ---------------------------------------------------------------------------

/**
 * Create a new constraint.
 *
 * Accepts: { text, severity, scope_paths, detection_hints?,
 *            source_episode_id?, source_reaction_label? }
 *
 * Generates constraint_id via SHA-256(text + JSON.stringify(scope_paths))
 * matching the Python ConstraintStore dedup pattern. If constraint already
 * exists, the CRUD layer enriches the examples array.
 *
 * On success, broadcasts a constraint_extracted SSE event.
 *
 * Returns: 201 with the created constraint, or 200 if duplicate (enriched).
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // --- Validate required fields ---
    if (!body.text || typeof body.text !== 'string' || body.text.trim().length === 0) {
      return NextResponse.json(
        { error: 'text is required and must be a non-empty string' },
        { status: 400 }
      );
    }

    if (!body.severity || !VALID_SEVERITIES.includes(body.severity)) {
      return NextResponse.json(
        { error: `severity is required and must be one of: ${VALID_SEVERITIES.join(', ')}` },
        { status: 400 }
      );
    }

    if (!Array.isArray(body.scope_paths)) {
      return NextResponse.json(
        { error: 'scope_paths is required and must be an array of strings' },
        { status: 400 }
      );
    }

    // --- Generate deterministic constraint ID ---
    const hash = createHash('sha256');
    hash.update(body.text);
    hash.update(JSON.stringify(body.scope_paths));
    const constraintId = hash.digest('hex');

    // --- Build examples array ---
    const examples = body.source_episode_id
      ? [
          {
            episode_id: body.source_episode_id,
            violation_description: body.text,
          },
        ]
      : [];

    // --- Insert constraint (handles dedup via CRUD layer) ---
    const db = getDb();
    const isNew = insertConstraint(db, {
      constraint_id: constraintId,
      text: body.text.trim(),
      severity: body.severity,
      scope_paths: body.scope_paths,
      detection_hints: Array.isArray(body.detection_hints) ? body.detection_hints : [],
      source_episode_id: body.source_episode_id ?? null,
      source_reaction_label: body.source_reaction_label ?? null,
      examples,
    });

    // --- Broadcast SSE event ---
    broadcastEpisodeEvent({
      type: 'constraint_extracted',
      episode_id: body.source_episode_id ?? '',
      timestamp: new Date().toISOString(),
      data: {
        constraint_id: constraintId,
        text: body.text.trim(),
        severity: body.severity,
        is_new: isNew,
        summary: `Constraint ${isNew ? 'created' : 'enriched'}: ${body.text.trim().substring(0, 60)}`,
      },
    });

    return NextResponse.json(
      {
        constraint_id: constraintId,
        text: body.text.trim(),
        severity: body.severity,
        scope_paths: body.scope_paths,
        detection_hints: body.detection_hints ?? [],
        is_new: isNew,
      },
      { status: isNew ? 201 : 200 }
    );
  } catch (err) {
    console.error('[POST /api/constraints] Error:', err);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
