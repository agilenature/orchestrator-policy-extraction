# Phase 17: Candidate Assessment System - Research

**Researched:** 2026-02-24
**Domain:** Assessment orchestration, Claude Code programmatic launch, DuckDB schema extension, TE computation, scenario generation
**Confidence:** HIGH (codebase investigation) / MEDIUM (Claude Code launch mechanics)

## Summary

Phase 17 builds a complete assessment system on top of the DDF Detection Substrate (Phase 15), TransportEfficiency (Phase 16), and the PAG hook (Phase 14). The system has four structural layers: (1) scenario generation from project_wisdom, (2) Actor session launch in an isolated filesystem environment, (3) Observer post-session analysis via the existing extract pipeline, and (4) Assessment Report deposit to memory_candidates. All seven gray-area decisions are locked.

The critical spike question is Claude Code session launch mechanics. Research confirms there is **no `--project-dir` flag** in Claude Code. The project directory is determined from CWD at launch time. The launch mechanism is therefore: `cd /tmp/ope_assess_{session_id}/ && unset CLAUDECODE && claude -p "..."` (or interactive `claude` without `-p`). JSONL transcripts are stored at `~/.claude/projects/{escaped-cwd-path}/{session-uuid}.jsonl`, where the escaped path replaces `/` with `-`. For CWD `/tmp/ope_assess_abc123`, transcripts go to `~/.claude/projects/-tmp-ope_assess_abc123/`.

The assessment TE formula drops `transport_speed` from the production formula, computing `raven_depth * crow_efficiency * trunk_quality` (3 sub-metrics). This requires a new `compute_assessment_te_for_session()` function or a parameter flag on the existing `compute_te_for_session()`. The existing TE computation reads directly from `flame_events` using SQL aggregation, so the assessment variant must either write flame_events from the Observer first, or compute from a result set directly.

**Primary recommendation:** Build in 4 waves: (1) schema + models, (2) scenario generator + annotation CLI, (3) session runner + observer integration, (4) report generator + assessment TE + deposit. Wave 3 depends on resolving the Claude Code launch spike in Wave 1.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Q1: Scenario Materialization - Seed-Based Synthesis**
- Two files per scenario: scenario_context.md (briefing) + minimal broken implementation file
- For L5-L7: Actor's CLAUDE.md pre-seeded with wrong framing candidate must reject
- project_wisdom gets new columns: scenario_seed TEXT, ddf_target_level INTEGER

**Q2: Actor-Observer Architecture - Strict Process Isolation**
- Actor: Claude Code instance with custom assessment CLAUDE.md (handicap framing)
- Observer: OPE extract pipeline running post-session against Actor's JSONL transcript
- ai_flame_events generated from transcript analysis by Observer (NOT live Actor state)
- Actor does NOT know it's in an assessment
- Handicap encoding: custom CLAUDE.md written to assessment working directory

**Q3: Session Isolation - Filesystem-Level (MVP)**
- /tmp/ope_assess_{session_id}/ as isolated working directory
- Claude Code launched with project dir set to assessment path
- PAG hook (Phase 14) blocks dangerous commands outside assessment dir
- Session cleanup: tar + store path in assessment_te_sessions -> rm -rf
- Assessment CLAUDE.md/MEMORY.md pre-seeded with current production IntelligenceProfile

**Q4: Memory Deposit Contamination - source_type column**
- Add source_type VARCHAR CHECK IN ('production', 'assessment', 'simulation_review') to memory_candidates
- ai_flame_events extended with assessment_session_id VARCHAR (nullable)
- IntelligenceProfile excludes source_type='assessment' by default
- Assessment Report is terminal deposit: source_type='simulation_review', fidelity=3
- simulation_review goes through standard MEMORY.md review CLI (Phase 16)
- Initial confidence: 0.85

**Q5: Level 5-7 Rejection Detection - Outcome-Gated**
- Rejection = Level 5 ONLY IF candidate_te > scenario_baseline_te * 0.9
- Rejection + candidate_te < threshold -> stubbornness_indicator=True
- Fringe-signal rejections bypass outcome gate (count as L5 pre_naming immediately)
- transport_speed excluded from assessment TE formula
- Assessment TE = raven_depth * crow_efficiency * trunk_quality (3 sub-metrics)

**Q6: TE Normalization - Within-Scenario Ratio**
- candidate_ratio = candidate_te / scenario_baseline_te
- Write to assessment_te_sessions (NOT transport_efficiency_sessions)
- assessment_baselines table: mean/stddev of ratio per scenario_id (N>=10 for percentile)
- When N<10: report ratio only, flag baseline_pending=True

**Q7: Scenario DDF-Level Annotation - CLI Annotation + Auto-Calibration**
- Add scenario_seed TEXT and ddf_target_level INTEGER to project_wisdom
- CLI: python -m src.pipeline.cli intelligence assess annotate-scenarios
- ddf_target_level is INTEGER (single level, not range)
- Auto-calibration is a proposal to memory_candidates for human review (does NOT auto-update)

### Claude's Discretion
- Internal module organization within src/pipeline/assessment/
- Specific heuristics for rejection detection (tool call divergence patterns)
- Assessment Report markdown rendering format
- Test structure and test fixture organization
- Scenario validation smoke test implementation details

### Deferred Ideas (OUT OF SCOPE)
- Docker/Firecracker container isolation (upgrade path, not MVP)
- Multi-concurrent-session assessment (single-session MVP)
- Adaptive scenario generation based on candidate's in-session performance
- Real-time Observer (post-session batch only for MVP)
- assessment_intelligence_profile as a separate DuckDB table (use view + filter)
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| duckdb | 1.2.x | Schema, queries, all persistence | Already used project-wide; single-writer model |
| pydantic | 2.x | Frozen data models | All DDF/Phase 15-16 models use frozen=True |
| click | 8.x | CLI subcommands under `intelligence assess` | All existing CLI uses Click groups |
| subprocess | stdlib | Launch Claude Code actor sessions | Process isolation for actor-observer |
| pathlib | stdlib | Filesystem path management | Used throughout project |
| hashlib | stdlib | Deterministic ID generation (sha256[:16]) | Consistent with all existing ID patterns |
| tarfile | stdlib | Session artifact archival | Session cleanup: tar before rm |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| loguru | 0.7.x | Structured logging | All CLI/pipeline modules use loguru |
| json | stdlib | JSONL parsing, metadata serialization | Observer reads JSONL transcripts |
| shutil | stdlib | Directory operations | Assessment dir creation/cleanup |
| tempfile | stdlib | Temp directory management | Assessment isolation base path |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| subprocess for Claude launch | pexpect | More control but unnecessary complexity for -p mode |
| tarfile for archival | shutil.make_archive | tarfile gives more control over compression level |
| Single compute function with flag | Separate assessment_te function | Separate function is cleaner; avoids flag pollution of production code |

**Installation:**
No new dependencies needed. All libraries are already in the project's dependency set.

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/assessment/
    __init__.py
    models.py              # AssessmentSession, ScenarioSpec, AssessmentReport (Pydantic frozen)
    schema.py              # assessment_te_sessions DDL, assessment_baselines DDL, ALTER TABLE extensions
    scenario_generator.py  # Builds scenario files from project_wisdom entries
    session_runner.py      # Launches Actor Claude Code session, manages lifecycle
    observer.py            # Post-session JSONL analysis via existing extract pipeline
    reporter.py            # Generates Assessment Report, deposits to memory_candidates
    te_assessment.py       # Assessment-specific TE computation (3-metric formula)
    rejection_detector.py  # Outcome-gated L5-7 rejection detection
src/pipeline/cli/assess.py # Click group: annotate-scenarios, run, report, calibrate
```

### Pattern 1: Schema Extension via ALTER TABLE (idempotent)
**What:** Add columns to existing tables using try/except wrapped ALTER TABLE
**When to use:** Extending memory_candidates, flame_events, project_wisdom
**Example:**
```python
# Source: src/pipeline/ddf/transport_efficiency.py lines 104-120
# and src/pipeline/ddf/schema.py lines 131-138

ASSESSMENT_EXTENSIONS: list[tuple[str, str]] = [
    ("source_type", "VARCHAR DEFAULT 'production'"),
    ("assessment_session_id", "VARCHAR"),
]

def create_assessment_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create assessment tables and extend existing tables (idempotent)."""
    # New table
    conn.execute(ASSESSMENT_TE_SESSIONS_DDL)
    conn.execute(ASSESSMENT_BASELINES_DDL)
    # Extend existing tables
    for col_name, col_def in ASSESSMENT_EXTENSIONS:
        try:
            conn.execute(f"ALTER TABLE memory_candidates ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # Column already exists
```

### Pattern 2: Click Group Nesting (3-level hierarchy)
**What:** `intelligence assess <subcommand>` as a nested Click group
**When to use:** All Phase 17 CLI commands
**Example:**
```python
# Source: src/pipeline/cli/intelligence.py lines 30-33, 163-166

@intelligence_group.group(name="assess")
def assess_group():
    """Assessment system commands."""
    pass

@assess_group.command(name="run")
@click.argument("scenario_id")
@click.argument("candidate_id")
@click.option("--db", default="data/ope.db")
def assess_run(scenario_id: str, candidate_id: str, db: str) -> None:
    """Launch an assessment session."""
    ...
```

### Pattern 3: Deterministic ID Generation
**What:** SHA-256[:16] of composite key for all new entity IDs
**When to use:** assessment_te_sessions.te_id, scenario IDs, report IDs
**Example:**
```python
# Source: src/pipeline/ddf/transport_efficiency.py lines 128-134

def _make_assessment_te_id(session_id: str, candidate_id: str) -> str:
    raw = f"assess:{session_id}:{candidate_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

### Pattern 4: Frozen Pydantic Models for Data Transfer
**What:** All data models are Pydantic v2 with frozen=True
**When to use:** ScenarioSpec, AssessmentSession, AssessmentReport
**Example:**
```python
# Source: src/pipeline/ddf/models.py pattern

class AssessmentSession(BaseModel, frozen=True):
    session_id: str
    scenario_id: str
    candidate_id: str
    assessment_dir: str
    actor_session_uuid: str | None = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### Anti-Patterns to Avoid
- **Writing assessment flame_events to production IntelligenceProfile:** All assessment flame_events must have assessment_session_id set; IntelligenceProfile query must exclude them by default.
- **Computing TE with 4 metrics for assessment:** Assessment TE drops transport_speed; never multiply by transport_speed in assessment context.
- **Launching Claude Code from inside a Claude Code session:** The CLAUDECODE environment variable must be unset. Error message confirmed: "Claude Code cannot be launched inside another Claude Code session."
- **Assuming --project-dir exists:** It does not. Use `cd` to set CWD before launching claude.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSONL transcript parsing | Custom JSONL parser | Existing extract pipeline (`PipelineRunner.run_session()`) | Already handles all message types, event normalization, tagging, segmentation |
| Flame event detection | Custom assessment-specific detectors | Existing Tier1 + Tier2 extractors | FlameEventExtractor.detect_ai_markers() and enrich_tier1() already produce L2-L6 events |
| Memory candidate deposit | Custom INSERT logic | `deposit_to_memory_candidates()` from `src/pipeline/ddf/deposit.py` | Handles dedup, detection_count increment, ID generation |
| TE sub-metric computation (raven_depth, crow_efficiency) | Custom SQL | Reuse SQL from `compute_te_for_session()` | Sub-metric formulas are already implemented and tested |
| MEMORY.md review workflow | New review pathway | Existing `intelligence memory-review` CLI (Phase 16) | Locked decision: simulation_review entries go through same review pipeline |
| Session JSONL location resolution | Hardcoded path construction | Derive from CWD: `~/.claude/projects/{cwd.replace('/', '-')}/` | This is Claude Code's actual storage convention |

**Key insight:** Phase 17 is an orchestration layer over Phases 14-16 infrastructure. Most individual operations (flame detection, TE computation, memory deposit, JSONL parsing) already exist. Phase 17 composes them into an assessment workflow.

## Common Pitfalls

### Pitfall 1: CLAUDECODE Environment Variable Blocks Nested Launch
**What goes wrong:** Attempting to launch `claude` from within a Claude Code session fails with "Claude Code cannot be launched inside another Claude Code session."
**Why it happens:** Claude Code sets `CLAUDECODE=1` in its process environment. Child processes inherit this.
**How to avoid:** Explicitly `unset CLAUDECODE` (or `env -u CLAUDECODE claude ...`) before launching the Actor subprocess.
**Warning signs:** subprocess returns immediately with exit code 1 and the nested session error message.

### Pitfall 2: Assessment Flame Events Contaminating Production IntelligenceProfile
**What goes wrong:** Assessment sessions produce genuine flame_events (the Actor's handicapped reasoning generates real L2-L3 events). If these flow into the production IntelligenceProfile, the AI's profile degrades.
**Why it happens:** flame_events table has no source_type column; IntelligenceProfile queries aggregate all rows.
**How to avoid:** Add `assessment_session_id` column to flame_events. IntelligenceProfile SQL must add `WHERE assessment_session_id IS NULL` (or equivalent filter). The locked decision specifies this column on the base flame_events table.
**Warning signs:** IntelligenceProfile avg_marker_level dropping after assessment sessions run.

### Pitfall 3: JSONL Session Path Resolution Failure
**What goes wrong:** After launching Claude Code in `/tmp/ope_assess_abc123/`, the Observer cannot find the JSONL transcript because it looks in the wrong directory.
**Why it happens:** Claude Code computes the project path from CWD at startup. The JSONL goes to `~/.claude/projects/-tmp-ope_assess_abc123/{session-uuid}.jsonl`. The session UUID is generated by Claude Code and is not known before launch.
**How to avoid:** After the Actor session completes, glob for `~/.claude/projects/{escaped_assessment_dir}/*.jsonl` and find the most recent file by modification time. Or capture the session UUID from Claude Code's stdout/stderr if available. The `--session-id <uuid>` flag can be used to specify a known UUID before launch.
**Warning signs:** Observer reports "no JSONL file found" for the assessment session.

### Pitfall 4: Assessment TE Using 4-Metric Formula Instead of 3-Metric
**What goes wrong:** Assessment TE includes transport_speed, producing incomparable scores with nonsensical values for short scenarios.
**Why it happens:** Copy-pasting from `compute_te_for_session()` which uses the 4-metric formula.
**How to avoid:** Create a separate `compute_assessment_te()` function that computes `raven_depth * crow_efficiency * trunk_quality` (3 metrics). Never call `compute_te_for_session()` for assessment data.
**Warning signs:** Assessment TE scores are orders of magnitude different from production scores.

### Pitfall 5: project_wisdom ALTER TABLE Failing Silently
**What goes wrong:** `scenario_seed` and `ddf_target_level` columns don't appear after schema migration.
**Why it happens:** `project_wisdom` is created in both `create_schema()` (storage/schema.py) and `WisdomStore._ensure_schema()`. The ALTER TABLE may run against a different connection or fail silently.
**How to avoid:** Add Phase 17 ALTER TABLE extensions in `create_assessment_schema()`, called from the main `create_schema()` chain. Use the same try/except pattern.
**Warning signs:** annotate-scenarios CLI crashes with "Unknown column scenario_seed".

### Pitfall 6: Race Condition on assessment_baselines Population
**What goes wrong:** Two concurrent assessment reports try to update assessment_baselines for the same scenario_id, producing incorrect mean/stddev.
**Why it happens:** DuckDB single-writer model prevents concurrent writes, but if the read-then-write is not atomic, stale reads produce wrong aggregates.
**How to avoid:** MVP is single-session (locked decision: no multi-concurrent-session). For MVP, this is not a concern. For future: use DuckDB transactions with INSERT OR REPLACE computing aggregates in a single statement.
**Warning signs:** N/A for MVP (deferred to Docker upgrade path).

## Code Examples

### Assessment TE Computation (3-Metric Formula)
```python
# Derived from: src/pipeline/ddf/transport_efficiency.py lines 179-249
# Modified: drops transport_speed from composite calculation

def compute_assessment_te(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
) -> list[dict]:
    """Compute Assessment TE (3-metric: raven_depth * crow_efficiency * trunk_quality).

    Differs from production TE: transport_speed excluded (scenarios too small).
    """
    rows = conn.execute(
        """
        SELECT
            session_id,
            subject,
            human_id,
            MAX(marker_level) / 7.0 AS raven_depth,
            CAST(COUNT(*) FILTER (WHERE axis_identified IS NOT NULL) AS FLOAT)
                / NULLIF(COUNT(*), 0) AS crow_efficiency,
            0.5 AS trunk_quality,
            'pending' AS trunk_quality_status
        FROM flame_events
        WHERE session_id = ?
          AND assessment_session_id IS NOT NULL
        GROUP BY session_id, subject, human_id
        """,
        [session_id],
    ).fetchall()

    result = []
    for row in rows:
        sid, subject, human_id, raven_depth, crow_eff, trunk_q, tq_status = row
        raven_depth = float(raven_depth) if raven_depth is not None else 0.0
        crow_eff = float(crow_eff) if crow_eff is not None else 0.0
        trunk_q = float(trunk_q) if trunk_q is not None else 0.5
        # 3-metric formula: NO transport_speed
        composite_te = raven_depth * crow_eff * trunk_q
        result.append({
            "session_id": sid,
            "subject": subject,
            "human_id": human_id,
            "raven_depth": raven_depth,
            "crow_efficiency": crow_eff,
            "trunk_quality": trunk_q,
            "composite_te": composite_te,
        })
    return result
```

### Claude Code Actor Launch
```python
# Verified: Claude Code has NO --project-dir flag.
# CWD determines project. CLAUDECODE env var must be unset.

import os
import subprocess
import uuid

def launch_actor_session(
    assessment_dir: str,
    scenario_prompt: str,
    session_id: str | None = None,
) -> dict:
    """Launch Claude Code Actor in the assessment directory.

    Args:
        assessment_dir: Absolute path to /tmp/ope_assess_{id}/
        scenario_prompt: Initial prompt for the assessment session
        session_id: Optional pre-determined session UUID

    Returns:
        Dict with session_uuid, jsonl_path, exit_code
    """
    session_uuid = session_id or str(uuid.uuid4())

    # Build environment: remove CLAUDECODE to prevent nested-session error
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    cmd = [
        "claude",
        "-p",  # Print mode (non-interactive, for programmatic use)
        "--session-id", session_uuid,
        "--dangerously-skip-permissions",  # Assessment env is disposable
        scenario_prompt,
    ]

    result = subprocess.run(
        cmd,
        cwd=assessment_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,  # 1 hour max
    )

    # Derive JSONL path from assessment_dir
    escaped_path = assessment_dir.replace("/", "-")
    jsonl_dir = os.path.expanduser(f"~/.claude/projects/{escaped_path}")
    jsonl_path = os.path.join(jsonl_dir, f"{session_uuid}.jsonl")

    return {
        "session_uuid": session_uuid,
        "jsonl_path": jsonl_path,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
```

### Assessment Directory Setup
```python
# Pattern: Pre-seed CLAUDE.md + MEMORY.md before Actor launch

import os
import shutil

def setup_assessment_dir(
    session_id: str,
    scenario_context: str,
    scenario_file_name: str,
    scenario_file_content: str,
    handicap_claude_md: str,
    production_memory_md: str,
) -> str:
    """Create and populate assessment working directory.

    Returns:
        Absolute path to assessment directory.
    """
    base_dir = f"/tmp/ope_assess_{session_id}"
    os.makedirs(base_dir, exist_ok=True)

    # Write scenario files
    with open(os.path.join(base_dir, "scenario_context.md"), "w") as f:
        f.write(scenario_context)
    with open(os.path.join(base_dir, scenario_file_name), "w") as f:
        f.write(scenario_file_content)

    # Write CLAUDE.md (handicap framing for L5-L7, neutral for L1-L4)
    with open(os.path.join(base_dir, "CLAUDE.md"), "w") as f:
        f.write(handicap_claude_md)

    # Pre-seed .claude/MEMORY.md from production (full intelligence)
    claude_dir = os.path.join(base_dir, ".claude", "projects",
                               base_dir.replace("/", "-"), "memory")
    os.makedirs(claude_dir, exist_ok=True)
    with open(os.path.join(claude_dir, "MEMORY.md"), "w") as f:
        f.write(production_memory_md)

    return base_dir
```

### DuckDB Schema Extensions
```python
# New tables (Phase 17)

ASSESSMENT_TE_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS assessment_te_sessions (
    te_id                VARCHAR PRIMARY KEY,
    session_id           VARCHAR NOT NULL,
    scenario_id          VARCHAR NOT NULL,
    candidate_id         VARCHAR NOT NULL,
    candidate_te         FLOAT,
    scenario_baseline_te FLOAT,
    candidate_ratio      FLOAT,
    raven_depth          FLOAT,
    crow_efficiency      FLOAT,
    trunk_quality        FLOAT,
    trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending'
                         CHECK (trunk_quality_status IN ('pending', 'confirmed')),
    fringe_drift_rate    FLOAT,
    scenario_ddf_level   INTEGER,
    session_artifact_path VARCHAR,
    assessment_date      TIMESTAMPTZ DEFAULT NOW()
)
"""

ASSESSMENT_BASELINES_DDL = """
CREATE TABLE IF NOT EXISTS assessment_baselines (
    scenario_id    VARCHAR PRIMARY KEY,
    n_assessments  INTEGER NOT NULL DEFAULT 0,
    mean_ratio     FLOAT,
    stddev_ratio   FLOAT,
    last_updated   TIMESTAMPTZ DEFAULT NOW()
)
"""

# ALTER TABLE extensions for existing tables
MEMORY_CANDIDATES_ASSESSMENT_EXTENSIONS = [
    ("source_type", "VARCHAR DEFAULT 'production'"),
]

FLAME_EVENTS_ASSESSMENT_EXTENSIONS = [
    ("assessment_session_id", "VARCHAR"),
]

PROJECT_WISDOM_ASSESSMENT_EXTENSIONS = [
    ("scenario_seed", "TEXT"),
    ("ddf_target_level", "INTEGER"),
]
```

### Observer: Post-Session Transcript Analysis
```python
# Reuses existing extract pipeline

from src.pipeline.runner import PipelineRunner
from src.pipeline.models.config import load_config

def run_observer(jsonl_path: str, db_path: str, assessment_session_id: str) -> dict:
    """Run OPE extract pipeline on Actor's JSONL transcript.

    The Observer generates flame_events (both human and AI) from the
    transcript. Assessment-source events are tagged with assessment_session_id.

    Returns:
        Pipeline result dict (event_count, episode_count, etc.)
    """
    config = load_config("data/config.yaml")
    runner = PipelineRunner(config, db_path=db_path)

    try:
        result = runner.run_session(Path(jsonl_path))
    finally:
        runner.close()

    # Post-process: tag all flame_events from this session with assessment_session_id
    import duckdb
    conn = duckdb.connect(db_path)
    session_id = result.get("session_id")
    if session_id:
        conn.execute(
            "UPDATE flame_events SET assessment_session_id = ? WHERE session_id = ?",
            [assessment_session_id, session_id],
        )
    conn.close()

    return result
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TE = 4 metrics (raven * crow * transport * trunk) | Assessment TE = 3 metrics (raven * crow * trunk) | Phase 17 decision | transport_speed excluded from assessment context |
| memory_candidates: no source_type | memory_candidates: source_type column | Phase 17 decision | Enables production/assessment/simulation_review separation |
| flame_events: no assessment tagging | flame_events: assessment_session_id column | Phase 17 decision | Enables IntelligenceProfile filtering |
| IntelligenceProfile: aggregates all flame_events | IntelligenceProfile: excludes assessment by default | Phase 17 decision | Prevents contamination |
| project_wisdom: no scenario metadata | project_wisdom: scenario_seed + ddf_target_level | Phase 17 decision | Enables scenario calibration |

**Deprecated/outdated:**
- The `--project-dir` flag mentioned in CONTEXT.md DOES NOT EXIST in Claude Code CLI. Use CWD-based launch instead.

## Claude Code Launch Mechanics (Spike Resolution)

### Verified Facts (HIGH confidence -- direct CLI investigation)

1. **No `--project-dir` flag exists.** The `claude --help` output was checked. Claude Code determines the project directory from the current working directory (CWD) at launch time.

2. **Launch mechanism:** `cd <assessment_dir> && claude [options] [prompt]`

3. **Available flags for assessment use:**
   - `-p, --print` -- Non-interactive mode, outputs response and exits. Suitable for automated calibration runs (baseline TE computation).
   - `--session-id <uuid>` -- Specify a known session UUID. Useful for the Observer to locate the JSONL transcript without globbing.
   - `--dangerously-skip-permissions` -- Bypasses permission checks. Appropriate for disposable assessment directories.
   - `--system-prompt <prompt>` -- Override system prompt. Could be used for handicap framing in addition to CLAUDE.md.
   - `--append-system-prompt <prompt>` -- Append to default system prompt. Alternative handicap injection point.
   - `--settings <file-or-json>` -- Load custom settings (hooks, permissions) for this session only.
   - `--model <model>` -- Control which model the Actor uses.
   - `--allowedTools, --allowed-tools <tools...>` -- Restrict Actor's available tools.

4. **CLAUDECODE environment variable:** Set to `1` inside Claude Code sessions. Must be unset (`env -u CLAUDECODE`) before launching Actor subprocess. Error message confirmed: "Claude Code cannot be launched inside another Claude Code session."

5. **JSONL transcript location:** `~/.claude/projects/{cwd-with-slashes-replaced-by-dashes}/{session-uuid}.jsonl`
   - For CWD `/tmp/ope_assess_abc123`: `~/.claude/projects/-tmp-ope_assess_abc123/{uuid}.jsonl`
   - Each session produces one JSONL file named by its session UUID.
   - The JSONL contains message types: `user`, `assistant`, `system`, `progress`, `file-history-snapshot`.
   - Assistant messages contain `content` arrays with types: `text`, `thinking`, `tool_use`.

6. **CLAUDE.md resolution:** Claude Code reads `CLAUDE.md` from the project root (CWD). Writing `/tmp/ope_assess_{id}/CLAUDE.md` before launch pre-seeds the Actor's instructions.

7. **MEMORY.md resolution:** Claude Code reads MEMORY.md from `~/.claude/projects/{escaped-cwd}/memory/MEMORY.md`. For assessment sessions, pre-seeding requires writing to `~/.claude/projects/-tmp-ope_assess_{id}/memory/MEMORY.md`.

### Assessment Session Types

| Type | Mode | Purpose | Launch Pattern |
|------|------|---------|---------------|
| Calibration (baseline) | `-p` (print/non-interactive) | Compute scenario_baseline_te | `cd $DIR && unset CLAUDECODE && claude -p "Solve this problem: $(cat scenario_context.md)"` |
| Candidate (interactive) | No `-p` (interactive terminal) | Actual assessment with human candidate | `cd $DIR && unset CLAUDECODE && claude` |
| Candidate (automated) | `-p` with candidate prompt | Automated assessment (future) | `cd $DIR && unset CLAUDECODE && claude -p "<candidate_input>"` |

### MEMORY.md Pre-Seeding Path (MEDIUM confidence -- derived from observation)

The MEMORY.md path for project-specific memory follows the pattern observed in the existing project:
```
~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/memory/MEMORY.md
```

For an assessment dir at `/tmp/ope_assess_abc123`, the MEMORY.md pre-seed path would be:
```
~/.claude/projects/-tmp-ope_assess_abc123/memory/MEMORY.md
```

**WARNING:** This path derivation is based on observed convention, not official documentation. The spike task (Plan 17-01) should verify this by launching a test session and confirming MEMORY.md is read from the expected location.

## DuckDB Schema Details

### Existing Tables Being Extended

**memory_candidates** (defined in `src/pipeline/review/schema.py`):
```sql
-- Current columns: id, source_instance_id, ccd_axis, scope_rule, flood_example,
--   pipeline_component, heuristic_description, status, created_at, reviewed_at
-- Phase 15 additions: source_flame_event_id, fidelity, detection_count
-- Phase 16 additions: pre_te_avg, post_te_avg, te_delta, confidence, subject, session_id
-- Phase 17 addition:
ALTER TABLE memory_candidates ADD COLUMN source_type VARCHAR DEFAULT 'production';
-- Note: CHECK constraint cannot be added via ALTER TABLE in DuckDB.
-- Validation enforced in code (Pydantic model).
```

**flame_events** (defined in `src/pipeline/ddf/schema.py`):
```sql
-- Current columns: flame_event_id, session_id, human_id, prompt_number,
--   marker_level, marker_type, evidence_excerpt, quality_score, axis_identified,
--   flood_confirmed, subject, detection_source, deposited_to_candidates,
--   source_episode_id, session_event_ref, created_at
-- Phase 17 addition:
ALTER TABLE flame_events ADD COLUMN assessment_session_id VARCHAR;
```

**project_wisdom** (defined in `src/pipeline/storage/schema.py`):
```sql
-- Current columns: wisdom_id, entity_type, title, description, context_tags,
--   scope_paths, confidence, source_document, source_phase, created_at,
--   last_updated, embedding, metadata
-- Phase 17 additions:
ALTER TABLE project_wisdom ADD COLUMN scenario_seed TEXT;
ALTER TABLE project_wisdom ADD COLUMN ddf_target_level INTEGER;
```

### New Tables

**assessment_te_sessions:**
```sql
CREATE TABLE IF NOT EXISTS assessment_te_sessions (
    te_id                VARCHAR PRIMARY KEY,
    session_id           VARCHAR NOT NULL,
    scenario_id          VARCHAR NOT NULL,
    candidate_id         VARCHAR NOT NULL,
    candidate_te         FLOAT,
    scenario_baseline_te FLOAT,
    candidate_ratio      FLOAT,
    raven_depth          FLOAT,
    crow_efficiency      FLOAT,
    trunk_quality        FLOAT,
    trunk_quality_status VARCHAR NOT NULL DEFAULT 'pending'
                         CHECK (trunk_quality_status IN ('pending', 'confirmed')),
    fringe_drift_rate    FLOAT,
    scenario_ddf_level   INTEGER,
    session_artifact_path VARCHAR,
    assessment_date      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assess_te_scenario ON assessment_te_sessions(scenario_id);
CREATE INDEX IF NOT EXISTS idx_assess_te_candidate ON assessment_te_sessions(candidate_id);
```

**assessment_baselines:**
```sql
CREATE TABLE IF NOT EXISTS assessment_baselines (
    scenario_id    VARCHAR PRIMARY KEY,
    n_assessments  INTEGER NOT NULL DEFAULT 0,
    mean_ratio     FLOAT,
    stddev_ratio   FLOAT,
    last_updated   TIMESTAMPTZ DEFAULT NOW()
);
```

### CHECK Constraint Limitation

DuckDB ALTER TABLE does not support adding CHECK constraints to existing columns. The `source_type` CHECK constraint (`IN ('production', 'assessment', 'simulation_review')`) must be enforced:
1. In the Pydantic model (`Literal["production", "assessment", "simulation_review"]`)
2. In insert functions (validation before INSERT)
3. NOT in DDL ALTER TABLE (which only adds the column with a DEFAULT)

## CLI Structure

### Command Hierarchy
```
python -m src.pipeline.cli intelligence assess annotate-scenarios [--db]
python -m src.pipeline.cli intelligence assess run <scenario_id> <candidate_id> [--db] [--interactive]
python -m src.pipeline.cli intelligence assess calibrate <scenario_id> [--db]
python -m src.pipeline.cli intelligence assess report <session_id> [--db] [--output]
python -m src.pipeline.cli intelligence assess list-scenarios [--db] [--level]
```

### Command Details

| Command | Arguments | Options | Exit Codes | Purpose |
|---------|-----------|---------|------------|---------|
| `annotate-scenarios` | none | `--db` | 0=success, 1=error | Interactive: present un-annotated wisdom entries for DDF level + seed |
| `run` | scenario_id, candidate_id | `--db`, `--interactive` | 0=completed, 1=error | Launch assessment session (Actor + Observer) |
| `calibrate` | scenario_id | `--db` | 0=success, 1=error | Run baseline (no-handicap) Actor, compute scenario_baseline_te |
| `report` | session_id | `--db`, `--output` | 0=success, 1=error | Generate Assessment Report, deposit to memory_candidates |
| `list-scenarios` | none | `--db`, `--level` | 0=success | List wisdom entries with scenario_seed + ddf_target_level |

### Integration with Existing CLI

The `assess` group is registered on `intelligence_group` in `src/pipeline/cli/intelligence.py`:

```python
# In intelligence.py, add:
from src.pipeline.cli.assess import assess_group
intelligence_group.add_command(assess_group)
```

Or define the group directly in intelligence.py (following the edges_group pattern on line 163).

## Wave Planning

### Wave 1: Schema + Models + Spike (Foundation)
**Dependencies:** None (builds on existing Phase 15-16 infrastructure)
**Components:**
1. `src/pipeline/assessment/schema.py` -- DDL for new tables, ALTER TABLE extensions
2. `src/pipeline/assessment/models.py` -- Pydantic models: ScenarioSpec, AssessmentSession, AssessmentReport
3. Schema integration: call `create_assessment_schema()` from `create_ddf_schema()` chain
4. **SPIKE**: Verify Claude Code launch from `/tmp` with `--session-id`, confirm JSONL location, confirm CLAUDE.md/MEMORY.md reading
5. Tests: schema creation idempotency, model validation, spike verification

**Terminal deposit impact:** Creates the schema that receives deposits. No deposits yet.

### Wave 2: Scenario Generator + Annotation CLI
**Dependencies:** Wave 1 (schema must exist for scenario_seed/ddf_target_level columns)
**Components:**
1. `src/pipeline/assessment/scenario_generator.py` -- Builds scenario files from project_wisdom entries
2. `src/pipeline/cli/assess.py` -- `annotate-scenarios` and `list-scenarios` commands
3. Scenario validation: smoke test that generated broken implementation actually fails
4. Tests: scenario generation for each DDF level tier, CLI integration

**Terminal deposit impact:** Populates scenario_seed/ddf_target_level (prerequisite for assessment runs).

### Wave 3: Session Runner + Observer
**Dependencies:** Wave 1 (spike must be resolved), Wave 2 (scenarios must exist)
**Components:**
1. `src/pipeline/assessment/session_runner.py` -- Assessment dir setup, Actor launch, lifecycle management
2. `src/pipeline/assessment/observer.py` -- Post-session JSONL analysis via PipelineRunner
3. `src/pipeline/cli/assess.py` -- `run` and `calibrate` commands
4. `src/pipeline/assessment/rejection_detector.py` -- Outcome-gated L5-7 rejection detection
5. Tests: session lifecycle (mock subprocess), observer integration, rejection detection

**Terminal deposit impact:** Produces flame_events and assessment_te_sessions rows. Calibration runs produce scenario_baseline_te.

### Wave 4: Report Generator + Terminal Deposit
**Dependencies:** Wave 3 (session data must exist for reports)
**Components:**
1. `src/pipeline/assessment/reporter.py` -- Assessment Report generation
2. `src/pipeline/assessment/te_assessment.py` -- 3-metric TE computation, candidate_ratio, baselines update
3. `src/pipeline/cli/assess.py` -- `report` command
4. Terminal deposit: Assessment Report -> memory_candidates (source_type='simulation_review', fidelity=3, confidence=0.85)
5. Auto-calibration proposal: writes to memory_candidates when median_ratio triggers threshold
6. Tests: report generation, TE computation, deposit verification, baselines update

**Terminal deposit impact:** This is the deposit wave. Assessment Reports are deposited to memory_candidates. Auto-calibration proposals are deposited. The deposit-not-detect governing axis is satisfied.

### Wave Dependencies Graph
```
Wave 1 (Schema + Spike)
    |
    +---> Wave 2 (Scenarios + CLI)
    |         |
    +---> Wave 3 (Session Runner + Observer) <--- Wave 2
              |
              +---> Wave 4 (Report + Deposit) <--- Wave 3
```

## Open Questions

1. **MEMORY.md pre-seeding path verification**
   - What we know: The pattern `~/.claude/projects/{escaped-cwd}/memory/MEMORY.md` is observed for the main project.
   - What's unclear: Whether Claude Code creates/reads from this path for arbitrary CWDs (like `/tmp/ope_assess_*`), or whether it requires git initialization or project registration first.
   - Recommendation: Wave 1 spike must verify this. If MEMORY.md is not read from `/tmp` paths, alternative: use `--append-system-prompt` to inject IntelligenceProfile content.

2. **Interactive vs non-interactive assessment sessions**
   - What we know: Calibration runs use `-p` (non-interactive). Real candidate assessments need human interaction.
   - What's unclear: For interactive sessions, how does the Observer know the session is complete? Does the CLI wait for Claude Code to exit?
   - Recommendation: `subprocess.run()` blocks until Claude Code exits (user types `/exit` or Ctrl+C). The Observer runs after `subprocess.run()` returns.

3. **Scenario file validation (smoke test)**
   - What we know: Locked decision says generated files should be validated (run + assert failure).
   - What's unclear: What constitutes "failure" for different scenario types? Python exit code != 0? Specific exception type?
   - Recommendation: For MVP, check exit code != 0 for Python files. For non-executable scenarios (scenario_context.md describes the problem), skip validation.

4. **PAG hook behavior in assessment sessions**
   - What we know: PAG hook (Phase 14) is configured globally in `~/.claude/settings.json`. It reads from `data/ope.db` for staining checks.
   - What's unclear: In assessment sessions running from `/tmp/ope_assess_*/`, the PAG hook will look for `data/ope.db` relative to CWD. The file won't exist. Should we symlink it? Or does the hook fail-open gracefully?
   - Recommendation: PAG hook is designed fail-open (always exits 0). If `data/ope.db` doesn't exist at the CWD, all checks silently skip. This is acceptable for assessment sessions -- the Actor shouldn't have PAG warnings anyway.

5. **Assessment session cleanup and JSONL persistence**
   - What we know: Locked decision: tar + store path + rm -rf the assessment dir.
   - What's unclear: Should the JSONL transcript (in `~/.claude/projects/`) also be cleaned up? Or kept for future re-analysis?
   - Recommendation: Keep JSONL transcripts indefinitely (they're small, ~1-15MB each). Only clean up the assessment working directory.

## Sources

### Primary (HIGH confidence)
- `claude --help` output -- verified all CLI flags, confirmed no --project-dir (2026-02-24)
- `src/pipeline/ddf/transport_efficiency.py` -- TE computation patterns, DDL, write patterns
- `src/pipeline/ddf/schema.py` -- flame_events DDL, ALTER TABLE extension pattern
- `src/pipeline/review/schema.py` -- memory_candidates DDL, status CHECK constraint
- `src/pipeline/storage/schema.py` -- project_wisdom DDL, full schema chain
- `src/pipeline/cli/intelligence.py` -- Click group pattern, memory-review implementation
- `src/pipeline/cli/__main__.py` -- CLI registration pattern
- `src/pipeline/ddf/models.py` -- Pydantic frozen model pattern
- `src/pipeline/ddf/deposit.py` -- memory_candidates deposit with dedup
- `src/pipeline/ddf/writer.py` -- flame_events INSERT OR REPLACE pattern
- `src/pipeline/live/hooks/premise_gate.py` -- PAG hook structure, fail-open design
- `src/pipeline/wisdom/store.py` -- WisdomStore CRUD patterns
- `src/pipeline/wisdom/models.py` -- WisdomEntity model structure
- `~/.claude/settings.json` -- hooks configuration structure
- `~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/*.jsonl` -- JSONL file location pattern

### Secondary (MEDIUM confidence)
- JSONL session file structure -- examined actual session files, confirmed message types and content structure
- MEMORY.md path derivation -- inferred from observed `~/.claude/projects/{escaped-path}/memory/MEMORY.md` pattern
- CLAUDECODE environment variable behavior -- confirmed error message from attempted nested launch

### Tertiary (LOW confidence)
- MEMORY.md reading for arbitrary CWDs (e.g., `/tmp` paths) -- not verified; spike needed
- Whether `--session-id` flag causes Claude Code to use the specified UUID in the JSONL filename -- not verified; spike needed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, patterns verified from codebase
- Architecture: HIGH -- all patterns derived from existing Phases 14-16 code
- Claude Code launch: MEDIUM -- CLI flags verified via --help; JSONL path and MEMORY.md path need spike
- Schema extensions: HIGH -- DDL patterns directly from existing schema files
- Pitfalls: HIGH -- identified from direct code investigation and error messages
- Wave planning: HIGH -- dependency graph follows locked decisions

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (30 days -- stable domain, codebase under active development)
