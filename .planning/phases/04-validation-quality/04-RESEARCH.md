# Phase 4: Validation & Quality - Research

**Researched:** 2026-02-11
**Domain:** Episode validation, quality metrics, gold-standard labeling, Parquet export
**Confidence:** HIGH

## Summary

Phase 4 builds a multi-layer validation system on top of the existing pipeline (Phases 1-3), extending the current single-layer `EpisodeValidator` (JSON Schema only) into a five-layer "genus-based" validator as specified in the Authoritative Design doc (Part 5). The existing codebase provides strong foundations: a `EpisodeValidator` class already handles JSON Schema validation (Layer A), a `ConstraintStore` with `.constraints` read-only access exists (needed for Layer D), and DuckDB natively supports Parquet export with `COPY TO` (no pyarrow dependency needed).

The three requirements (VALID-01, VALID-02, VALID-03) decompose into four work areas: (1) extending the validator with four new check layers beyond schema validation, (2) building a manual validation CLI workflow that exports episodes for human review and imports verified labels to create a gold-standard dataset, (3) computing quality metrics by comparing pipeline output against the gold-standard set, and (4) adding Parquet export capability for ML training pipelines. The work is primarily Python, uses libraries already in the project (pydantic, jsonschema, duckdb, click), and requires no new external dependencies.

**Primary recommendation:** Extend `EpisodeValidator` with pluggable validation layers (schema, evidence grounding, non-contradiction, constraint enforcement, episode integrity), build a gold-standard workflow as a CLI subcommand using JSON files for human annotation, compute metrics using standard accuracy/precision calculations against the gold set, and export validated episodes to Parquet via DuckDB's native COPY command.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.0 (installed: 2.11.7) | Episode model validation, config models | Already used throughout project; frozen models enforce immutability |
| jsonschema | >=4.20 (installed: 4.25.1) | JSON Schema validation (Layer A) | Already used in EpisodeValidator; Draft 2020-12 support |
| duckdb | >=1.0 (installed: 1.4.4) | Episode storage, Parquet export, SQL queries for metrics | Already the project database; native Parquet COPY TO works without pyarrow |
| click | >=8.0 (installed) | CLI for validation workflow and export commands | Already used for extract CLI |
| loguru | >=0.7 (installed) | Structured logging for validation results | Already used throughout pipeline |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | N/A | Gold-standard label file I/O, constraint store reading | All manual validation workflows |
| collections.Counter (stdlib) | N/A | Metric computation (accuracy, confusion matrices) | Quality metrics calculation |
| pathlib (stdlib) | N/A | File path handling for export | Export and I/O operations |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB native Parquet | pyarrow for Parquet export | pyarrow adds 150MB+ dependency; DuckDB COPY TO handles Parquet natively including STRUCT columns -- verified working with this project's schema |
| JSON gold-standard files | SQLite for gold-standard labels | JSON is simpler, human-readable, diff-friendly in git; project already uses JSON for constraints.json |
| Manual CLI workflow | Web UI for labeling | Web UI is heavy for 100+ episodes; CLI + JSON is sufficient for v1, MC-03 provides web UI in Phase 6 |
| Custom metric calculations | scikit-learn metrics | sklearn would add dependency for simple accuracy/precision/recall calculations; stdlib math is sufficient for >=85%/>=80%/>=90% threshold checks |

**Installation:**
```bash
# No new dependencies needed -- all libraries already installed
```

## Architecture Patterns

### Recommended Project Structure
```
src/pipeline/
    validation/                    # NEW: Phase 4 validation module
        __init__.py
        genus_validator.py         # Multi-layer validator (VALID-01)
        layers.py                  # Individual validation layer implementations
        gold_standard.py           # Gold-standard workflow (VALID-02)
        metrics.py                 # Quality metrics calculator (VALID-03)
        exporter.py                # Parquet export (Success Criterion 4)
    episode_validator.py           # EXISTING: Keep as-is, wrap in genus validator Layer A
    constraint_store.py            # EXISTING: Read-only access for Layer D
    constraint_extractor.py        # EXISTING: Rate measurement for VALID-03
src/pipeline/cli/
    extract.py                     # EXISTING: Extend with validation and export subcommands
    validate.py                    # NEW: CLI for validation workflow
data/
    schemas/
        orchestrator-episode.schema.json  # EXISTING
        constraint.schema.json            # EXISTING
        gold-standard-label.schema.json   # NEW: Schema for human review labels
    gold-standard/                 # NEW: Gold-standard labeled episodes
        episodes/                  # Exported episodes for review (JSON)
        labels/                    # Human-verified labels (JSON)
        metrics/                   # Computed quality reports (JSON)
```

### Pattern 1: Layered Validator (Chain of Responsibility)
**What:** Each validation layer is a separate callable that returns (pass/fail, list[str] errors). The GenusValidator runs all layers in sequence, collecting errors, and rejects episodes that fail any layer.
**When to use:** When validation has multiple independent concerns that each contribute pass/fail signals.
**Example:**
```python
# Source: Project design (AUTHORITATIVE_DESIGN.md Part 5)
from typing import Protocol

class ValidationLayer(Protocol):
    """Protocol for pluggable validation layers."""
    def validate(self, episode: dict) -> tuple[bool, list[str]]:
        """Return (is_valid, error_messages)."""
        ...

class GenusValidator:
    """Five-layer genus-based validator per AUTHORITATIVE_DESIGN.md Part 5."""

    def __init__(self, layers: list[ValidationLayer]) -> None:
        self._layers = layers

    def validate(self, episode: dict) -> tuple[bool, list[str]]:
        all_errors: list[str] = []
        for layer in self._layers:
            _, errors = layer.validate(episode)
            all_errors.extend(errors)
        return (len(all_errors) == 0, all_errors)
```

### Pattern 2: Gold-Standard Export/Import Workflow
**What:** Episodes are exported to human-readable JSON files. Humans review and annotate with verified labels. Annotations are imported back and stored as the gold-standard dataset for metric computation.
**When to use:** When building a manually verified reference dataset for accuracy measurement.
**Example:**
```python
# Export episodes for human review
def export_for_review(conn, output_dir: Path, sample_size: int = 100):
    """Export a stratified sample of episodes for human labeling."""
    # Stratify by mode + reaction_label to ensure coverage
    episodes = conn.execute("""
        SELECT episode_id, mode, reaction_label, reaction_confidence,
               orchestrator_action, outcome, observation
        FROM episodes
        ORDER BY RANDOM()
    """).fetchall()
    # Write each as a reviewable JSON with blank fields for human labels

# Import verified labels
def import_labels(label_dir: Path) -> list[dict]:
    """Read human-verified labels from JSON files."""
    labels = []
    for f in sorted(label_dir.glob("*.json")):
        labels.append(json.loads(f.read_text()))
    return labels
```

### Pattern 3: DuckDB Native Parquet Export
**What:** Use DuckDB's built-in `COPY TO` with `FORMAT PARQUET` for training pipeline export. No pyarrow needed.
**When to use:** For all Parquet export needs.
**Example:**
```python
# Source: Verified via local testing (DuckDB 1.4.4)
def export_parquet(conn, output_path: str, query: str | None = None):
    """Export validated episodes to Parquet format."""
    if query is None:
        query = "SELECT * FROM episodes WHERE reaction_label IS NOT NULL"
    conn.execute(f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET)")
```

### Anti-Patterns to Avoid
- **Monolithic validator:** Don't put all five layers in one method. Each layer is a separate class/function so they can be tested independently and enabled/disabled per config.
- **Hardcoded thresholds:** Don't hardcode 85%/80%/90% in code. Put thresholds in config.yaml so they can be tuned.
- **Gold-standard as DuckDB table:** Don't store gold-standard labels in DuckDB. Use JSON files in `data/gold-standard/` for version control, human readability, and git diffing.
- **Blocking validation in pipeline:** The existing pipeline Step 10 already validates. Don't break the pipeline runner. Phase 4 adds a *separate* deeper validation pass that can run post-pipeline as a quality assurance step.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation | Custom field-by-field checking | jsonschema library (already used in EpisodeValidator) | Edge cases in schema validation are numerous; jsonschema handles Draft 2020-12 correctly |
| Parquet file generation | Custom binary Parquet writer | DuckDB `COPY TO FORMAT PARQUET` | DuckDB handles Parquet natively including STRUCT columns; tested and confirmed working |
| Confusion matrix math | Custom accuracy calculation | collections.Counter + simple division | Standard accuracy = correct/total; no need for sklearn for these basic metrics |
| Episode sampling | Custom random sampling | DuckDB `ORDER BY RANDOM() LIMIT N` or stratified SQL query | DuckDB handles sampling efficiently with SQL |

**Key insight:** Phase 4 is primarily about *composing* existing components (validator, constraint store, DuckDB, CLI) into new workflows. The complexity is in the validation logic rules, not in new library integration.

## Common Pitfalls

### Pitfall 1: Validator Layer Ordering Matters
**What goes wrong:** Running expensive layers (evidence grounding) before cheap layers (schema validity) wastes time on episodes that would fail basic checks.
**Why it happens:** Natural tendency to implement layers in conceptual order rather than performance order.
**How to avoid:** Layer A (schema) runs first and short-circuits. Only structurally valid episodes proceed to layers B-E.
**Warning signs:** Slow validation times, evidence grounding errors that are actually schema failures.

### Pitfall 2: Gold-Standard Label Format Drift
**What goes wrong:** Human annotators add fields or use slightly different values than the schema expects, making import fail silently.
**Why it happens:** JSON is flexible; without schema enforcement on the label files, anything goes.
**How to avoid:** Define a `gold-standard-label.schema.json` and validate label files on import. Provide a template with the export.
**Warning signs:** Import succeeds but metrics show 0% accuracy because labels don't match expected format.

### Pitfall 3: Metric Denominators Can Be Zero
**What goes wrong:** Division by zero when computing accuracy for categories with no gold-standard examples (e.g., no "block" reactions in the sample).
**Why it happens:** Stratified sampling may still miss rare labels; 100 episodes may not cover all 6 reaction types.
**How to avoid:** Always check denominators. Report "N/A" for metrics with insufficient samples. Require minimum sample sizes per label in the gold-standard spec.
**Warning signs:** Metrics report 100% accuracy (actually 0/0) or crash with ZeroDivisionError.

### Pitfall 4: Constraint Enforcement Without Scope Matching
**What goes wrong:** Layer D (constraint enforcement) flags all episodes as violations because it checks repo-wide constraints against episodes that touch different files.
**Why it happens:** Constraints have scope (paths). Enforcement must match episode's scope.paths against constraint's scope.paths.
**How to avoid:** Implement scope intersection logic: a constraint applies to an episode only if their scope paths overlap or the constraint is repo-wide (empty paths).
**Warning signs:** 100% of episodes flagged by constraint enforcement; all constraints appear violated.

### Pitfall 5: Evidence Grounding Layer Too Strict
**What goes wrong:** Layer B (evidence grounding) rejects valid episodes because the heuristic rules are too rigid (e.g., "Implement mode must have tests" -- but not all implementations have tests yet).
**Why it happens:** Design doc lists aspirational checks; real data is messy.
**How to avoid:** Make evidence grounding checks produce warnings (not hard failures) initially. Track rates. Tighten thresholds after measuring on real data.
**Warning signs:** >50% of episodes fail evidence grounding layer; validators reject more than they accept.

## Code Examples

### Existing EpisodeValidator (Layer A Foundation)
```python
# Source: src/pipeline/episode_validator.py (existing)
# This becomes Layer A of the GenusValidator
class EpisodeValidator:
    def validate(self, episode_dict: dict) -> tuple[bool, list[str]]:
        errors = []
        for error in self._validator.iter_errors(episode_dict):
            path = ".".join(str(p) for p in error.absolute_path)
            errors.append(f"{path}: {error.message}" if path else error.message)
        errors.extend(self._check_business_rules(episode_dict))
        return (len(errors) == 0, errors)
```

### ConstraintStore Read Access (Layer D Foundation)
```python
# Source: src/pipeline/constraint_store.py (existing)
# Phase 4 Layer D reads constraints via this interface
store = ConstraintStore(
    path=Path("data/constraints.json"),
    schema_path=Path("data/schemas/constraint.schema.json"),
)
constraints = store.constraints  # Read-only list[dict]
# Each constraint has: constraint_id, text, severity, scope.paths, detection_hints
```

### DuckDB Parquet Export (Verified)
```python
# Source: Verified via local testing (DuckDB 1.4.4, 2026-02-11)
# DuckDB exports STRUCT columns to Parquet natively
conn.execute("""
    COPY (
        SELECT episode_id, session_id, timestamp, mode, risk,
               reaction_label, reaction_confidence, outcome_type,
               observation, orchestrator_action, outcome, provenance
        FROM episodes
        WHERE reaction_label IS NOT NULL
    ) TO 'data/export/episodes.parquet' (FORMAT PARQUET)
""")
# Partitioned export by mode:
conn.execute("""
    COPY episodes TO 'data/export/by_mode' (FORMAT PARQUET, PARTITION_BY (mode))
""")
```

### Quality Metrics Computation Pattern
```python
# Source: Standard accuracy calculation pattern
def compute_mode_accuracy(gold_labels: list[dict], pipeline_episodes: dict) -> dict:
    """Compare pipeline mode inference against human-verified modes."""
    correct = 0
    total = 0
    for label in gold_labels:
        episode_id = label["episode_id"]
        if episode_id in pipeline_episodes:
            total += 1
            if pipeline_episodes[episode_id]["mode"] == label["verified_mode"]:
                correct += 1
    accuracy = correct / total if total > 0 else None
    return {"accuracy": accuracy, "correct": correct, "total": total}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pyarrow for Parquet | DuckDB native COPY TO | DuckDB 0.9+ (2023) | Eliminates 150MB+ dependency; simpler code |
| Single-pass validation | Layered validation with Protocol classes | Pydantic v2 / Python 3.10+ | Clean separation of concerns; each layer testable |
| Manual CSV/Excel labeling | JSON-file-based gold-standard workflow | Industry standard for structured data | Git-trackable, schema-validated, machine-readable |

**Deprecated/outdated:**
- pyarrow as required dependency for Parquet: DuckDB 1.x handles Parquet natively
- jsonschema <4.18: Older versions lack Draft 2020-12 support

## Open Questions

1. **Evidence Grounding Strictness Level**
   - What we know: Design doc (Part 5.2.B) specifies checks like "If Implement chosen: clear requirements stated? Relevant files inspected?" These are aspirational for a rule-based system.
   - What's unclear: How strict should Layer B be in v1? Should failures be errors (reject episode) or warnings (flag but accept)?
   - Recommendation: Start with warnings-only for evidence grounding. Measure violation rates on real data. Promote to errors only after confirming <20% false positive rate.

2. **Gold-Standard Sample Size Distribution**
   - What we know: Target is 100+ episodes with verified mode/reaction labels. 7 modes and 6 reaction types = 42 possible combinations.
   - What's unclear: What stratification ensures meaningful accuracy measurement for rare categories (e.g., "block" reactions, "Triage" mode)?
   - Recommendation: Stratified sampling weighted toward ensuring minimum 5 examples per mode and per reaction label. Accept that some rare combinations may have N/A metrics.

3. **Non-Contradiction Layer Scope**
   - What we know: Design doc lists specific contradictions to check (Explore + write_allowed, no_network + "look up docs"). These are mode-specific semantic rules.
   - What's unclear: How many non-contradiction rules are needed for v1? What's the balance between coverage and false positives?
   - Recommendation: Implement the three explicit rules from the design doc (Explore+write, gate+instruction contradiction, no_write_before_plan+Implement). Extend based on real data analysis.

4. **Constraint Enforcement Detection Methodology**
   - What we know: Constraints have detection_hints (patterns) and scope (paths). Episodes have orchestrator_action.scope and executor_effects.
   - What's unclear: Should constraint enforcement check the episode's *intended* action or the *actual* outcome? Both?
   - Recommendation: Check both: (a) does the action's scope overlap with forbidden constraint scopes? (b) do executor_effects contain patterns matching detection_hints? Report separately.

## Validation Layer Design Detail

### Layer A: Schema Validity (EXISTING)
- Wraps existing `EpisodeValidator.validate()`
- Checks: All required fields present, enum values valid, types correct, provenance non-empty
- Confidence: HIGH -- already implemented and tested (14 tests)

### Layer B: Evidence Grounding
- Checks: Mode-specific evidence requirements
  - Explore: observation.context.recent_summary should show uncertainty/investigation
  - Plan: observation should reference prior exploration or requirements
  - Implement: should have scope.paths defined (not empty)
  - Verify: outcome should include test/lint results
  - Integrate: outcome should include git_events
- Confidence: MEDIUM -- rules are heuristic; will need tuning on real data

### Layer C: Non-Contradiction
- Checks: Mode/gate/instruction consistency
  - mode=Explore but executor_effects has large file changes -> flag
  - gate type conflicts with instruction content
  - mode=Implement with no scope paths -> warning
- Confidence: MEDIUM -- three specific rules from design doc; extensible

### Layer D: Constraint Enforcement
- Checks: Episode actions against stored constraints
  - Scope overlap check (constraint paths vs episode paths)
  - Detection hint pattern matching against executor effects
  - Severity-aware: forbidden = error, requires_approval = warning, warning = info
- Confidence: HIGH -- ConstraintStore already provides read-only access

### Layer E: Episode Integrity
- Checks: Temporal and structural coherence
  - timestamp is valid and not in the future
  - observation precedes action (implicit in structure)
  - provenance sources reference valid file paths
  - episode_id is deterministic and non-empty
  - reaction label attached to correct boundary (confidence > 0)
- Confidence: HIGH -- straightforward structural checks

## Sources

### Primary (HIGH confidence)
- `src/pipeline/episode_validator.py` -- existing Layer A implementation, 169 lines, 14 tests
- `src/pipeline/constraint_store.py` -- existing constraint access, 193 lines, `.constraints` property
- `src/pipeline/constraint_extractor.py` -- constraint structure reference, 277 lines
- `src/pipeline/runner.py` -- pipeline integration points (Steps 10-12), 688 lines
- `src/pipeline/storage/writer.py` -- DuckDB episode write/read patterns, 745 lines
- `src/pipeline/storage/schema.py` -- DuckDB episodes table schema, 197 lines
- `data/schemas/orchestrator-episode.schema.json` -- full episode schema, 476 lines
- `data/schemas/constraint.schema.json` -- constraint schema, 64 lines
- `docs/design/AUTHORITATIVE_DESIGN.md` -- Part 5: Genus-Based Validation spec, Part 11: Success Criteria
- `.planning/REQUIREMENTS.md` -- VALID-01, VALID-02, VALID-03 requirement definitions
- `.planning/ROADMAP.md` -- Phase 4 success criteria
- Local DuckDB 1.4.4 testing: confirmed native Parquet export works with STRUCT columns

### Secondary (MEDIUM confidence)
- `docs/design/The Genus Method.md` -- philosophical grounding for "genus-based" validation approach
- `src/pipeline/models/episodes.py` -- Episode Pydantic model, 363 lines (informs validation rules)
- `src/pipeline/models/config.py` -- PipelineConfig with ValidationConfig, 253 lines
- `src/pipeline/reaction_labeler.py` -- reaction labeling logic (baseline for gold-standard comparison)
- `src/pipeline/populator.py` -- mode inference logic (baseline for gold-standard comparison)

### Tertiary (LOW confidence)
- None -- all findings verified against existing codebase and local testing

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and in use; no new dependencies
- Architecture: HIGH - Extends existing patterns (validator, store, CLI); clear integration points
- Pitfalls: HIGH - Derived from direct codebase analysis and testing
- Validation layers: MEDIUM - Layers B (evidence) and C (non-contradiction) are heuristic and will need tuning
- Quality metrics: HIGH - Standard accuracy computation; thresholds defined in requirements
- Parquet export: HIGH - Verified working via local DuckDB testing including STRUCT columns

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (stable domain; no external dependency changes expected)
