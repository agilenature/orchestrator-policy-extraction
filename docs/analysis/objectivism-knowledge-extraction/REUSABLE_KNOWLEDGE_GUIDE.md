# Reusable Knowledge Guide: Bulk Metadata Generation + Gemini File Search Upload Pipeline

**Project:** Objectivism Library Semantic Search
**Analysis Date:** 2026-02-17
**Source Material:** Git history (85 commits, 2026-02-15 to 2026-02-17), planning documents, session files
**Pipeline:** Mistral API batch metadata extraction → Gemini File Search upload for 1,749 philosophical text files

---

## Purpose

This guide collapses the exploratory spiral of building a two-stage pipeline: (1) AI-powered metadata generation for a large text corpus using the Mistral API, and (2) upload of files with enriched metadata to the Gemini File Search API for semantic search. A future agent building a similar pipeline should be able to read this document once and avoid repeating 19 planning cycles and several painful dead ends.

---

## A. Breakthrough Moments

### Breakthrough 1: The Two-Step Gemini Upload Pattern

**Problem:** The planning docs initially assumed `upload_to_file_search_store()` could attach `custom_metadata` in one call.

**Discovery (Phase 2 research, commit `58322531`):** The single-step `upload_to_file_search_store()` method does NOT support `custom_metadata` in its documented config. Metadata attachment requires a two-step pattern:

```python
# Step 1: Upload the raw file to the Files API
file_obj = await client.aio.files.upload(
    file=str(file_path),
    config={"display_name": file_path.name}
)

# Step 2: Wait for file to be ACTIVE
while file_obj.state != "ACTIVE":
    await asyncio.sleep(5)
    file_obj = await client.aio.files.get(name=file_obj.name)

# Step 3: Import into File Search store WITH custom_metadata
operation = await client.aio.file_search_stores.import_file(
    file_search_store_name=store_name,
    file_name=file_obj.name,
    config={"custom_metadata": metadata_list}
)
```

This two-step pattern also gives better crash recovery: upload failures are separate from import failures.

**State decision (`02-01-PLAN` decision):** Write upload INTENT to SQLite before the API call; write RESULT after. This creates a crash anchor — on restart, any file showing "uploading" state is retried from scratch.

---

### Breakthrough 2: Gemini's `string_list_value` Format

**Problem:** When building enriched metadata with list fields (topics, aspects, entity names), the naive approach of using bare lists caused `400 INVALID_ARGUMENT` errors.

**Discovery (Phase 6.2 research, commit `325fded`):** Gemini's `CustomMetadata` type has three distinct value types. List fields require a specific nested wrapper:

```python
# WRONG — causes INVALID_ARGUMENT:
{"key": "topics", "value": ["epistemology", "reason"]}

# CORRECT — proper string_list_value wrapper:
{"key": "topics", "string_list_value": {"values": ["epistemology", "reason"]}}

# Full metadata entry structure:
custom_metadata = [
    {"key": "category", "string_value": "course_transcript"},
    {"key": "difficulty", "string_value": "intermediate"},
    {"key": "year", "numeric_value": 1985},
    {"key": "topics", "string_list_value": {"values": ["epistemology", "concept_formation"]}},
    {"key": "aspects", "string_list_value": {"values": ["measurement omission principle"]}},
    {"key": "entities", "string_list_value": {"values": ["Ayn Rand", "Leonard Peikoff"]}},
]
```

The `string_list_value` fields are filterable in Gemini queries using the `:` (has) operator: `topics:"epistemology"`. Maximum 20 `custom_metadata` entries per document.

---

### Breakthrough 3: Magistral Response Format — Content Is an Array

**Problem:** Initial code used `response.choices[0].message.content` as a plain string. With magistral-medium-latest, this crashes with TypeError because content is a list of objects.

**Discovery (Phase 6 research, commit `2139df1`):** The magistral reasoning model returns content as an array containing a mix of thinking blocks and text blocks:

```python
def parse_magistral_response(response) -> dict:
    """Two-phase parser for magistral array-format response."""
    content = response.choices[0].message.content

    # Phase 1: Handle array format (thinking + text objects)
    if isinstance(content, list):
        # Filter for TextChunk objects (type='text'), skip ThinkChunk (type='thinking')
        text_parts = [
            obj.text for obj in content
            if getattr(obj, 'type', None) == 'text'
        ]
        combined = ''.join(text_parts)
        try:
            return json.loads(combined)
        except json.JSONDecodeError:
            pass  # Fall through to regex

    # Phase 2: Handle string format
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

    # Phase 3: Regex extraction (last resort — handles nested objects)
    text = str(content)
    match = re.search(r'\{(?:[^{}]|\{[^{}]*\})*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("No valid JSON found in magistral response")
```

**Critical constraint:** magistral-medium-latest requires `temperature=1.0`. Setting lower temperatures produces degraded or empty responses. Document this as a hard requirement.

---

### Breakthrough 4: 400 Errors Are Usually Transient, Not Permanent

**Problem:** After the initial upload run, 38 files had status=`failed` with error `400 INVALID_ARGUMENT - Failed to create file`. The assumption was these files were broken.

**Discovery (CRITICAL_THINKING_BREAKTHROUGH.md, 2026-02-17):** Manual upload of a "failed" file succeeded immediately. Investigation showed:
- File content was clean ASCII text
- Filename had no invalid characters
- The error was transient (temporary API service issue)

**Action:** Reset all 38 files to `pending` and re-ran the upload. Result: 36/38 succeeded (95% recovery). Only 1 file was genuinely broken (a corrupted transcript containing only single repeated words).

**Pattern:** Treat `400 INVALID_ARGUMENT - Failed to create file` as potentially transient. Always check whether a "failed" file has a `gemini_file_id` assigned — if it does, the upload actually succeeded despite the error status (polling timeout).

**Classification established:**
```python
# Treat as transient (retry):
"Failed to create file"      # 400 — proved transient in practice
"Failed to count tokens"     # 503 — transient unless file is corrupted
"Service unavailable"        # 503
"Operation did not complete" # polling timeout — check for gemini_file_id

# Treat as permanent (do not retry):
"Authentication failed"      # 401
"Permission denied"          # 403
```

---

### Breakthrough 5: Metadata-First Execution Strategy

**Problem:** The natural execution order was 1 → 2 → 3 → 4 → 5 → 6 → 7 (phases). Phases 4 and 5 would have come before Phase 6 (AI metadata enrichment). This meant uploading 1,721 files with incomplete metadata, then having to re-upload everything after Phase 6.

**Discovery (roadmap decision, `a4fbdc9`):** Executing Phase 6 before the full library upload avoids re-uploading 1,721 files. With ~28% of files (496/1,749) having `category: "unknown"`, uploading without enriched metadata would have meant permanently degraded search quality or a costly full re-upload.

**Actual execution order:** 1 → 2 → 3 → **6** → **6.1** → **6.2** → [FULL UPLOAD] → 4 → 5 → 7

**Lesson:** For a large corpus, plan the metadata enrichment phase to run BEFORE the bulk upload, not after. Re-uploading thousands of files to update metadata is expensive in API quota and time.

---

## B. Dead Ends and Reversals

### Dead End 1: `pybreaker` for Circuit Breaker

**What was tried:** Using `pybreaker` 1.4.1 for the upload pipeline's circuit breaker.

**Why it failed:** pybreaker's model (fail_max consecutive failures) does not match the requirement (5% 429 rate over a rolling window of 100 requests). The library's state machine tracks consecutive failures, not percentage-based rate degradation.

**Resolution:** Hand-rolled a custom circuit breaker using `collections.deque(maxlen=100)` for the rolling window (~80 lines of code). State machine: CLOSED → OPEN (trips at 5% 429 rate OR 3 consecutive 429s) → HALF_OPEN (after 5-minute cooldown).

```python
from collections import deque

class RollingWindowCircuitBreaker:
    def __init__(self, window_size=100, error_threshold=0.05):
        self._window = deque(maxlen=window_size)
        self._threshold = error_threshold
        self.state = "CLOSED"  # CLOSED / OPEN / HALF_OPEN

    def record_429(self):
        self._window.append(True)
        rate = sum(self._window) / len(self._window)
        if rate >= self._threshold:
            self.state = "OPEN"

    def record_success(self):
        self._window.append(False)
```

---

### Dead End 2: Single-Step Upload Assumption

**What was tried:** Using `upload_to_file_search_store()` with metadata in the config.

**Why it failed:** The SDK method does not expose `custom_metadata` in its config parameter (at least in google-genai v1.63.0). The docs are unclear about this.

**Resolution:** The two-step pattern (see Breakthrough 1): `files.upload()` → wait ACTIVE → `file_search_stores.import_file()` with `custom_metadata`.

---

### Dead End 3: Mistral SDK Import Path

**What was tried (from research):** `from mistralai.client import MistralClient`

**Why it failed:** This is the old SDK (pre-1.0) import path. The Mistral SDK v1.0+ changed the import.

**Resolution:**
```python
# Old (pre-1.0) — BROKEN:
from mistralai.client import MistralClient

# Current (v1.0+) — CORRECT:
from mistralai import Mistral
client = Mistral(api_key=api_key)
response = await client.chat.complete_async(
    model="magistral-medium-latest",
    messages=[...],
    temperature=1.0,  # Required for magistral
    max_tokens=8000,
    response_format={"type": "json_object"}
)
```

---

### Dead End 4: Using `request_options` in Gemini Search

**What was tried:** Adding `request_options` to `GenerateContentConfig` for search calls.

**Why it failed:** The parameter does not exist in the SDK's `GenerateContentConfig`. Caused immediate runtime error.

**Resolution (commit `444174f`):** Removed the invalid parameter. The SDK handles timeouts at the client level, not per-request config.

---

### Dead End 5: Sync `sqlite3` in Async Upload Pipeline

**What was tried (considered):** Using sync `sqlite3` calls within the async orchestrator.

**Why it would fail:** SQLite has a single-writer constraint. Sync writes block the async event loop, causing concurrency to degrade to sequential. With `aiosqlite`, writes are non-blocking.

**Resolution:** Used `aiosqlite` throughout the async upload pipeline. Critical rule: commit state writes immediately — do NOT hold transactions open across `await` boundaries.

```python
# WRONG — transaction held across await:
async with conn.execute("BEGIN"):
    conn.execute("UPDATE files SET status='uploading' ...")
    await upload_api_call()   # Event loop can switch here
    conn.execute("UPDATE files SET status='uploaded' ...")
    await conn.commit()

# CORRECT — commit before await:
await conn.execute("UPDATE files SET status='uploading' ...")
await conn.commit()           # Commit immediately
result = await upload_api_call()
await conn.execute("UPDATE files SET status='uploaded' ...")
await conn.commit()
```

---

### Dead End 6: JSON Mode + Magistral Thinking Blocks Conflict

**What was tried:** Assuming `response_format={"type": "json_object"}` would produce a plain JSON string in `response.content`.

**Why it failed:** With magistral-medium-latest, thinking blocks appear even in JSON mode. The content field is always an array regardless of `response_format`.

**Resolution:** Always use the two-phase parser (see Breakthrough 3). Never assume `content` is a string.

---

## C. Reusable Patterns (The Collapsed Spiral)

### Pattern 1: SQLite as Pipeline State Machine

SQLite WAL mode is the right choice for tracking file state across all pipeline phases. Configure it once:

```python
import sqlite3

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")       # Concurrent reads during writes
    conn.execute("PRAGMA synchronous=NORMAL")      # Good durability without FULL overhead
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")       # Wait up to 5s on lock contention
    conn.row_factory = sqlite3.Row                 # Dict-like row access
    return conn
```

**Schema decisions that paid off:**
- `content_hash TEXT` (SHA-256 hexdigest) — enables idempotent reprocessing
- `status TEXT` with explicit enum values: `pending` / `uploading` / `uploaded` / `failed` / `skipped`
- `gemini_file_id TEXT` — store immediately when obtained; check for this before marking as failed
- `upload_timestamp TEXT` — for 48-hour expiration tracking
- `last_upload_hash TEXT` — SHA-256 of (phase1_metadata + ai_metadata + entity_names + content_hash); prevents re-uploads when nothing changed

**Schema migration pattern (SQLite lacks `IF NOT EXISTS` for columns):**
```python
try:
    conn.execute("ALTER TABLE files ADD COLUMN ai_metadata_status TEXT DEFAULT 'pending'")
except sqlite3.OperationalError:
    pass  # Column already exists — migration is idempotent

conn.execute("PRAGMA user_version = 5")  # Track schema version
```

---

### Pattern 2: Write-Ahead Intent Logging for Crash Recovery

Before any API call, write intent to SQLite. After success, write result. This is the crash recovery anchor:

```python
# BEFORE API call — record intent
await state.execute(
    "UPDATE files SET status='uploading', upload_started_at=? WHERE file_path=?",
    (datetime.now().isoformat(), file_path)
)
await state.commit()

# API call
result = await client.upload_file(file_path, metadata)

# AFTER success — record result
await state.execute(
    "UPDATE files SET status='uploaded', gemini_file_id=?, upload_completed_at=? WHERE file_path=?",
    (result.gemini_file_id, datetime.now().isoformat(), file_path)
)
await state.commit()
```

**On restart:** Any file with `status='uploading'` is treated as interrupted; check the Gemini API for whether it succeeded before retrying.

---

### Pattern 3: Async Semaphore + Rate Limiter Composition

The proven concurrency pattern for Gemini File Search uploads:

```python
import asyncio
from aiolimiter import AsyncLimiter

class UploadOrchestrator:
    def __init__(self, config):
        # Conservative defaults for initial deployment
        self._semaphore = asyncio.Semaphore(2)      # Max concurrent uploads
        self._rate_limiter = AsyncLimiter(20, 60)   # 20 req/min (Gemini Tier 1)

    async def _upload_single_file(self, file_record):
        async with self._semaphore:
            async with self._rate_limiter:
                # Only the API call section is semaphore-guarded
                # DB writes happen outside semaphore to avoid deadlocks
                return await self._client.upload_and_import(file_record)
```

**Tuning guidance:**
- Start with `Semaphore(2)` and 1-second stagger between launches for enriched uploads
- `Semaphore(5-7)` works for basic uploads without metadata
- The circuit breaker cuts concurrency in half when 429s appear

---

### Pattern 4: Atomic Checkpoint with tmp-then-rename

For long-running batch jobs where you want crash-safe state persistence:

```python
class CheckpointManager:
    def __init__(self, checkpoint_path: Path):
        self.path = checkpoint_path

    def save(self, state: dict):
        """Atomic write — no partial state on crash."""
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, indent=2))
        tmp.rename(self.path)   # Atomic on POSIX systems

    def load(self) -> dict | None:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return None
```

Use this for credit exhaustion (HTTP 402) on Mistral:
```python
except MistralAPIException as e:
    if e.status_code == 402:  # Payment Required — credits exhausted
        checkpoint.save({'next_file_index': current_idx, ...})
        print("MISTRAL CREDITS EXHAUSTED — Resume with: objlib extract --resume")
        sys.exit(0)  # Clean exit, not crash
    elif e.status_code == 429:  # Rate limit — retry with backoff, do NOT exit
        raise  # Let tenacity handle
```

---

### Pattern 5: Pydantic as Both Prompt Schema and Validator

Use a single Pydantic model to (a) generate the JSON schema injected into the prompt and (b) validate the LLM response:

```python
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum

class Category(str, Enum):
    COURSE_TRANSCRIPT = "course_transcript"
    BOOK_EXCERPT = "book_excerpt"
    QA_SESSION = "qa_session"
    ARTICLE = "article"
    PHILOSOPHY_COMPARISON = "philosophy_comparison"
    CONCEPT_EXPLORATION = "concept_exploration"
    CULTURAL_COMMENTARY = "cultural_commentary"

CONTROLLED_VOCABULARY = frozenset([
    "epistemology", "metaphysics", "ethics", "politics", "aesthetics",
    "reason", "volition", "rational_egoism", "individual_rights", "capitalism",
    # ... 30+ more
])

class ExtractedMetadata(BaseModel):
    category: Category
    difficulty: str = Field(description="One of: intro, intermediate, advanced")
    primary_topics: list[str] = Field(min_length=3, max_length=8)
    topic_aspects: list[str] = Field(min_length=3, max_length=10)
    semantic_description: dict
    confidence_score: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra='ignore')  # Ignore hallucinated fields

    @field_validator('primary_topics')
    @classmethod
    def filter_to_controlled_vocab(cls, v):
        # Silently filter invalid topics rather than raising (reduces retries)
        return [t for t in v if t in CONTROLLED_VOCABULARY]

# For prompt injection:
schema = ExtractedMetadata.model_json_schema()
prompt = f"Return JSON matching this schema: {json.dumps(schema)}"

# For response validation:
metadata = ExtractedMetadata.model_validate(parsed_json)
```

---

### Pattern 6: Stratified Test File Sampling for LLM Prompt Discovery

Before committing to a prompt strategy for a large corpus, test on a representative sample. Use stratified sampling by file size and content type:

```python
def select_test_files(all_files, n=20, seed=42):
    """Select stratified sample balanced by size and population type."""
    import random
    random.seed(seed)

    # Adjust bucket boundaries based on actual data distribution
    buckets = {
        'small':    [f for f in all_files if f.size_bytes < 10_000],
        'medium':   [f for f in all_files if 10_000 <= f.size_bytes < 30_000],
        'large':    [f for f in all_files if 30_000 <= f.size_bytes < 100_000],
        'very_large': [f for f in all_files if f.size_bytes >= 100_000],
    }

    # Also stratify by population type if known (e.g., podcast vs lecture)
    targets = {'small': 5, 'medium': 7, 'large': 6, 'very_large': 2}

    selected = []
    for bucket, target in targets.items():
        available = buckets[bucket]
        # Deficit redistribution: carry over if bucket smaller than target
        n_select = min(target, len(available))
        selected.extend(random.sample(available, n_select))

    return selected
```

---

### Pattern 7: Adaptive Chunking for Long Documents

For files that exceed the LLM context window:

```python
def prepare_transcript(text: str, max_tokens: int = 18_000) -> str:
    """Adaptive chunking: full / head-tail / windowed."""
    estimated_tokens = len(text) // 4  # ~4 chars per token

    if estimated_tokens <= max_tokens:
        return text  # Full text fits

    head_chars = max_tokens * 4 * 0.7  # 70% from start
    tail_chars = max_tokens * 4 * 0.3  # 30% from end

    if estimated_tokens <= max_tokens * 1.5:
        # Slightly over: head-tail strategy
        return (
            text[:int(head_chars)] +
            "\n\n[... MIDDLE OMITTED ...]\n\n" +
            text[-int(tail_chars):]
        )

    # Very long: windowed sampling
    head = text[:12_000]
    tail = text[-12_000:]
    # Extract 3 middle windows evenly spaced
    mid_points = [len(text)//4, len(text)//2, 3*len(text)//4]
    windows = [text[max(0, m-1200):m+1200] for m in mid_points]
    middle = "\n\n[...]\n\n".join(windows)
    return f"{head}\n\n[EXCERPTS]\n{middle}\n\n[END]\n{tail}"
```

---

### Pattern 8: Tier 4 Content Injection for Semantic Embedding

Prepending AI-generated summaries to file content before upload improves embedding quality. The injected text becomes part of what Gemini embeds:

```python
import tempfile

def prepare_enriched_content(
    original_file_path: Path,
    ai_metadata: dict
) -> tuple[Path | None, Path | None]:
    """Prepend AI analysis to file for richer embeddings."""
    semantic = ai_metadata.get('semantic_description', {})

    # Only inject if Tier 4 content exists
    if not any([
        semantic.get('summary'),
        semantic.get('key_arguments'),
        semantic.get('philosophical_positions')
    ]):
        return None, None  # Caller uses original file

    header_lines = ["[AI Analysis]"]
    if semantic.get('summary'):
        header_lines.append(f"Summary: {semantic['summary']}")
    if semantic.get('key_arguments'):
        header_lines.append("Key Arguments:")
        for arg in semantic['key_arguments']:
            header_lines.append(f"  - {arg}")
    if semantic.get('philosophical_positions'):
        header_lines.append("Philosophical Positions:")
        for pos in semantic['philosophical_positions']:
            header_lines.append(f"  - {pos}")
    header_lines.append("\n[Original Text]")

    header = "\n".join(header_lines) + "\n"

    # Write to temp file (caller must clean up)
    tmp = tempfile.NamedTemporaryFile(
        suffix='.txt', delete=False, mode='w', encoding='utf-8'
    )
    tmp.write(header)
    tmp.write(original_file_path.read_text(encoding='utf-8', errors='replace'))
    tmp.close()

    return Path(tmp.name), original_file_path  # temp_path, cleanup_path
```

---

### Pattern 9: Idempotency via Upload Hash

Prevent re-uploading unchanged files when re-running:

```python
import hashlib, json

def compute_upload_hash(
    phase1_metadata: dict,
    ai_metadata: dict,
    entity_names: list[str],
    content_hash: str
) -> str:
    """Deterministic hash of all inputs that determine upload content."""
    canonical = {
        'phase1': sorted(phase1_metadata.items()),
        'ai': sorted(ai_metadata.items()) if ai_metadata else [],
        'entities': sorted(entity_names),
        'content': content_hash,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()

# In orchestrator:
new_hash = compute_upload_hash(phase1, ai_meta, entities, content_hash)
if file_record.last_upload_hash == new_hash:
    continue  # Nothing changed — skip
# ... proceed with upload, store new_hash on success
```

---

### Pattern 10: Two-Level Validation with Category Alias Repair

LLMs frequently output plausible variations of controlled vocabulary terms. Repair before hard-failing:

```python
CATEGORY_ALIASES = {
    'course': 'course_transcript',
    'transcript': 'course_transcript',
    'book': 'book_excerpt',
    'qa': 'qa_session',
    'q&a': 'qa_session',
    'comparison': 'philosophy_comparison',
    'exploration': 'concept_exploration',
    'commentary': 'cultural_commentary',
}

def repair_category(value: str) -> str:
    """Repair common LLM category variations before hard validation."""
    lower = value.lower().strip()
    if lower in VALID_CATEGORIES:
        return lower
    for alias, canonical in CATEGORY_ALIASES.items():
        if alias in lower:
            return canonical
    return value  # Return as-is for hard validation to reject

def validate_metadata(metadata: dict) -> ValidationResult:
    # Attempt repair before hard fail
    metadata['category'] = repair_category(metadata.get('category', ''))

    hard_failures = []
    if metadata['category'] not in VALID_CATEGORIES:
        hard_failures.append(f"Invalid category: {metadata['category']}")

    soft_warnings = []
    if len(metadata.get('topic_aspects', [])) < 3:
        soft_warnings.append("Fewer than 3 topic_aspects")

    if hard_failures:
        return ValidationResult(status='failed_validation', failures=hard_failures)
    if soft_warnings:
        return ValidationResult(status='needs_review', warnings=soft_warnings)
    return ValidationResult(status='extracted')
```

---

## D. Final Working Architecture

### System Overview

```
Local File System (1,749 .txt files)
    │
    ▼
[Phase 1: Foundation] — SQLite database, SHA-256 hashing, metadata extraction from paths
    │  No API dependencies. Run offline. Produces 1,749 file records.
    │
    ▼
[Phase 6: AI Metadata Extraction] — Mistral magistral-medium-latest
    │  Wave 1 (20 files × 3 strategies) → select winning prompt
    │  Wave 2 (~473 unknown files) → 4-tier metadata: category + topics + aspects + description
    │
    ▼
[Phase 6.1: Entity Extraction] — Deterministic fuzzy matching (RapidFuzz)
    │  Extract 15 canonical Objectivist philosophers from transcripts
    │  Fuzzy threshold: ≥92 accept, 80-91 LLM fallback stub, <80 reject
    │
    ▼
[Phase 6.2: Enriched Gemini Upload] — google-genai SDK, two-step pattern
    │  Gate: BOTH ai_metadata_status IN ('extracted','approved','needs_review')
    │       AND entity_extraction_status = 'entities_done'
    │  Upload: temp file with Tier 4 header + custom_metadata with string_list_value
    │  Concurrency: Semaphore(2) + AsyncLimiter(20, 60)
    │
    ▼
[Gemini File Search Store] — Persistent indexed store
    │  Gemini handles chunking, embedding, vector indexing internally
    │
    ▼
[Phase 3: Search CLI] — Typer + Rich
    Query: generateContent with file_search tool
    Browse/Filter: SQLite metadata queries
    Citations: two-pass lookup (filename → Gemini file ID)
```

### Database Schema (Final — v5)

```sql
CREATE TABLE files (
    file_path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,                    -- SHA-256 hexdigest
    file_size INTEGER,
    metadata_json TEXT,                            -- Phase 1 path-extracted metadata
    status TEXT DEFAULT 'pending'                  -- pending/uploading/uploaded/failed/skipped
        CHECK(status IN ('pending','uploading','uploaded','failed','skipped')),
    gemini_file_id TEXT,                           -- Set as soon as obtained
    gemini_file_uri TEXT,
    upload_timestamp TEXT,                         -- ISO 8601 with ms
    error_message TEXT,
    ai_metadata_status TEXT DEFAULT 'pending'
        CHECK(ai_metadata_status IN (
            'pending','extracted','partial','needs_review',
            'failed_json','failed_validation','retry_scheduled','approved'
        )),
    ai_confidence_score REAL,
    entity_extraction_status TEXT DEFAULT 'pending'
        CHECK(entity_extraction_status IN ('pending','entities_done','error')),
    upload_attempt_count INTEGER DEFAULT 0,
    last_upload_hash TEXT,                         -- Idempotency key
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
);

CREATE TABLE file_metadata_ai (
    metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    metadata_json TEXT NOT NULL,                   -- Full 4-tier JSON
    model TEXT NOT NULL,                           -- 'magistral-medium-latest'
    prompt_version TEXT NOT NULL,                  -- Semantic version e.g. '1.0.0'
    extraction_config_hash TEXT,                   -- sha256(temp+schema+vocab)
    is_current INTEGER DEFAULT 1,                  -- Only latest version = 1
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
    FOREIGN KEY (file_path) REFERENCES files(file_path)
);

CREATE TABLE file_primary_topics (
    file_path TEXT NOT NULL,
    topic_tag TEXT NOT NULL,                       -- From controlled 40-tag vocab
    PRIMARY KEY (file_path, topic_tag),
    FOREIGN KEY (file_path) REFERENCES files(file_path)
);

CREATE TABLE person (
    person_id TEXT PRIMARY KEY,                    -- Slug: 'ayn-rand'
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL
);

CREATE TABLE person_alias (
    alias TEXT NOT NULL,
    person_id TEXT NOT NULL,
    is_blocked INTEGER DEFAULT 0,                  -- Ambiguous names blocked
    PRIMARY KEY (alias, person_id),
    FOREIGN KEY (person_id) REFERENCES person(person_id)
);

CREATE TABLE transcript_entity (
    file_path TEXT NOT NULL,
    person_id TEXT NOT NULL,
    mention_count INTEGER DEFAULT 0,
    confidence REAL,
    PRIMARY KEY (file_path, person_id)
);
```

### File Structure

```
src/objlib/
├── scanner/           # Phase 1: file discovery, path metadata extraction, change detection
├── upload/            # Phase 2 + 6.2: Gemini upload pipeline
│   ├── client.py              # GeminiFileSearchClient (two-step upload pattern)
│   ├── circuit_breaker.py     # RollingWindowCircuitBreaker (deque-based, 5% threshold)
│   ├── rate_limiter.py        # AdaptiveRateLimiter + tier config
│   ├── state.py               # AsyncUploadStateManager (aiosqlite)
│   ├── orchestrator.py        # UploadOrchestrator + EnrichedUploadOrchestrator
│   ├── progress.py            # Rich three-tier progress bars
│   ├── recovery.py            # Crash recovery protocol
│   ├── metadata_builder.py    # build_enriched_metadata() with string_list_value
│   └── content_preparer.py    # Tier 4 content injection into temp files
├── extraction/        # Phase 6: Mistral AI metadata extraction
│   ├── schemas.py             # Pydantic models + CONTROLLED_VOCABULARY (40 tags)
│   ├── client.py              # MistralClient (async, JSON mode, magistral parser)
│   ├── parser.py              # parse_magistral_response() two-phase parser
│   ├── prompts.py             # build_system_prompt(), build_user_prompt()
│   ├── strategies.py          # Wave 1: Minimalist / Teacher / Reasoner configs
│   ├── sampler.py             # Stratified test file selection
│   ├── orchestrator.py        # ExtractionOrchestrator (semaphore + rate limiter)
│   ├── checkpoint.py          # Atomic checkpoint + credit exhaustion handler
│   ├── validator.py           # Two-level validation (hard reject / soft warn)
│   ├── confidence.py          # Multi-dimensional weighted confidence scoring
│   ├── chunker.py             # Adaptive chunking (full / head-tail / windowed)
│   └── review.py              # Rich 4-tier metadata display + interactive review
├── entities/          # Phase 6.1: Person name extraction and normalization
│   ├── registry.py            # PersonRegistry (loads canonical names from SQLite)
│   ├── extractor.py           # EntityExtractor (exact → alias → fuzzy pipeline)
│   └── models.py              # TranscriptEntityOutput Pydantic model
├── database.py        # SQLite schema migrations (v1-v5), query methods
├── models.py          # Core data models, enums
├── config.py          # Keyring-based API key management
└── cli.py             # Typer app: scan / upload / enriched-upload / search / entities / metadata
```

### Key API Calls Reference

**Gemini File Search — Two-Step Upload:**
```python
# Step 1: Upload file
file_obj = await client.aio.files.upload(
    file=str(file_path),
    config={"display_name": display_name}
)
# Step 2: Wait for ACTIVE state
# Step 3: Import with metadata
operation = await client.aio.file_search_stores.import_file(
    file_search_store_name=store_name,
    file_name=file_obj.name,
    config={"custom_metadata": [
        {"key": "category", "string_value": "course_transcript"},
        {"key": "topics", "string_list_value": {"values": ["epistemology"]}},
    ]}
)
```

**Gemini Search:**
```python
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=query,
    config={
        "tools": [{"file_search": {"file_search_store_names": [store_name]}}]
    }
)
# Extract citations from response.candidates[0].grounding_metadata
```

**Mistral Extraction:**
```python
response = await client.chat.complete_async(
    model="magistral-medium-latest",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    temperature=1.0,           # REQUIRED for magistral — do not change
    max_tokens=8000,
    response_format={"type": "json_object"}
)
# Always use parse_magistral_response() — content is an array, not a string
```

---

## E. Cost and Scale Reference

### Actual Numbers from This Project

- **Corpus:** 1,749 .txt files, 1,884 total files (includes 135 .epub/.pdf — skipped)
- **AI extraction target:** ~473 unknown-category .txt files
- **Mistral cost (magistral-medium-latest):** ~$0.012 per file (3,500 input tokens + 1,000 output tokens at $2/M input, $5/M output)
- **Wave 1 (20 files × 3 strategies):** ~$0.72 total
- **Wave 2 (453 files):** ~$6 total (actual costs 5-10x lower than initial estimates)
- **Gemini upload:** No per-file cost; File Search store pricing is tier-based (1GB free)
- **Upload success rate:** 99.94% (1,748/1,749 text files) after retry logic

### Timing

- **Total pipeline development:** ~81 minutes across 19 planning plans
- **Average plan execution:** 4.3 minutes per plan
- **Phase 1 (foundation, 3 plans):** 10 minutes
- **Phase 2 (upload pipeline, 4 plans):** 17 minutes
- **Phase 3 (search + CLI, 3 plans):** 13 minutes
- **Phase 6 (AI metadata, 5 plans):** 24 minutes
- **Phase 6.1 (entity extraction, 2 plans):** 9 minutes
- **Phase 6.2 (enriched upload, 2 plans):** 6 minutes

### Rate Limits to Respect

- **Gemini File Search uploads:** Tier 1 = 20 RPM; use `Semaphore(2-7)` depending on stability
- **Mistral magistral-medium-latest:** 60 req/min, 3 concurrent; use `Semaphore(3)` + `AsyncLimiter(60, 60)`
- **48-hour file expiration:** Gemini raw File API objects expire after 48 hours; the File Search store indexed data persists indefinitely

---

## F. What to Do Differently

1. **Add automatic retry for 400 errors in the upload pipeline from day one.** The pipeline initially marked 400 errors as permanent failures. 95% were actually transient. Build in 3 automatic retries with exponential backoff before marking `failed`.

2. **Always check `gemini_file_id` before marking a file as failed.** Polling timeouts can occur even after a successful upload. If the file has a `gemini_file_id`, it uploaded; update status accordingly.

3. **Test the Mistral response parser against a real API response in Phase 1.** The array-format response (thinking blocks + text blocks) is non-obvious and causes a hard crash if you assume content is a string.

4. **Verify `string_list_value` format before the first enriched upload batch.** Run a 5-file test batch and check for `INVALID_ARGUMENT` errors. The `{values: [...]}` wrapper is easy to omit.

5. **Treat 402 (Payment Required) and 429 (Rate Limit) differently.** 402 means credits exhausted — save checkpoint and exit cleanly. 429 means rate limited — use exponential backoff and continue. Never retry on 402.

6. **Do metadata enrichment before bulk upload, not after.** The cost of re-uploading 1,700+ files just to update metadata is prohibitive. Run AI extraction first on the "unknown" subset, then upload with full metadata.

---

*Analysis based on: 85 git commits (2026-02-15 to 2026-02-17), 19 planning phases, session files from ~/.claude/projects/-Users-david-projects-objectivism-library-semantic-search/*
