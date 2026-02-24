# Phase 18: Bridge-Warden Structural Integrity Detection - Research

**Researched:** 2026-02-24
**Domain:** DDF structural signal detection, DuckDB schema extension, pipeline step integration
**Confidence:** HIGH

## Summary

Phase 18 adds the third dimension (Integrity) to the IntelligenceProfile (Ignition x Transport x Integrity) by detecting whether knowledge structures are structurally sound -- i.e., whether high-level abstractions (L5+) have concrete grounding. This is orthogonal to Phase 15's upward abstraction detection. The implementation is a second-pass reader over existing `flame_events` and `ai_flame_events` tables, writing only to a new `structural_events` table and to `memory_candidates` via Op-8 correction deposits.

The architecture is well-constrained by locked decisions. Four signal detectors (Gravity Check, Main Cable, Dependency Sequencing, Spiral Reinforcement) operate as SQL pattern queries against `flame_events`. Op-8 (floating cable correction) deposits CCD-format entries to `memory_candidates`. The `StructuralIntegrityScore` is a weighted ratio formula consistent with the `TransportEfficiency` pattern from Phase 16. All mutations are additive -- zero writes to Phase 15-17 tables.

**Primary recommendation:** Follow the established Phase 15-17 pattern exactly: frozen Pydantic models, DuckDB DDL constants, idempotent ALTER TABLE extensions, INSERT OR REPLACE writers, and pipeline runner step integration with lazy imports and try/except ImportError guards.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Detection mechanism:** Second-pass flame_event pattern analysis. Phase 18 reads flame_events and ai_flame_events as read-only input; writes only to structural_events. No new NLP/text processing.

2. **Structural signal definitions (via flame_event patterns):**
   - Gravity Check = L5+ flame_event with co-occurring L0-L2 for same axis within +/-3 prompts. POSITIVE signal (signal_passed=True) when present; NEGATIVE (signal_passed=False) when absent.
   - Main Cable = L5+ flame_event with generalization_radius >= 2 (references same ccd_axis from 2+ distinct scope_prefixes)
   - Dependency Sequencing = L5+ concept introduction preceded only by L3+ on prerequisite axes (using axis_edges for prerequisite structure)
   - Spiral Reinforcement = cross-reference to existing project_wisdom promotion events from Phase 15 spiral tracker

3. **CTT Op-8:**
   - Post-response analysis only (non-blocking)
   - Trigger: ai_flame_events at marker_level >= 5 where (a) no co-occurring L0-L2 ai_flame_event for same ccd_axis within session AND (b) flood_confirmed = False
   - Both conditions must be true
   - Correction granularity: one candidate per floating axis per session
   - Correction format: CCD-format memory_candidates entry with source_type='op8_correction', fidelity=2, confidence=0.60

4. **StructuralIntegrityScore formula:**
   ```
   Score = 0.30 * gravity_ratio + 0.40 * main_cable_grounded_ratio + 0.20 * dependency_respected_ratio + 0.10 * spiral_count_capped
   ```
   - Empty denominators -> 0.5 neutral
   - Score = NULL when total L5+ flame_events == 0 for session+subject pair

5. **structural_events schema (separate table, additive):**
   ```sql
   CREATE TABLE structural_events (
       event_id VARCHAR PRIMARY KEY,
       session_id VARCHAR NOT NULL,
       assessment_session_id VARCHAR,
       prompt_number INTEGER NOT NULL,
       subject VARCHAR NOT NULL,
       signal_type VARCHAR NOT NULL,
       structural_role VARCHAR,
       evidence VARCHAR,
       signal_passed BOOLEAN NOT NULL,
       score_contribution FLOAT,
       contributing_flame_event_ids VARCHAR[],
       op8_status VARCHAR,
       op8_correction_candidate_id VARCHAR,
       created_at TIMESTAMPTZ DEFAULT now()
   );
   ```

6. **Op-8 correction format:** Reuse existing memory_candidates schema with source_type='op8_correction'. No new schema fields needed.

7. **Separation rule:** Phase 18 pipeline step (Step 21) is read-only on flame_events. Writes only structural_events + memory_candidates (via Op-8). Zero mutations to Phase 15 tables.

8. **3D IntelligenceProfile:** Add integrity_score: Optional[float] and structural_event_count: Optional[int] to existing IntelligenceProfile model. No archetype strings in v1.

9. **Wave structure:**
   - Wave 1: Plan 18-01 -- Schema + models + StructuralConfig
   - Wave 2a: Plan 18-02 -- Four signal detectors + StructuralIntegrityComputer + Op-8 + pipeline Step 21
   - Wave 2b: Plan 18-03 -- Integration tests for BRIDGE-01 through BRIDGE-04
   - Wave 3: Plan 18-04 -- 3D IntelligenceProfile extension + CLI bridge subcommand

### Claude's Discretion
- Internal code organization within each plan
- Test fixture design and helper function structure
- Exact SQL query structure for signal detection (within the locked signal definitions)
- StructuralConfig field names and defaults (must include gravity_window=3)

### Deferred Ideas (OUT OF SCOPE)
- Archetype strings ("The Dreamer", "The Technician")
- Materialized views for structural_events aggregation
- Separate lineage table
- Temporal decay in StructuralIntegrityScore
- Cross-session Op-8 checks (only within-session)
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.x | Schema DDL, query engine, data storage | Project-wide database; all Phase 15-17 tables live here |
| pydantic | 2.x | Frozen immutable models for StructuralEvent, StructuralConfig | Project pattern: all DDF models use frozen=True |
| hashlib | stdlib | SHA-256[:16] deterministic IDs | Project pattern: FlameEvent.make_id, EdgeRecord.make_id, TE _make_te_id |
| click | 8.x | CLI subcommand registration | Project pattern: intelligence_group.add_command() |
| loguru | latest | Structured logging | Project-wide logging standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.x | Test framework | All unit + integration tests |

### Alternatives Considered
None -- all locked decisions use existing project stack. No new dependencies.

**Installation:**
```bash
# No new packages needed -- all dependencies already in project
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/ddf/
    structural/                 # NEW: Phase 18 module
        __init__.py
        models.py              # StructuralEvent, StructuralConfig, StructuralIntegrityScore
        schema.py              # STRUCTURAL_EVENTS_DDL, create_structural_schema
        writer.py              # write_structural_events (INSERT OR REPLACE)
        detectors.py           # GravityCheck, MainCable, DependencySequencing, SpiralReinforcement
        computer.py            # StructuralIntegrityComputer (score formula)
        op8.py                 # Op8CorrectionDepositor
    intelligence_profile.py    # MODIFIED: add integrity_score + structural_event_count fields
    models.py                  # MODIFIED: IntelligenceProfile gets new Optional fields
src/pipeline/cli/
    intelligence.py            # MODIFIED: add bridge subgroup
tests/
    test_structural_schema.py  # Plan 18-01 tests
    test_structural_detectors.py  # Plan 18-02 tests
    test_structural_integration.py  # Plan 18-03 integration tests
    test_structural_profile.py  # Plan 18-04 tests
```

### Pattern 1: Schema Creation Chain
**What:** Each phase adds its DDL to the schema creation chain via function calls at the end of the parent schema creator.
**When to use:** Adding new tables that depend on prior phases existing.
**Example:**
```python
# In src/pipeline/ddf/schema.py -- add at end of create_ddf_schema():
def create_ddf_schema(conn: duckdb.DuckDBPyConnection) -> None:
    # ... existing Phase 15-17 schema creation ...

    # Phase 18: Structural Integrity tables
    from src.pipeline.ddf.structural.schema import create_structural_schema
    create_structural_schema(conn)
```
**Source:** Verified in `src/pipeline/ddf/schema.py` lines 140-153 -- existing pattern for topology, TE, and assessment schemas.

### Pattern 2: Frozen Pydantic Models with make_id()
**What:** All DDF data models use `frozen=True` with a `make_id()` classmethod for deterministic ID generation.
**When to use:** Any new model that will be persisted to DuckDB.
**Example:**
```python
class StructuralEvent(BaseModel, frozen=True):
    event_id: str
    session_id: str
    # ... fields ...

    @classmethod
    def make_id(cls, session_id: str, prompt_number: int, signal_type: str) -> str:
        key = f"{session_id}:{prompt_number}:{signal_type}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
```
**Source:** Verified in `src/pipeline/ddf/models.py` lines 28-88, `src/pipeline/ddf/topology/models.py` lines 43-111.

### Pattern 3: Pipeline Runner Step Integration
**What:** New pipeline steps are added to `runner.py` with lazy imports, try/except ImportError guards, and stats accumulation.
**When to use:** Adding Step 21 structural analysis.
**Example:**
```python
# Step 21: Structural integrity analysis (Phase 18)
ddf_structural_count = 0
ddf_op8_corrections = 0
try:
    from src.pipeline.ddf.structural.detectors import detect_structural_signals
    from src.pipeline.ddf.structural.op8 import deposit_op8_corrections
    from src.pipeline.ddf.structural.writer import write_structural_events as _write_structural

    structural_events = detect_structural_signals(self._conn, session_id)
    if structural_events:
        ddf_structural_count = _write_structural(self._conn, structural_events)

    ddf_op8_corrections = deposit_op8_corrections(self._conn, session_id)

    if ddf_structural_count > 0 or ddf_op8_corrections > 0:
        logger.info("Step 21: {} structural events, {} Op-8 corrections",
                     ddf_structural_count, ddf_op8_corrections)
except ImportError:
    pass
except Exception as e:
    logger.warning("Structural integrity analysis failed: {}", e)
    warnings.append(f"Structural integrity analysis failed: {e}")
```
**Source:** Verified in `src/pipeline/runner.py` lines 875-904 (Step 20 pattern).

### Pattern 4: INSERT OR REPLACE Idempotent Writers
**What:** All DDF writers use `INSERT OR REPLACE INTO` with deterministic IDs for idempotent pipeline re-runs.
**When to use:** `write_structural_events()` function.
**Example:**
```python
def write_structural_events(
    conn: duckdb.DuckDBPyConnection,
    events: list[StructuralEvent],
) -> int:
    if not events:
        return 0
    for e in events:
        conn.execute(
            "INSERT OR REPLACE INTO structural_events (...) VALUES (...)",
            [e.event_id, e.session_id, ...],
        )
    return len(events)
```
**Source:** Verified in `src/pipeline/ddf/writer.py` lines 17-70, `src/pipeline/ddf/transport_efficiency.py` lines 252-294.

### Pattern 5: Direct INSERT for Terminal Deposits
**What:** Phase 17 uses direct INSERT into memory_candidates (not `deposit_to_memory_candidates`) for terminal deposits where the source_type and fields differ from the standard DDF deposit path.
**When to use:** Op-8 correction deposits to memory_candidates with `source_type='op8_correction'`.
**Example:**
```python
conn.execute(
    """
    INSERT INTO memory_candidates (
        id, ccd_axis, scope_rule, flood_example, status,
        source_type, fidelity, confidence, subject, session_id,
        source_flame_event_id, detection_count
    ) VALUES (?, ?, ?, ?, 'pending', 'op8_correction', 2, 0.60, 'ai', ?, ?, 1)
    """,
    [candidate_id, ccd_axis, scope_rule, flood_example, session_id, source_flame_event_id],
)
```
**Source:** Verified from Plan 17-04 decision: "Direct INSERT into memory_candidates (not deposit_to_memory_candidates) for terminal deposit."

### Pattern 6: Assessment Session Filtering
**What:** All IntelligenceProfile queries include `assessment_session_id IS NULL` to exclude assessment data from production metrics.
**When to use:** Any query that computes structural integrity scores for production (non-assessment) sessions.
**Example:**
```sql
SELECT ... FROM flame_events
WHERE session_id = ? AND subject = ?
  AND (assessment_session_id IS NULL)
```
**Source:** Verified in `src/pipeline/ddf/intelligence_profile.py` lines 43-49, 94-100, 162.

### Anti-Patterns to Avoid
- **Mutating Phase 15 tables:** structural_events is additive-only. Never ALTER or UPDATE flame_events from Phase 18 code.
- **Re-detecting spirals:** Spiral Reinforcement records a cross-reference to existing `project_wisdom` promotion events, not a re-detection.
- **Using deposit_to_memory_candidates for Op-8:** The existing deposit function uses `pipeline_component` field and does soft dedup on (ccd_axis, scope_rule). Op-8 corrections need `source_type='op8_correction'` and have different dedup semantics (one per axis per session), so use direct INSERT.
- **Blocking pipeline on Op-8:** Op-8 runs post-response within the pipeline step. It reads flame_events, produces structural_events and memory_candidates entries. Never blocks or modifies the LLM response.
- **Forgetting assessment_session_id column:** structural_events needs this column (matching flame_events pattern from Phase 17) so assessment sessions can be filtered out of production structural integrity scores.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Deterministic IDs | Custom UUID generation | SHA-256[:16] via hashlib | Project-wide pattern; collision-resistant + deterministic |
| Schema creation chain | Manual DDL in runner.py | `create_structural_schema()` called from `create_ddf_schema()` | Idempotent chain ensures dependency ordering |
| Idempotent writes | Custom upsert logic | DuckDB `INSERT OR REPLACE INTO` | Built-in, tested pattern across Phase 15-17 |
| Scope prefix extraction | New parser | Reuse `_extract_scope_prefix()` from generalization.py | Already handles all edge cases |
| TE-style score computation | Ad hoc formula | Follow `compute_te_for_session()` pattern | Consistent style, tested approach |
| CLI subgroup registration | Manual argument parsing | `intelligence_group.add_command(bridge_group)` | Click group pattern from Phase 17 assess |

**Key insight:** Phase 18 introduces zero new infrastructure patterns. Every component follows an established Phase 15-17 template. The research confirms that the planner should specify which existing template to follow for each new component, not invent new approaches.

## Common Pitfalls

### Pitfall 1: VARCHAR[] Array Insert Syntax in DuckDB
**What goes wrong:** Python lists need to be passed correctly to DuckDB for VARCHAR[] columns.
**Why it happens:** DuckDB accepts Python lists directly in parameterized queries for array types, but some developers try to JSON-serialize them first.
**How to avoid:** Pass Python `list[str]` directly as parameter value: `conn.execute("INSERT INTO t (ids) VALUES (?)", [["a","b"]])`. Verified working with DuckDB 1.x.
**Warning signs:** JSON string `'["a","b"]'` stored instead of native array `['a','b']`.

### Pitfall 2: Step Numbering Collision with Stats Step
**What goes wrong:** The current Step 21 is "Compute stats" (the final step). Phase 18 adds Step 21 as structural analysis, but stats must remain the last step.
**Why it happens:** Runner.py currently labels the stats computation as "Step 21" in the code comments. Adding Phase 18's Step 21 between Step 20 (TE) and the stats step requires renumbering.
**How to avoid:** Insert Phase 18 structural analysis as new Step 21. Shift stats computation to Step 22 (or simply keep it unlabeled as the final block -- it's already just the return-value assembly at lines 907-957). The stats block does not have a step number in the code; it's just the final section. So Phase 18 inserts Step 21 between the TE try/except block (ending ~line 904) and the stats computation (starting ~line 907).
**Warning signs:** Step 21 structural analysis running AFTER stats computation.

### Pitfall 3: Gravity Check axis Matching Logic
**What goes wrong:** The Gravity Check requires matching `ccd_axis` between L5+ and L0-L2 flame_events, but `ccd_axis` is a Phase 17 ALTER TABLE column while the original `axis_identified` has been the axis field since Phase 15.
**Why it happens:** Phase 17 added `ccd_axis` to flame_events via ALTER TABLE, but earlier flame_events use `axis_identified`. The gravity check must match on EITHER field.
**How to avoid:** Use `COALESCE(ccd_axis, axis_identified)` in the SQL query for axis matching. Both fields may contain axis names; the Gravity Check should match if either field identifies the same axis.
**Warning signs:** Gravity Check always returns signal_passed=False because it only checks one axis field.

### Pitfall 4: Op-8 Dedup on Same Axis in Same Session
**What goes wrong:** If the same floating axis appears in multiple L5+ flame_events in a session, Op-8 should produce ONE correction candidate with an appropriate detection_count, not multiple candidates.
**Why it happens:** Naive iteration over all floating flame_events produces duplicate candidates per axis.
**How to avoid:** Group floating flame_events by axis before depositing. Use a dict keyed by axis name; count occurrences for detection_count. The make_id for the correction candidate should include session_id + axis to ensure deterministic dedup.
**Warning signs:** Multiple Op-8 corrections for the same axis in the same session in memory_candidates.

### Pitfall 5: drop_schema Dependency Order
**What goes wrong:** Adding `structural_events` to the schema means it must also be dropped before `flame_events` in `drop_schema()` to avoid FK-like dependency issues (even though DuckDB doesn't enforce FKs, the test fixture `drop_schema` should be comprehensive).
**Why it happens:** Phase 16.1 already had this issue with `axis_edges` -- it must be dropped before `ai_flame_events` view is dropped.
**How to avoid:** Add `conn.execute("DROP TABLE IF EXISTS structural_events")` to `drop_schema()` in `storage/schema.py` BEFORE the existing flame_events drop. Same position as axis_edges.
**Warning signs:** Tests fail during cleanup with "table structural_events still exists" errors.

### Pitfall 6: Empty axis_edges Table for Dependency Sequencing
**What goes wrong:** Dependency Sequencing relies on `axis_edges` to define prerequisite structure. If no edges exist (common in early pipeline runs), the detector must handle this gracefully.
**Why it happens:** axis_edges is populated by Phase 16.1 topology generation, which requires sufficient flame_event data. Early sessions may have no edges.
**How to avoid:** When axis_edges has no relevant edges for a given axis, Dependency Sequencing should emit signal_passed=True (no violations detectable) or skip entirely. Document this behavior. The score formula already handles empty denominators with the 0.5 neutral fallback.
**Warning signs:** Dependency Sequencing always reports failures when no axis_edges exist.

### Pitfall 7: IntelligenceProfile Model Backward Compatibility
**What goes wrong:** Adding `integrity_score` and `structural_event_count` to the frozen IntelligenceProfile model breaks existing code that constructs it without these fields.
**Why it happens:** Frozen Pydantic models reject unexpected constructor arguments, but Optional fields with defaults work fine.
**How to avoid:** Use `Optional[float] = None` and `Optional[int] = None` defaults. All existing callers (`compute_intelligence_profile`, `compute_ai_profile`) continue to work because they don't pass these new fields. Phase 18 will populate them in a separate computation step.
**Warning signs:** `ValidationError: extra fields not permitted` when constructing IntelligenceProfile without the new fields.

## Code Examples

Verified patterns from the existing codebase:

### Schema DDL Constant Pattern
```python
# Source: src/pipeline/ddf/transport_efficiency.py lines 41-57
STRUCTURAL_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS structural_events (
    event_id                     VARCHAR PRIMARY KEY,
    session_id                   VARCHAR NOT NULL,
    assessment_session_id        VARCHAR,
    prompt_number                INTEGER NOT NULL,
    subject                      VARCHAR NOT NULL CHECK (subject IN ('human', 'ai')),
    signal_type                  VARCHAR NOT NULL
                                 CHECK (signal_type IN ('gravity_check', 'main_cable',
                                        'dependency_sequencing', 'spiral_reinforcement')),
    structural_role              VARCHAR,
    evidence                     VARCHAR,
    signal_passed                BOOLEAN NOT NULL,
    score_contribution           FLOAT,
    contributing_flame_event_ids VARCHAR[],
    op8_status                   VARCHAR CHECK (op8_status IN ('pass', 'fail', 'na') OR op8_status IS NULL),
    op8_correction_candidate_id  VARCHAR,
    created_at                   TIMESTAMPTZ DEFAULT NOW()
)
"""

STRUCTURAL_EVENTS_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_structural_session ON structural_events(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_structural_signal ON structural_events(signal_type)",
    "CREATE INDEX IF NOT EXISTS idx_structural_subject ON structural_events(subject)",
]
```

### Gravity Check SQL Query Pattern
```python
# Gravity Check: find L5+ events with or without co-occurring L0-L2 for same axis
# Uses COALESCE to match on either ccd_axis or axis_identified
gravity_check_sql = """
SELECT
    fe_high.flame_event_id,
    fe_high.session_id,
    fe_high.prompt_number,
    fe_high.subject,
    COALESCE(fe_high.ccd_axis, fe_high.axis_identified) AS axis,
    CASE WHEN COUNT(fe_low.flame_event_id) > 0 THEN TRUE ELSE FALSE END AS signal_passed,
    LIST(fe_low.flame_event_id) AS grounding_ids
FROM flame_events fe_high
LEFT JOIN flame_events fe_low
    ON fe_low.session_id = fe_high.session_id
    AND fe_low.subject = fe_high.subject
    AND fe_low.marker_level BETWEEN 0 AND 2
    AND COALESCE(fe_low.ccd_axis, fe_low.axis_identified) = COALESCE(fe_high.ccd_axis, fe_high.axis_identified)
    AND ABS(fe_low.prompt_number - fe_high.prompt_number) <= ?  -- gravity_window
    AND (fe_low.assessment_session_id IS NULL)
WHERE fe_high.session_id = ?
    AND fe_high.subject = ?
    AND fe_high.marker_level >= 5
    AND COALESCE(fe_high.ccd_axis, fe_high.axis_identified) IS NOT NULL
    AND (fe_high.assessment_session_id IS NULL)
GROUP BY fe_high.flame_event_id, fe_high.session_id, fe_high.prompt_number,
         fe_high.subject, COALESCE(fe_high.ccd_axis, fe_high.axis_identified)
"""
```

### StructuralIntegrityScore Computation Pattern
```python
# Source: follows compute_te_for_session pattern from transport_efficiency.py
def compute_structural_integrity(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    subject: str,
) -> dict | None:
    # Check if any L5+ events exist
    l5_count_row = conn.execute(
        "SELECT COUNT(*) FROM flame_events "
        "WHERE session_id = ? AND subject = ? AND marker_level >= 5 "
        "AND (assessment_session_id IS NULL)",
        [session_id, subject],
    ).fetchone()

    l5_count = l5_count_row[0] if l5_count_row else 0
    if l5_count == 0:
        return None  # NULL score when no L5+ events

    # Compute ratios (0.5 neutral for empty denominators)
    gravity_ratio = _compute_gravity_ratio(conn, session_id, subject)
    main_cable_ratio = _compute_main_cable_ratio(conn, session_id, subject)
    dependency_ratio = _compute_dependency_ratio(conn, session_id, subject)
    spiral_count_capped = _compute_spiral_capped(conn, session_id, subject)

    score = (
        0.30 * gravity_ratio +
        0.40 * main_cable_ratio +
        0.20 * dependency_ratio +
        0.10 * spiral_count_capped
    )

    return {
        "session_id": session_id,
        "subject": subject,
        "integrity_score": score,
        "gravity_ratio": gravity_ratio,
        "main_cable_ratio": main_cable_ratio,
        "dependency_ratio": dependency_ratio,
        "spiral_capped": spiral_count_capped,
    }
```

### Op-8 Correction Deposit Pattern
```python
# Source: follows Phase 17 direct INSERT pattern (Plan 17-04)
def deposit_op8_correction(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    ccd_axis: str,
    scope_rule: str,
    flood_example: str,
    source_flame_event_id: str,
    detection_count: int = 1,
) -> str:
    candidate_id = hashlib.sha256(
        f"op8:{session_id}:{ccd_axis}".encode()
    ).hexdigest()[:16]

    conn.execute(
        """
        INSERT OR REPLACE INTO memory_candidates (
            id, ccd_axis, scope_rule, flood_example, status,
            source_type, fidelity, confidence, subject, session_id,
            source_flame_event_id, detection_count, pipeline_component
        ) VALUES (?, ?, ?, ?, 'pending', 'op8_correction', 2, 0.60,
                  'ai', ?, ?, ?, 'op8_structural')
        """,
        [candidate_id, ccd_axis, scope_rule, flood_example,
         session_id, source_flame_event_id, detection_count],
    )
    return candidate_id
```

### Schema Chain Integration
```python
# Source: verified pattern from src/pipeline/ddf/schema.py lines 140-153
# In create_ddf_schema(), add after create_assessment_schema():

    # Phase 18: Structural Integrity tables
    from src.pipeline.ddf.structural.schema import create_structural_schema
    create_structural_schema(conn)
```

### drop_schema Update
```python
# Source: src/pipeline/storage/schema.py lines 413-439
# Add at the top of drop_schema(), before axis_edges:
    conn.execute("DROP TABLE IF EXISTS structural_events")
    conn.execute("DROP TABLE IF EXISTS axis_edges")  # existing
    conn.execute("DROP VIEW IF EXISTS ai_flame_events")  # existing
    # ... rest of drops
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-dimension profile (Ignition only) | Two-dimension (Ignition + Transport) | Phase 16 | IntelligenceProfile has flame metrics + TE |
| No structural grounding check | Four-signal structural analysis | Phase 18 (now) | Third dimension added to profile |
| No AI self-correction mechanism | Op-8 floating cable deposits | Phase 18 (now) | AI reasoning gaps become correction candidates |
| axis_identified only | ccd_axis + axis_identified (Phase 17) | Phase 17 | Both fields must be checked for axis matching |

**Deprecated/outdated:**
- None in the Phase 18 domain. All infrastructure is current as of Phase 17 completion.

## Open Questions

1. **Main Cable generalization_radius computation**
   - What we know: Main Cable requires generalization_radius >= 2, meaning the axis appears in 2+ distinct scope_prefixes. The existing `compute_generalization_radius()` in generalization.py operates on `session_constraint_eval`, not on `flame_events`.
   - What's unclear: For Main Cable, we need to compute generalization_radius from flame_events (not constraint_eval). This is COUNT(DISTINCT scope_prefix) from the evidence_excerpt or evidence_json of flame_events for a given ccd_axis.
   - Recommendation: Implement a per-session scope_prefix count on flame_events. If a session has flame_events for the same axis from 2+ distinct scope_path prefixes (derived from evidence_excerpt or source_episode_id episode scope paths), the Main Cable signal passes. Alternatively, simply check if the axis appears in `axis_edges` (which implies cross-domain connectivity).

2. **prompt_number availability on flame_events**
   - What we know: Gravity Check uses `prompt_number` for the +/-3 window. The flame_events table has `prompt_number INTEGER` as a nullable field.
   - What's unclear: Are prompt_numbers reliably populated for all flame_events? Tier 1 markers use sequential assignment (`o_axs_count`), but Tier 2 enrichment may not set them.
   - Recommendation: Use `COALESCE(prompt_number, 0)` in queries. If prompt_number is NULL for a flame_event, gravity check against it with window-based matching falls back to matching any event in the session (effectively a wider window). Document this fallback.

3. **Structural Config location in PipelineConfig**
   - What we know: Phase 15 added `DDFConfig` to `PipelineConfig`. Phase 18 needs configurable parameters (gravity_window=3, weights, etc.).
   - What's unclear: Whether to add a `StructuralConfig` as a sub-model of `DDFConfig` or as a top-level config section.
   - Recommendation: Add `structural: StructuralConfig = Field(default_factory=StructuralConfig)` to `DDFConfig`, consistent with how `o_axs: OAxsConfig` is nested under `DDFConfig`.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/ddf/schema.py` -- schema creation chain, DDL constants, idempotent ALTER TABLE
- `src/pipeline/ddf/models.py` -- FlameEvent frozen model, make_id pattern
- `src/pipeline/ddf/writer.py` -- INSERT OR REPLACE writer pattern
- `src/pipeline/ddf/deposit.py` -- memory_candidates deposit with soft dedup
- `src/pipeline/ddf/transport_efficiency.py` -- TE schema, computation engine, backfill pattern
- `src/pipeline/ddf/intelligence_profile.py` -- IntelligenceProfile aggregation, assessment_session_id filtering
- `src/pipeline/ddf/generalization.py` -- GeneralizationRadius, scope_prefix extraction
- `src/pipeline/ddf/spiral.py` -- spiral detection, project_wisdom promotion
- `src/pipeline/ddf/topology/models.py` -- EdgeRecord model, axis_edges structure
- `src/pipeline/ddf/topology/schema.py` -- axis_edges DDL, create_topology_schema
- `src/pipeline/runner.py` -- pipeline step integration, lazy imports, try/except guards
- `src/pipeline/storage/schema.py` -- create_schema chain, drop_schema dependency order
- `src/pipeline/assessment/schema.py` -- ASSESSMENT_ALTER_EXTENSIONS, ai_flame_events view refresh
- `src/pipeline/models/config.py` -- PipelineConfig, DDFConfig, OAxsConfig nesting
- `src/pipeline/cli/intelligence.py` -- CLI subgroup pattern, add_command registration
- `src/pipeline/review/schema.py` -- memory_candidates base DDL, CCD format constraints

### Secondary (MEDIUM confidence)
- DuckDB VARCHAR[] array type -- verified via Python 3 interactive test (parameterized insert works)
- CONTEXT.md locked decisions -- user-confirmed architectural constraints
- CLARIFICATIONS-ANSWERED.md -- YOLO-mode decisions with provider synthesis

### Tertiary (LOW confidence)
- None. All findings verified against source code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, zero new dependencies
- Architecture: HIGH -- every pattern has a verified template in Phase 15-17 code
- Pitfalls: HIGH -- identified from actual codebase analysis (axis field duality, drop_schema ordering, prompt_number nullability)
- Signal definitions: HIGH -- locked in CONTEXT.md with SQL-level precision
- Op-8 logic: HIGH -- locked with both conditions specified

**Research date:** 2026-02-24
**Valid until:** Indefinite (internal codebase patterns, not external API dependencies)
