# Phase 10: Cross-Session Decision Durability - Research

**Researched:** 2026-02-20
**Domain:** Constraint durability tracking, cross-session evaluation, amnesia detection
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **No decisions.json** -- extend constraints.json with `type: "behavioral_constraint" | "architectural_decision"` field. Both use existing `active/candidate/retired` lifecycle.

2. **3-state evaluation**: HONORED | VIOLATED | UNKNOWN
   - VIOLATED: hint_patterns regex matches event payload AND scope overlaps
   - HONORED: scope overlaps but no hint_patterns match
   - UNKNOWN/IRRELEVANT: scope does NOT overlap -- excluded from denominator entirely

3. **sessions_active denominator**: sessions where (a) session.start_time >= constraint.created_at AND (b) session scope_paths intersect constraint scope_paths AND (c) constraint status was `active` at session time

4. **status_history array**: add `status_history: [{status, changed_at}]` to constraint schema for point-in-time status lookup

5. **hint_patterns regex** as primary violation detector (no LLM in detection path)

6. **Session scope from event payloads**: derive scope_paths from Read/Edit/Write/Bash tool file path args

7. **Two DuckDB tables**: `session_constraint_eval(session_id, constraint_id, eval_state, evidence_json, scope_matched, eval_ts)` and `amnesia_events(session_id, constraint_id, constraint_type, severity, evidence_json, detected_at)`

8. **O_ESC episodes auto-qualify as VIOLATED** for the constraint in `bypassed_constraint_id`

9. **CLI**: `python -m src.pipeline.cli audit session [--session-id ID] [--json]` and `audit durability [--constraint-id ID] [--json]`. Exit 0 = clean, 1 = runtime error, 2 = amnesia found.

10. **ShadowReporter** gains `amnesia_rate` and `avg_durability_score` metrics

### Claude's Discretion

None explicitly marked -- all 10 decisions above are locked.

### Deferred Ideas (OUT OF SCOPE)

- LLM-based violation detection
- Semantic/embedding-based constraint matching
- Multi-dimensional scope (beyond file paths)
- Grace period for newly created constraints
- Auto-retirement of behavioral constraints when architectural decisions retire
</user_constraints>

## Summary

Phase 10 adds cross-session memory to the pipeline. Currently, constraints are extracted and stored (Phase 3) and escalation episodes reference bypassed constraints (Phase 9), but no mechanism evaluates whether constraints are being honored or violated across sessions. Phase 10 fills this gap with three capabilities: (1) a session-level constraint evaluator that checks each active constraint against session events, (2) a durability index that scores each constraint's survival rate across sessions, and (3) amnesia detection that flags sessions violating pre-existing active constraints.

The implementation builds on substantial existing infrastructure. The `ConstraintStore` already manages `data/constraints.json` with SHA-256 IDs and schema validation. The constraint schema already has `detection_hints` (renamed from `hint_patterns` in the CONTEXT -- see note below), `scope.paths`, `status`, and `created_at` fields. The `_scopes_overlap()` function in `validation/layers.py` already implements bidirectional prefix matching. DuckDB patterns for table creation, staging-table upserts, and MERGE are well-established. The CLI uses Click groups. The ShadowReporter already computes aggregate metrics from DuckDB. All pieces exist; Phase 10 connects them.

One critical terminology note: the CONTEXT.md references `hint_patterns` as a constraint field, but the actual constraint schema uses `detection_hints` (array of strings). The evaluator must use `detection_hints` as the field name. The detection logic should treat each detection hint as a case-insensitive substring pattern applied against stringified event payloads -- consistent with Phase 9's always-bypass pattern matching approach.

**Primary recommendation:** Build this in 5-6 plans: (1) constraint schema migration (type, status_history, supersedes), (2) session scope derivation + constraint evaluator, (3) DuckDB tables + durability index, (4) amnesia detection, (5) CLI audit commands, (6) ShadowReporter integration.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | Project standard |
| DuckDB | 1.4.4 | Analytical storage, eval tables | Already primary store |
| Pydantic v2 | 2.11.7 | Config models, data validation | Already used everywhere |
| Click | 8.3.1 | CLI framework | Already used for extract/validate/train |
| jsonschema | 4.25.1 | Constraint schema validation | Already used in ConstraintStore |
| loguru | (installed) | Logging | Already used throughout pipeline |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| re (stdlib) | -- | Pattern matching for violation detection | Constraint eval against event payloads |
| json (stdlib) | -- | JSON serialization for evidence | Evidence storage in DuckDB JSON columns |
| hashlib (stdlib) | -- | Deterministic IDs for amnesia events | SHA-256 for amnesia_id generation |
| datetime (stdlib) | -- | Temporal comparisons | status_history point-in-time lookups |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Substring matching | Full regex | Substring is simpler and matches Phase 9 pattern; regex could be added later if needed |
| JSON in DuckDB | Separate evidence table | JSON column is simpler for variable-length evidence lists |
| SQL aggregation | Python aggregation | SQL is faster for analytical queries; DuckDB excels at this |

**Installation:**
No new dependencies needed. All libraries already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/
  constraint_store.py          # MODIFY: add status_history methods, type field support
  constraint_extractor.py      # MODIFY: set type="behavioral_constraint" on extracted constraints
  durability/                  # NEW module
    __init__.py
    evaluator.py               # SessionConstraintEvaluator: evaluate all constraints for a session
    scope_extractor.py         # SessionScopeExtractor: derive scope_paths from events
    index.py                   # DurabilityIndex: compute durability_score per constraint
    amnesia.py                 # AmnesiaDetector: flag violations of active constraints
  storage/
    schema.py                  # MODIFY: add session_constraint_eval and amnesia_events tables
    writer.py                  # MODIFY: add write_constraint_evals() and write_amnesia_events()
  shadow/
    reporter.py                # MODIFY: add amnesia_rate and avg_durability_score
  cli/
    __main__.py                # MODIFY: add audit group
    audit.py                   # NEW: audit session and audit durability commands
  runner.py                    # MODIFY: add Step 14 (constraint evaluation)
  models/
    config.py                  # MODIFY: add DurabilityConfig sub-model
data/
  schemas/
    constraint.schema.json     # MODIFY: add type, status_history, supersedes fields
  constraints.json             # MIGRATED: existing constraints gain type + status_history
```

### Pattern 1: Session Constraint Evaluation Pipeline
**What:** For each session, derive scope, then evaluate every active constraint, producing HONORED/VIOLATED/UNKNOWN per constraint.
**When to use:** After events are written to DuckDB (Step 8+), as part of the audit command or as pipeline Step 14.
**Example:**
```python
# Source: Derived from existing patterns in runner.py and validation/layers.py
class SessionConstraintEvaluator:
    def evaluate(
        self,
        session_id: str,
        session_scope_paths: list[str],
        session_start_time: str,
        events: list[dict],
        constraints: list[dict],
    ) -> list[ConstraintEvalResult]:
        results = []
        for constraint in constraints:
            # Check temporal validity
            status_at_time = self._get_status_at_time(constraint, session_start_time)
            if status_at_time != "active":
                continue  # Skip non-active constraints

            # Check scope overlap
            if not self._scopes_overlap(session_scope_paths, constraint["scope"]["paths"]):
                continue  # UNKNOWN -- excluded from results entirely

            # Check for O_ESC auto-violation
            if self._has_escalation_violation(session_id, constraint["constraint_id"]):
                results.append(ConstraintEvalResult(
                    session_id=session_id,
                    constraint_id=constraint["constraint_id"],
                    eval_state="VIOLATED",
                    evidence=[...],
                ))
                continue

            # Check detection hints against event payloads
            evidence = self._scan_events(events, constraint.get("detection_hints", []))
            if evidence:
                eval_state = "VIOLATED"
            else:
                eval_state = "HONORED"

            results.append(ConstraintEvalResult(
                session_id=session_id,
                constraint_id=constraint["constraint_id"],
                eval_state=eval_state,
                evidence=evidence,
            ))
        return results
```

### Pattern 2: Bidirectional Prefix Scope Matching (Reuse)
**What:** Reuse the existing `_scopes_overlap()` from `validation/layers.py`. Empty constraint paths = repo-wide = matches everything.
**When to use:** Determining if a constraint is relevant to a session's scope.
**Example:**
```python
# Source: src/pipeline/validation/layers.py lines 246-265 (verified in codebase)
@staticmethod
def _scopes_overlap(episode_paths: list[str], constraint_paths: list[str]) -> bool:
    if not constraint_paths:
        return True  # Repo-wide constraint
    for ep in episode_paths:
        for cp in constraint_paths:
            if ep.startswith(cp) or cp.startswith(ep):
                return True
    return False
```
This should be extracted into a shared utility (e.g., `src/pipeline/utils.py`) so both validation/layers.py and durability/evaluator.py can use it without import cycles.

### Pattern 3: Status History Point-in-Time Lookup
**What:** Given a constraint with `status_history` array and a session timestamp, determine what the constraint's status was at that time.
**When to use:** Durability score calculation -- only count sessions where constraint was `active`.
**Example:**
```python
# Source: Derived from CONTEXT.md Q4 decision
def get_status_at_time(constraint: dict, session_time: str) -> str | None:
    """Find constraint status at a given point in time.

    Returns the status from the last history entry where changed_at <= session_time.
    Returns None if no history entry exists before session_time (constraint didn't exist yet).
    """
    history = constraint.get("status_history", [])
    if not history:
        # Fallback: use current status if no history
        return constraint.get("status")

    # Sort by changed_at (should already be sorted, but be safe)
    sorted_history = sorted(history, key=lambda h: h["changed_at"])

    result = None
    for entry in sorted_history:
        if entry["changed_at"] <= session_time:
            result = entry["status"]
        else:
            break
    return result
```

### Pattern 4: DuckDB INSERT OR REPLACE for Eval Results
**What:** Use DuckDB's INSERT OR REPLACE for idempotent constraint evaluation storage. Re-running evaluation for a session replaces previous results.
**When to use:** Writing session_constraint_eval rows.
**Example:**
```python
# Source: Verified against DuckDB 1.4.4 in local testing
conn.execute("""
    INSERT OR REPLACE INTO session_constraint_eval
    (session_id, constraint_id, eval_state, evidence_json, scope_matched, eval_ts)
    VALUES (?, ?, ?, ?, ?, current_timestamp)
""", [session_id, constraint_id, eval_state, evidence_json, True])
```

### Pattern 5: Session Scope Extraction from Events
**What:** Derive session scope_paths by extracting file paths from tool call event payloads.
**When to use:** Before constraint evaluation, to determine which constraints are relevant.
**Example:**
```python
# Source: Derived from event payload structure in normalizer.py and CONTEXT.md Q6
import re

_FILE_PATH_RE = re.compile(
    r'(?:^|\s)((?:[\w.-]+/)+[\w.-]+\.[\w]+|[\w.-]+\.(?:py|js|ts|tsx|jsx|rs|go|java|rb|c|cpp|h|hpp|md|yaml|yml|json|toml|sql|sh|css|html))'
)

def extract_session_scope(events: list[dict]) -> list[str]:
    """Extract file paths from tool call events to build session scope."""
    paths: set[str] = set()
    for event in events:
        payload = event.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                continue

        # Extract from payload.details.file_path (Read/Edit/Write tools)
        details = payload.get("details", {})
        if isinstance(details, dict):
            file_path = details.get("file_path", "")
            if file_path:
                paths.add(file_path)

        # Extract from payload.common.text (Bash commands with file args)
        common = payload.get("common", {})
        text = common.get("text", "")
        if text:
            for match in _FILE_PATH_RE.findall(text):
                paths.add(match.strip())

    return sorted(paths)
```

### Anti-Patterns to Avoid
- **Evaluating constraints against sessions before the constraint existed:** Always check `session.start_time >= constraint.created_at` AND status_history lookup shows `active` at that time.
- **Including UNKNOWN in durability denominator:** UNKNOWN means "not relevant to this session" -- including it would dilute scores for well-scoped constraints.
- **Using the `status` field directly for historical queries:** The `status` field is the *current* state. For historical queries, always use `status_history` point-in-time lookup.
- **Scanning events after session processing is complete:** The evaluator reads events from DuckDB (already stored), not from the in-memory event list during processing. This ensures all events (including late-arriving ones) are included.
- **Regex compilation in hot loop:** Pre-compile detection hint patterns once per constraint, not once per event. Cache compiled patterns.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scope overlap detection | Custom path matching | Reuse `_scopes_overlap()` from `validation/layers.py` | Already tested and handles empty paths = repo-wide |
| DuckDB table creation | Manual ALTER TABLE sequences | `CREATE TABLE IF NOT EXISTS` pattern from `schema.py` | Idempotent, established pattern |
| Idempotent upserts | Custom dedup logic | DuckDB `INSERT OR REPLACE` with composite PK | Verified working in DuckDB 1.4.4 |
| SHA-256 deterministic IDs | UUID generation | `hashlib.sha256(...).hexdigest()[:16]` pattern | Consistent with constraint_id and episode_id patterns |
| JSON serialization for evidence | Custom serialization | `json.dumps()` for DuckDB JSON columns | Standard pattern used in writer.py |
| CLI group structure | Standalone scripts | Click group `audit` under existing CLI | Consistent with extract/validate/train groups |
| Aggregate metrics | Manual iteration over results | DuckDB SQL aggregation queries | DuckDB is optimized for analytical queries |

**Key insight:** This phase is mostly integration and wiring. Nearly every building block exists. The risk is in getting the evaluation semantics right (temporal validity, scope matching, evidence grounding), not in building new infrastructure.

## Common Pitfalls

### Pitfall 1: detection_hints vs hint_patterns Naming Mismatch
**What goes wrong:** CONTEXT.md references `hint_patterns` but the actual constraint schema field is `detection_hints`. Using the wrong field name produces zero violations (silent failure).
**Why it happens:** CONTEXT.md was generated from multi-provider synthesis that used a different naming convention than the actual schema.
**How to avoid:** Always use `detection_hints` as the field name. Add an assertion or log warning if a constraint has neither field.
**Warning signs:** All constraints evaluating to HONORED when some should be VIOLATED.

### Pitfall 2: String Comparison for Temporal Status Lookup
**What goes wrong:** ISO 8601 timestamps stored as strings can sort incorrectly if timezone offsets vary (e.g., `+00:00` vs `Z` vs `+05:00`).
**Why it happens:** `created_at` fields in existing constraints use mixed timezone formats.
**How to avoid:** Normalize all timestamps to UTC with consistent format before comparison. Use `datetime.fromisoformat()` for parsing, then compare datetime objects, not strings.
**Warning signs:** Constraints showing wrong status at session time, especially around DST transitions.

### Pitfall 3: Constraint Schema Validation Failure After Migration
**What goes wrong:** Adding `type`, `status_history`, and `supersedes` fields to constraints requires updating `constraint.schema.json`. If the schema uses `"additionalProperties": false` (which it does -- verified), new fields MUST be added to the schema BEFORE constraints containing those fields are validated.
**Why it happens:** The ConstraintStore validates every constraint against the schema on load.
**How to avoid:** Update `constraint.schema.json` FIRST, then migrate constraints, then update ConstraintStore code. The schema change and migration must happen in the same plan.
**Warning signs:** `ConstraintStore` refusing to load migrated constraints, logging "failed validation" warnings.

### Pitfall 4: Empty detection_hints Array
**What goes wrong:** Some constraints have `"detection_hints": []` (empty array) or missing `detection_hints`. These can never be VIOLATED through pattern matching, only through O_ESC linkage. Without careful handling, they would always show HONORED (artificially inflating durability scores).
**Why it happens:** Early constraints were extracted before detection_hints extraction was robust.
**How to avoid:** Constraints with empty/missing detection_hints AND no O_ESC violations should evaluate to UNKNOWN (not enough information to determine compliance), excluded from durability calculation. OR: log a warning and include them as HONORED (optimistic, per locked decision). The locked decision says HONORED when "scope overlaps but no hint_patterns match" -- so this is the correct behavior per the spec, but it should be logged for transparency.
**Warning signs:** Constraints with empty detection_hints showing perfect 1.0 durability scores.

### Pitfall 5: DuckDB Composite Primary Key with INSERT OR REPLACE
**What goes wrong:** `INSERT OR REPLACE` requires a PRIMARY KEY constraint to detect conflicts. If the composite PK `(session_id, constraint_id)` is not defined, DuckDB will insert duplicates.
**Why it happens:** Forgetting to add PRIMARY KEY in CREATE TABLE.
**How to avoid:** Always define `PRIMARY KEY (session_id, constraint_id)` on `session_constraint_eval`. Verified working in DuckDB 1.4.4 testing.
**Warning signs:** Duplicate rows in session_constraint_eval for the same session+constraint pair.

### Pitfall 6: Circular Import with Shared Utility
**What goes wrong:** Extracting `_scopes_overlap()` to a shared utility could create import cycles if both `validation/layers.py` and `durability/evaluator.py` import from it while the utility imports from models.
**Why it happens:** Python circular import resolution.
**How to avoid:** Put the utility in a standalone module (`src/pipeline/utils.py`) with zero internal imports. It's a pure function that takes lists of strings -- no dependencies.
**Warning signs:** ImportError on module load.

### Pitfall 7: Large Event Payloads in Violation Evidence
**What goes wrong:** Storing full event payloads as evidence can produce very large JSON blobs in the `evidence_json` column.
**Why it happens:** Events can have multi-KB payloads (especially assistant_text with long code blocks).
**How to avoid:** Store evidence as `{event_id, matched_pattern, payload_excerpt}` where `payload_excerpt` is truncated to first 500 chars of the matching context. The locked decision specifies this exact format.
**Warning signs:** ope.db growing rapidly in size after running audit.

### Pitfall 8: Minimum Sessions Threshold
**What goes wrong:** Showing durability_score for constraints with only 1-2 active sessions produces misleading scores (e.g., 0.0 from a single violation).
**Why it happens:** Small sample sizes.
**How to avoid:** The locked decision specifies minimum 3 sessions before showing a score. Below 3, return `durability_score: null` with `insufficient_data: true`.
**Warning signs:** Constraints showing 0.0 or 1.0 scores with very low session counts.

## Code Examples

Verified patterns from the existing codebase:

### DuckDB Table Creation (from schema.py pattern)
```python
# Source: src/pipeline/storage/schema.py lines 250-265 (verified)
# Pattern: CREATE TABLE IF NOT EXISTS + try/except ALTER TABLE for idempotent additions

def create_durability_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_constraint_eval (
            session_id VARCHAR NOT NULL,
            constraint_id VARCHAR NOT NULL,
            eval_state VARCHAR NOT NULL,
            evidence_json JSON,
            scope_matched BOOLEAN NOT NULL DEFAULT TRUE,
            eval_ts TIMESTAMPTZ DEFAULT current_timestamp,
            PRIMARY KEY (session_id, constraint_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS amnesia_events (
            amnesia_id VARCHAR PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            constraint_id VARCHAR NOT NULL,
            constraint_type VARCHAR,
            severity VARCHAR,
            evidence_json JSON,
            detected_at TIMESTAMPTZ DEFAULT current_timestamp
        )
    """)

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_constraint "
        "ON session_constraint_eval(constraint_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_session "
        "ON session_constraint_eval(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_amnesia_session "
        "ON amnesia_events(session_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_amnesia_constraint "
        "ON amnesia_events(constraint_id)"
    )
```

### Durability Score SQL Query
```python
# Source: Derived from ShadowReporter pattern + locked decision formula
DURABILITY_QUERY = """
    SELECT
        constraint_id,
        COUNT(*) as sessions_active,
        SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) as sessions_honored,
        SUM(CASE WHEN eval_state = 'VIOLATED' THEN 1 ELSE 0 END) as sessions_violated,
        CASE
            WHEN COUNT(*) >= 3
            THEN CAST(SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)
            ELSE NULL
        END as durability_score
    FROM session_constraint_eval
    WHERE eval_state IN ('HONORED', 'VIOLATED')
    GROUP BY constraint_id
"""

# For a single constraint:
SINGLE_DURABILITY_QUERY = """
    SELECT
        COUNT(*) as sessions_active,
        SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) as sessions_honored,
        SUM(CASE WHEN eval_state = 'VIOLATED' THEN 1 ELSE 0 END) as sessions_violated,
        CASE
            WHEN COUNT(*) >= 3
            THEN CAST(SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)
            ELSE NULL
        END as durability_score
    FROM session_constraint_eval
    WHERE constraint_id = ?
      AND eval_state IN ('HONORED', 'VIOLATED')
"""
```

### Click CLI Group Pattern (from __main__.py)
```python
# Source: src/pipeline/cli/__main__.py (verified)
# Pattern: add_command() for new group

# In __main__.py:
from src.pipeline.cli.audit import audit_group
cli.add_command(audit_group, name="audit")

# In audit.py:
@click.group("audit")
def audit_group():
    """Audit session constraint compliance and durability metrics."""
    pass

@audit_group.command(name="session")
@click.option("--session-id", default=None, help="Specific session ID to audit.")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
@click.option("--constraints", default="data/constraints.json", help="Constraints file.")
def audit_session(session_id, output_json, db, constraints):
    """Audit session(s) for constraint compliance. Exit 2 if amnesia found."""
    ...

@audit_group.command(name="durability")
@click.option("--constraint-id", default=None, help="Specific constraint ID.")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.option("--db", default="data/ope.db", help="DuckDB database path.")
def audit_durability(constraint_id, output_json, db):
    """Show durability scores for constraints."""
    ...
```

### Constraint Migration Script Pattern
```python
# Source: Derived from existing constraint schema + locked migration decision
import json
from pathlib import Path

def migrate_constraints(path: Path = Path("data/constraints.json")) -> int:
    """Add type, status_history, supersedes fields to existing constraints.

    Returns number of constraints migrated.
    """
    if not path.exists():
        return 0

    with open(path) as f:
        constraints = json.load(f)

    migrated = 0
    for c in constraints:
        changed = False

        # Add type field (default: behavioral_constraint)
        if "type" not in c:
            c["type"] = "behavioral_constraint"
            changed = True

        # Add status_history (bootstrap from current status + created_at)
        if "status_history" not in c:
            status = c.get("status", "active")
            created_at = c.get("created_at", "")
            if created_at:
                c["status_history"] = [{"status": status, "changed_at": created_at}]
            else:
                # Fallback: use earliest example timestamp
                examples = c.get("examples", [])
                # Cannot determine created_at -- use empty history
                c["status_history"] = []
            changed = True

        # Add supersedes field (null for behavioral constraints)
        if "supersedes" not in c:
            c["supersedes"] = None
            changed = True

        if changed:
            migrated += 1

    with open(path, "w") as f:
        json.dump(constraints, f, indent=2)
        f.write("\n")

    return migrated
```

### ShadowReporter Extension Pattern
```python
# Source: src/pipeline/shadow/reporter.py _compute_escalation_metrics() pattern (verified)
def _compute_amnesia_metrics(self) -> dict:
    """Compute amnesia and durability metrics from DuckDB tables."""
    try:
        # Amnesia rate: sessions with at least one amnesia event / total audited sessions
        row = self._conn.execute("""
            SELECT
                COUNT(DISTINCT e.session_id) as audited_sessions,
                COUNT(DISTINCT a.session_id) as sessions_with_amnesia
            FROM (SELECT DISTINCT session_id FROM session_constraint_eval) e
            LEFT JOIN amnesia_events a ON e.session_id = a.session_id
        """).fetchone()
    except Exception:
        return {"amnesia_rate": None, "avg_durability_score": None}

    audited = row[0] or 0
    with_amnesia = row[1] or 0
    amnesia_rate = with_amnesia / audited if audited > 0 else None

    try:
        # Average durability score across all constraints with sufficient data
        dur_row = self._conn.execute("""
            SELECT AVG(durability_score)
            FROM (
                SELECT
                    constraint_id,
                    CAST(SUM(CASE WHEN eval_state = 'HONORED' THEN 1 ELSE 0 END) AS FLOAT)
                        / COUNT(*) as durability_score
                FROM session_constraint_eval
                WHERE eval_state IN ('HONORED', 'VIOLATED')
                GROUP BY constraint_id
                HAVING COUNT(*) >= 3
            )
        """).fetchone()
    except Exception:
        dur_row = (None,)

    avg_durability = dur_row[0] if dur_row else None

    return {
        "amnesia_rate": amnesia_rate,
        "avg_durability_score": avg_durability,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No cross-session tracking | Constraints extracted per-session, stored | Phase 3 (Plan 03-01) | Constraints persist but no evaluation |
| No escalation linkage | O_ESC episodes link to bypassed_constraint_id | Phase 9 (Plan 09-03) | Escalations reference specific constraints |
| No temporal history | status field only (current state) | Current | Cannot determine historical status |
| No durability metrics | ShadowReporter has escalation metrics only | Phase 9 (Plan 09-04) | No cross-session compliance visibility |

**What Phase 10 changes:**
- `constraints.json` gains `type`, `status_history`, `supersedes` fields
- DuckDB gains `session_constraint_eval` and `amnesia_events` tables
- Pipeline gains Step 14 (session constraint evaluation)
- CLI gains `audit session` and `audit durability` commands
- ShadowReporter gains amnesia and durability metrics

## Open Questions

1. **Should audit run automatically in the pipeline or only via CLI?**
   - What we know: The locked decision says `audit session` is a CLI command. But the Architecture Summary in CLARIFICATIONS-ANSWERED.md mentions "Step 14 in run_session()" for automatic evaluation.
   - What's unclear: Whether constraint evaluation should run on every `extract` invocation automatically, or only when explicitly requested via `audit session`.
   - Recommendation: Make it both. Add as Step 14 in runner.py (automatically runs during extraction), AND expose via CLI for ad-hoc auditing of already-processed sessions. The CLI command can re-evaluate sessions that were processed before Phase 10 was deployed.

2. **How to handle existing constraints without proper detection_hints?**
   - What we know: Many existing constraints have low-quality detection_hints (e.g., long prose excerpts, not actual patterns).
   - What's unclear: Whether these should be treated as HONORED (per locked decision) or flagged for human review.
   - Recommendation: Follow the locked decision (HONORED when scope overlaps but no pattern matches). Log a warning for constraints with empty detection_hints. Add a future task to improve hint quality.

3. **Should session start_time come from events table or session metadata?**
   - What we know: There is no explicit `sessions` table. Sessions are identified by `session_id` across events/episodes.
   - What's unclear: How to get session start_time reliably.
   - Recommendation: Use `MIN(ts_utc) FROM events WHERE session_id = ?` as session start_time. This is the earliest event timestamp for that session.

4. **Amnesia event ID generation**
   - What we know: Other IDs use SHA-256(deterministic input)[:16].
   - What's unclear: What input to hash for amnesia_id.
   - Recommendation: `amnesia_id = SHA-256(session_id + constraint_id)[:16]`. This ensures one amnesia event per (session, constraint) pair and is idempotent on re-run.

## Existing Infrastructure Inventory

This section maps exactly what exists and what must be created/modified.

### Files to MODIFY

| File | Change | Why |
|------|--------|-----|
| `data/schemas/constraint.schema.json` | Add `type`, `status_history`, `supersedes` properties | Schema must allow new fields before migration |
| `src/pipeline/constraint_store.py` | Add `get_status_at_time()`, `add_status_history_entry()`, `get_by_type()` methods | Support temporal queries and type filtering |
| `src/pipeline/constraint_extractor.py` | Set `type="behavioral_constraint"` and initialize `status_history` on new constraints | New constraints must have type field |
| `src/pipeline/escalation/constraint_gen.py` | Set `type="behavioral_constraint"` and initialize `status_history` on generated constraints | Escalation-inferred constraints also need type |
| `src/pipeline/storage/schema.py` | Add `session_constraint_eval` and `amnesia_events` table creation in `create_schema()` | New DuckDB tables |
| `src/pipeline/storage/writer.py` | Add `write_constraint_evals()` and `write_amnesia_events()` functions | Write evaluation results |
| `src/pipeline/shadow/reporter.py` | Add `_compute_amnesia_metrics()` and integrate into `compute_report()` + `format_report()` | New metrics in shadow report |
| `src/pipeline/runner.py` | Add Step 14: session constraint evaluation after escalation detection | Automatic evaluation during pipeline run |
| `src/pipeline/cli/__main__.py` | Add `audit_group` command | New CLI subcommand |
| `src/pipeline/models/config.py` | Add `DurabilityConfig` sub-model (optional, for min_sessions threshold etc.) | Configuration for durability parameters |
| `data/config.yaml` | Add `durability:` section | Config values for durability tracking |

### Files to CREATE

| File | Purpose |
|------|---------|
| `src/pipeline/durability/__init__.py` | Module init |
| `src/pipeline/durability/evaluator.py` | `SessionConstraintEvaluator` class |
| `src/pipeline/durability/scope_extractor.py` | `SessionScopeExtractor` -- derives scope from events |
| `src/pipeline/durability/index.py` | `DurabilityIndex` -- computes scores via SQL |
| `src/pipeline/durability/amnesia.py` | `AmnesiaDetector` -- flags violated active constraints |
| `src/pipeline/durability/migration.py` | Constraint migration script |
| `src/pipeline/cli/audit.py` | CLI audit commands |
| `tests/test_durability_evaluator.py` | Tests for evaluator |
| `tests/test_durability_scope.py` | Tests for scope extraction |
| `tests/test_durability_index.py` | Tests for durability index |
| `tests/test_durability_amnesia.py` | Tests for amnesia detection |
| `tests/test_durability_migration.py` | Tests for constraint migration |
| `tests/test_audit_cli.py` | Tests for audit CLI commands |

### Reusable Functions (extract to shared utility)

| Function | Current Location | Used By |
|----------|-----------------|---------|
| `_scopes_overlap()` | `validation/layers.py` L246 | validation + durability evaluator |
| File path regex | `constraint_extractor.py` L63 | constraint extractor + scope extractor |

## Sources

### Primary (HIGH confidence)
- **Codebase inspection** -- All source files read and verified directly:
  - `src/pipeline/constraint_store.py` -- ConstraintStore API (add, save, count, constraints)
  - `src/pipeline/constraint_extractor.py` -- ConstraintExtractor (detection_hints field name confirmed)
  - `src/pipeline/storage/schema.py` -- DuckDB schema (CREATE TABLE IF NOT EXISTS pattern, ALTER TABLE pattern)
  - `src/pipeline/storage/writer.py` -- write_events, write_episodes, write_escalation_episodes patterns
  - `src/pipeline/shadow/reporter.py` -- ShadowReporter (compute_report, format_report, _compute_escalation_metrics)
  - `src/pipeline/runner.py` -- PipelineRunner.run_session() (Steps 1-13)
  - `src/pipeline/validation/layers.py` -- _scopes_overlap() bidirectional prefix matching
  - `src/pipeline/cli/__main__.py` -- Click group structure (cli.add_command pattern)
  - `src/pipeline/models/config.py` -- PipelineConfig with sub-models (EscalationConfig pattern)
  - `src/pipeline/escalation/detector.py` -- EscalationDetector pattern matching approach
  - `src/pipeline/escalation/constraint_gen.py` -- EscalationConstraintGenerator (constraint creation pattern)
  - `data/schemas/constraint.schema.json` -- Current schema (additionalProperties: false confirmed)
  - `data/constraints.json` -- Existing constraint structure (detection_hints, scope.paths, status, created_at)
  - `tests/conftest.py` -- Test fixture patterns (make_event, make_tagged_event)
  - `tests/test_constraint_store.py` -- Test patterns (_make_constraint helper, tmp_path fixtures)

### Secondary (MEDIUM confidence)
- **DuckDB 1.4.4 verification** -- INSERT OR REPLACE with composite PK tested locally and confirmed working
- **DuckDB JSON column roundtrip** -- JSON storage and retrieval verified locally

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or local testing

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, versions verified
- Architecture: HIGH -- all patterns derived from existing codebase, no new infrastructure
- Pitfalls: HIGH -- identified from actual codebase inspection (schema additionalProperties, field naming, etc.)
- Code examples: HIGH -- derived from verified existing patterns in the codebase

**Research date:** 2026-02-20
**Valid until:** 2026-03-20 (30 days -- stable domain, all libraries mature)
