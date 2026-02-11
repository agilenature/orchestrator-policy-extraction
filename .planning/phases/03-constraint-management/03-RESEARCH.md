# Phase 3: Constraint Management - Research

**Researched:** 2026-02-11
**Domain:** Constraint extraction from reactions, severity assignment, scope inference, version-controlled JSON store, pipeline integration
**Confidence:** HIGH (verified against Phase 2 codebase, existing constraint schema, reaction labeler output, and design spec Stage F)

---

## Summary

Phase 3 converts corrections and blocks from Phase 2's reaction labels into durable, enforceable orchestration constraints. The input is the populated `episodes` table in DuckDB, specifically episodes where `reaction_label IN ('correct', 'block')`. The output is a `data/constraints.json` file containing structured constraint objects (text, severity, scope, detection_hints) and -- optionally -- back-populating the episode's `constraints_extracted` array field.

The technical challenge is modest: the constraint schema already exists (`data/schemas/constraint.schema.json`), the Pydantic models already exist (`ConstraintRef`, `ConstraintScope` in `src/pipeline/models/episodes.py`), and the config already has `constraint_patterns` with keyword categories (forbidden, required, preferred). Phase 3's core work is (1) a `ConstraintExtractor` class that takes a reaction message + episode context and produces a constraint object, (2) a `ConstraintStore` that manages the `data/constraints.json` file with deduplication and version tracking, and (3) pipeline integration to run constraint extraction as a new stage after reaction labeling.

The design spec (AUTHORITATIVE_DESIGN.md, Stage F) is concise and prescriptive: block reactions map to `forbidden` severity, correct reactions map to `requires_approval` or `warning`, scope comes from mentioned paths (defaulting to narrowest applicable), and detection hints are extracted from command patterns, forbidden strings, file globs, and library names. The constraint_patterns config already defines keyword categories for these mappings. The existing `_extract_scope_paths()` method in `EpisodePopulator` already extracts file paths from text using regex -- this same approach applies for scope inference.

**Primary recommendation:** Build a `ConstraintExtractor` class (regex-based text analysis using existing constraint_patterns config) and a `ConstraintStore` class (JSON file I/O with deduplication) as two new modules. Wire into `PipelineRunner` as a new Step 12 after episode validation/storage. Back-populate `constraints_extracted` on episodes in DuckDB. Use TDD following the Phase 2 pattern.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **json** | stdlib | Constraint JSON file I/O | data/constraints.json is a plain JSON file; no special library needed |
| **re** | stdlib | Keyword matching, path extraction, detection hint patterns | Same regex approach used by ReactionLabeler and EpisodePopulator |
| **hashlib** | stdlib | Deterministic constraint IDs | SHA-256 hash of (text + scope) for reproducible, deduplicated IDs |
| **Pydantic** | 2.11.7 (installed) | ConstraintRef model already exists | Frozen model for immutable constraints, `model_dump()` for serialization |
| **jsonschema** | 4.25.1 (installed) | Validate constraints against constraint.schema.json | Same validation pattern as EpisodeValidator |
| **DuckDB** | 1.4.4 (installed) | Read episodes with correct/block reactions, update constraints_extracted | Existing connection and query patterns from Phase 2 |
| **loguru** | 0.7.3 (installed) | Structured logging | Consistent with all pipeline components |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **datetime** | stdlib | created_at timestamps on constraints | ISO 8601 format consistent with episode timestamps |
| **pathlib** | stdlib | File path handling for constraints.json | Consistent with existing file I/O patterns |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSON file store | DuckDB constraints table | JSON file is simpler, version-controlled in git, human-readable, explicitly required by CONST-02. DuckDB table is better for querying but not required until Phase 4/6. |
| Regex keyword matching for severity | LLM-based classification | Over-engineered for Phase 3. Keyword matching against constraint_patterns config handles the defined severity categories well. LLM classification deferred to Phase 4 if needed. |
| Manual deduplication | Fuzzy matching (edit distance, semantic similarity) | ADV-01 explicitly defers fuzzy dedup to v2. Phase 3 uses deterministic hash-based dedup only. |

**Installation:**
```bash
# No new dependencies needed -- all libraries already installed from Phase 1/2
```

---

## Architecture Patterns

### Recommended Project Structure (Phase 3 Additions)

```
src/
  pipeline/
    constraint_extractor.py    # NEW: ConstraintExtractor - extracts constraints from reactions
    constraint_store.py        # NEW: ConstraintStore - manages data/constraints.json
    runner.py                  # EXTEND: Add constraint extraction as new pipeline step
data/
  constraints.json             # NEW: Version-controlled constraint store (created at runtime)
  schemas/
    constraint.schema.json     # EXISTS: Already defined
tests/
  test_constraint_extractor.py # NEW: TDD tests for extraction logic
  test_constraint_store.py     # NEW: TDD tests for JSON store operations
```

### Pattern 1: ConstraintExtractor (Reaction -> Constraint)

**What:** A class that takes an episode dict (with reaction) and produces zero or one `ConstraintRef` objects. Only processes episodes where `reaction_label IN ('correct', 'block')`. Uses the reaction message text, constraint_patterns config, and episode context to derive text, severity, scope, and detection hints.

**When to use:** Every episode with a correct or block reaction should be passed through the extractor.

**Key design detail:** The extractor works in four steps:
1. **Text normalization:** Extract the constraint statement from the reaction message (the correction text IS the constraint, normalized to imperative form)
2. **Severity assignment:** Reaction label + keyword analysis determines severity
3. **Scope inference:** Extract file paths from reaction message + episode scope; default to narrowest applicable
4. **Detection hint extraction:** Find actionable patterns (commands, library names, file globs, forbidden strings)

**Example:**
```python
# Source: Verified against design spec Stage F + existing constraint_patterns config
class ConstraintExtractor:
    """Extracts durable constraints from correct/block reactions."""

    def __init__(self, config: PipelineConfig):
        self._config = config
        self._forbidden_patterns = self._compile_patterns(
            config.constraint_patterns.get("forbidden", [])
        )
        self._required_patterns = self._compile_patterns(
            config.constraint_patterns.get("required", [])
        )
        self._preferred_patterns = self._compile_patterns(
            config.constraint_patterns.get("preferred", [])
        )
        # Reuse scope path extraction regex from populator
        self._scope_path_re = re.compile(
            r'(?:^|\s)((?:[\w.-]+/)+[\w.-]+\.[\w]+|[\w.-]+\.(?:py|js|ts|tsx|jsx|rs|go|java|rb|c|cpp|h|hpp|md|yaml|yml|json|toml|sql|sh|css|html))'
        )

    def extract(self, episode: dict) -> dict | None:
        """Extract a constraint from an episode with correct/block reaction.

        Args:
            episode: Episode dict with outcome.reaction populated.

        Returns:
            Constraint dict matching constraint.schema.json, or None if
            no constraint can be extracted (e.g., approve reaction).
        """
        reaction = episode.get("outcome", {}).get("reaction")
        if reaction is None:
            return None

        label = reaction.get("label")
        if label not in ("correct", "block"):
            return None

        message = reaction.get("message", "")
        if not message.strip():
            return None

        text = self._normalize_text(message)
        severity = self._assign_severity(label, message)
        scope_paths = self._infer_scope(message, episode)
        detection_hints = self._extract_detection_hints(message)
        constraint_id = self._make_constraint_id(text, scope_paths)

        return {
            "constraint_id": constraint_id,
            "text": text,
            "severity": severity,
            "scope": {"paths": scope_paths},
            "detection_hints": detection_hints,
            "source_episode_id": episode.get("episode_id", ""),
            "created_at": episode.get("timestamp", ""),
        }
```

### Pattern 2: Severity Assignment Logic

**What:** Maps reaction label + keyword analysis to severity levels. The design spec defines the mapping clearly:
- `block` reactions -> `forbidden` (always)
- `correct` reactions -> `requires_approval` (default) or `warning` (when soft correction)

**When to use:** During constraint extraction, after identifying the reaction type.

**Key design detail:** The "soft correction" vs "hard correction" distinction determines whether a correct reaction produces `warning` or `requires_approval`. Soft corrections suggest alternatives without prohibiting ("use X instead of Y", "prefer async"). Hard corrections prohibit actions ("don't use regex for XML", "never deploy without tests"). The constraint_patterns config already categorizes keywords: `forbidden` keywords ("don't", "never", "avoid", "do not") indicate hard corrections -> `requires_approval`, while `preferred` keywords ("use", "prefer", "better to") indicate soft corrections -> `warning`.

**Example:**
```python
def _assign_severity(self, reaction_label: str, message: str) -> str:
    """Assign severity based on reaction label + keyword analysis.

    Rules from AUTHORITATIVE_DESIGN.md Stage F:
    - block -> forbidden (always)
    - correct + forbidden keywords -> requires_approval
    - correct + preferred keywords only -> warning
    - correct (default) -> requires_approval
    """
    if reaction_label == "block":
        return "forbidden"

    # correct reaction: check keywords
    message_lower = message.lower()

    # Check for forbidden keywords (hard correction -> requires_approval)
    has_forbidden = any(p.search(message_lower) for p in self._forbidden_patterns)

    # Check for preferred keywords (soft correction -> warning)
    has_preferred = any(p.search(message_lower) for p in self._preferred_patterns)

    if has_forbidden:
        return "requires_approval"
    elif has_preferred and not has_forbidden:
        return "warning"
    else:
        # Default for correct reactions
        return "requires_approval"
```

### Pattern 3: Scope Inference (Narrowest Applicable)

**What:** Determines the constraint's scope from mentioned file paths, defaulting to the narrowest applicable scope rather than repo-wide. This is a key requirement (CONST-04, success criterion 4).

**When to use:** During constraint extraction, after text normalization.

**Key design detail:** Scope inference follows this hierarchy:
1. **File-level**: If specific files are mentioned in the reaction message, use those paths
2. **Module-level**: If directory paths are mentioned, use those (e.g., "src/pipeline/")
3. **Episode scope fallback**: If no paths in the message, use the episode's own `orchestrator_action.scope.paths` (the paths the episode was working on)
4. **Repo-wide**: Only if none of the above yields paths, use empty array (meaning repo-wide per schema: "Empty array means repo-wide")

The `_extract_scope_paths()` regex from `EpisodePopulator` already handles file path extraction. Reuse this same pattern.

**Example:**
```python
def _infer_scope(self, message: str, episode: dict) -> list[str]:
    """Infer constraint scope from mentioned paths.

    Priority (narrowest first):
    1. Paths mentioned in reaction message
    2. Paths from episode's orchestrator_action.scope
    3. Empty list (repo-wide) as last resort
    """
    # First: extract paths from reaction message
    paths = self._extract_paths(message)
    if paths:
        return paths

    # Second: use episode's scope paths
    action_scope = episode.get("orchestrator_action", {}).get("scope", {})
    episode_paths = action_scope.get("paths", [])
    if episode_paths:
        return episode_paths

    # Last resort: repo-wide (empty array per schema)
    return []
```

### Pattern 4: ConstraintStore (JSON File Manager)

**What:** A class that manages `data/constraints.json` with read/write/dedup operations. The store is append-only (new constraints are added, never removed automatically). Deduplication uses deterministic constraint IDs (hash of text + scope).

**When to use:** After extracting constraints, to persist them to the version-controlled JSON file.

**Key design detail:** The JSON file structure is a top-level array of constraint objects. Each object matches `constraint.schema.json`. The store loads existing constraints, checks for duplicates by constraint_id, adds new constraints, and writes back. The file is committed to git for version control (CONST-02).

**Example:**
```python
class ConstraintStore:
    """Manages data/constraints.json with dedup and validation."""

    def __init__(
        self,
        path: Path = Path("data/constraints.json"),
        schema_path: Path = Path("data/schemas/constraint.schema.json"),
    ):
        self._path = path
        self._schema = self._load_schema(schema_path)
        self._constraints: list[dict] = self._load()

    def add(self, constraint: dict) -> bool:
        """Add a constraint if not already present.

        Returns True if added (new), False if duplicate.
        """
        cid = constraint["constraint_id"]
        if any(c["constraint_id"] == cid for c in self._constraints):
            return False  # Duplicate
        # Validate against schema
        self._validate(constraint)
        self._constraints.append(constraint)
        return True

    def save(self) -> int:
        """Write constraints to JSON file. Returns count written."""
        with open(self._path, "w") as f:
            json.dump(self._constraints, f, indent=2, sort_keys=False)
        return len(self._constraints)

    @property
    def constraints(self) -> list[dict]:
        """Return current constraints (read-only copy)."""
        return list(self._constraints)
```

### Pattern 5: Detection Hint Extraction

**What:** Extracts actionable patterns from the reaction message that could help detect future violations. These are strings that can be searched for in code, commands, or file paths.

**When to use:** During constraint extraction, as the final derivation step.

**Key design detail:** Detection hints fall into four categories per the design spec:
1. **Command patterns**: shell commands mentioned ("rm -rf", "git push --force")
2. **Forbidden strings**: specific terms to avoid ("regex", "hardcoded", "eval")
3. **File globs**: file patterns mentioned ("*.env", "db/migrations/*")
4. **Library names**: specific libraries or tools ("jQuery", "moment.js")

The extraction uses simple regex patterns to identify these from the message text. Detection hints are informational -- they help downstream systems (Phase 4 validator, Phase 6 Mission Control) detect violations, but do not need to be perfect.

**Example:**
```python
def _extract_detection_hints(self, message: str) -> list[str]:
    """Extract detection hint patterns from reaction message.

    Looks for:
    1. Quoted strings (likely specific terms to detect)
    2. File paths and globs
    3. Command-like patterns
    4. Technical terms following "don't use", "avoid", "never"
    """
    hints: list[str] = []
    seen: set[str] = set()

    # Quoted strings: "regex", 'eval', `rm -rf`
    for match in re.finditer(r'["`\']([\w\s.*/-]+)["`\']', message):
        hint = match.group(1).strip()
        if hint and hint not in seen:
            seen.add(hint)
            hints.append(hint)

    # File paths/globs
    for path in self._extract_paths(message):
        if path not in seen:
            seen.add(path)
            hints.append(path)

    # Terms after prohibition keywords: "don't use X", "avoid X", "never X"
    for match in re.finditer(
        r"(?:don't\s+use|avoid|never\s+use|stop\s+using)\s+([\w.-]+)",
        message,
        re.IGNORECASE,
    ):
        term = match.group(1).strip()
        if term and term not in seen:
            seen.add(term)
            hints.append(term)

    return hints
```

### Pattern 6: Pipeline Integration

**What:** Wire constraint extraction into the existing PipelineRunner after the episode validation/storage step. For each valid episode with a correct/block reaction, extract a constraint and add it to the store. At the end of batch processing, save the store.

**When to use:** As a new step in the pipeline runner (Step 12 or 13).

**Key design detail:** Constraint extraction runs AFTER episode storage (not before) because we need the full episode context including reaction labels. The store is opened at PipelineRunner init and saved after each session (or at batch end). Back-populate `constraints_extracted` on the episode dict before DuckDB write if extraction succeeds.

**Example integration point in runner.py:**
```python
# In PipelineRunner.__init__:
self._constraint_extractor = ConstraintExtractor(config)
self._constraint_store = ConstraintStore()

# After Step 11 (write episodes), add Step 12:
# Step 12: Extract constraints from correct/block episodes
constraints_extracted = 0
for episode in valid_episodes:
    constraint = self._constraint_extractor.extract(episode)
    if constraint is not None:
        added = self._constraint_store.add(constraint)
        if added:
            constraints_extracted += 1
            # Back-populate on episode
            episode.setdefault("constraints_extracted", []).append({
                "constraint_id": constraint["constraint_id"],
                "text": constraint["text"],
                "severity": constraint["severity"],
                "scope": constraint["scope"],
                "detection_hints": constraint.get("detection_hints", []),
            })

self._constraint_store.save()
```

### Anti-Patterns to Avoid

- **Extracting constraints from approve/question/redirect reactions:** Only `correct` and `block` reactions produce constraints per design spec Stage F. Other reactions are feedback but not durable rules.
- **Defaulting to repo-wide scope when episode has specific paths:** The requirement says "narrowest applicable scope." Always check reaction message paths first, then episode scope, then fall back to repo-wide.
- **Building fuzzy deduplication:** ADV-01 explicitly defers this to v2. Phase 3 uses hash-based (exact) dedup only. Two constraints with slightly different wording are stored as separate constraints.
- **Storing constraints only in DuckDB:** CONST-02 specifically requires `data/constraints.json` as a version-controlled JSON file. The constraints may ALSO be referenced in episodes via `constraints_extracted`, but the primary store is the JSON file.
- **Over-engineering text normalization:** The reaction message text IS the constraint text (possibly cleaned up). Do not attempt NLP-style paraphrasing or summarization. Simple cleanup (trim whitespace, capitalize first letter, ensure period at end) is sufficient.
- **Making constraint extraction block the pipeline:** If extraction fails for one episode, log the error and continue. Constraint extraction is additive -- a missing constraint is tolerable; a pipeline crash is not.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation for constraints | Custom dict-key checking | jsonschema 4.25.1 with constraint.schema.json | Schema already defined, library handles edge cases |
| File path extraction from text | Custom parser | Reuse `_scope_path_re` regex from EpisodePopulator | Same pattern already works, proven in Phase 2 |
| Constraint ID generation | Random UUID | Deterministic SHA-256 hash(text + scope_paths) | Enables dedup on re-runs, consistent with Phase 1/2 ID patterns |
| Keyword matching for severity | ML classifier | Config-driven regex matching against constraint_patterns | Config already has forbidden/required/preferred categories; keyword matching is sufficient |
| Fuzzy constraint deduplication | Edit distance / semantic similarity | Deterministic hash dedup (exact match) | ADV-01 explicitly defers fuzzy dedup to v2; hash dedup prevents exact duplicates from re-runs |
| Constraint version history | Custom diff/changelog system | Git version control on data/constraints.json | CONST-02 says "version-controlled JSON file" -- git handles this natively |

**Key insight:** Phase 3's complexity is in the extraction heuristics (turning human correction text into structured constraint objects), not in storage or validation. The schema, models, config patterns, and file I/O are all straightforward. Invest code quality in the extractor's severity assignment and scope inference logic.

---

## Common Pitfalls

### Pitfall 1: Extracting Constraints from Non-Correction Reactions

**What goes wrong:** Processing all episodes through constraint extraction, producing nonsensical constraints from "yes" (approve) or "why?" (question) messages.

**Why it happens:** The reaction_label filter is missed or too broad.

**How to avoid:** Gate constraint extraction on `reaction_label IN ('correct', 'block')` with an explicit early return. Log and count skipped episodes for verification.

**Warning signs:** Constraints containing approval language ("yes", "looks good"). Constraint count exceeding correct+block episode count.

### Pitfall 2: All Scopes Default to Repo-Wide

**What goes wrong:** Constraint scope is always `{"paths": []}` (repo-wide) because path extraction fails to find paths in reaction messages.

**Why it happens:** Reaction messages are often brief ("no, don't do that") without mentioning specific files. If the fallback to episode scope is not implemented, everything becomes repo-wide.

**How to avoid:** Implement the three-tier scope fallback: (1) paths from reaction message, (2) paths from episode's orchestrator_action.scope, (3) repo-wide only as last resort. The episode already has scope paths from Phase 2's populator -- use them.

**Warning signs:** 90%+ of constraints having empty paths array. Zero file-level or module-level constraints.

### Pitfall 3: Severity Assignment Too Coarse

**What goes wrong:** All correct reactions get `requires_approval` and all block reactions get `forbidden`, with no `warning` level constraints ever produced.

**Why it happens:** The "soft correction" detection is not implemented -- only the reaction_label -> severity mapping is used, without keyword analysis.

**How to avoid:** Implement the keyword analysis step: correct reactions with preferred keywords (and without forbidden keywords) should produce `warning` severity. Test with examples like "use pytest instead of unittest" (should be warning, not requires_approval).

**Warning signs:** Zero `warning` severity constraints. All constraints being either `requires_approval` or `forbidden`.

### Pitfall 4: Duplicate Constraints on Re-Run

**What goes wrong:** Running the pipeline twice on the same data produces duplicate constraints in constraints.json.

**Why it happens:** Constraint IDs are not deterministic, or the dedup check is missing.

**How to avoid:** Use deterministic SHA-256(text + sorted scope paths) for constraint IDs. The ConstraintStore.add() method checks for existing constraint_id before adding.

**Warning signs:** constraints.json growing on each pipeline run. Identical constraint text appearing with different IDs.

### Pitfall 5: Constraint Text Mirrors Reaction Message Verbatim

**What goes wrong:** Constraints contain conversational text ("no, don't use regex for that, it's terrible") instead of normalized constraint statements ("Avoid using regex for XML parsing").

**Why it happens:** No text normalization step -- the raw reaction message is used as constraint text.

**How to avoid:** Apply basic text normalization: strip leading "no, " or "don't " prefixes, capitalize, ensure the text reads as an imperative rule. Do NOT over-engineer this (no NLP paraphrasing), but basic cleanup makes constraints much more readable.

**Warning signs:** Constraints starting with "no, " or "stop". Constraints containing conversational filler ("hmm", "well", "actually").

### Pitfall 6: Detection Hints Empty for Most Constraints

**What goes wrong:** The detection_hints array is empty for most constraints because the extraction regex is too strict.

**Why it happens:** The hint extraction only looks for quoted strings or exact patterns, missing common forms like "don't use regex" (where "regex" is not quoted).

**How to avoid:** Extract terms following prohibition patterns ("don't use X", "avoid X", "never X") in addition to quoted strings and file paths. These prohibition-adjacent terms are the most actionable hints.

**Warning signs:** More than 50% of constraints having empty detection_hints. Hints that are too generic (single characters, common words like "the").

---

## Code Examples

### Constraint Text Normalization

```python
# Source: Derived from design spec Stage F + existing reaction patterns
def _normalize_text(self, message: str) -> str:
    """Normalize reaction message into a constraint statement.

    Applies basic cleanup:
    1. Strip leading correction prefixes ("no, ", "nope, ", "wrong, ")
    2. Strip trailing conversational filler
    3. Capitalize first letter
    4. Ensure ends with period
    """
    text = message.strip()

    # Remove leading correction prefixes
    prefix_patterns = [
        r"^(?:no|nope|wrong|stop|never),?\s+",
        r"^(?:don't|do\s+not)\s+(?:do\s+that),?\s*",
        r"^(?:that's?\s+(?:wrong|not\s+right|incorrect)),?\s+",
    ]
    for pattern in prefix_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    # Capitalize first letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Ensure ends with period
    if text and text[-1] not in ".!":
        text = text + "."

    return text
```

### Deterministic Constraint ID

```python
# Source: Consistent with Phase 1/2 ID generation pattern (SHA-256)
def _make_constraint_id(self, text: str, scope_paths: list[str]) -> str:
    """Generate deterministic constraint ID.

    SHA-256(normalized_text + sorted_scope_paths) truncated to 16 hex chars.
    Same text + same scope = same ID = dedup on re-run.
    """
    scope_key = "|".join(sorted(scope_paths))
    key = f"{text.lower().strip()}:{scope_key}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### Constraint Store Load/Save

```python
# Source: Standard JSON file I/O pattern
class ConstraintStore:
    """Manages data/constraints.json with dedup and validation."""

    def __init__(
        self,
        path: Path = Path("data/constraints.json"),
        schema_path: Path = Path("data/schemas/constraint.schema.json"),
    ):
        self._path = path
        self._validator = self._load_validator(schema_path)
        self._constraints: list[dict] = self._load()
        self._added_count = 0

    def _load(self) -> list[dict]:
        """Load existing constraints from JSON file."""
        if not self._path.exists():
            return []
        with open(self._path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data

    def _load_validator(self, schema_path: Path):
        """Load JSON Schema validator for constraints."""
        if not schema_path.exists():
            return None
        with open(schema_path) as f:
            schema = json.load(f)
        validator_cls = jsonschema.validators.validator_for(schema)
        return validator_cls(schema, format_checker=jsonschema.FormatChecker())

    def add(self, constraint: dict) -> bool:
        """Add a constraint if not duplicate. Returns True if added."""
        cid = constraint.get("constraint_id", "")
        if any(c.get("constraint_id") == cid for c in self._constraints):
            return False

        # Validate against schema (skip optional fields that may be absent)
        if self._validator:
            errors = list(self._validator.iter_errors(constraint))
            if errors:
                logger.warning(
                    "Constraint {} failed validation: {}",
                    cid, errors[0].message,
                )
                return False

        self._constraints.append(constraint)
        self._added_count += 1
        return True

    def save(self) -> int:
        """Persist constraints to JSON file. Returns total count."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._constraints, f, indent=2)
        return len(self._constraints)

    @property
    def count(self) -> int:
        return len(self._constraints)

    @property
    def added_count(self) -> int:
        return self._added_count
```

### Full Extraction Flow Example

```python
# Source: Integration of all extraction steps
# Given an episode dict from DuckDB:
episode = {
    "episode_id": "abc123",
    "timestamp": "2026-02-11T12:00:00Z",
    "orchestrator_action": {
        "mode": "Implement",
        "scope": {"paths": ["src/pipeline/tagger.py"]},
        ...
    },
    "outcome": {
        "reaction": {
            "label": "correct",
            "message": "No, don't use regex for XML parsing. Use lxml instead.",
            "confidence": 0.85,
        },
        ...
    },
}

# Extraction produces:
constraint = {
    "constraint_id": "a1b2c3d4e5f6...",  # SHA-256 hash
    "text": "Use lxml instead of regex for XML parsing.",
    "severity": "requires_approval",  # correct + "don't" -> requires_approval
    "scope": {"paths": ["src/pipeline/tagger.py"]},  # from episode scope
    "detection_hints": ["regex", "lxml"],  # from prohibition pattern
    "source_episode_id": "abc123",
    "created_at": "2026-02-11T12:00:00Z",
}
```

### DuckDB Episode Update for constraints_extracted

```python
# Source: Consistent with Phase 2 MERGE pattern
def update_episode_constraints(
    conn: duckdb.DuckDBPyConnection,
    episode_id: str,
    constraints: list[dict],
) -> None:
    """Update an episode's constraints_extracted field in DuckDB.

    The constraints_extracted is stored in the outcome JSON column.
    """
    constraints_json = json.dumps(constraints)
    conn.execute(
        """
        UPDATE episodes
        SET outcome = json_merge_patch(
            outcome,
            json_object('constraints_extracted', CAST(? AS JSON))
        ),
        updated_at = current_timestamp
        WHERE episode_id = ?
        """,
        [constraints_json, episode_id],
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Constraints as ephemeral feedback | Durable constraints in version-controlled JSON | Design decision (this project) | Constraints survive across sessions, enabling enforcement in future runs |
| Single severity level | Three-tier severity (warning / requires_approval / forbidden) | Design spec | Graduated enforcement: warnings are advisory, requires_approval needs human OK, forbidden blocks execution |
| Global scope for all constraints | Narrowest-applicable scope inference | CONST-04 requirement | Constraints scoped to specific files/modules don't over-restrict unrelated code |

**Deprecated/outdated:**
- No deprecated approaches in this domain; Phase 3 is implementing the first version of constraint management.

---

## Integration Points with Existing Code

### Input: Phase 2 Pipeline Output

Phase 3 consumes episodes from the Phase 2 pipeline. Key fields used:

| Episode Field | Used For |
|---------------|----------|
| `outcome.reaction.label` | Gate: only process `correct` and `block` |
| `outcome.reaction.message` | Primary input for constraint text extraction |
| `outcome.reaction.confidence` | Optional: could weight constraint importance |
| `orchestrator_action.scope.paths` | Fallback scope when reaction message lacks paths |
| `episode_id` | Back-reference: `source_episode_id` in constraint |
| `timestamp` | Constraint `created_at` timestamp |

### Output: data/constraints.json

The JSON file is the primary artifact. Structure:

```json
[
  {
    "constraint_id": "a1b2c3d4e5f67890",
    "text": "Avoid using regex for XML parsing.",
    "severity": "requires_approval",
    "scope": {"paths": ["src/pipeline/"]},
    "detection_hints": ["regex", "xml"],
    "source_episode_id": "abc123",
    "created_at": "2026-02-11T12:00:00Z",
    "examples": [
      {
        "episode_id": "abc123",
        "violation_description": "Used regex to parse XML config file"
      }
    ]
  }
]
```

### Downstream Consumers

| Consumer | Phase | What They Need |
|----------|-------|----------------|
| Genus-based validator | Phase 4 | Reads constraints.json to check constraint enforcement validity (Layer D) |
| RAG baseline orchestrator | Phase 5 | Loads constraints_in_force for observation context |
| Mission Control | Phase 6 | Displays constraints in review widget, enforces in workflow transitions |
| Episode observation.context.constraints_in_force | Phase 4+ | Populated from active constraints matching current scope |

### Existing Code to Reuse

| Existing Code | Where | Reuse In Phase 3 |
|---------------|-------|-------------------|
| `ConstraintRef` Pydantic model | `src/pipeline/models/episodes.py` | Validation and type checking for constraint objects |
| `ConstraintScope` Pydantic model | `src/pipeline/models/episodes.py` | Scope validation |
| `constraint.schema.json` | `data/schemas/` | JSON Schema validation in ConstraintStore |
| `constraint_patterns` config | `data/config.yaml` | Keyword lists for severity assignment |
| `_scope_path_re` regex | `src/pipeline/populator.py` | File path extraction from text |
| `EpisodeValidator` pattern | `src/pipeline/episode_validator.py` | Validator architecture for ConstraintStore |
| MERGE upsert pattern | `src/pipeline/storage/writer.py` | Episode update for constraints_extracted |
| PipelineRunner step pattern | `src/pipeline/runner.py` | Integration point for new constraint step |

---

## Open Questions

1. **Constraint text normalization quality**
   - What we know: Basic prefix stripping ("no, ", "don't") and capitalization produce readable constraint text from reaction messages.
   - What's unclear: How well this works on real-world correction messages (we have no real data to test against yet -- no JSONL sessions are loaded in the DB).
   - Recommendation: Implement basic normalization for Phase 3. Phase 4 (Validation & Quality) will evaluate extraction quality against gold-standard labels and can refine.

2. **Back-populating constraints_extracted in episodes table**
   - What we know: The episode schema has a `constraints_extracted` field (array of Constraint objects). The DuckDB `outcome` column is JSON, so we can update it. But the schema expects `constraints_extracted` at the top level of the episode, not inside `outcome`.
   - What's unclear: Whether to update the top-level episode in DuckDB or just store in constraints.json.
   - Recommendation: Store constraints in `data/constraints.json` (primary, per CONST-02). Optionally update the episode's `constraints_extracted` array in DuckDB for analytical queries. This is a nice-to-have, not a must-have for Phase 3.

3. **Constraint deduplication across sessions**
   - What we know: The same correction might appear in multiple sessions (user repeatedly says "don't use regex for XML"). Hash-based dedup handles exact matches.
   - What's unclear: Whether near-duplicate constraints (same intent, different wording) should be merged.
   - Recommendation: Hash-based (exact) dedup only for Phase 3. ADV-01 explicitly defers fuzzy matching to v2. The `examples` array on constraints can accumulate multiple source episodes for the same constraint.

4. **Examples array population**
   - What we know: The constraint schema includes an `examples` array with `episode_id` and `violation_description`. For a new constraint, the source episode is the first example.
   - What's unclear: Whether to update existing constraints with additional examples when the same constraint is re-extracted.
   - Recommendation: On duplicate detection, append the new episode to the existing constraint's `examples` array if not already present. This enriches constraints with multiple evidence points without creating duplicates.

---

## Sources

### Primary (HIGH confidence)

- **Phase 2 codebase:** Direct inspection of `src/pipeline/reaction_labeler.py`, `populator.py`, `runner.py`, `storage/writer.py`, `storage/schema.py`, `models/episodes.py`, `models/config.py` -- all verified and tested (198 tests passing).
- **`data/schemas/constraint.schema.json`:** Existing constraint schema with required fields (constraint_id, text, severity, scope) and optional fields (detection_hints, source_episode_id, created_at, examples).
- **`data/schemas/orchestrator-episode.schema.json`:** Episode schema including `constraints_extracted` array and inline `Constraint` definition matching the standalone constraint schema.
- **`data/config.yaml`:** Existing `constraint_patterns` config with `forbidden`, `required`, and `preferred` keyword categories.
- **AUTHORITATIVE_DESIGN.md, Stage F:** Explicit constraint extraction rules: block -> forbidden, correct -> requires_approval/warning, scope from paths, detection hints from patterns.
- **REQUIREMENTS.md:** EXTRACT-06, CONST-01 through CONST-04 defining exact requirements for Phase 3.

### Secondary (MEDIUM confidence)

- **Phase 2 RESEARCH.md:** Verified DuckDB MERGE patterns, JSON column updates, and overall architecture patterns that Phase 3 builds on.
- **Phase 2 plan summaries:** Confirmed pipeline architecture (stages run sequentially, PipelineRunner orchestrates all steps, new steps added at end).

### Tertiary (LOW confidence)

- **Constraint text normalization quality:** No real-world data to validate against. Basic prefix-stripping approach is reasonable but untested at scale.
- **Detection hint extraction coverage:** The regex-based approach for extracting hints from message text is a best-effort heuristic. Coverage on real correction messages is unknown.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; all libraries already installed and verified
- Architecture: HIGH - Builds directly on Phase 2 patterns; two new modules + pipeline integration; constraint schema already exists
- Extraction logic: MEDIUM - Design spec is clear on severity/scope rules, but text normalization and detection hint extraction quality is untested against real data
- Pitfalls: HIGH - Grounded in actual codebase analysis and design spec requirements
- Storage: HIGH - JSON file I/O with schema validation is straightforward; dedup via deterministic hashing is proven pattern

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (stable -- constraint schema is frozen; extraction patterns are deterministic)
