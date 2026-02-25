---
phase: 18-bridge-warden-structural-integrity
verified: 2026-02-25T02:54:14Z
status: passed
score: 6/6 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "Phase 17 assessment scenarios extended with structural integrity dimension: candidates assessed not just for CCD identification but for whether they ground abstractions, string load-bearing principles, and respect dependencies — and whether they notice when the AI's principles are floating cables"
  gaps_remaining: []
  regressions: []
human_verification: null
---

# Phase 18: Bridge-Warden Structural Integrity Detection — Verification Report

**Phase Goal:** Implement the Suspension Bridge dimension of the DDF — detecting not whether the human or AI is ascending to abstraction (Phase 15) but whether the knowledge structure being built is structurally sound. The human dimension measures structural reasoning quality. The AI dimension is the self-correction mechanism: floating cables detected in the AI's own reasoning become correction candidates in the `memory_candidates` pipeline, actively changing what the AI will assert in the next session — not just flagging the weakness but closing the loop on it. Together with Phases 15-16, this produces a three-dimensional picture: Ignition (upward) x Integrity (downward) x Transport (the mechanism connecting them).
**Verified:** 2026-02-25T02:54:14Z
**Status:** passed
**Re-verification:** Yes — after gap closure (18-05)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `structural_events` table records all four signal types per session with evidence, prompt_number, structural_role, and subject ('human' or 'ai') | VERIFIED | `src/pipeline/ddf/structural/schema.py` — DDL defines 14 columns with CHECK constraints on subject IN ('human','ai'), signal_type IN ('gravity_check','main_cable','dependency_sequencing','spiral_reinforcement'), op8_status. All four detectors populate all required fields. |
| 2 | AI structural detection: AI's own responses assessed for structural integrity; floating cables flagged as AI-level amnesia precursors | VERIFIED | `detectors.py` lines 163-223: `detect_main_cables()` reads `f.subject` from `flame_events` — AI flame events (subject='ai') produce structural events with `subject='ai'`. `op8.py` lines 51-62: filters `se.subject = 'ai'` for floating cable deposits to `memory_candidates`. |
| 3 | CTT Op-8 implemented: Main Cable detection triggers Op-8; AI principles failing Op-8 returned to MEMORY.md pipeline as correction candidates | VERIFIED | `op8.py` — `deposit_op8_corrections()` queries AI main_cable failures (signal_passed=False, subject='ai'), inserts to `memory_candidates` with source_type='op8_correction', status='pending', fidelity=2, confidence=0.60. SHA-256 dedup prevents duplicate deposits on re-run. Op-8 wired in runner Step 21 (`runner.py` line 916-920). |
| 4 | `StructuralIntegrityScore` computed per session for both human and AI — ratio of grounded abstractions, load-bearing principles, respected hierarchical sequences, spiral reinforcement events | VERIFIED | `computer.py` — locked formula: 0.30*gravity_ratio + 0.40*main_cable_ratio + 0.20*dependency_ratio + 0.10*spiral_capped. Neutral fallback (0.5) for empty denominators. `compute_structural_integrity_for_profile()` in `intelligence_profile.py` aggregates per-session then averages. Both `compute_intelligence_profile()` (human) and `compute_ai_profile()` (AI) call it. |
| 5 | Three-dimensional IntelligenceProfile: Ignition axis x Transport axis x Integrity axis — complete characterization | VERIFIED | `models.py` lines 168-169: IntelligenceProfile has `integrity_score: Optional[float]` and `structural_event_count: Optional[int]`. CLI `intelligence profile` calls `_display_te_metrics()` then `_display_structural_integrity()` (`intelligence.py` lines 92-96), producing all three dimensions in CLI output. `bridge_group` subcommand with stats/list/floating-cables wired at `intelligence.py` line 386. |
| 6 | Phase 17 assessment scenarios extended with structural integrity dimension: candidates assessed for grounding abstractions, stringing load-bearing principles, respecting dependencies, and noticing AI floating cables | VERIFIED | `src/pipeline/assessment/models.py` lines 152-154: AssessmentReport has `structural_integrity_score: Optional[float]`, `structural_event_count: int = 0`, `floating_cable_count: int = 0`. `reporter.py` lines 174-208: Step 9.5 queries `structural_events` via `compute_structural_integrity()`, counts AI floating cables. `deposit_report()` lines 549-551: scope_rule includes "Structural integrity:" and "Floating cables:". `scenario_generator.py` lines 290-295: `_build_handicap()` accepts optional `floating_cable_context` parameter and appends AI Analysis Notes section. `tests/test_assessment_structural.py`: 12 tests covering model defaults, reporter integration, markdown formatting, deposit text, handicap context, and end-to-end chain. |

**Score:** 6/6 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pipeline/ddf/structural/__init__.py` | Package init with exports | VERIFIED | 31 lines; exports StructuralEvent, StructuralIntegrityResult, detect_structural_signals, compute_structural_integrity, deposit_op8_corrections |
| `src/pipeline/ddf/structural/models.py` | Frozen Pydantic models with make_id | VERIFIED | 96 lines; StructuralEvent (14 fields, frozen=True, make_id SHA-256[:16]) and StructuralIntegrityResult (7 fields) |
| `src/pipeline/ddf/structural/schema.py` | DDL with CHECK constraints, indexes, create function | VERIFIED | 62 lines; 14-column DDL, 3 CHECK constraints, 3 indexes, idempotent create_structural_schema() |
| `src/pipeline/ddf/structural/writer.py` | Idempotent INSERT OR REPLACE writer | VERIFIED | 65 lines; write_structural_events() with INSERT OR REPLACE, returns int count |
| `src/pipeline/ddf/structural/detectors.py` | Four detectors + orchestrator | VERIFIED | 439 lines; detect_gravity_checks, detect_main_cables, detect_dependency_sequencing, detect_spiral_reinforcement, detect_structural_signals |
| `src/pipeline/ddf/structural/computer.py` | Weighted score formula | VERIFIED | 120 lines; compute_structural_integrity() with locked formula from DDFConfig weights |
| `src/pipeline/ddf/structural/op8.py` | Op-8 depositor for AI floating cables | VERIFIED | 114 lines; deposit_op8_corrections() with AI subject filter, SHA-256 dedup, memory_candidates insert |
| `src/pipeline/ddf/models.py` | IntelligenceProfile extended | VERIFIED | Lines 168-169: integrity_score: Optional[float], structural_event_count: Optional[int] added |
| `src/pipeline/models/config.py` | StructuralConfig under DDFConfig | VERIFIED | Line 223-245: StructuralConfig with gravity_window=3, weights summing to 1.0, nested under DDFConfig.structural |
| `src/pipeline/ddf/schema.py` | create_ddf_schema includes structural | VERIFIED | Lines 156-158: lazy import and call to create_structural_schema(conn) |
| `src/pipeline/storage/schema.py` | drop_schema drops structural_events | VERIFIED | Line 422: DROP TABLE IF EXISTS structural_events |
| `src/pipeline/runner.py` | Step 21 structural analysis | VERIFIED | Lines 906-941: Step 21 with lazy import, detect+write+op8, graceful fallback |
| `src/pipeline/ddf/intelligence_profile.py` | compute_structural_integrity_for_profile() | VERIFIED | Lines 138-215: per-session computation then average; integrated into both compute_intelligence_profile() (line 261) and compute_ai_profile() (line 316) |
| `src/pipeline/cli/intelligence.py` | bridge subgroup (stats/list/floating-cables) | VERIFIED | Line 386: @intelligence_group.group(name="bridge"); bridge_stats (line 392), bridge_list (line 501), bridge_floating_cables (line 600); _display_structural_integrity helper (line 1103) called in profile command |
| `tests/test_structural_schema.py` | 13 schema tests | VERIFIED | 251 lines; 13 tests |
| `tests/test_structural_detectors.py` | 26 detector/computer/op8 tests | VERIFIED | 522 lines; 26 tests |
| `tests/test_structural_integration.py` | 18 BRIDGE-01/02/03 integration tests | VERIFIED | 551 lines; 18 tests covering full chain flame_events -> detect -> write -> compute -> deposit |
| `tests/test_structural_profile.py` | 12 profile extension and CLI tests | VERIFIED | 399 lines; 12 tests |
| `src/pipeline/assessment/models.py` | AssessmentReport with 3 structural fields | VERIFIED | Lines 152-154: structural_integrity_score: Optional[float], structural_event_count: int = 0, floating_cable_count: int = 0 |
| `src/pipeline/assessment/reporter.py` | generate_report() queries structural_events; deposit includes structural data | VERIFIED | Lines 174-208: Step 9.5 — lazy import of compute_structural_integrity, query structural_events for assessment session, count AI floating cables. Lines 549-551: scope_rule contains "Structural integrity:" and "Floating cables:". Lines 556-558: flood_example contains "structural integrity". |
| `src/pipeline/assessment/scenario_generator.py` | _build_handicap() accepts floating_cable_context | VERIFIED | Lines 290-295: `floating_cable_context: str | None = None` parameter. Lines 334-339: when provided, appends AI Analysis Notes section to handicap markdown. |
| `tests/test_assessment_structural.py` | 12 tests for structural assessment integration | VERIFIED | 431 lines; 12 tests in 4 classes: TestAssessmentReportStructuralDefaults (3), TestReporterStructuralIntegration (5), TestScenarioGeneratorHandicap (2), TestStructuralAssessmentEndToEnd (2) |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `detectors.py` | `flame_events` (DuckDB) | SQL queries for L5+ events | VERIFIED | Four detectors each query flame_events READ-ONLY; subject field sourced from f.subject |
| `detectors.py` | `axis_edges` (DuckDB) | SQL queries for topology | VERIFIED | detect_main_cables and detect_dependency_sequencing check axis_edges; graceful fallback if table missing |
| `detectors.py` | `project_wisdom` (DuckDB) | metadata JSON LIKE search | VERIFIED | detect_spiral_reinforcement queries project_wisdom.metadata; graceful fallback if table missing |
| `writer.py` | `structural_events` (DuckDB) | INSERT OR REPLACE | VERIFIED | write_structural_events() writes StructuralEvent objects to structural_events table |
| `op8.py` | `structural_events` (DuckDB) | SQL query for AI main_cable failures | VERIFIED | Queries structural_events WHERE signal_type='main_cable' AND signal_passed=false AND subject='ai' |
| `op8.py` | `memory_candidates` (DuckDB) | INSERT OR REPLACE | VERIFIED | Deposits to memory_candidates with source_type='op8_correction', status='pending' |
| `runner.py Step 21` | `structural/detectors.py` | Lazy import + call | VERIFIED | Lines 910-926: imports detect_structural_signals, write_structural_events, deposit_op8_corrections; calls detect then write then deposit |
| `intelligence_profile.py` | `structural/computer.py` | Import inside try/except | VERIFIED | compute_structural_integrity_for_profile() lazy-imports compute_structural_integrity; called in both profile functions |
| `cli/intelligence.py` | `intelligence_profile.py` | _display_structural_integrity() call | VERIFIED | Lines 95-96: _display_structural_integrity(conn, human_id, show_ai) called after TE display |
| `assessment/reporter.py` | `structural_events` + `compute_structural_integrity` | Step 9.5 lazy import | VERIFIED | Lines 174-208: lazy import of compute_structural_integrity inside try/except; queries structural_events for AI floating cable count; graceful fallback on any exception |
| `assessment/reporter.py` | `memory_candidates` | deposit_report() scope_rule/flood_example text | VERIFIED | Lines 549-558: structural_integrity_score and floating_cable_count written into scope_rule and flood_example CCD text fields |
| `assessment/scenario_generator.py` | handicap markdown | floating_cable_context parameter | VERIFIED | Lines 334-339: floating_cable_context appended as AI Analysis Notes section when provided |

---

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| BRIDGE-01: StructuralEvent detection — human and AI | SATISFIED | All four signal types detected; subject field sourced from flame_events.subject; both human and AI events produced |
| BRIDGE-02: StructuralIntegrityScore | SATISFIED | compute_structural_integrity() computes locked formula per session for both subjects |
| BRIDGE-03: CTT Op-8 validation | SATISFIED | deposit_op8_corrections() fires on AI main_cable failures; deposits to memory_candidates as op8_correction |
| BRIDGE-04: Three-dimensional IntelligenceProfile | SATISFIED | IntelligenceProfile carries integrity_score; CLI profile shows Integrity row after TE; bridge subgroup exposes structural commands |
| Phase 17 Assessment Extension (Criterion 6) | SATISFIED | AssessmentReport carries structural_integrity_score/structural_event_count/floating_cable_count; reporter queries structural_events in generate_report() Step 9.5; deposit_report() embeds structural data in scope_rule and flood_example; scenario_generator._build_handicap() accepts floating_cable_context; 12 tests pass |

---

## Anti-Patterns Found

None. No TODOs, FIXMEs, placeholder patterns, empty return stubs, or orphaned artifacts detected across the verified files.

---

## Re-verification Summary

The single gap from the initial verification (Truth 6) is now closed. Plan 18-05 delivered:

1. `src/pipeline/assessment/models.py` — AssessmentReport gained three structural fields (`structural_integrity_score`, `structural_event_count`, `floating_cable_count`) at lines 152-154. All frozen, all have appropriate defaults.

2. `src/pipeline/assessment/reporter.py` — Step 9.5 (lines 174-208) added between rejection analysis and report construction. Uses lazy import of `compute_structural_integrity` inside try/except, matching the existing rejection_detector import pattern. Queries `structural_events` for AI floating cable count separately. `deposit_report()` embeds structural fields in the CCD text fields (`scope_rule` and `flood_example`).

3. `src/pipeline/assessment/scenario_generator.py` — `_build_handicap()` signature extended with `floating_cable_context: str | None = None`. When provided, appends an `### AI Analysis Notes` section, enabling L5-L7 scenarios that surface AI floating cables for candidate scrutiny.

4. `tests/test_assessment_structural.py` — 12 tests across four classes (model defaults, reporter integration, markdown formatting, deposit text inclusion, handicap parameter, end-to-end chain, and graceful fallback when `structural_events` table is absent).

The five truths verified in the initial verification show no regressions: all structural module files intact, IntelligenceProfile fields intact, runner Step 21 intact, CLI bridge subgroup intact, op8 deposit wiring intact.

---

_Verified: 2026-02-25T02:54:14Z_
_Verifier: Claude (gsd-verifier)_
