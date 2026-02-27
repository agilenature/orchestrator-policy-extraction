# CLARIFICATIONS-ANSWERED.md

## Phase 16.1: Topological Edge-Generation — Design Decisions

**Generated:** 2026-02-24
**Source:** Multi-round architectural dialogue (human-led, session 2026-02-24)

All decisions were made by the human in real-time dialogue. No YOLO auto-generation.

---

## Q1: What is the axis_edges schema?

**DECISION:** First-class artifact table (not a pointer):

```sql
CREATE TABLE axis_edges (
  edge_id             TEXT PRIMARY KEY,  -- SHA-256[:16](axis_a || axis_b || relationship_text)
  axis_a              TEXT NOT NULL,
  axis_b              TEXT NOT NULL,
  relationship_text   TEXT NOT NULL,
  activation_condition JSON NOT NULL,    -- STRUCTURALLY PROHIBITED FROM NULL
  evidence            JSON NOT NULL,     -- {session_id, episode_id, flame_event_ids}
  abstraction_level   INTEGER NOT NULL,
  status              TEXT NOT NULL DEFAULT 'candidate'
                      CHECK(status IN ('candidate','active','superseded')),
  trunk_quality       FLOAT NOT NULL DEFAULT 1.0,
  created_session_id  TEXT NOT NULL,
  created_at          TIMESTAMPTZ DEFAULT now()
);
```

**Rationale:** An edge is a knowledge claim with evidence, scope, and quality — not a pointer between nodes.

---

## Q2: What fires the edge-generation detector?

**DECISION:** Conjunctive Flame Trigger:
- Level ≥ 5 (absolute) AND
- Abstraction Delta ≥ 2 above baseline_marker_level (rolling median, last 10 markers, per session) AND
- Both axis_a and axis_b active in same episode within 5-minute window

**NOT disjunctive.** Delta alone at low levels does not qualify. Level alone without delta does not qualify.

---

## Q3: Is activation_condition optional?

**DECISION:** No. Structurally mandatory. Schema enforces NOT NULL on activation_condition. An edge written without an activation_condition JSON object (or with `{}`) is rejected at write time.

Minimum valid activation_condition:
```json
{"goal_type": ["any"], "scope_prefix": "", "min_axes_simultaneously_active": 2}
```

---

## Q4: Where does Frontier Warning live?

**DECISION:** PAG gate extension. Not a separate monitoring daemon. The PAG gate already intercepts PREMISE declarations — it extends its check to: "Are two axes simultaneously referenced? If so, does an active edge exist for this context?"

Frontier Warning is a log entry, not a block. It is permanent infrastructure.

---

## Q5: What threshold triggers edge retirement?

**DECISION:** trunk_quality < 0.3 → status = 'superseded'. Degradation rate: -0.1 per failed cross-axis verification, -0.2 per explicit contradiction from a new flame event. Recovery: not implemented (retirement is one-directional — create a new edge if the relationship holds again in a different context).

---

## Q6: What is the foil level-matching rule?

**DECISION:** Foil abstraction level must be ≤ Premise abstraction level + 1. Comparing a Security-principle-level claim to a Naming-convention-level observation is Equivocation — the PAG gate's cross-axis verification rejects cross-level foils.

---

## Q7: What does the CLI show?

**DECISION:**
- `intelligence edges list [--axis AXIS]` — active edges for axis (or all)
- `intelligence edges frontier` — axis pairs active in recent sessions with no active edge
- `intelligence edges show EDGE_ID` — full artifact with evidence, trunk_quality, status

CLI is Layer 6 (Meta) scaffolding. It is instrumental — deposit-not-detect axis: do not prioritize CLI over the axis_edges write path.

---

## Q8: Plans structure?

**DECISION:** 4 plans in 3 waves:
- **Wave 1:** Plan 16.1-01 — axis_edges schema + models + writer
- **Wave 2:** Plan 16.1-02 — conjunctive Flame detector + edge generation logic (depends on 01)
- **Wave 2:** Plan 16.1-03 — PAG gate extension: Frontier Warning + Cross-Axis Verification (depends on 01)
- **Wave 3:** Plan 16.1-04 — integration tests + intelligence edges CLI (depends on 02, 03)

---

*All answers derived from human-led architectural dialogue. No open questions remain.*
