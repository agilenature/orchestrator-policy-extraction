# Phase 24: Genus-Check Gate - Research

**Researched:** 2026-02-28
**Domain:** PAG hook extension, PREMISE block parsing, DuckDB (axis_edges / flame_events), FundamentalityChecker, CRAD algorithm
**Confidence:** HIGH

## Summary

Phase 24 extends the PAG PreToolUse hook with one new enforcement layer: before any write-class tool call, the PREMISE block must include a `GENUS` field declaring the category of the problem being solved. The PAG validates the genus using the fundamentality criterion (two citable instances + causal explanation), writes accepted genera as `EdgeRecord`s to `axis_edges`, and emits `genus_shift` events to `flame_events` (visible via the `ai_flame_events` view).

The phase is not new infrastructure. All dependencies are live in production:
- PAG hook: `src/pipeline/live/hooks/premise_gate.py` (574 lines, Phase 14.1, verified 2026-02-23)
- PREMISE parser: `src/pipeline/premise/parser.py` with compiled regex (Phase 14.1, verified)
- `axis_edges` table: 11 columns in ope.db, EdgeWriter/EdgeRecord at `src/pipeline/ddf/topology/` (Phase 16.1)
- `flame_events` table: 19 columns in ope.db (expanded by Phase 17), `ai_flame_events` VIEW = subject='ai' rows
- `premise_staging.jsonl` staging pattern: established two-writer solution

The A7 test case is the self-contained validation: Assertion 7 of check_stability.py fails because per-file searchability is not achieved by the stem-query approach for a minority of files. The genus of the problem is "corpus-relative identity retrieval" — the failure pattern manifests in EVERY project where items share a common background but need individual discrimination. CRAD (crad_algorithm.py) solves it in three passes that are direct structural consequences of the genus: Pass 1 (identify genus = shared aspects), Pass 2 (identify differentia = rare aspects), Pass 3 (essentialization = short phrase). The gate's job is to force genus declaration BEFORE solution design so the solution can be read off from the genus + differentia structure.

**Primary recommendation:** Implement in three waves. Wave 1: extend the PREMISE parser to parse the GENUS field and update ParsedPremise/PremiseRecord models. Wave 2: FundamentalityChecker class with two-instance + causal-explanation validation, integrated into the PAG hook. Wave 3: axis_edges write on accepted genus + flame_events genus_shift emission, both via staging (never directly to ope.db).

## Standard Stack

### Core (Already in Project — All Live in ope.db)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3.13 | 3.13.x | Runtime | Project standard |
| DuckDB | 1.4.4 | axis_edges write, flame_events emit — both via staging | Project standard; axis_edges and flame_events confirmed live in ope.db |
| Pydantic v2 | 2.11.7 | ParsedPremise extension, GenusDeclaration model, FundamentalityResult model | Frozen BaseModel is project-wide pattern |
| re (stdlib) | stdlib | GENUS field regex extension of PREMISE_BLOCK_RE | parser.py already uses pre-compiled multiline regex |
| hashlib (stdlib) | stdlib | Deterministic edge_id for axis_edges write | SHA-256[:16] is project-wide ID convention |
| json (stdlib) | stdlib | JSON field serialization for axis_edges evidence | Used throughout pipeline |
| loguru | 0.7.3 | Logging in FundamentalityChecker, genus writer | Project standard logging |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| fcntl (stdlib) | stdlib | File locking for staging writes | premise_gate.py already uses via staging.py's append_to_staging() |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extend PREMISE_BLOCK_RE | New standalone GENUS_RE | Extending PREMISE_BLOCK_RE keeps parsing in one place and avoids a two-pass scan; standalone GENUS_RE would require coordinating match positions |
| JSONL staging for genus write | Direct ope.db write from hook | Direct write violates the two-writer constraint (DuckDB single write connection); staging is the established pattern from Phase 14.1 |
| flame_events for genus_shift | New genus_events table | flame_events already has subject='ai' and detection_source='stub'/'opeml'; genus_shift is a new marker_type on the existing table; no new table needed |

## Architecture Patterns

### Module Structure (New Files Only)
```
src/pipeline/premise/
    fundamentality.py      # FundamentalityChecker class
    genus_writer.py        # GenusEdgeWriter: stages EdgeRecord + emits FlameEvent on genus_shift

src/pipeline/live/hooks/
    premise_gate.py        # EXTEND (not replace): add _check_genus() and genus dispatch

tests/pipeline/premise/
    test_fundamentality.py # FundamentalityChecker tests
    test_genus_writer.py   # GenusEdgeWriter tests

tests/pipeline/live/hooks/
    test_premise_gate.py   # EXTEND with genus-specific test cases
```

### Pattern 1: Extending PREMISE_BLOCK_RE for GENUS Field

**What:** The existing PREMISE block is 4 lines (PREMISE / VALIDATED_BY / FOIL / SCOPE). The GENUS field is a 5th optional line that follows SCOPE.

**Format (specified in ROADMAP):**
```
PREMISE: [claim]
VALIDATED_BY: [evidence]
FOIL: [confusable] | [distinguishing property]
SCOPE: [validity context]
GENUS: [name] | INSTANCES: [A, B]
```

**Parsing strategy:** The current `PREMISE_BLOCK_RE` in parser.py is a strict 4-field multiline regex. Extending it to optionally match a 5th `GENUS` line requires making the 5th capture group optional (`(?:...)?`). However, the current regex requires `\r?\n|$` at the end of SCOPE — when GENUS follows, SCOPE ends with `\n` and GENUS starts the next line.

**Revised regex (verified approach):**
```python
PREMISE_BLOCK_RE = re.compile(
    r"^\s*PREMISE:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*VALIDATED_BY:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*FOIL:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*SCOPE:\s*(.+?)[ \t]*(?:\r?\n)"
    r"(?:^\s*GENUS:\s*(.+?)[ \t]*(?:\r?\n|$))?",
    re.MULTILINE,
)
```
Groups: 1=claim, 2=validated_by, 3=foil_line, 4=scope, 5=genus_line (optional, None if absent).

**ParsedPremise model extension** (frozen Pydantic v2):
```python
# Add to ParsedPremise in src/pipeline/premise/models.py
genus_name: str | None = None       # The genus name (left of " | INSTANCES: ")
genus_instances: list[str] | None = None  # The instance citations (after "INSTANCES: ")
```

**GENUS line parsing:**
- Split on ` | INSTANCES: ` (exact string, case-sensitive per format spec)
- Left part = genus_name
- Right part = comma-separated instance citations

**Example:**
```
GENUS: corpus-relative identity retrieval | INSTANCES: A7 per-file searchability failure, ObjectivismLibrary-MOTM-dedup-failure
```
Produces: `genus_name="corpus-relative identity retrieval"`, `genus_instances=["A7 per-file searchability failure", "ObjectivismLibrary-MOTM-dedup-failure"]`

### Pattern 2: FundamentalityChecker

**What:** Validates that a genus declaration meets the fundamentality criterion: (1) exactly two or more citable instances, (2) a causal explanation (genus_name must be explanatory, not merely descriptive).

**Class interface:**
```python
# src/pipeline/premise/fundamentality.py
from dataclasses import dataclass

@dataclass(frozen=True)
class FundamentalityResult:
    valid: bool
    genus_name: str
    instances: list[str]
    causal_explanation_present: bool
    failure_reason: str | None  # None when valid=True

class FundamentalityChecker:
    def check(self, genus_name: str, instances: list[str]) -> FundamentalityResult:
        ...
```

**Validation rules:**
1. `instances` must have >= 2 elements (two citable instances)
2. `genus_name` must not be empty
3. Causal explanation detection: the genus_name contains at least one "explanatory word" from a configurable list — words that indicate mechanism, not just classification. The list (verifiable from ROADMAP/CRAD context): "retrieval", "identification", "formation", "derivation", "detection", "synchronization", "propagation", "extraction", "resolution", "scoping", "isolation", "drift", "failure". If none of these appear, the checker attempts a fallback: accept if genus_name is >= 3 words (multi-word names are more likely to encode causal structure than single-word names).
4. Instance citations must be non-empty strings.

**Key insight from ROADMAP:** The "causal explanation" criterion distinguishes a genus from a mere label. "Searchability failure" is a label (what the problem looks like). "Corpus-relative identity retrieval" is a causal explanation (it names the mechanism that, when absent, causes the observed failure). The checker can't fully validate causal adequacy with regex — it checks for structural proxies (explanatory words, multi-word structure). The full validation happens via the A7 test case.

**CONFIDENCE on causal check:** MEDIUM — the explanatory word list is inferred from the domain; it needs calibration after deployment. Start with HIGH RECALL (accept if any structural proxy passes), let the A7 test validate the end-to-end result.

### Pattern 3: PAG Hook Extension (_check_genus)

**What:** A new check in premise_gate.py `main()` that fires after PREMISE parsing if any premise has `genus_name` set.

**Extension point in main():**
```python
# After step 6 (_check_cross_axis), before step 7 (OPE bus check):
# Step 6.5: Genus check (Phase 24)
genus_warnings = _check_genus(all_premises, session_id, cwd, tool_use_id)
additional_context.extend(genus_warnings)
```

**`_check_genus` function signature:**
```python
def _check_genus(
    premises: list,
    session_id: str,
    cwd: str,
    tool_use_id: str,
) -> list[str]:
    """Validate genus declarations and write accepted genera to staging.

    Returns list of warning messages (GENUS_INVALID or GENUS_ACCEPTED).
    """
```

**Behavior:**
- If no premises have genus_name: return [] (fail-open, no GENUS field = no genus check)
- For each premise with genus_name: call FundamentalityChecker.check()
- If invalid: append `GENUS_INVALID: [reason]` warning
- If valid: call GenusEdgeWriter to append EdgeRecord + FlameEvent to genus staging JSONL
- Return all warnings

**CRITICAL: The hook NEVER writes to ope.db directly.** Genus writes go to a new `data/genus_staging.jsonl` file (separate from `data/premise_staging.jsonl` to avoid mixing schemas). The batch pipeline ingests both staging files.

### Pattern 4: GenusEdgeWriter

**What:** Builds `EdgeRecord` and `FlameEvent` objects from a validated genus declaration and appends them to genus staging JSONL.

**EdgeRecord construction for accepted genus:**
```python
# src/pipeline/premise/genus_writer.py
from src.pipeline.ddf.topology.models import EdgeRecord, ActivationCondition

def build_genus_edge(
    genus_name: str,
    instances: list[str],
    session_id: str,
    tool_use_id: str,
    premise_claim: str,
) -> EdgeRecord:
    """Build an EdgeRecord representing the accepted genus declaration.

    axis_a = genus_name (the genus)
    axis_b = premise_claim[:60] (the specific problem being solved)
    relationship_text = "genus_of"
    activation_condition = ActivationCondition(goal_type=["genus_check"], scope_prefix="")
    evidence = {"session_id": ..., "instances": [...], "tool_use_id": ...}
    abstraction_level = 3  (Theory layer per epistemological-layer-hierarchy CCD)
    """
```

**FlameEvent construction for genus_shift:**
```python
from src.pipeline.ddf.models import FlameEvent

def build_genus_shift_event(
    genus_name: str,
    session_id: str,
    prompt_number: int | None,
) -> FlameEvent:
    """Build a FlameEvent for a genus shift detection.

    marker_type = "genus_shift"
    marker_level = 3  (Theory-layer reframing = L3 causal claim)
    subject = "ai"
    detection_source = "stub"
    axis_identified = genus_name
    """
```

**flame_events columns used by genus_shift:**
From actual ope.db schema (19 columns including Phase 17 extensions):
- `flame_event_id`: SHA-256(session_id + prompt_number + "genus_shift")[:16]
- `session_id`: current session
- `marker_level`: 3 (causal claim level — naming the genus IS a causal claim)
- `marker_type`: "genus_shift"
- `subject`: "ai" (this is the AI making the genus declaration)
- `detection_source`: "stub" (Tier 1 — no LLM scoring needed, genus is in the GENUS field)
- `axis_identified`: genus_name
- `flood_confirmed`: False (confirmation happens post-hoc)

**Staging write pattern** (from premise_staging.py):
```python
GENUS_STAGING_PATH = Path("data/genus_staging.jsonl")

def append_genus_staging(records: list[dict]) -> None:
    """Append genus edge + flame event records to genus_staging.jsonl.
    Uses fcntl.flock for concurrent write safety (same pattern as staging.py).
    """
```

### Pattern 5: Batch Pipeline Ingestion of Genus Staging

**What:** The batch pipeline runner needs a new step to ingest `genus_staging.jsonl` into `axis_edges` and `flame_events`.

**Runner integration point:** After Step 11.5 (premise staging ingestion), add Step 11.6:
```python
# Step 11.6: Ingest genus staging (Phase 24)
try:
    from src.pipeline.premise.genus_writer import ingest_genus_staging
    genus_stats = ingest_genus_staging(self._conn)
    if genus_stats.get("edges_written", 0) > 0:
        logger.info("Step 11.6: Ingested {} genus edges, {} flame events",
                    genus_stats["edges_written"], genus_stats["flame_events_written"])
except ImportError:
    pass
except Exception as e:
    logger.warning("Genus staging ingestion failed: {}", e)
    warnings.append(f"Genus staging ingestion failed: {e}")
```

**`ingest_genus_staging(conn)` implementation:**
- Read genus_staging.jsonl
- For each record with type="edge": construct EdgeRecord, call EdgeWriter.write_edge()
- For each record with type="flame_event": construct FlameEvent, call write_flame_events()
- Clear staging after successful ingestion
- Return stats dict

### Anti-Patterns to Avoid

- **DO NOT make GENUS a mandatory field.** The existing PAG is fail-open on missing PREMISE blocks. Missing GENUS = no genus check fired. Only existing GENUS fields are validated. Writing an existing PREMISES without a GENUS field is not a violation.
- **DO NOT extend PREMISE_BLOCK_RE to make GENUS mandatory.** Optional 5th group preserves backward compatibility with 164 existing premise tests.
- **DO NOT write directly to ope.db from the hook.** DuckDB single-writer constraint. Use genus_staging.jsonl (same pattern as premise_staging.jsonl from Phase 14.1).
- **DO NOT use a new table for genus events.** flame_events with marker_type='genus_shift' and subject='ai' is sufficient. The ai_flame_events VIEW already filters subject='ai'.
- **DO NOT create a separate `genus_edges` table.** The ROADMAP explicitly says "axis_edges write on accepted genus declaration". EdgeRecord maps directly; abstraction_level=3 distinguishes genus edges from other edge types.
- **DO NOT hard-code the fundamentality word list.** Put it in data/config.yaml under `genus_check:` section with a `causal_indicator_words` list.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File-locked JSONL staging | Custom file write | `append_to_staging()` pattern from staging.py with `fcntl.flock` | Concurrent write safety is already solved; copy the pattern to genus_writer.py |
| EdgeRecord construction | Custom dict assembly | `EdgeRecord` + `ActivationCondition` from `src/pipeline/ddf/topology/models.py` | Pydantic validation ensures correct types; make_id() gives deterministic IDs |
| axis_edges write | Raw SQL INSERT | `EdgeWriter.write_edge()` from `src/pipeline/ddf/topology/writer.py` | Handles INSERT OR REPLACE idempotency, activation_condition validation |
| FlameEvent construction | Custom dict | `FlameEvent.make_id()` + frozen `FlameEvent` from `src/pipeline/ddf/models.py` | Deterministic ID generation, Pydantic field_validator on marker_level (0-7) |
| flame_events write | Raw SQL INSERT | `write_flame_events()` from `src/pipeline/ddf/writer.py` | Handles executemany pattern, correct column ordering for 19 columns |
| ID generation | uuid4 or custom | `hashlib.sha256(...)[:16]` | Project-wide convention; content-addressable for idempotency |
| Config loading | Hardcoded constants | `data/config.yaml` + `models/config.py` Pydantic model | Allows field-tuning without code changes |

**Key insight:** The Phase 24 code surface is small. Every component it needs (EdgeWriter, EdgeRecord, FlameEvent, write_flame_events, staging pattern, SHA-256 IDs) is already implemented and tested. The new code is: one regex extension, one ParsedPremise field addition, one FundamentalityChecker class, one `_check_genus` function, one GenusEdgeWriter module, one runner step. Total new logic: approximately 250 lines.

## Common Pitfalls

### Pitfall 1: Optional GENUS Regex Breaks Existing PREMISE Tests
**What goes wrong:** Making the 5th GENUS capture group mandatory changes the regex so it no longer matches 4-line PREMISE blocks, breaking all 22 parser tests.
**Why it happens:** The existing 164 premise tests use PREMISE blocks without GENUS fields.
**How to avoid:** The 5th group MUST be optional: `(?:^\s*GENUS:\s*(.+?)[ \t]*(?:\r?\n|$))?`. Verify with `python -m pytest tests/pipeline/premise/test_parser.py -v` after the regex change.
**Warning signs:** Parser tests failing immediately after regex change.

### Pitfall 2: GENUS Field After SCOPE but Before End-of-Block
**What goes wrong:** The regex captures SCOPE with `(\r?\n|$)` — if GENUS follows, SCOPE ends with `\n` (not `$`). The current SCOPE group uses `(?:\r?\n|$)` which already handles this. But if the GENUS group's `?` makes the SCOPE group match the GENUS line instead.
**Why it happens:** Greedy vs. non-greedy matching in the SCOPE group can consume the GENUS line.
**How to avoid:** Keep SCOPE's capture as `(.+?)` (non-greedy). After the `(?:\r?\n)` for SCOPE, the optional GENUS group's `^\s*GENUS:` anchor will not match if the SCOPE line just ended. The multiline `re.MULTILINE` flag ensures `^` matches at line boundaries.
**Warning signs:** GENUS content appearing in the SCOPE field; test_parser.py shows SCOPE capturing GENUS line text.

### Pitfall 3: FundamentalityChecker Causal Word List Rejects Valid Genera
**What goes wrong:** The causal indicator word list is too restrictive and rejects "corpus-relative identity retrieval" because it doesn't contain "retrieval".
**Why it happens:** The word list was built without including the exact words in the test case genus.
**How to avoid:** The test case genus (`corpus-relative identity retrieval`) validates the word list. Include "retrieval" in the list. Also include the multi-word fallback (>= 3 words passes) as a safety net.
**Warning signs:** The A7 test case validation fails at the FundamentalityChecker step.

### Pitfall 4: Genus Staging Not Cleared After Ingestion
**What goes wrong:** `genus_staging.jsonl` grows unbounded because `ingest_genus_staging` doesn't call `clear_staging`.
**Why it happens:** If the "clear after successful ingestion" logic is not atomic with the write.
**How to avoid:** Follow the exact pattern from ingestion.py: read all records, ingest all, THEN clear. If ingestion fails partway, do NOT clear (allow retry on next pipeline run). Use `try/finally` for this.
**Warning signs:** genus_staging.jsonl file size growing after multiple runs; duplicate genus edges in axis_edges (prevented by INSERT OR REPLACE, but still wasteful).

### Pitfall 5: axis_edges activation_condition Null Check Fails
**What goes wrong:** `EdgeWriter.write_edge()` raises ValueError because activation_condition is empty.
**Why it happens:** `ActivationCondition()` with all defaults has `goal_type=["any"]`, `scope_prefix=""`, `min_axes_simultaneously_active=2`. The EdgeWriter's activation_condition check: `if not ac_dict or all(v is None for v in ac_dict.values())` — with defaults, `ac_dict` is non-empty and values are not None. This should NOT fail.
**How to avoid:** Use `ActivationCondition(goal_type=["genus_check"])` explicitly (not the empty default) so the intent is clear and the validation passes.
**Warning signs:** `ValueError: activation_condition must have at least one non-null field` in hook stderr.

### Pitfall 6: flame_events Schema Has 19 Columns (Not 16)
**What goes wrong:** `write_flame_events()` in ddf/writer.py uses a 16-column INSERT. But the live ope.db has 19 columns (Phase 17 added `assessment_session_id`, `ccd_axis`, `differential`). The executemany INSERT with 16 columns will fail if the table has NOT NULL constraints on the new columns.
**Why it happens:** Phase 17 extended flame_events. The ddf/writer.py may not have been updated to include the new columns.
**How to avoid:** Before writing, verify the writer.py INSERT column list matches the table. The new columns added by Phase 17 (`assessment_session_id`, `ccd_axis`, `differential`) are likely nullable. Check the Phase 17 SUMMARY for their DDL definitions. If they're nullable, the 16-column INSERT is fine — the extra columns default to NULL. Verify: `python -c "from src.pipeline.ddf.writer import write_flame_events; print('import OK')"` and run a real insert against an in-memory DB with the full schema.
**Warning signs:** `Binder Error` or `not enough values` in DuckDB when inserting flame events.

### Pitfall 7: Two-Writer Conflict Between Hook and Pipeline
**What goes wrong:** The hook writes to `genus_staging.jsonl` at the same time the batch pipeline reads it, corrupting the JSONL.
**Why it happens:** File-level write/read race without locking on the reader side.
**How to avoid:** The `read_staging()` pattern from premise/staging.py reads the whole file atomically. The hook's `append_to_staging()` uses `fcntl.flock(LOCK_EX)`. The reader (`ingest_genus_staging`) should read the entire file in one operation and then clear. This is the same pattern as premise_staging.jsonl — it works.
**Warning signs:** JSON decode errors in `ingest_genus_staging` due to partial writes.

## Code Examples

### Extended PREMISE_BLOCK_RE with Optional GENUS Field
```python
# Source: src/pipeline/premise/parser.py (current regex, extended for Phase 24)
import re

PREMISE_BLOCK_RE = re.compile(
    r"^\s*PREMISE:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*VALIDATED_BY:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*FOIL:\s*(.+?)[ \t]*(?:\r?\n)"
    r"^\s*SCOPE:\s*(.+?)[ \t]*(?:\r?\n)"
    r"(?:^\s*GENUS:\s*(.+?)[ \t]*(?:\r?\n|$))?",
    re.MULTILINE,
)

def parse_genus_field(genus_line: str | None) -> tuple[str | None, list[str] | None]:
    """Parse GENUS line: 'name | INSTANCES: A, B' -> (name, [A, B])"""
    if not genus_line:
        return None, None
    if " | INSTANCES: " in genus_line:
        parts = genus_line.split(" | INSTANCES: ", 1)
        genus_name = parts[0].strip()
        instances_raw = parts[1].strip()
        instances = [i.strip() for i in instances_raw.split(",") if i.strip()]
        return genus_name, instances
    # No INSTANCES separator: treat entire line as genus name, empty instance list
    return genus_line.strip(), []
```

### FundamentalityChecker
```python
# Source: New file src/pipeline/premise/fundamentality.py
from dataclasses import dataclass

# Words that indicate causal/mechanistic explanation (not just naming)
# Derived from CRAD and OPE domain vocabulary
CAUSAL_INDICATOR_WORDS = {
    "retrieval", "identification", "formation", "derivation", "detection",
    "synchronization", "propagation", "extraction", "resolution", "scoping",
    "isolation", "drift", "failure", "mechanism", "process", "computation",
    "generation", "validation", "discrimination", "differentiation",
    "selection", "projection", "instantiation", "classification",
}

@dataclass(frozen=True)
class FundamentalityResult:
    valid: bool
    genus_name: str
    instances: list[str]
    causal_explanation_present: bool
    failure_reason: str | None = None  # None when valid

class FundamentalityChecker:
    def __init__(self, causal_words: set[str] | None = None):
        self._causal_words = causal_words or CAUSAL_INDICATOR_WORDS

    def check(self, genus_name: str, instances: list[str]) -> FundamentalityResult:
        # Rule 1: Two citable instances required
        if len(instances) < 2:
            return FundamentalityResult(
                valid=False,
                genus_name=genus_name,
                instances=instances,
                causal_explanation_present=False,
                failure_reason=f"Requires 2 instances, got {len(instances)}"
            )
        # Rule 2: Non-empty genus
        if not genus_name.strip():
            return FundamentalityResult(
                valid=False, genus_name=genus_name, instances=instances,
                causal_explanation_present=False,
                failure_reason="Genus name is empty"
            )
        # Rule 3: Causal explanation proxy
        words_in_genus = set(genus_name.lower().split())
        causal_present = bool(words_in_genus & self._causal_words)
        # Fallback: multi-word genus (>= 3 words) accepted regardless
        if not causal_present and len(words_in_genus) >= 3:
            causal_present = True
        if not causal_present:
            return FundamentalityResult(
                valid=False, genus_name=genus_name, instances=instances,
                causal_explanation_present=False,
                failure_reason=(
                    "Genus lacks causal explanation: must contain a mechanism/process word "
                    "or be >= 3 words. Single-word or two-word labels are insufficient."
                )
            )
        return FundamentalityResult(
            valid=True, genus_name=genus_name, instances=instances,
            causal_explanation_present=True
        )
```

### GenusEdgeWriter — EdgeRecord and FlameEvent construction
```python
# Source: New file src/pipeline/premise/genus_writer.py
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.ddf.topology.models import EdgeRecord, ActivationCondition
from src.pipeline.ddf.models import FlameEvent

GENUS_STAGING_PATH = Path("data/genus_staging.jsonl")

def build_genus_edge(
    genus_name: str,
    instances: list[str],
    session_id: str,
    tool_use_id: str,
    premise_claim: str,
) -> EdgeRecord:
    """Build EdgeRecord for accepted genus declaration."""
    axis_b = premise_claim[:60].strip()
    edge_id = EdgeRecord.make_id(genus_name, axis_b, "genus_of")
    return EdgeRecord(
        edge_id=edge_id,
        axis_a=genus_name,
        axis_b=axis_b,
        relationship_text="genus_of",
        activation_condition=ActivationCondition(goal_type=["genus_check"]),
        evidence={"session_id": session_id, "instances": instances, "tool_use_id": tool_use_id},
        abstraction_level=3,  # Theory layer per epistemological-layer-hierarchy CCD
        status="candidate",
        trunk_quality=1.0,
        created_session_id=session_id,
        created_at=datetime.now(timezone.utc),
    )

def build_genus_shift_event(
    genus_name: str,
    session_id: str,
    prompt_number: int | None = None,
) -> FlameEvent:
    """Build FlameEvent for genus_shift detection."""
    event_id = FlameEvent.make_id(session_id, prompt_number, "genus_shift")
    return FlameEvent(
        flame_event_id=event_id,
        session_id=session_id,
        prompt_number=prompt_number,
        marker_level=3,        # Causal claim level
        marker_type="genus_shift",
        subject="ai",
        detection_source="stub",
        axis_identified=genus_name,
        flood_confirmed=False,
    )
```

### _check_genus in premise_gate.py
```python
# Source: Extension to src/pipeline/live/hooks/premise_gate.py
def _check_genus(
    premises: list,
    session_id: str,
    cwd: str,
    tool_use_id: str,
) -> list[str]:
    """Validate genus declarations and stage accepted genera.

    Fires only when premises contain genus_name fields. Fail-open
    if FundamentalityChecker or GenusEdgeWriter unavailable.
    """
    warnings: list[str] = []
    genus_premises = [p for p in premises if getattr(p, "genus_name", None)]
    if not genus_premises:
        return warnings

    try:
        from src.pipeline.premise.fundamentality import FundamentalityChecker
        from src.pipeline.premise.genus_writer import (
            build_genus_edge, build_genus_shift_event, append_genus_staging
        )
        checker = FundamentalityChecker()
    except ImportError:
        return warnings  # fail-open: genus module not yet available

    for premise in genus_premises:
        genus_name = premise.genus_name
        instances = premise.genus_instances or []
        result = checker.check(genus_name, instances)

        if not result.valid:
            warnings.append(
                f"GENUS_INVALID: '{genus_name}' — {result.failure_reason}. "
                f"Genus requires 2+ citable instances and a causal explanation."
            )
        else:
            # Build staging records
            edge = build_genus_edge(
                genus_name=genus_name,
                instances=instances,
                session_id=session_id,
                tool_use_id=tool_use_id,
                premise_claim=premise.claim,
            )
            flame_event = build_genus_shift_event(
                genus_name=genus_name,
                session_id=session_id,
            )
            try:
                append_genus_staging([
                    {"type": "edge", "data": edge.model_dump()},
                    {"type": "flame_event", "data": flame_event.model_dump()},
                ])
                warnings.append(
                    f"GENUS_ACCEPTED: '{genus_name}' staged for axis_edges. "
                    f"Instances: {instances}"
                )
            except Exception as e:
                logger.debug("Genus staging write failed (fail-open): %s", e)

    return warnings
```

## A7 → CRAD: The Test Case

**What A7 checks (Assertion 7 in check_stability.py):** A random sample of N indexed files in the Gemini File Search store. For each file, construct a query from its filename stem (e.g., "What is 'B001 Introduction to Objectivism' about?") and verify the file appears in the top-5 search results. Files that fail this check are not searchable via their stem query.

**Why it fails for a subset of files:** When multiple files share the same topic aspects (a common "background" within a series), the stem-query hits the shared background instead of the specific file. The search engine cannot distinguish files that share common aspects — they all score similarly for any query about those aspects.

**The wrong genus (and why it leads to wrong solutions):**
- "File storage failure" → solution: re-upload files (addressed by Assertions 1-3)
- "Query construction failure" → solution: change query format (addresses the stem query construction, not the discrimination problem)
- "Embedding problem" → solution: change embedding model (addresses similarity model, not corpus structure)

**The correct genus: "corpus-relative identity retrieval"**

This genus names the mechanism: *identity* requires discrimination; *retrieval* requires the discriminating feature to be in the query; *corpus-relative* names the scope — the discriminating feature must be relative to the corpus structure (what makes this file different from its siblings), not absolute.

**How the correct genus makes CRAD self-evident:**
1. Genus identified: corpus-relative identity retrieval
2. Differentia: the aspects that make this file different from others IN ITS SERIES (not different in absolute terms)
3. Essentialization: concatenate the top differentia into <= 7 words
4. That IS crad_algorithm.py's 3 passes: Pass 1 = find shared aspects (genus profile), Pass 2 = select differentiating aspects (differentia), Pass 3 = concatenate (essentialization)

The genus declaration `GENUS: corpus-relative identity retrieval | INSTANCES: A7 per-file searchability failure, MOTM-series disambiguation failure` fully specifies the solution structure. The test case validates that the gate forces this framing BEFORE solution design — the gate is working when the CRAD solution becomes derivable without research.

**What "without knowing CRAD in advance" means:** The verification is: given ONLY the genus declaration and the failure description (A7), can a planner derive the CRAD algorithm structure? Yes: genus = corpus-relative → need corpus structure; differentia = what makes file distinct IN CORPUS → need series-relative aspect frequencies; essentialization → need short phrase from top differentia. That IS crad_algorithm.py.

## Wave Structure for Planning

### Wave 1: Parser Extension + Model Update (No External Dependencies)
**Goal:** Extend PREMISE_BLOCK_RE with optional GENUS group; add genus_name/genus_instances to ParsedPremise; add genus fields to PremiseRecord.
**Files:** `parser.py`, `models.py`, `tests/pipeline/premise/test_parser.py` (add GENUS test cases)
**Seam:** Complete when all 22+ parser tests pass including new GENUS cases. No hook changes needed yet.

### Wave 2: FundamentalityChecker + Hook Integration (Depends on Wave 1)
**Goal:** FundamentalityChecker class, `_check_genus` function in premise_gate.py.
**Files:** `src/pipeline/premise/fundamentality.py`, `src/pipeline/live/hooks/premise_gate.py` (extend main()), `tests/pipeline/premise/test_fundamentality.py`, `tests/pipeline/live/hooks/test_premise_gate.py` (extend)
**Seam:** Complete when FundamentalityChecker validates the A7 genus correctly AND invalid genus emits GENUS_INVALID warning.

### Wave 3: GenusEdgeWriter + Batch Pipeline Ingestion (Depends on Wave 2)
**Goal:** GenusEdgeWriter builds EdgeRecord + FlameEvent from valid genus; stages to genus_staging.jsonl; `ingest_genus_staging()` reads staging into axis_edges + flame_events; runner.py Step 11.6.
**Files:** `src/pipeline/premise/genus_writer.py`, `src/pipeline/runner.py` (Step 11.6), `tests/pipeline/premise/test_genus_writer.py`
**Seam:** Complete when a full PAG run produces a genus_staging.jsonl entry that ingest_genus_staging() writes to axis_edges and flame_events with zero regressions in existing tests.

**Natural seams rationale:**
- Wave 1 is purely internal to the parser — it can be fully tested with unit tests, no infrastructure needed.
- Wave 2 is the gate integration — needs Wave 1's ParsedPremise.genus_name field but nothing else.
- Wave 3 is the write path — needs Wave 2's FundamentalityChecker result but nothing from the live database (writes to staging JSONL only).

## Open Questions

1. **flame_events write compatibility with 19-column schema**
   - What we know: ope.db has 19 columns in flame_events (Phase 17 added assessment_session_id, ccd_axis, differential). The `write_flame_events()` function in ddf/writer.py uses a 16-column INSERT.
   - What's unclear: Are the Phase 17 columns nullable? If so, the existing writer works. If NOT NULL, the write will fail.
   - Recommendation: Check ddf/writer.py in Wave 3 and either (a) confirm columns are nullable and use existing writer, or (b) add the 3 columns to the INSERT with NULL defaults.

2. **Should GENUS_INVALID block the tool call or warn only?**
   - What we know: The ROADMAP says the gate "blocks writes lacking valid genus." But the Phase 14.1 principle is fail-open (always exit 0). The ROADMAP may be describing the intended behavior once Phase 24 is complete.
   - What's unclear: Is Phase 24 the first phase that actually blocks (exit 2)?
   - Recommendation: Implement as WARN-only (exit 0) in Wave 2. Add a config flag `genus_check.block_on_invalid: false` (default). The A7 test case can demonstrate correctness without blocking. Blocking is a future escalation.

3. **Genus staging JSONL vs. reusing premise_staging.jsonl**
   - What we know: premise_staging.jsonl stores PremiseRecord dicts. Genus staging stores {type: "edge"|"flame_event", data: {...}} dicts with different schemas.
   - What's unclear: Whether mixing schemas in one file is acceptable or creates parsing complexity.
   - Recommendation: Use a separate `data/genus_staging.jsonl` file. Schema isolation prevents the ingestion logic from having to type-check every record in premise_staging.jsonl. This matches the principle of one staging file per target table-group.

4. **PremiseRecord schema extension for genus fields**
   - What we know: PremiseRecord has 20 columns matching the premise_registry table schema. Adding genus_name/genus_instances to ParsedPremise does not require adding them to PremiseRecord if the genus data is written to axis_edges, not premise_registry.
   - What's unclear: Should premise_registry also store the genus declaration for completeness?
   - Recommendation: Do NOT add genus fields to PremiseRecord or premise_registry in Phase 24. The genus is written to axis_edges. Premise_registry records the claim/PREMISE; axis_edges records the genus. Separation is cleaner and avoids a schema migration on premise_registry.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/live/hooks/premise_gate.py` — Full PAG hook implementation, 574 lines, Phase 14.1 verified
- `src/pipeline/premise/parser.py` — PREMISE_BLOCK_RE regex, parse_premise_blocks(), ParsedPremise model, cross-reference detection
- `src/pipeline/premise/models.py` — ParsedPremise/PremiseRecord Pydantic models, make_id() classmethod
- `src/pipeline/ddf/schema.py` — flame_events DDL, ai_flame_events VIEW, create_ddf_schema()
- `src/pipeline/ddf/topology/schema.py` / `writer.py` / `models.py` — axis_edges DDL, EdgeWriter, EdgeRecord, ActivationCondition
- `src/pipeline/ddf/models.py` — FlameEvent frozen Pydantic model, make_id()
- `src/pipeline/ddf/writer.py` — write_flame_events() 16-column INSERT
- `data/ope.db` — Live DuckDB: axis_edges (11 cols), flame_events (19 cols), premise_registry (20 cols) confirmed
- `src/pipeline/premise/staging.py` — append_to_staging(), fcntl.flock pattern, STAGING_PATH
- `.planning/phases/14.1-premise-registry-premise-assertion-gate/14.1-VERIFICATION.md` — Phase 14.1 fully verified, 164 tests passing
- `/Users/david/projects/objectivism-library-semantic-search/scripts/check_stability.py` — A7 assertion: per-file searchability, sample loop, CRAD fallback in check_targeted_searchability()
- `/Users/david/projects/objectivism-library-semantic-search/scripts/crad_algorithm.py` — CRAD 3-pass algorithm: Pass 1 (genus via aspect frequency), Pass 2 (differentia via Claude), Pass 3 (essentialization)
- `.planning/ROADMAP.md` lines 519-530 — Phase 24 specification, genus format, test case description

### Secondary (MEDIUM confidence)
- Phase 15 RESEARCH.md — flame_events schema design decisions, marker_level semantics, detection_source values
- Phase 16.1 Plan 01 — EdgeRecord construction, ActivationCondition defaults, EdgeWriter validation logic
- Phase 14.1 RESEARCH.md — transcript parsing, PAG extension points, fail-open principle, staging two-writer pattern

### Tertiary (LOW confidence)
- FundamentalityChecker causal word list — derived from domain vocabulary analysis of CRAD + OPE; needs empirical calibration post-deployment
- flame_events 19-column write compatibility — Phase 17 columns assumed nullable; needs verification in Wave 3

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All libraries verified on disk; axis_edges, flame_events, premise_registry confirmed live in ope.db
- Architecture: HIGH — PAG hook structure fully known from implemented source code; staging pattern verified; EdgeWriter/FlameEvent interfaces verified
- GENUS regex extension: HIGH — Parser regex structure verified, optional 5th group is standard Python regex
- FundamentalityChecker logic: MEDIUM — Causal word list is inferred from domain; multi-word fallback is a safe proxy
- A7/CRAD analysis: HIGH — check_stability.py and crad_algorithm.py read and analyzed directly
- Wave structure: HIGH — Natural seams match the three-component design (parser → gate → write path)

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable domain — DuckDB schema, hook protocol, PREMISE format unlikely to change in 30 days)
