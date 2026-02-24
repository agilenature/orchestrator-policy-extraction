---
phase: 17-candidate-assessment-system
verified: 2026-02-24T23:01:37Z
status: gaps_found
score: 4/5 must-haves verified
gaps:
  - truth: "Rejection detector runs without error in the live environment"
    status: failed
    reason: "rejection_detector.py queries ccd_axis and differential columns on flame_events, but these columns do not exist in the base FLAME_EVENTS_DDL or in the live database. Tests pass only because test fixtures manually add these columns via ALTER TABLE. Any real assessment session calling detect_rejections() will raise a BinderException."
    artifacts:
      - path: "src/pipeline/assessment/rejection_detector.py"
        issue: "Lines 63-68 query ccd_axis and differential from flame_events, but these columns are absent from the DDL"
      - path: "src/pipeline/ddf/schema.py"
        issue: "FLAME_EVENTS_DDL does not define ccd_axis or differential columns"
    missing:
      - "Add ccd_axis VARCHAR and differential VARCHAR to FLAME_EVENTS_DDL (or add them to ASSESSMENT_ALTER_EXTENSIONS in assessment/schema.py)"
      - "Run schema migration against live database to add missing assessment columns (assessment_te_sessions, assessment_baselines, project_wisdom.ddf_target_level, flame_events.assessment_session_id, memory_candidates.source_type)"

  - truth: "Phase 17 schema is deployed in the live database"
    status: failed
    reason: "The live database (data/ope.db) has not had create_assessment_schema() applied. Tables assessment_te_sessions and assessment_baselines do not exist. Columns project_wisdom.ddf_target_level, project_wisdom.scenario_seed, flame_events.assessment_session_id, memory_candidates.source_type are absent. The code chains create_assessment_schema() correctly at the end of create_ddf_schema(), but the live DB predates this schema migration call."
    artifacts:
      - path: "data/ope.db"
        issue: "No assessment_te_sessions or assessment_baselines tables; no Phase 17 ALTER TABLE columns applied"
    missing:
      - "Run create_ddf_schema() against data/ope.db to apply assessment schema (or run the assess annotate-scenarios CLI which calls create_assessment_schema explicitly)"

human_verification:
  - test: "Run a real assessment session end-to-end"
    expected: "CLI assess run <scenario_id> <candidate_id> completes without error, Actor JSONL produced, Observer processes it, TE written, report generated"
    why_human: "Requires live Actor Claude Code launch in /tmp directory and active JSONL session -- cannot verify subprocess execution programmatically"
  - test: "Scenario bank seeding from OPE historical data"
    expected: "project_wisdom has annotated entries with ddf_target_level set for OPE's own dead ends and breakthroughs"
    why_human: "project_wisdom table currently has 0 rows -- the scenario bank is structurally ready (annotation CLI exists) but not yet populated with OPE historical data"
---

# Phase 17: Candidate Assessment System Verification Report

**Phase Goal:** Use the full IntelligenceProfile (Phase 15 FlameEvents + Phase 16 TransportEfficiency) to assess the epistemological quality of candidates for collaborating with AI. Phase 17 is simultaneously the highest-fidelity AI self-improvement mechanism: calibrated DDF Levels 5-7 scenarios force ai_flame_events at depth that routine sessions cannot generate.

**Verified:** 2026-02-24T23:01:37Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Scenario generator pulls from wisdom/episode database to construct pile problems calibrated by DDF level (L1-2 breakthrough, L2-4 dead_end, L5-7 with handicap CLAUDE.md) | VERIFIED | `scenario_generator.py` queries `project_wisdom`, maps entity_type to DDF levels, builds `scenario_context.md` + `broken_impl.py` + optional handicap `CLAUDE.md` |
| 2 | Candidate sessions run in isolated Claude Code environments with live DDF detection via Phase 14/15 infrastructure; AI enters with IntelligenceProfile loaded | VERIFIED | `session_runner.py` creates `/tmp/ope_assess_{id}/`, pre-seeds MEMORY.md from production, launches `unset CLAUDECODE && claude --session-id`, `observer.py` runs PipelineRunner post-session |
| 3 | Assessment Report produced at session end with all required sub-metrics | VERIFIED | `reporter.py` produces FlameEvent timeline, level_distribution, candidate_te, raven_depth, crow_efficiency, trunk_quality, candidate_ratio, percentile_rank, axis_quality_scores, flood_rate, spiral_evidence, fringe_drift_rate, ai_avg_marker_level, ai_flame_event_count, rejections_detected, rejections_level5, stubbornness_indicators |
| 4 | Scenario bank seeded from OPE project's own historical dead ends and breakthroughs | PARTIAL | Schema ready (`project_wisdom.ddf_target_level`, `scenario_seed` columns added via ALTER TABLE, annotation CLI exists), but `project_wisdom` has 0 rows — no scenarios have been annotated yet |
| 5 | Transparency: candidate knows they are in an AI-assisted coding session being assessed for epistemological quality | UNCERTAIN | No code implements explicit transparency disclosure to the candidate. Per CLARIFICATIONS-ANSWERED.md Q2, "The Actor does NOT know it is in an assessment. The candidate knows." — this is a human-process requirement, not a code requirement. No enforcement mechanism exists in the codebase. |

**Score:** 3 cleanly verified, 1 partial, 1 uncertain → 4/5 must-haves structurally implemented

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/assessment/__init__.py` | Module init | EXISTS (empty, 1 line) | Empty file — acceptable for namespace package |
| `src/pipeline/assessment/schema.py` | DDL + create_assessment_schema | VERIFIED | 127 lines, substantive DDL for assessment_te_sessions, assessment_baselines, ALTER TABLE extensions, chained in create_ddf_schema() |
| `src/pipeline/assessment/models.py` | Frozen Pydantic v2 models | VERIFIED | 178 lines, ScenarioSpec + AssessmentSession + AssessmentReport all frozen, validators, deterministic IDs |
| `src/pipeline/assessment/scenario_generator.py` | Generate pile problems from wisdom | VERIFIED | 333 lines, ScenarioGenerator class, DDF-level-to-entity mapping, handicap CLAUDE.md for L5-7, validate_broken_impl |
| `src/pipeline/assessment/session_runner.py` | Session lifecycle management | VERIFIED | 355 lines, setup_assessment_dir + launch_actor + cleanup_session, MEMORY.md pre-seeding |
| `src/pipeline/assessment/observer.py` | Post-session pipeline runner | VERIFIED | 113 lines, AssessmentObserver using PipelineRunner, tags flame_events with assessment_session_id |
| `src/pipeline/assessment/rejection_detector.py` | Outcome-gated rejection detection | STUB/PARTIAL | 197 lines, logic correct, but queries `ccd_axis` and `differential` columns not in FLAME_EVENTS_DDL — will fail in production |
| `src/pipeline/assessment/te_assessment.py` | 3-metric TE computation | VERIFIED | 225 lines, compute_assessment_te (raven_depth × crow_efficiency × trunk_quality), write_assessment_te_row, update_assessment_baselines |
| `src/pipeline/assessment/reporter.py` | Report generator + terminal deposit | VERIFIED | 696 lines, generate_report (all sub-metrics), format_report_markdown (all sections), deposit_report to memory_candidates (source_type='simulation_review', fidelity=3, confidence=0.85), auto-calibration proposals |
| `src/pipeline/cli/assess.py` | CLI commands | VERIFIED | 616 lines, assess group with annotate-scenarios, list-scenarios, run, calibrate, report — all registered under intelligence_group |
| `src/pipeline/ddf/intelligence_profile.py` | Modified to exclude assessment events | VERIFIED | All four queries (compute_intelligence_profile, compute_ai_profile, compute_spiral_depth_for_human, _compute_ai_spiral_depth, list_available_humans) filter `assessment_session_id IS NULL` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/pipeline/ddf/schema.py` | `src/pipeline/assessment/schema.py` | `create_assessment_schema(conn)` at end of `create_ddf_schema()` | WIRED | Lines 150-153 call create_assessment_schema after create_te_schema |
| `src/pipeline/cli/intelligence.py` | `src/pipeline/cli/assess.py` | `intelligence_group.add_command(assess_group)` | WIRED | Lines 793-795, assess_group imported and registered |
| `session_runner.py` | `scenario_generator.py` | `ScenarioGenerator(conn).generate_scenario_files()` | WIRED | Line 83-84 in setup_assessment_dir |
| `observer.py` | `PipelineRunner` | `runner.run_session(session.jsonl_path)` | WIRED | Lines 71-72, lazy import to avoid circular dependency |
| `reporter.py` | `rejection_detector.py` | `RejectionDetector(conn).detect_rejections()` | WIRED (code level) | Lines 156-163, but rejection_detector will fail on missing columns in production |
| `reporter.py` | `memory_candidates` table | Direct INSERT with DELETE+INSERT upsert | WIRED | Lines 505-534, deposits with source_type='simulation_review' |
| `intelligence_profile.py` | assessment exclusion filter | `WHERE assessment_session_id IS NULL` | WIRED | All 4 aggregation queries carry this filter |
| `rejection_detector.py` | `flame_events.ccd_axis` | SQL SELECT column | NOT_WIRED | Column does not exist in FLAME_EVENTS_DDL or live DB |
| `rejection_detector.py` | `flame_events.differential` | SQL SELECT column | NOT_WIRED | Column does not exist in FLAME_EVENTS_DDL or live DB |

---

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| SC1: Scenario generator calibrated by DDF level (L1-2/L3-4/L5-7) | SATISFIED | ScenarioGenerator maps entity_type to DDF levels, handicap CLAUDE.md for L5-7 |
| SC2: Isolated sessions with live DDF detection, IntelligenceProfile loaded | SATISFIED | /tmp isolation, MEMORY.md pre-seeding, PipelineRunner observer post-session |
| SC3: Assessment Report with full sub-metrics including AI contribution profile | SATISFIED | All required fields present in AssessmentReport model and format_report_markdown |
| SC4: Scenario bank from OPE historical dead ends and breakthroughs | PARTIAL | Schema and annotation CLI ready; project_wisdom has 0 rows |
| SC5: Transparency — candidate knows they are in an AI-assisted session | UNCERTAIN | No code enforces this; it is a human-process requirement per CLARIFICATIONS-ANSWERED.md Q2 |

---

### Anti-Patterns Found

| File | Location | Pattern | Severity | Impact |
|------|----------|---------|----------|--------|
| `src/pipeline/assessment/rejection_detector.py` | Lines 63-68 | Queries `ccd_axis` and `differential` columns not in DDL | BLOCKER | Any live assessment calling detect_rejections() will raise a DuckDB BinderException; tests mask this via manual ALTER TABLE in fixture |
| `src/pipeline/assessment/te_assessment.py` | Line 67 | `trunk_quality = 0.5  # Placeholder until confirmed` | WARNING | trunk_quality is always 0.5 (pending) until a human review confirms it; the assessment TE formula is structurally correct but trunk_quality is intentionally a placeholder per design |
| `data/ope.db` | Live database | No Phase 17 schema applied | BLOCKER | assessment_te_sessions, assessment_baselines tables absent; ddf_target_level, scenario_seed, assessment_session_id, source_type columns absent from live tables |
| `src/pipeline/assessment/scenario_generator.py` | `_build_handicap()` | Wrong framing always uses generic `"configuration handling"` regardless of scenario content | WARNING | Handicap CLAUDE.md is not truly calibrated to the specific wisdom entry — it's always a generic "wrong component: configuration handling" story. Not a stub (it runs), but calibration quality is limited |

---

### Human Verification Required

#### 1. End-to-End Assessment Session
**Test:** Run `python -m src.pipeline.cli intelligence assess annotate-scenarios --db data/ope.db` to annotate an entry, then `python -m src.pipeline.cli intelligence assess calibrate <scenario_id>` and `python -m src.pipeline.cli intelligence assess run <scenario_id> <candidate_id>`.
**Expected:** Actor Claude Code launched in /tmp directory, JSONL produced, Observer pipeline processes it, TE computed, report generated.
**Why human:** Requires live subprocess Actor launch and real Claude Code session execution — cannot verify programmatically.

#### 2. Scenario Bank Seeding
**Test:** Inspect `project_wisdom` table contents after populating with OPE's actual historical dead ends and breakthroughs from the planning documents.
**Expected:** At least 5-10 annotated entries across DDF levels 1-7.
**Why human:** Requires human judgment on which wisdom entries map to which DDF levels; currently 0 entries exist.

#### 3. Transparency Protocol
**Test:** Verify that candidates are actually informed they are in an AI-assisted coding session being assessed for epistemological quality before the session starts.
**Expected:** Some process or UI element informs the candidate.
**Why human:** This is a human-process requirement; no code enforces it. The architecture intentionally treats this as operational procedure (per CLARIFICATIONS-ANSWERED.md Q2), not a codebase concern.

---

### Gaps Summary

**Two blockers and one partial prevent full goal achievement:**

**Blocker 1 — rejection_detector queries non-existent columns.** The `rejection_detector.py` queries `ccd_axis` and `differential` from `flame_events` at lines 63-68, but neither column is defined in `FLAME_EVENTS_DDL` (src/pipeline/ddf/schema.py) or added by `ASSESSMENT_ALTER_EXTENSIONS`. Unit tests add these columns manually in fixtures (`_add_rejection_columns`), masking the defect. In any live assessment session, calling `detect_rejections()` will fail with a DuckDB BinderException. The fix is either adding these two columns to FLAME_EVENTS_DDL, adding them to ASSESSMENT_ALTER_EXTENSIONS, or removing them from the rejection_detector query and using the `axis_identified` column that does exist.

**Blocker 2 — Phase 17 schema not applied to live database.** The live database (`data/ope.db`, last modified 2026-02-24 14:22) does not have the Phase 17 schema applied. Tables `assessment_te_sessions` and `assessment_baselines` are absent. Columns `flame_events.assessment_session_id`, `memory_candidates.source_type`, `project_wisdom.ddf_target_level`, and `project_wisdom.scenario_seed` are absent. The schema migration is wired correctly (create_ddf_schema chains to create_assessment_schema), but the live DB predates the Phase 17 commits and has not had the migration run. This is a deployment gap: running the schema chain against the live DB would apply all changes idempotently.

**Partial — Scenario bank empty.** The scenario bank infrastructure is complete (annotation CLI, schema extensions, generator), but `project_wisdom` has 0 rows. Success Criterion #4 ("seeded from OPE project's own historical dead ends and breakthroughs") is structurally ready but not yet fulfilled.

---

*Verified: 2026-02-24T23:01:37Z*
*Verifier: Claude (gsd-verifier)*
