# Phase 23: Autonomous Loop Mode-Switch Detection - Research

**Researched:** 2026-02-27
**Domain:** EBC-Drift detection / operational mode classification / alert artifact system
**Confidence:** HIGH (internal codebase domain; no external libraries required)

## Summary

Phase 23 introduces an **External Behavioral Contract (EBC)** system that detects when a GSD execution session drifts from its planned behavioral contract. The core insight: every PLAN.md file already declares an implicit behavioral contract via its YAML frontmatter (`files_modified`, `autonomous`, `wave`, `must_haves.artifacts`, `must_haves.key_links`). Phase 23 formalizes this contract into a machine-readable schema, then compares it against actual session behavior observed in ingested JSONL data to detect mode-switches from Execution Mode (working within contract) to Discovery Mode (exploring outside contract).

This is a post-hoc detection system, not a real-time one. Detection happens during pipeline ingestion (`run_session()` in `runner.py`), after episodes are populated and stored. When drift is detected, the system: (1) logs to stderr via loguru, (2) persists a structured alert artifact to `data/alerts/`, (3) optionally injects a warning into STATE.md, and (4) provides a `/project:autonomous-loop-mode-switch` command for recovery.

**Primary recommendation:** Build the EBC as a Pydantic model parsed from PLAN.md frontmatter + must_haves sections. Add a new `EBCDriftDetector` class (analogous to `EscalationDetector`) that runs as Step 22.5 in the pipeline runner. Alert artifacts are standalone JSON files in `data/alerts/` -- not DuckDB rows -- because they must be human-readable and git-trackable.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | v2 (existing) | EBC schema model, alert artifact model | Already used for all pipeline models (EscalationCandidate, FlameEvent, etc.) |
| loguru | existing | stderr alert output | Already used for all pipeline logging |
| click | existing | CLI command for `/project:autonomous-loop-mode-switch` | Already used for all CLI subcommands |
| PyYAML | existing | PLAN.md frontmatter parsing | Already used for config.yaml loading |
| DuckDB | existing | Querying ingested session data for drift signals | Already the primary storage backend |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-frontmatter | N/A (hand-roll) | Parsing PLAN.md YAML frontmatter | See "Don't Hand-Roll" exception below |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Standalone JSON alert files | DuckDB alerts table | JSON files are git-trackable and human-readable without DB tooling; table would require CLI to inspect |
| PLAN.md frontmatter as EBC source | Separate EBC YAML files | Using existing frontmatter avoids creating a parallel artifact; every PLAN.md already has `files_modified` and `must_haves` |
| Post-hoc detection at ingestion time | Real-time detection via PreToolUse hooks | Post-hoc is simpler, leverages existing pipeline; real-time could be a Phase 24 extension |

**Installation:** No new dependencies needed. All required libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure

```
src/pipeline/
    ebc/
        __init__.py          # Package exports
        models.py            # EBC schema + EBCDriftAlert Pydantic models
        parser.py            # Parse PLAN.md frontmatter into EBC
        detector.py          # EBCDriftDetector: compare EBC vs session behavior
        writer.py            # Write alert JSON to data/alerts/
        state_injector.py    # Inject warning into STATE.md
    cli/
        ebc.py               # CLI subcommand group for EBC operations
.claude/commands/
    autonomous-loop-mode-switch.md  # Local project command
data/
    alerts/                  # Alert artifact directory (git-tracked)
        .gitkeep
```

### Pattern 1: Detector-at-Ingestion (following EscalationDetector)

**What:** A detector class that takes session data + EBC contract and produces drift candidates, wired into `runner.py` as a numbered pipeline step.

**When to use:** This is the established pattern for all detection subsystems in the pipeline (EscalationDetector, AmnesiaDetector, OAxsDetector, FalseIntegrationDetector, CausalIsolationRecorder).

**Evidence from codebase:**
- `EscalationDetector.__init__(config)` + `.detect(tagged_events) -> list[EscalationCandidate]` (src/pipeline/escalation/detector.py:70)
- `AmnesiaDetector().detect(eval_results, constraints) -> list[AmnesiaEvent]` (src/pipeline/durability/amnesia.py)
- Runner wiring: try/except with ImportError fallback, logger.info for counts, stats dict accumulation (runner.py:477-572 for escalation)

**Example structure:**
```python
# src/pipeline/ebc/detector.py
class EBCDriftDetector:
    def __init__(self, config: PipelineConfig) -> None:
        self._config = config

    def detect(
        self,
        ebc: ExternalBehavioralContract,
        session_events: list[dict],
        tagged_events: list[TaggedEvent],
        valid_episodes: list[dict],
    ) -> EBCDriftAlert | None:
        """Compare EBC expectations against actual session behavior.
        Returns an alert if drift exceeds threshold, None otherwise."""
```

### Pattern 2: PLAN.md Frontmatter as Contract Source

**What:** The EBC is derived from PLAN.md YAML frontmatter, not a separate artifact. This means the "contract" is whatever the plan already declares.

**When to use:** Every plan execution. The EBC parser reads the frontmatter of the plan currently being executed.

**Evidence from codebase:**
Every PLAN.md has this frontmatter structure (verified across 93 plans):
```yaml
---
phase: 22-unified-discriminated-query-interface
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/pipeline/session_query.py
  - src/pipeline/code_query.py
  - tests/test_session_query.py
  - tests/test_code_query.py
autonomous: true

must_haves:
  truths:
    - "query_sessions('segmenter fix') returns episode matches..."
  artifacts:
    - path: "src/pipeline/session_query.py"
      provides: "BM25 fulltext search over episode_search_text..."
      exports: ["query_sessions"]
  key_links:
    - from: "src/pipeline/session_query.py"
      to: "episode_search_text table"
      via: "DuckDB BM25 match_bm25()..."
      pattern: "fts_main_episode_search_text\\.match_bm25|ILIKE"
---
```

The EBC schema formalizes these into a contract:
- `files_modified` -> expected file paths
- `must_haves.artifacts[].path` -> expected artifact paths with `exports` and `contains`
- `must_haves.key_links[].pattern` -> expected code patterns (regex)
- `autonomous: true/false` -> whether human review is expected
- `type: execute` -> expected operational mode

### Pattern 3: Alert Artifact as Standalone JSON (not DuckDB)

**What:** Alert files are written to `data/alerts/{session_id}-ebc-drift.json` as human-readable JSON, not stored in DuckDB.

**Why this pattern:**
1. Human-readable without DB tooling
2. Git-trackable (shows in `git status`, reviewable in PRs)
3. Machine-parseable for downstream tools
4. Analogous to how `data/constraints.json` works -- a filesystem artifact that the human can inspect directly

**Structure parallels:**
- `data/constraints.json` -- JSON file, git-tracked, human-readable constraint store
- `data/projects.json` -- JSON file, git-tracked, project registry
- `data/alerts/` directory -- new, follows same convention

### Pattern 4: STATE.md Injection (Append-Only Warning Block)

**What:** When an EBC drift is detected, inject a warning block into STATE.md in a dedicated section.

**Key design constraint:** STATE.md is a human-maintained file that changes format between phases. The injector must not corrupt existing content. The safest approach: append a clearly-delimited block at a known location.

**Evidence from codebase:**
STATE.md has a "Current Position" section (line 11-21) that tracks the current phase/plan. The injector should add a warning section below "Current Position" and above "Performance Metrics":

```markdown
## EBC Drift Alerts

> **WARNING:** Session `{session_id}` drifted from EBC for Phase {phase}, Plan {plan}
> - Files outside contract: `src/unexpected/file.py`
> - Expected files untouched: `src/pipeline/expected.py`
> - Drift score: 0.73 (threshold: 0.5)
> - Alert artifact: `data/alerts/{session_id}-ebc-drift.json`
> - Recovery: Run `/project:autonomous-loop-mode-switch` for options
```

### Anti-Patterns to Avoid

- **Anti-pattern: Real-time blocking.** Phase 23 is post-hoc detection, not PreToolUse enforcement. Do not block the pipeline if drift is detected -- log and persist only.
- **Anti-pattern: Overwriting STATE.md content.** The injector must only append/update the "EBC Drift Alerts" section. Never rewrite other sections.
- **Anti-pattern: Hard-coded thresholds.** All drift thresholds should be configurable via `data/config.yaml` (following every other subsystem's pattern).
- **Anti-pattern: Requiring a PLAN.md to exist.** Not all sessions are executed under a plan. The detector must gracefully handle "no EBC available" by skipping detection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | Custom regex parser | PyYAML `yaml.safe_load()` on the `---`-delimited frontmatter block | Standard, handles all YAML types |
| JSON Schema for alert artifacts | N/A -- no external validator needed | Pydantic model + `.model_dump_json()` | Pydantic already ensures structural validity |
| File diffing/comparison | Custom diff engine | Simple set operations on file paths | EBC drift is about expected-vs-actual file sets, not content diff |

**Key insight:** The EBC-drift detector is structurally simple -- it compares two sets (expected files vs actual files, expected patterns vs actual patterns). The complexity is in (a) reliably parsing the EBC from PLAN.md frontmatter, (b) reliably extracting "actual behavior" from ingested session data, and (c) producing useful alert artifacts. None of these require external libraries.

**Exception: python-frontmatter library.** The `python-frontmatter` package could parse PLAN.md frontmatter, but it is an unnecessary dependency. The frontmatter is delimited by `---` markers and is valid YAML. A 10-line parser using `yaml.safe_load()` on the text between the first two `---` markers is sufficient and avoids a new dependency. This is the same approach the project uses for config loading.

## Common Pitfalls

### Pitfall 1: Session-to-Plan Association

**What goes wrong:** The pipeline ingests a JSONL session file by `session_id` (a UUID), but has no built-in way to know which PLAN.md that session was executing. Without this association, the detector cannot load the correct EBC.

**Why it happens:** Sessions are raw JSONL files in `~/.claude/projects/{project}/`. They contain no explicit reference to a GSD plan number.

**How to avoid:** The association must be established through one of these mechanisms (in order of reliability):
1. **Session metadata in the session events themselves.** Claude Code session JSONL often includes the initial prompt which may reference the plan. Search for patterns like "Plan 22-01" or "PLAN.md" in early user messages.
2. **Temporal correlation.** Match the session timestamp to the plan execution window (STATE.md tracks "Last activity" per phase).
3. **Manual specification.** The `extract` CLI could accept a `--plan` flag: `python -m src.pipeline.cli extract session.jsonl --plan 22-01`.
4. **Convention-based.** If a session modifies files that exactly match a PLAN.md's `files_modified`, that's strong evidence.

**Recommended approach:** Combine (1) and (3). Support an optional `--plan` flag on the extract command, and attempt automatic detection from session content as a fallback.

**Warning signs:** If drift detection is firing on every session, the session-to-plan association is likely wrong.

### Pitfall 2: files_modified is Not files_read

**What goes wrong:** The PLAN.md `files_modified` list says which files should be written. But during execution, the agent also reads many files (via Read, Glob, Grep) that are not in `files_modified`. If the detector treats all file accesses as "touching" and compares against `files_modified`, it will produce false-positive drift alerts on every session.

**Why it happens:** Confusing "scope of modification" with "scope of interaction."

**How to avoid:** Distinguish file operations:
- **Write-class operations** (Edit, Write, Bash mutations): compare against `files_modified`
- **Read-class operations** (Read, Glob, Grep): do NOT trigger drift alerts
- This mirrors the pipeline's existing distinction: `EscalationConfig.exempt_tools` = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task"]

**Warning signs:** If every session shows files "outside contract," the detector is counting reads as modifications.

### Pitfall 3: STATE.md Corruption

**What goes wrong:** The STATE.md injector writes a malformed block, duplicates the alert section, or overwrites unrelated content.

**Why it happens:** STATE.md is a human-edited markdown file with no guaranteed structure. The injector makes assumptions about section headers that may not hold.

**How to avoid:**
1. Use a clearly-delimited sentinel pattern: `<!-- EBC_DRIFT_ALERTS_START -->` / `<!-- EBC_DRIFT_ALERTS_END -->` HTML comments that are invisible in markdown rendering.
2. If the sentinel exists, replace the content between sentinels.
3. If the sentinel does not exist, append the sentinel block at the end of the file (safest default).
4. Never use regex replacement on arbitrary STATE.md content.
5. Write a test that verifies injection on the actual current STATE.md file.

**Warning signs:** Merge conflicts in STATE.md after running the pipeline.

### Pitfall 4: Over-Sensitive Drift Scoring

**What goes wrong:** Minor deviations (a test helper file, an `__init__.py` update) trigger drift alerts, making the system noisy and ignored.

**Why it happens:** The drift score treats all unexpected files equally.

**How to avoid:**
- Weight unexpected file types: `__init__.py` and `__pycache__` = 0 weight. Test files = low weight. Source files outside scope = high weight.
- Only alert if drift score exceeds a configurable threshold (default: suggest 0.5).
- Allow a "tolerance set" in the EBC: commonly-modified infrastructure files that don't indicate mode-switch.

### Pitfall 5: No EBC Available (Graceful Degradation)

**What goes wrong:** The detector crashes or produces misleading alerts when no PLAN.md is associated with the session.

**Why it happens:** Not all sessions are plan-driven. Ad hoc exploration sessions, debugging sessions, and non-GSD projects will have no EBC.

**How to avoid:** The detector must return `None` (no alert) when no EBC is available. Log a DEBUG message: "No EBC found for session {session_id}, skipping drift detection." Never raise an exception.

## Code Examples

### EBC Schema (Pydantic Model)

```python
# src/pipeline/ebc/models.py
from pydantic import BaseModel, Field

class EBCArtifact(BaseModel, frozen=True):
    """Expected artifact from must_haves.artifacts."""
    path: str
    provides: str = ""
    exports: list[str] = Field(default_factory=list)
    contains: str = ""

class EBCKeyLink(BaseModel, frozen=True):
    """Expected code link from must_haves.key_links."""
    from_path: str = Field(..., alias="from")
    to_target: str = Field(..., alias="to")
    via: str = ""
    pattern: str = ""

class ExternalBehavioralContract(BaseModel, frozen=True):
    """EBC parsed from a PLAN.md frontmatter + must_haves section."""
    phase: str
    plan: int | str
    plan_type: str = "execute"
    wave: int = 1
    depends_on: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    autonomous: bool = True
    truths: list[str] = Field(default_factory=list)
    artifacts: list[EBCArtifact] = Field(default_factory=list)
    key_links: list[EBCKeyLink] = Field(default_factory=list)

    @property
    def expected_write_paths(self) -> set[str]:
        """All paths where writes are expected."""
        paths = set(self.files_modified)
        for artifact in self.artifacts:
            paths.add(artifact.path)
        return paths
```

### PLAN.md Frontmatter Parser

```python
# src/pipeline/ebc/parser.py
import yaml
from pathlib import Path
from src.pipeline.ebc.models import ExternalBehavioralContract

def parse_ebc_from_plan(plan_path: str | Path) -> ExternalBehavioralContract | None:
    """Parse a PLAN.md file's frontmatter into an EBC.

    Returns None if the file has no valid frontmatter.
    """
    plan_path = Path(plan_path)
    if not plan_path.exists():
        return None

    text = plan_path.read_text()
    if not text.startswith("---"):
        return None

    # Extract YAML between first two --- markers
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None

    if not isinstance(frontmatter, dict):
        return None

    # Extract must_haves fields
    must_haves = frontmatter.pop("must_haves", {})
    if isinstance(must_haves, dict):
        frontmatter["truths"] = must_haves.get("truths", [])
        frontmatter["artifacts"] = must_haves.get("artifacts", [])
        frontmatter["key_links"] = must_haves.get("key_links", [])

    # Rename 'type' to 'plan_type' to avoid Pydantic conflict
    if "type" in frontmatter:
        frontmatter["plan_type"] = frontmatter.pop("type")

    return ExternalBehavioralContract(**frontmatter)
```

### Drift Detection Core Logic

```python
# src/pipeline/ebc/detector.py
from dataclasses import dataclass

@dataclass
class DriftSignal:
    """A single drift signal contributing to the overall score."""
    signal_type: str  # "unexpected_file", "missing_expected_file", "no_progress"
    detail: str
    weight: float

class EBCDriftDetector:
    WRITE_TOOLS = frozenset({"Edit", "Write"})
    BASH_WRITE_INDICATORS = frozenset({"mkdir", "cp ", "mv ", "touch ", "> ", ">> ", "tee "})

    def detect(
        self,
        ebc: ExternalBehavioralContract,
        session_events: list[dict],
        tagged_events: list,
        valid_episodes: list[dict],
    ) -> EBCDriftAlert | None:
        signals: list[DriftSignal] = []

        # 1. Extract actual files written from session events
        actual_writes = self._extract_write_paths(session_events)

        # 2. Files written but NOT in EBC
        unexpected = actual_writes - ebc.expected_write_paths
        for f in unexpected:
            weight = self._file_weight(f)
            signals.append(DriftSignal("unexpected_file", f, weight))

        # 3. Files in EBC but NOT written
        missing = ebc.expected_write_paths - actual_writes
        for f in missing:
            signals.append(DriftSignal("missing_expected_file", f, 0.3))

        # 4. Compute drift score
        if not signals:
            return None

        drift_score = sum(s.weight for s in signals) / max(len(ebc.expected_write_paths), 1)
        drift_score = min(drift_score, 1.0)

        if drift_score < self._threshold:
            return None

        return EBCDriftAlert(
            session_id=...,
            drift_score=drift_score,
            signals=signals,
            ebc_phase=ebc.phase,
            ebc_plan=str(ebc.plan),
        )
```

### Alert Artifact Writer

```python
# src/pipeline/ebc/writer.py
import json
from pathlib import Path
from src.pipeline.ebc.models import EBCDriftAlert

ALERTS_DIR = Path("data/alerts")

def write_alert(alert: EBCDriftAlert) -> Path:
    """Write an EBC drift alert to data/alerts/.

    Returns the path to the written file.
    """
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{alert.session_id}-ebc-drift.json"
    out_path = ALERTS_DIR / filename
    out_path.write_text(
        alert.model_dump_json(indent=2) + "\n"
    )
    return out_path
```

### STATE.md Injector

```python
# src/pipeline/ebc/state_injector.py
from pathlib import Path

SENTINEL_START = "<!-- EBC_DRIFT_ALERTS_START -->"
SENTINEL_END = "<!-- EBC_DRIFT_ALERTS_END -->"

def inject_alert_into_state(
    state_path: Path,
    alert_block: str,
) -> bool:
    """Inject or update the EBC drift alert section in STATE.md.

    Uses HTML comment sentinels for safe replacement.
    Returns True if the file was modified.
    """
    if not state_path.exists():
        return False

    content = state_path.read_text()

    new_section = f"{SENTINEL_START}\n## EBC Drift Alerts\n\n{alert_block}\n{SENTINEL_END}"

    if SENTINEL_START in content:
        # Replace existing section
        import re
        pattern = re.escape(SENTINEL_START) + r".*?" + re.escape(SENTINEL_END)
        content = re.sub(pattern, new_section, content, flags=re.DOTALL)
    else:
        # Append before Performance Metrics (or at end)
        marker = "## Performance Metrics"
        if marker in content:
            content = content.replace(marker, new_section + "\n\n" + marker)
        else:
            content = content.rstrip() + "\n\n" + new_section + "\n"

    state_path.write_text(content)
    return True
```

### Runner Integration

```python
# In src/pipeline/runner.py, after Step 22 (compute stats), before return:

# Step 23: EBC Drift Detection (Phase 23)
ebc_drift_detected = False
try:
    from src.pipeline.ebc.detector import EBCDriftDetector as _EBCDriftDetector
    from src.pipeline.ebc.parser import parse_ebc_from_plan as _parse_ebc
    from src.pipeline.ebc.writer import write_alert as _write_alert

    # Attempt to find the plan associated with this session
    ebc = self._resolve_ebc_for_session(session_id, valid_episodes)
    if ebc is not None:
        detector = _EBCDriftDetector(self._config)
        alert = detector.detect(ebc, all_session_events, tagged_events, valid_episodes)
        if alert is not None:
            alert_path = _write_alert(alert)
            logger.warning("EBC DRIFT detected for session {}: score={:.2f}, alert={}",
                           session_id, alert.drift_score, alert_path)
            ebc_drift_detected = True
except ImportError:
    pass
except Exception as e:
    logger.warning("EBC drift detection failed: {}", e)
    warnings.append(f"EBC drift detection failed: {e}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No behavioral contract | PLAN.md frontmatter as implicit contract | Phases 1-22 | Contract exists but is not machine-enforced |
| Manual mode-switch detection (human notices) | Automated post-hoc detection | Phase 23 (this phase) | Detects drift before false completions accumulate |
| Alerts only in loguru | Persistent alert artifacts + STATE.md injection | Phase 23 (this phase) | Alerts survive session boundaries |

**Deprecated/outdated:**
- None. This is a new capability with no predecessor to deprecate.

## Open Questions

1. **Session-to-Plan association mechanism**
   - What we know: Sessions are UUID-named JSONL files; PLAN.md files are numbered. No current link exists in the data model.
   - What's unclear: The best primary mechanism. Option A (CLI `--plan` flag) is explicit but requires user input. Option B (content-based detection from early messages) is automatic but fragile.
   - Recommendation: Implement both. `--plan` flag takes priority; content-based detection is the fallback. For batch mode, support a `--plan-dir` flag pointing to the `.planning/phases/{phase}/` directory so the detector can try to match sessions to plans by file overlap.

2. **Drift threshold default**
   - What we know: A score of 0.0 = perfect contract adherence. A score of 1.0 = complete divergence.
   - What's unclear: What default threshold minimizes false positives while catching real mode-switches.
   - Recommendation: Start with 0.5 (configurable in `data/config.yaml`). Tune based on first few runs. Log all drift scores (even sub-threshold) at DEBUG level for calibration.

3. **STATE.md injection timing**
   - What we know: STATE.md injection is useful for the next session to see the warning.
   - What's unclear: Whether injection should happen during `run_session()` (automatic) or only on CLI demand.
   - Recommendation: Make it opt-in via a `--inject-state` flag on the extract command, not automatic. STATE.md is human-maintained; automatic writes could surprise the user. The `/project:autonomous-loop-mode-switch` command can trigger injection explicitly.

4. **Multi-plan sessions**
   - What we know: Some sessions span multiple plans (e.g., the user runs Plan 01, then Plan 02 in the same session).
   - What's unclear: How to handle EBC drift when the session has multiple contracts.
   - Recommendation: For Phase 23, support one EBC per session (the primary plan). Multi-plan detection is a future enhancement.

5. **What signals indicate Discovery Mode?**
   - What we know: "Discovery Mode" means the agent is exploring/investigating rather than executing the plan. Signals: heavy Read/Grep/Glob usage, no Write/Edit operations, accessing files far outside `files_modified`, web searches, repeated error loops.
   - What's unclear: How to weight these signals relative to each other.
   - Recommendation: Start with file-set comparison as the primary signal (it's the most concrete). Add behavioral pattern detection (tool usage ratios, error loops) as secondary signals in Wave 2.

## Key Design Decisions for Planner

### Decision 1: Where to store the EBC

The EBC is parsed on-demand from the PLAN.md frontmatter. It is NOT stored in DuckDB. Rationale: the EBC is a static contract derived from an existing artifact; caching it in DuckDB adds complexity (staleness, schema migration) without benefit.

### Decision 2: Alert persistence format

Alerts go to `data/alerts/{session_id}-ebc-drift.json` as standalone JSON files. They are NOT stored in a DuckDB table. Rationale: (a) git-trackable, (b) human-readable without tooling, (c) analogous to `data/constraints.json` pattern.

### Decision 3: Runner integration point

EBC drift detection runs AFTER episode population and validation (Step 22 in current runner) but BEFORE the stats return. It needs `valid_episodes` and `all_session_events` which are available at that point. It follows the ImportError-safe pattern used by all optional subsystems (DDF, premise, structural).

### Decision 4: Config section

Add an `ebc_drift` section to `data/config.yaml` and a corresponding `EBCDriftConfig` Pydantic sub-model on `PipelineConfig`:

```yaml
ebc_drift:
  enabled: true
  threshold: 0.5
  inject_state: false
  tolerance_patterns:
    - "__init__.py"
    - "__pycache__"
    - "*.pyc"
  write_tool_names:
    - "Edit"
    - "Write"
  bash_write_indicators:
    - "mkdir"
    - "cp "
    - "mv "
    - "touch "
    - "> "
    - ">> "
```

### Decision 5: Wave structure recommendation

- **Wave 1:** EBC model + parser + detector (file-set comparison only) + alert writer + runner integration + basic tests
- **Wave 2:** STATE.md injector + `/project:autonomous-loop-mode-switch` command + behavioral pattern detection (tool ratios, error loops)
- **Wave 3:** Auto session-to-plan association + batch mode support + integration tests on real data

## Sources

### Primary (HIGH confidence)
- `src/pipeline/runner.py` -- Pipeline runner: 22-step pipeline with ImportError-safe optional subsystem pattern (lines 477-1016)
- `src/pipeline/escalation/detector.py` -- EscalationDetector pattern: `__init__(config)`, `.detect(events) -> list[Candidate]` (lines 37-131)
- `src/pipeline/escalation/models.py` -- Pydantic frozen model pattern for detection artifacts (lines 16-63)
- `src/pipeline/models/config.py` -- Config sub-model pattern: Pydantic BaseModel + Field(default_factory=) + wired into PipelineConfig (lines 158-311)
- `src/pipeline/storage/schema.py` -- Schema pattern: CREATE TABLE IF NOT EXISTS, ALTER TABLE for backward-compatible extensions (lines 50-411)
- `.planning/phases/22-*/22-01-PLAN.md` -- PLAN.md frontmatter structure with files_modified, autonomous, must_haves (lines 1-40)
- `.planning/phases/15-*/15-01-PLAN.md` -- PLAN.md frontmatter with must_haves.artifacts and key_links (lines 1-48)
- `.planning/phases/09-*/09-01-PLAN.md` -- PLAN.md frontmatter demonstrating full contract shape (lines 1-50)
- `data/config.yaml` -- Configuration convention: YAML sections loaded by Pydantic models (355 lines)
- `.claude/commands/add-project.md` -- Local project command pattern: markdown file with instructions (11 lines)
- `.claude/commands/query.md` -- Local project command pattern: detailed usage guide with examples (99 lines)
- `.planning/STATE.md` -- STATE.md structure: Current Position section + Performance Metrics (100+ lines)
- `data/projects.json` -- JSON artifact convention: standalone, git-tracked, human-readable (89 lines)
- `src/pipeline/cli/__main__.py` -- CLI registration pattern: click.group + add_command (68 lines)

### Secondary (MEDIUM confidence)
- Analysis of 93 PLAN.md files across all phases for consistent frontmatter structure

### Tertiary (LOW confidence)
- None. All findings are from direct codebase evidence.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in use, no new dependencies
- Architecture: HIGH - follows established patterns from 22 prior phases (detector, models, runner integration, config, CLI)
- Pitfalls: HIGH - derived from direct analysis of data model gaps (session-to-plan association) and file operation semantics (read vs write)

**Research date:** 2026-02-27
**Valid until:** 2026-03-29 (stable internal domain; no external dependency drift)
