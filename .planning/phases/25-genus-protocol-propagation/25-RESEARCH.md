# Phase 25: Genus Protocol Propagation - Research

**Researched:** 2026-02-28
**Domain:** OPE Governance Bus extension, CLAUDE.md protocol extension, session-start hooks, genus-first skill enhancement
**Confidence:** HIGH

## Summary

Phase 25 activates the genus mechanism built in Phase 24 across four propagation pathways: CLAUDE.md protocol extension, session-start genus hint, bus-mediated genus oracle endpoint, and skill-level bus escalation. The core technical challenge is not the mechanisms themselves but the text-matching algorithm for `/api/genus-consult` -- OPE has no vector DB and `axis_edges` currently has 0 rows, so the design must handle both the cold-start case and eventual populated case gracefully.

The existing codebase provides strong patterns for every deliverable: `doc_query.py` has a proven tokenization + token-overlap scoring approach for matching queries against CCD axis names (directly reusable for genus matching). The bus server pattern (Starlette + DuckDB + fail-open) is mature with 4 existing endpoints. `session_start.py` already has the `_post_json()` helper and `[OPE]` prefix convention. The `/genus-first` SKILL.md already documents the "Future Capability: Bus-Mediated Genus Oracle" as the correct architecture.

**Primary recommendation:** Reuse `doc_query.py`'s `_tokenize()` and `_score_axis_match()` pattern for genus matching. The handler queries `axis_edges WHERE relationship_text = 'genus_of'` directly through the server's DuckDB connection. Repo scoping requires a JOIN through `bus_sessions` on `created_session_id = session_id` -- there is no `repo` column on `axis_edges`.

## Standard Stack

### Core (all already in the project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| starlette | existing | Async ASGI server for bus endpoints | Already runs 4 routes |
| duckdb | existing | Query axis_edges for genus matching | Already the project's data store |
| pydantic | v2 (existing) | Request/response models | Already used for BusSession, CheckResponse |
| httpx | existing | Test client with ASGITransport | Already used in test_bus_foundation.py |
| http.client | stdlib | Unix socket HTTP in session_start.py | Already used for _post_json() |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | existing | Async test harness | Bus endpoint tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Token-overlap scoring | BM25 FTS | Overkill for genus names (short strings), adds FTS index dependency |
| Token-overlap scoring | ILIKE substring | Less precise -- "retrieval" ILIKE would match unrelated edges |
| JOIN bus_sessions for repo | Add repo column to axis_edges | Schema change affects all edge writers; JOIN is simpler for Phase 25 |

## Architecture Patterns

### Recommended Changes Map
```
~/.claude/CLAUDE.md                     # Additive: GENUS line in declaration format
~/.claude/skills/genus-first/SKILL.md   # Additive: Mode A bus path in Step 3

src/pipeline/live/bus/
├── server.py          # +genus_consult() handler, +Route in create_app()
├── models.py          # +GenusConsultRequest, +GenusConsultResponse
└── schema.py          # No changes (axis_edges already exists via pipeline schema)

src/pipeline/live/hooks/
└── session_start.py   # +genus hint section after relevant_docs

src/pipeline/live/genus_oracle.py  # NEW: GenusOracleHandler class
                                   #   - query_genus(problem, repo?) -> GenusConsultResponse
                                   #   - Uses tokenization matching on axis_a
                                   #   - Extracts instances from evidence JSON
                                   #   - Computes confidence score
```

### Pattern 1: Bus Endpoint Handler (Existing Pattern)
**What:** Async handler function registered as a Route in create_app()
**When to use:** Every bus endpoint follows this pattern
**Example (from server.py):**
```python
# Source: src/pipeline/live/bus/server.py lines 108-135
async def check(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        briefing = _daemon.get_briefing(
            body.get("session_id", ""),
            body.get("run_id", ""),
            repo=body.get("repo", None),
        )
        return JSONResponse({...})
    except Exception:
        resp = CheckResponse()
        return JSONResponse({...})  # fail-open default
```

### Pattern 2: Session Start Hint (Existing Pattern)
**What:** `_post_json()` call followed by conditional stdout print with `[OPE]` prefix
**When to use:** Adding genus hint mirrors the relevant_docs pattern (Phase 21)
**Example (from session_start.py):**
```python
# Source: src/pipeline/live/hooks/session_start.py lines 119-130
relevant_docs = check.get("relevant_docs", [])
if relevant_docs:
    print(f"\n[OPE] {len(relevant_docs)} relevant doc(s) for this session:", flush=True)
    for doc in relevant_docs[:3]:
        path = doc.get("doc_path", "")
        axis = doc.get("ccd_axis", "")
        # ...
```

### Pattern 3: Tokenization-Based Genus Matching (Adapted from doc_query.py)
**What:** Split problem description into tokens, match against `axis_a` values in `axis_edges WHERE relationship_text = 'genus_of'`
**When to use:** For `/api/genus-consult` endpoint
**Example (adapted from doc_query.py):**
```python
# Source: src/pipeline/doc_query.py lines 58-83
def _tokenize(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in raw if t not in QUERY_STOPWORDS and len(t) > 2}

def _score_axis_match(query_tokens: set[str], axis: str) -> int:
    tokens = _axis_non_stop_tokens(axis)
    if len(tokens) < _MIN_AXIS_TOKENS:
        return 0
    return sum(1 for t in tokens if t.lower() in query_tokens)
```

### Pattern 4: Test Client for Bus Endpoints
**What:** httpx AsyncClient with ASGITransport, file-based DuckDB for verification
**When to use:** All bus endpoint tests
**Example (from test_push_links.py):**
```python
# Source: tests/test_push_links.py lines 28-48
@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")

@pytest.fixture
def app(db_path, tmp_path):
    daemon = GovernorDaemon(
        db_path=":memory:",
        constraints_path=str(tmp_path / "nonexistent" / "constraints.json"),
    )
    return create_app(db_path=db_path, daemon=daemon)

@pytest.fixture
def client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
```

### Anti-Patterns to Avoid
- **Opening a separate DuckDB connection in the handler:** The bus server already has `conn` in the closure scope. Opening another connection causes single-writer conflicts. Use the existing `conn` object.
- **Adding axis_edges creation to bus schema.py:** `axis_edges` is created by `create_topology_schema()` called from the pipeline's `create_schema()`. The bus server accesses it through the shared `ope.db` file. Adding redundant DDL creates confusion about ownership.
- **Blocking on empty axis_edges:** `axis_edges` currently has 0 genus_of rows. The handler MUST return a valid response (`{"genus": null, "instances": [], "valid": false, "confidence": 0.0}`) when no matches found. This is the cold-start case.
- **Using read_only=True for the handler's DuckDB connection:** DuckDB rejects read_only connections when a read-write connection is already open to the same file. The bus server already has a read-write connection. Query through it.

## Critical Technical Findings

### Finding 1: axis_edges Has No Repo Column
**Confidence:** HIGH
**Source:** `src/pipeline/ddf/topology/schema.py` AXIS_EDGES_DDL

`axis_edges` columns: `edge_id, axis_a, axis_b, relationship_text, activation_condition, evidence, abstraction_level, status, trunk_quality, created_session_id, created_at`. No `repo` column.

**Implication for session_start.py genus hint:** Cannot query `axis_edges WHERE repo = ?` directly. Two options:
1. **JOIN through bus_sessions:** `SELECT COUNT(*) FROM axis_edges ae JOIN bus_sessions bs ON ae.created_session_id = bs.session_id WHERE ae.relationship_text = 'genus_of' AND bs.repo = ?`
   - Problem: `bus_sessions` only exists when bus server has started and registered sessions. Table may not exist.
2. **Query all genus_of edges via bus endpoint:** Add genus count to the `/api/check` response, or add a dedicated field in the check response.
   - Better: the bus server's DuckDB conn has both tables available.

**Recommendation:** For session_start.py, extend `/api/check` response to include a `genus_count` field (like it already includes `relevant_docs`). The daemon handles the query. Alternatively, session_start.py can query axis_edges directly from bus (POST /api/genus-consult with just repo parameter).

### Finding 2: axis_edges Currently Has 0 Rows
**Confidence:** HIGH
**Source:** DuckDB query `SELECT COUNT(*) FROM axis_edges` returned 0

No genus_of edges have been ingested. `data/genus_staging.jsonl` exists but is empty. This means:
- All tests must seed their own genus_of edges in the test DB
- The session_start hint must handle the 0-edge case gracefully (emit nothing)
- The integration test (SC 5) must create the A7/CRAD genus_of edge in the test fixture

### Finding 3: Bus Server Connection Shares ope.db with Pipeline
**Confidence:** HIGH
**Source:** `create_app(db_path="data/ope.db")` in server.py; `create_schema(conn)` in storage/schema.py creates axis_edges in same ope.db

The bus server's `conn = duckdb.connect(db_path)` at line 46 of server.py gets a connection to the same DB that contains `axis_edges`. However, `create_bus_schema(conn)` does NOT call `create_topology_schema()` -- it only creates bus_sessions, governance_signals, push_links, and doc_index.

**Implication:** The `/api/genus-consult` handler can query `axis_edges` through the existing `conn` IF the table exists. Must check for table existence first (same pattern as `_check_frontier_warning()` in premise_gate.py):
```python
tables = conn.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_name = 'axis_edges'"
).fetchall()
if not tables:
    return JSONResponse({"genus": None, ...})  # fail-open
```

### Finding 4: GenusEdgeWriter Evidence Structure
**Confidence:** HIGH
**Source:** `src/pipeline/premise/genus_writer.py` lines 76-84

Evidence JSON for genus_of edges:
```python
evidence = {
    "instances": instances or [],        # list of instance name strings
    "source": "genus_check_gate",
    "session_id": session_id,
}
```

The `/api/genus-consult` handler needs to extract `instances` from the evidence JSON for the response. DuckDB supports `json_extract(evidence, '$.instances')` for this.

### Finding 5: CLAUDE.md Structure for GENUS Field
**Confidence:** HIGH
**Source:** `~/.claude/CLAUDE.md` (92 lines, read in full)

The current CLAUDE.md has:
1. `## Premise Declaration Protocol` header
2. `### Declaration Format` with 4-line block: PREMISE, VALIDATED_BY, FOIL, SCOPE
3. `### Staleness Rule`
4. `### Foil Verification Format`
5. `### The Test`
6. `### Why This Exists`

The GENUS field goes as an optional 5th line in the Declaration Format block, right after SCOPE:
```
PREMISE: [claim]
VALIDATED_BY: [evidence]
FOIL: [confusable] | [distinguishing property]
SCOPE: [validity context]
GENUS: [mechanism name] | INSTANCES: [instance A, instance B]
```

Plus a new `### Genus Declaration` subsection explaining fundamentality criterion and mechanism-vs-symptom distinction. Must be additive-only -- no changes to existing PREMISE/VALIDATED_BY/FOIL/SCOPE fields.

### Finding 6: SKILL.md Is Markdown, Not Python
**Confidence:** HIGH
**Source:** `~/.claude/skills/genus-first/SKILL.md` (171 lines, read in full)

The SKILL.md is a declarative instruction document read by Claude Code. Changes are pure markdown edits. Step 3 ("Detect Capabilities") currently checks for `src/pipeline/premise/fundamentality.py` OR `data/ope.db`. The new Mode A bus path adds a third check:
- OPE mode: `fundamentality.py` exists OR `data/ope.db` exists
- **Bus mode (NEW):** `data/ope.db` absent AND `OPE_BUS_SOCKET` is set
- Lightweight mode: none of the above

The `genus-framework.md` already documents "Future Capability: Bus-Mediated Genus Oracle" at line 107. This section gets replaced with the actual implementation instructions.

### Finding 7: session_start.py Uses /api/check for All Data
**Confidence:** HIGH
**Source:** `src/pipeline/live/hooks/session_start.py` lines 94-130

session_start.py currently makes two bus calls: `/api/register` and `/api/check`. All session-start data comes through `/api/check` response (constraints, relevant_docs). For genus hint:

**Option A:** Extend `/api/check` response to include `genus_count` (like `relevant_docs`). This follows the existing pattern and avoids a third bus call.
**Option B:** Add a third call to `/api/genus-consult` from session_start.py.

**Recommendation:** Option A (extend /api/check) for the genus hint count. It's a single integer and doesn't warrant a separate HTTP call. The daemon already opens a DuckDB connection for doc queries -- add a genus count query there.

### Finding 8: Confidence Scoring Algorithm
**Confidence:** MEDIUM (design recommendation, not from existing code)

For `/api/genus-consult`, confidence should be computed as:
```
confidence = matched_tokens / total_genus_tokens
```
Where `matched_tokens` = count of genus name tokens found in the problem description, and `total_genus_tokens` = total non-stopword tokens in the genus name. This directly mirrors `doc_query.py`'s `_score_axis_match()`.

If multiple genus_of edges match, return the one with highest confidence (top-1 by specification). A confidence of 0.0 means no match; 1.0 means all genus tokens matched.

Example: problem = "per-file searchability is broken for minority files"
- Genus "corpus-relative identity retrieval" -> tokens: [corpus, relative, identity, retrieval]
- Query tokens: [per, file, searchability, broken, minority, files]
- Match: 0/4 -> confidence 0.0 (no match)
- But if problem = "corpus relative searchability retrieval" -> 3/4 -> confidence 0.75

This is adequate for Phase 25 -- not a vector search, just token overlap. The `/genus-first` skill provides the full genus context when invoked explicitly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text tokenization | Custom tokenizer | `doc_query._tokenize()` pattern | Already handles stopwords, short tokens, splitting |
| Axis name scoring | Custom scorer | `doc_query._score_axis_match()` pattern | Already tested, handles min-token threshold |
| Bus HTTP calls | Raw socket code | `session_start._post_json()` | Already handles timeouts, Unix socket, fail-open |
| DuckDB JSON extraction | Manual JSON parsing | `json_extract()` / `json_extract_string()` | DuckDB native; already used in premise_gate.py line 148 |
| Async test client | Manual test server | `httpx.AsyncClient(transport=ASGITransport(app=app))` | Pattern used in all 5 bus test files |

## Common Pitfalls

### Pitfall 1: DuckDB Single-Writer Conflict
**What goes wrong:** Opening a second DuckDB connection to the same file while the bus server holds a write connection causes a lock error.
**Why it happens:** DuckDB allows one write connection per file. The bus server's `conn = duckdb.connect(db_path)` is a write connection.
**How to avoid:** The `/api/genus-consult` handler MUST use the server's existing `conn` object (passed through closure or app state), never open a new connection.
**Warning signs:** `duckdb.IOException: Could not set lock on file` in tests or production.

### Pitfall 2: axis_edges Table Not Existing at Bus Startup
**What goes wrong:** The bus server creates `bus_sessions`, `governance_signals`, `push_links`, `doc_index` at startup via `create_bus_schema()`. But `axis_edges` is created by the pipeline's `create_schema()` -> `create_ddf_schema()` -> `create_topology_schema()`. If the bus starts before the pipeline has ever run, `axis_edges` does not exist.
**Why it happens:** Two separate schema creation paths share the same DB file.
**How to avoid:** Check for table existence before querying (same pattern as premise_gate.py and daemon.py). Return empty/null result if table missing.
**Warning signs:** `CatalogException: Table with name axis_edges does not exist!`

### Pitfall 3: bus_sessions Not Existing for Repo JOIN
**What goes wrong:** Querying `JOIN bus_sessions ON ...` fails if bus_sessions doesn't exist yet.
**Why it happens:** bus_sessions is created by create_bus_schema(), but if you're in a test or a context where only create_schema() was called (no bus), it won't exist.
**How to avoid:** For tests: call both `create_schema(conn)` and `create_bus_schema(conn)`. For production: check table existence before JOIN.
**Warning signs:** `CatalogException: Table with name bus_sessions does not exist!` -- exactly what happened in our research query.

### Pitfall 4: Empty genus_staging.jsonl / 0 Genus Edges
**What goes wrong:** Tests pass with seeded data but the feature appears broken in production because no genus_of edges have been ingested yet.
**Why it happens:** Phase 24 set `block_on_invalid: false` and genus is advisory-only. No PREMISE blocks with GENUS field have been written yet, so no genus_staging records exist.
**How to avoid:** All user-facing messages must handle the 0-edge case gracefully. session_start.py emits nothing when genus_count = 0 (same as constraints/docs when empty). `/api/genus-consult` returns `{"genus": null, "valid": false, "confidence": 0.0}`.
**Warning signs:** `[OPE] 0 prior genera` message in stdout (should be silent).

### Pitfall 5: Timeout in session_start.py
**What goes wrong:** Adding a third bus call (genus-consult) to session_start.py increases total hook latency. If the bus is slow, the session start hook might feel sluggish.
**Why it happens:** Each `_post_json()` has a 1.0s timeout. Three calls = up to 3.0s worst case.
**How to avoid:** Extend `/api/check` response with genus data rather than adding a separate call. One bus call returns constraints + docs + genus hint.

### Pitfall 6: CLAUDE.md Edit Breaking Existing Format
**What goes wrong:** Adding the GENUS field changes the parsing expectations for PREMISE blocks in `premise_gate.py`'s `parse_premise_blocks()`.
**Why it happens:** The parser already handles GENUS -- it was added in Phase 24.
**How to avoid:** Verify `parse_premise_blocks()` already handles the GENUS line before editing CLAUDE.md. If it does (it should per Phase 24), the CLAUDE.md edit is purely documentation.
**Warning signs:** PREMISE blocks with GENUS field not being parsed correctly.

## Code Examples

### Example 1: Genus Oracle Query (axis_edges search)
```python
# Adapted from doc_query.py pattern
import re
from typing import Any

QUERY_STOPWORDS = frozenset({
    "not", "vs", "as", "to", "the", "a", "an", "in", "of", "for", "is",
    "and", "or", "but", "if", "by", "on", "at", "up", "out", "be",
    # ... (reuse from doc_query.py)
})

def _tokenize(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in raw if t not in QUERY_STOPWORDS and len(t) > 2}

def query_genus(
    conn, problem: str, repo: str | None = None
) -> dict[str, Any]:
    """Find best-matching genus for a problem description."""
    # Check table exists
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'axis_edges'"
    ).fetchall()
    if not tables:
        return {"genus": None, "instances": [], "valid": False, "confidence": 0.0}

    # Fetch all genus_of edges
    rows = conn.execute(
        "SELECT axis_a, evidence FROM axis_edges "
        "WHERE relationship_text = 'genus_of' "
        "AND status IN ('candidate', 'active')"
    ).fetchall()

    if not rows:
        return {"genus": None, "instances": [], "valid": False, "confidence": 0.0}

    query_tokens = _tokenize(problem)
    if not query_tokens:
        return {"genus": None, "instances": [], "valid": False, "confidence": 0.0}

    best_genus = None
    best_score = 0.0
    best_evidence = {}

    for axis_a, evidence_json in rows:
        genus_tokens = [
            t for t in re.findall(r"[a-zA-Z]+", axis_a.lower())
            if t not in QUERY_STOPWORDS and len(t) > 2
        ]
        if not genus_tokens:
            continue
        matched = sum(1 for t in genus_tokens if t in query_tokens)
        score = matched / len(genus_tokens)
        if score > best_score:
            best_score = score
            best_genus = axis_a
            best_evidence = json.loads(evidence_json) if isinstance(evidence_json, str) else evidence_json

    if best_genus is None or best_score == 0.0:
        return {"genus": None, "instances": [], "valid": False, "confidence": 0.0}

    instances = best_evidence.get("instances", [])
    return {
        "genus": best_genus,
        "instances": instances[:2],  # top 2 as per spec
        "valid": len(instances) >= 2,
        "confidence": round(best_score, 2),
    }
```

### Example 2: Bus Handler Registration (follow push_link pattern)
```python
# In server.py create_app()
async def genus_consult(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        problem = body.get("problem", "")
        session_id = body.get("session_id", "")
        repo = body.get("repo", None)
        result = _genus_oracle.query_genus(problem, repo)
        return JSONResponse(result)
    except Exception:
        return JSONResponse({
            "genus": None, "instances": [], "valid": False, "confidence": 0.0
        })

# Add to routes:
Route("/api/genus-consult", genus_consult, methods=["POST"]),
```

### Example 3: session_start.py Genus Hint
```python
# After relevant_docs section, before exit
genus_count = check.get("genus_count", 0)
if genus_count > 0:
    print(
        f"\n[OPE] GENUS: {genus_count} prior genera available "
        f"-- /genus-first before writing",
        flush=True,
    )
```

### Example 4: CLAUDE.md GENUS Addition
```markdown
### Declaration Format

\`\`\`
PREMISE: [claim]
VALIDATED_BY: [evidence]
FOIL: [confusable] | [distinguishing property]
SCOPE: [validity context]
GENUS: [mechanism name] | INSTANCES: [instance A, instance B]
\`\`\`

The GENUS line is optional. Include it when your write addresses a problem
that has a nameable mechanism (what process, when absent, causes the failure).
\`\`\`

### Genus Declaration

The GENUS field declares the fundamental mechanism behind a problem before
implementing a fix. A valid genus satisfies:
1. **Two citable instances** -- 2+ specific occurrences of the same failure class
2. **Causal explanation** -- the name encodes a mechanism, not a symptom
3. **Mechanism-vs-symptom test** -- does the name imply the solution structure?

| Symptom (invalid) | Mechanism (valid) |
|-------------------|-------------------|
| "search failure"  | "corpus-relative identity retrieval" |
| "import error"    | "module boundary dissolution" |

If the solution structure is not readable from the genus name, the genus
is probably still at the symptom level.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No genus in PREMISE blocks | GENUS as optional 5th line (Phase 24) | Phase 24 | PAG parses GENUS, FundamentalityChecker validates |
| No genus staging | genus_staging.jsonl + batch ingestion (Phase 24) | Phase 24 | GenusEdgeWriter builds EdgeRecord + FlameEvent |
| /genus-first OPE mode only | Bus oracle path (Phase 25 target) | Phase 25 | Cross-session genus access without importing OPE |
| Manual genus identification | Automatic genus hint at session start (Phase 25 target) | Phase 25 | Passive advisory for all sessions |

## Open Questions

1. **Should /api/check return genus_count, or should session_start.py make a separate /api/genus-consult call?**
   - What we know: session_start.py already makes 2 calls (register + check). Adding a 3rd increases latency.
   - What we know: The daemon already opens a DuckDB connection for doc queries; adding a genus count query is trivial.
   - Recommendation: Extend /api/check response. Add `genus_count` to CheckResponse model and have daemon query it.

2. **How to handle repo scoping with no repo column on axis_edges?**
   - What we know: axis_edges has `created_session_id` but no `repo`. bus_sessions has `repo` but may not exist.
   - What we know: In the bus server context, bus_sessions WILL exist (created at server startup).
   - Recommendation: For the bus handler (where bus_sessions exists), JOIN through bus_sessions. For session_start genus hint, rely on the /api/check response (daemon handles repo scoping internally). For the cold-start case (0 edges), no scoping needed.

3. **Should the genus oracle also search the evidence text field, or only axis_a (genus name)?**
   - What we know: evidence contains `{"instances": [...], "source": "genus_check_gate", "session_id": "..."}`. The instances are short string names.
   - Recommendation: Search both axis_a (primary) and evidence.instances (secondary, lower weight). This increases recall when the problem description mentions a known instance rather than the genus name.

## Sources

### Primary (HIGH confidence)
- `src/pipeline/live/bus/server.py` -- bus endpoint pattern, create_app structure
- `src/pipeline/live/bus/models.py` -- Pydantic models for bus requests/responses
- `src/pipeline/live/bus/schema.py` -- bus schema DDL, create_bus_schema
- `src/pipeline/live/hooks/session_start.py` -- session start hook, _post_json, [OPE] pattern
- `src/pipeline/live/hooks/premise_gate.py` -- _check_genus, existing genus handling in PAG
- `src/pipeline/premise/genus_writer.py` -- GenusEdgeWriter, evidence JSON structure
- `src/pipeline/premise/fundamentality.py` -- FundamentalityChecker, FundamentalityResult
- `src/pipeline/ddf/topology/schema.py` -- axis_edges DDL, no repo column
- `src/pipeline/ddf/topology/writer.py` -- EdgeWriter, query patterns for axis_edges
- `src/pipeline/ddf/topology/models.py` -- EdgeRecord, ActivationCondition
- `src/pipeline/doc_query.py` -- tokenization + scoring pattern (reusable for genus matching)
- `src/pipeline/live/governor/daemon.py` -- GovernorDaemon, get_briefing, _query_relevant_docs
- `src/pipeline/live/bus/doc_schema.py` -- doc_index DDL pattern for additive schema
- `~/.claude/CLAUDE.md` -- current Premise Declaration Protocol (92 lines)
- `~/.claude/skills/genus-first/SKILL.md` -- current /genus-first skill (171 lines)
- `~/.claude/skills/genus-first/genus-framework.md` -- genus framework reference

### Test patterns (HIGH confidence)
- `tests/test_bus_foundation.py` -- bus endpoint test fixtures, httpx ASGITransport
- `tests/test_bus_integration.py` -- cross-session tests, file-based DuckDB verification
- `tests/test_push_links.py` -- round-trip testing pattern, field validation, idempotency
- `tests/pipeline/premise/test_genus_writer.py` -- genus staging roundtrip tests

### Data state verification (HIGH confidence)
- DuckDB query: `axis_edges` has 0 rows, no genus_of edges ingested yet
- DuckDB query: `bus_sessions` does not exist in ope.db (created by bus server)
- File check: `data/genus_staging.jsonl` exists but is empty

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- all patterns directly observed in existing code
- Pitfalls: HIGH -- each identified from actual DuckDB query results and code review
- Text matching algorithm: MEDIUM -- design recommendation adapted from doc_query.py, not yet tested in genus context

**Research date:** 2026-02-28
**Valid until:** 2026-03-30 (stable project, no external dependency changes expected)
