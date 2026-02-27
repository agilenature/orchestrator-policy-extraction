# CONTEXT.md — Phase 12: Governance Protocol Integration

**Generated:** 2026-02-20
**Phase Goal:** The pipeline ingests governance documents (pre-mortem files, DECISIONS.md) as structured constraint and wisdom sources. Stability check scripts run as episode outcome validators. Sessions performing bulk operations without a stability check are flagged.
**Synthesis Source:** Multi-provider AI analysis (OpenAI gpt-4.1, Gemini Pro, Perplexity Sonar Deep Research)

---

## Overview

Phase 12 closes the governance loop: human-authored governance artifacts (pre-mortem failure analyses, architectural decision records) are translated into machine-enforceable constraints and searchable wisdom entities. The challenge is bridging unstructured Markdown narrative to the structured stores already built in Phases 9–11.

The three providers reached consensus on all Tier 1 issues. The main risks are: (1) parsing fragility from unstructured Markdown, (2) ambiguous "bulk operation" definition leading to noisy flagging, and (3) dual-store atomicity given ConstraintStore (JSON) and WisdomStore (DuckDB).

**Confidence markers:**
- ✅ **Consensus** — All 3 providers identified this as critical
- ⚠️ **Recommended** — 2 providers identified this as important
- 🔍 **Noted** — 1 provider identified, potentially important

---

## Gray Areas Identified

### ✅ 1. Document Format Parsing Strategy (Consensus)

**What needs to be decided:**
How `govern ingest <file>` identifies and extracts failure stories and assumptions from unstructured Markdown, and whether a strict schema is required.

**Why it's ambiguous:**
Neither pre-mortem files nor DECISIONS.md have a mandated structure in the project. The reference dataset (objectivism pre-mortem) is the only empirical grounding — we don't know if its section headers are typical or idiosyncratic.

**Provider synthesis:**
- **OpenAI:** Strict schema with YAML frontmatter + required sections; reject non-conforming files
- **Gemini:** Config-driven header-hierarchy parser; tolerate variation in header phrasing
- **Perplexity:** Layered architecture (section detection → content extraction); lightweight template guidance, no hard schema requirement

**Proposed implementation decision:**
Header-hierarchy parser with a configurable keyword list for section recognition. H2 headers containing "Failure Stories", "Ways We Could Fail", or "Stories" → `dead_end` extraction mode. Headers containing "Assumptions", "Key Assumptions", "Core Assumptions" → constraint extraction mode. Headers containing "Decisions", "Scope Decisions" → `scope_decision` extraction mode. No YAML frontmatter required (reduces friction, the objectivism pre-mortem doesn't have it). Files that produce zero extracted entities emit a warning but don't hard-fail.

**Open questions:**
- Does the objectivism pre-mortem use H2 or H3 for section headers?
- Are there multiple pre-mortem files to ingest, or one canonical file?

---

### ✅ 2. Failure Story vs. Assumption Classification (Consensus)

**What needs to be decided:**
Within a "Failure Stories" section, how individual stories are extracted (paragraph vs. list item vs. sub-heading). Within an "Assumptions" section, how individual assumptions are extracted (one per sentence? one per list item?).

**Why it's ambiguous:**
Pre-mortem documents blend narrative and factual statement. A single paragraph may contain both a failure narrative and the assumption it violated.

**Provider synthesis:**
- **OpenAI:** Linguistic heuristics — conditional/outcome phrasing → dead_end; declarative/assertion phrasing → constraint
- **Gemini:** Section header as primary signal; numbered/bulleted list items as story/assumption units
- **Perplexity:** Multi-stage — section context first, then linguistic markers (conditional phrases, "must"/"assumes"), then human-in-loop override

**Proposed implementation decision:**
Use section context as primary classifier. Within failure-story sections: treat each top-level list item (or sub-heading block) as one `dead_end` entity. Within assumption sections: treat each list item as one constraint. Apply linguistic secondary check only to flag ambiguous items for the `--dry-run` output. No NLP — regex patterns only (e.g., `\b(could fail|risk of|if .+ then)\b` → dead_end signal, `\b(must|assumes|requires|shall)\b` → constraint signal).

**Open questions:**
- Are the 11 objectivism pre-mortem stories organized as a numbered list or as H3 sub-headers?
- Are the 15 assumptions a bulleted list or multi-paragraph?

---

### ✅ 3. Bulk Operation Definition (Consensus)

**What needs to be decided:**
The precise technical threshold that makes a session "bulk" and triggers the missing_validation requirement.

**Why it's ambiguous:**
"Multi-file writes, mass git commits" is examples, not a definition. OpenAI anchored on git commit metadata, Gemini on tool-call count per episode, Perplexity on store-modification entity count — three valid but different signals.

**Provider synthesis:**
- **OpenAI:** Git-based thresholds: ≥10 files in one commit, or ≥500 lines changed, or `git add -A` pattern
- **Gemini:** Tool-call volume within an episode: Write/Edit tools called ≥3 times in one episode
- **Perplexity:** Store modification count: ≥5 entities modified across ConstraintStore + WisdomStore in one ingest call

**Proposed implementation decision:**
Two complementary signals, both configurable:
1. **Ingest bulk signal**: A `govern ingest` call that writes ≥5 entities (constraints + wisdom combined) is a bulk operation. This fires immediately and is easy to detect.
2. **Session bulk signal**: A session where ≥10 files were modified (via Write/Edit tool events) is a bulk session. This integrates with existing episode event stream.
Config key: `governance.bulk_ingest_threshold: 5` and `governance.bulk_session_file_threshold: 10`.

**Open questions:**
- Should generated files (e.g., test snapshots) count toward the session file threshold?

---

### ✅ 4. Stability Check Definition and Execution (Consensus)

**What needs to be decided:**
What a "stability check" is, what script it runs, how it's registered, and how results are stored.

**Why it's ambiguous:**
"Stability check scripts" is undefined — the project has 712 tests but no `tests/stability/` subset. It's unclear if stability = running all tests, a specific subset, or something else entirely.

**Provider synthesis:**
- **OpenAI:** YAML allowlist registry in config; subprocess with timeout; restricted cwd
- **Gemini:** Single `stability_check_command` in config (default: `pytest`); creates an Episode with `stability_check` type
- **Perplexity:** Multi-layer validation functions (constraint consistency, assumption consistency, cross-store deps)

**Proposed implementation decision:**
Register stability check commands in `data/config.yaml` under `governance.stability_checks` (array of `{id, command, timeout_seconds, description}`). Default entry: run the pipeline test suite. Execute via `subprocess.run` with `capture_output=True`, 120s timeout, repo root as cwd. Record result in a new DuckDB table `stability_outcomes(run_id UUID, check_id, session_id, status, exit_code, stdout, stderr, started_at, ended_at)`. CLI exit code: 0=all passed, 1=error, 2=any check failed.

**Open questions:**
- Is there a natural "stability subset" of the 712 tests to run, or should all tests run?

---

### ✅ 5. Missing Validation Flagging and Persistence (Consensus)

**What needs to be decided:**
Where and how "missing_validation" state is stored and surfaced. Is it a new episode type, a flag on existing episodes, or a DuckDB query?

**Why it's ambiguous:**
"Flagged as missing_validation episodes" implies persistence but doesn't specify the store schema or how the flag is detected. Gemini proposed a boolean column on the Episode table; Perplexity proposed episode metadata; OpenAI proposed a state machine with grace window.

**Provider synthesis:**
- **OpenAI:** `validation_pending` → `validated` / `missing_validation` state machine; 2-hour grace window
- **Gemini:** `requires_stability_check` boolean on Episode DuckDB table
- **Perplexity:** Episode metadata flag + ShadowReporter missing_validation_rate metric

**Proposed implementation decision:**
Add `requires_stability_check BOOLEAN DEFAULT FALSE` and `stability_check_status VARCHAR` (`pending`/`validated`/`missing`) to the `episodes` DuckDB table. A bulk operation (either ingest or session) sets `requires_stability_check=TRUE` on the relevant episode(s). After a stability check passes, update episodes to `stability_check_status='validated'`. The `govern check-stability` command also queries for `requires_stability_check=TRUE AND stability_check_status IS NULL` past a grace window (default 2h) and marks them `missing`. Add `missing_validation_rate` to ShadowReporter (sessions with missing flag / total sessions).

**Open questions:**
- Should a failed stability check still set `stability_check_status='validated'` (check was run) or leave it `pending` (not satisfied)?

---

### ✅ 6. Idempotency and Re-ingestion Semantics (Consensus)

**What needs to be decided:**
How re-ingesting the same pre-mortem file is handled. Should entities be updated, skipped, or duplicated?

**Why it's ambiguous:**
The reference dataset has exact target counts (11/15). Re-running would inflate counts if not idempotent.

**Provider synthesis:**
All 3 providers agreed: content-based SHA-256 identifiers + upsert semantics. The existing ConstraintStore already uses SHA-256(text + scope_paths). WisdomStore should match.

**Proposed implementation decision:**
Wisdom entity IDs: `w-` + first 16 hex chars of SHA-256(`entity_type + title + source_doc_id`). Constraint IDs: SHA-256(`text + JSON.stringify(scope_paths)`) — existing pattern. `govern ingest` uses WisdomIngestor upsert semantics for wisdom and ConstraintStore.add() (already dedup-aware) for constraints. Re-running the same file produces identical entity sets. IngestResult reports: `inserted=N`, `updated=M`, `skipped=K`.

---

### ✅ 7. Dual Store Integration: ConstraintStore (JSON) + WisdomStore (DuckDB) (Consensus)

**What needs to be decided:**
How one `govern ingest` call atomically writes to two different storage backends without corruption on partial failure.

**Why it's ambiguous:**
ConstraintStore is a JSON file; WisdomStore is DuckDB. They have different transaction semantics. OpenAI proposed dual-write with DuckDB mirror; Gemini proposed sequential with rollback; Perplexity proposed transaction-per-store.

**Proposed implementation decision:**
Sequential write with per-store atomicity:
1. Parse entire doc in memory first
2. Write constraints: load JSON → apply upserts → write to temp file → atomic rename (existing ConstraintStore pattern)
3. Write wisdom: DuckDB transaction via WisdomIngestor
4. If step 3 fails, constraints remain committed (acceptable — they're independently valid); log the partial failure
5. No new DuckDB `project_constraints` mirror table in Phase 12 (avoid over-engineering; JSON ConstraintStore remains the enforcement source of truth)

**Open questions:**
- Is it acceptable for constraints to commit even if wisdom fails? (Yes, per above — independently valid)

---

### ⚠️ 8. Constraint Severity Assignment from Assumptions (Recommended)

**What needs to be decided:**
How to map a parsed assumption statement to `warning` / `requires_approval` / `forbidden` severity automatically.

**Why it's ambiguous:**
GOVERN-01 doesn't specify severity rules for governance-ingested constraints.

**Provider synthesis:**
- **OpenAI:** Default `requires_approval`; apply `forbidden` heuristic for strong prohibition language
- **Perplexity:** Three-tier mapping (security impact → forbidden, functional impact → requires_approval, best-practice → warning)

**Proposed implementation decision:**
Default: `requires_approval`. Apply `forbidden` upgrade heuristic: if assumption text matches `\b(must not|never|forbidden|do not|shall not)\b` (case-insensitive) → `forbidden`. Record `created_by: "govern_ingest"` and `source_excerpt: <original text>` on all ingested constraints for traceability.

---

### ⚠️ 9. Wisdom-Constraint Linkage Model (Recommended)

**What needs to be decided:**
How a dead_end wisdom entity references the constraints extracted from the same pre-mortem document.

**Why it's ambiguous:**
Success criterion says "dead_end wisdom entities with associated constraints" but the linkage mechanism is unspecified.

**Provider synthesis:**
- **OpenAI:** Join table `wisdom_constraint_links` with heuristic string-overlap
- **Perplexity:** Optional `related_constraint_ids` field on wisdom entity + semantic search
- **Gemini:** `related_constraints: List[str]` in wisdom entity metadata

**Proposed implementation decision:**
Add `related_constraint_ids: List[str]` to the WisdomEntity `metadata` JSON field (no schema change needed — metadata is already a flexible JSON column). During ingest, populate via simple co-occurrence heuristic: if a failure story and an assumption come from the same document, link them (all constraints from document → referenced by all dead_ends from document). Refine in a future phase with semantic similarity. No join table for Phase 12 — keep it simple.

---

### ⚠️ 10. Reference Dataset Acceptance Test (Recommended)

**What needs to be decided:**
How strictly the pipeline's extraction is validated against the objectivism pre-mortem (11 stories → 11 dead_end, 15 assumptions → 15 constraints).

**Why it's ambiguous:**
Success criterion specifies exact counts but not whether content must exactly match.

**Provider synthesis:**
- **OpenAI:** Deterministic golden test with committed snapshot file for normalized text
- **Perplexity:** Integration test asserting exact counts; integration test verifying linkages

**Proposed implementation decision:**
Write an integration test that reads the objectivism pre-mortem file(s) from `docs/analysis/objectivism-knowledge-extraction/` and asserts: `len(dead_ends) == 11` and `len(constraints) == 15`. Do NOT commit a text snapshot (fragile to source edits). Count-based assertion is sufficient for Phase 12. Linkage validation can be added later.

---

### 🔍 11. Stability Check Execution Security Model (Noted)

**What needs to be decided:**
What trust/sandbox model applies when running stability check scripts.

**Why it's ambiguous:**
Only OpenAI raised this explicitly. Given the project runs locally as a single trusted operator, elaborate sandboxing may be over-engineering for Phase 12.

**Proposed implementation decision:**
For Phase 12 (local CLI, single trusted operator): subprocess execution with explicit timeout (120s) and repo root as cwd. No Docker/venv sandboxing. Add a note in the config schema that stability check commands should be project-local commands. Record `actor_name`/`actor_email` from git config on each stability run for audit trail.

---

## Summary: Decision Checklist

Before planning, confirm:

**Tier 1 (Blocking):**
- [x] Document parsing: header-hierarchy, config-driven section keywords, no YAML frontmatter required
- [x] Classification: section-header primary, linguistic regex secondary, list-item granularity
- [x] Bulk operation: ≥5 ingest entities OR ≥10 session file edits (both configurable)
- [x] Stability check: registered commands in config.yaml, subprocess execution, `stability_outcomes` DuckDB table
- [x] Missing validation: `requires_stability_check` + `stability_check_status` columns on episodes table
- [x] Idempotency: SHA-256 content IDs + upsert for both stores
- [x] Dual-store: sequential write, per-store atomic, no DuckDB constraint mirror

**Tier 2 (Important):**
- [x] Constraint severity: default `requires_approval`, forbidden heuristic for prohibition language
- [x] Wisdom-constraint linkage: `related_constraint_ids` in metadata, co-occurrence heuristic
- [x] Reference dataset test: count-based assertion (11 dead_ends, 15 constraints)

**Tier 3 (Polish):**
- [x] Stability check security: trusted operator, subprocess + timeout, no sandbox

---

*Multi-provider synthesis by: OpenAI gpt-4.1, Gemini Pro, Perplexity Sonar Deep Research*
*Generated: 2026-02-20*
