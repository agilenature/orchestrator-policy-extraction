# Phase 0: Data Infrastructure Design Decisions

**Status:** IN PROGRESS
**Decision Date:** 2026-02-05
**Approver:** TBD (User review required)

---

## Critical Architectural Decisions

This document records the key decisions made during Phase 0 that will shape the entire project architecture.

---

## Decision 1: Multi-Project vs. Single-Project Architecture

**Decision:** MULTI-PROJECT architecture with per-project isolation and cross-project merging

**Rationale:**
- Dataset will grow beyond initial `modernizing-tool` project
- This project (`orchestrator-policy-extraction`) is itself a data source
- Different projects have different characteristics (phase structure, workflow, domain)
- Need to analyze both per-project and cross-project patterns

**Implications:**
- Project registry required (`data/projects.json`)
- Per-project directories in `raw/` and `processed/`
- Merged indices for cross-project analysis
- Processing scripts must handle project isolation

**Alternatives Considered:**
- ❌ Single unified dataset → No way to track project-specific patterns
- ❌ Separate repos per project → Fragmented tooling, hard to compare

---

## Decision 2: Session Data Storage Strategy

**Decision:** REFERENCE IN PLACE for active projects, COPY for archived projects

**Rationale:**
- Session data lives in `~/.claude/projects/` which is user-managed
- For active projects, sessions continue to accumulate → reference original location
- For archived/completed projects → copy for long-term preservation
- Avoids duplicating large datasets unnecessarily

**Implementation:**
- `metadata.json` includes `sessions.directory` field (absolute path)
- Processing scripts read from original location
- `scripts/archive-project.py` (future) copies sessions to `data/raw/PROJECT/sessions/`

**Implications:**
- Projects must specify whether sessions are copied or referenced
- Copied projects are portable (can share dataset)
- Referenced projects require access to original `~/.claude/` directory

**Alternatives Considered:**
- ❌ Always copy → Wastes disk space for active projects
- ❌ Always reference → Not portable, breaks if user deletes sessions
- ❌ Extract to DB → Loses raw format, harder to debug/inspect

---

## Decision 3: Git Repository Storage Strategy

**Decision:** SHALLOW CLONE with commit metadata extraction to JSON

**Rationale:**
- Full git history is large and mostly irrelevant
- Only need commits in date range (e.g., Feb 3-5, 2026)
- Commit metadata (message, author, timestamp, files changed) is small
- Diffs needed for hash extraction, but blobs can be discarded after

**Implementation:**
```bash
# Clone with shallow history
git clone --shallow-since="START_DATE" REPO_URL data/raw/PROJECT/git/

# Extract commit metadata
scripts/extract-git-metadata.py --project PROJECT
# Output: data/processed/PROJECT/git-metadata.json

# Optionally discard .git directory after extraction (saves space)
rm -rf data/raw/PROJECT/git/.git/
```

**Format (git-metadata.json):**
```json
{
  "commits": [
    {
      "sha": "abc123...",
      "author": "David Alfaro",
      "timestamp": "2026-02-03T10:23:00Z",
      "message": "feat(03.1-01): Add initial parser\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>",
      "files": [
        {"path": "src/parser.cpp", "status": "added"},
        {"path": "tests/test_parser.cpp", "status": "added"}
      ]
    }
  ]
}
```

**Implications:**
- Git repository not needed after metadata extraction (can delete)
- Metadata JSON is small (few KB per 100 commits)
- Can regenerate hashes from diffs (stored in metadata)

**Alternatives Considered:**
- ❌ Full clone → Too large, unnecessary history
- ❌ No clone (use GitHub API) → Rate limits, requires network, missing diffs
- ❌ Keep only .git directory → Still large, not human-readable

---

## Decision 4: Episode Dataset Format

**Decision:** JSONL (JSON Lines) for episodes, SQLite for queryable indices (future)

**Rationale:**
- **JSONL advantages:**
  - Human-readable (easy to inspect)
  - Streamable (process line-by-line)
  - Append-only (incremental updates)
  - Standard format (many tools support)
  - Good for RAG retrieval (load into vector DB)

- **SQLite for future:**
  - If dataset grows large (>10K episodes)
  - If need complex queries (JOIN episodes with correlations)
  - If performance becomes bottleneck

**Implementation:**
- Episodes: `data/processed/PROJECT/episodes/SESSION-ID.jsonl` (one per session)
- Merged: `data/merged/all-episodes.jsonl` (all projects combined)
- Optional: `data/merged/episodes.db` (SQLite view for queries)

**Schema (per episode):**
```json
{
  "episode_id": "modernizing-tool_session-abc_turn-05",
  "project": "modernizing-tool",
  "session_id": "abc123...",
  "turn_index": 5,
  "timestamp": "2026-02-01T14:23:00Z",
  "observation": {
    "conversation_context": [...],
    "file_state": [...],
    "phase_label": "03.1-01",
    "test_status": "passing",
    "current_task": "Implement parser"
  },
  "claude_action": {
    "tool": "Edit",
    "parameters": {...},
    "reasoning": "..."
  },
  "user_reaction": {
    "type": "approve",
    "message": "...",
    "next_action": {...}
  },
  "correlated_commit": "sha256_if_available"
}
```

**Implications:**
- Easy to add new fields (just append to JSON)
- Can load into pandas, DuckDB, vector DBs
- May need SQLite later for performance

**Alternatives Considered:**
- ❌ CSV → Not nested structures, hard to read
- ❌ Parquet → Binary, not human-readable, harder to append
- ❌ SQLite only → Harder to inspect, less portable

---

## Decision 5: Action Taxonomy Storage

**Decision:** JSON schema with hierarchical categories

**Rationale:**
- Need structured taxonomy for classifying tool calls
- Hierarchical (high-level → specific actions)
- Easy to update as we discover new patterns
- Can validate against schema

**Implementation:**

`data/action-taxonomy.json`:
```json
{
  "version": "1.0",
  "categories": [
    {
      "id": "inspect",
      "name": "Inspect Codebase",
      "description": "Read and analyze existing code",
      "actions": [
        {
          "id": "inspect.read",
          "name": "Read File",
          "tools": ["Read"],
          "pattern": "Single Read tool call"
        },
        {
          "id": "inspect.search",
          "name": "Search Codebase",
          "tools": ["Grep", "Glob"],
          "pattern": "Grep or Glob tool calls"
        }
      ]
    },
    {
      "id": "test",
      "name": "Run Tests",
      "description": "Execute test suites",
      "actions": [
        {
          "id": "test.unit",
          "name": "Run Unit Tests",
          "tools": ["Bash"],
          "pattern": "Bash with pytest/ctest/make test"
        }
      ]
    }
  ]
}
```

**Mapping Logic:**
- Rule-based: Tool name + parameters → action ID
- Extendable: Can add ML classifier later if needed

**Alternatives Considered:**
- ❌ Flat list → Hard to organize, no structure
- ❌ Hardcoded in Python → Less flexible, harder to update
- ❌ LLM-based classification → Too slow, not reproducible

---

## Decision 6: Reaction Taxonomy Storage

**Decision:** Similar JSON schema as action taxonomy, with categorization rules

`data/reaction-taxonomy.json`:
```json
{
  "version": "1.0",
  "categories": [
    {
      "id": "approve",
      "name": "Approve",
      "description": "User accepts action and continues",
      "indicators": {
        "keywords": ["good", "thanks", "continue", "yes"],
        "patterns": ["User asks next step without correction"]
      }
    },
    {
      "id": "correct",
      "name": "Correct",
      "description": "User points out mistake",
      "indicators": {
        "keywords": ["no", "wrong", "actually", "instead", "fix"],
        "patterns": ["User provides corrected version"]
      }
    }
  ]
}
```

**Rationale:** Same as action taxonomy (structured, versionable, extendable)

---

## Decision 7: Project Registry Schema

**Decision:** JSON file with per-project metadata and processing status

**Implementation:** `data/projects.json` (already created)

**Fields:**
- `id`: Unique project identifier
- `name`: Human-readable name
- `metadata_path`: Path to detailed metadata
- `status`: `pending_processing` | `processing` | `completed` | `archived`
- `added_date`: When project was added
- `notes`: Free-form notes

**Implications:**
- Single source of truth for project list
- Scripts iterate over registry for batch operations
- Easy to add/remove projects

---

## Decision 8: Correlation Precision Threshold

**Decision:** Minimum 0.7 correlation precision to include project in dataset

**Rationale:**
- Below 0.7 → too many false positives, unreliable ground truth
- 0.7-0.9 → acceptable with manual spot-checking
- >0.9 → excellent, high confidence

**Implementation:**
- `scripts/process-project.py` reports precision
- User reviews before accepting project
- Low-precision projects documented in `NOTES.md` (may exclude from training)

**Implications:**
- Some projects may not be usable if correlation fails
- Need manual labeling fallback for important projects

---

## Decision 9: Instrumentation Requirements

**Decision:** Session IDs in commits are HIGHLY RECOMMENDED but not required

**Rationale:**
- Session IDs enable 95%+ precision correlation
- But can fall back to heuristic matching (70-80% precision)
- Don't want to block retroactive analysis of old projects

**Tiers:**
- **Tier 1 (Best):** Session IDs + Claude attribution in commits
- **Tier 2 (Good):** Claude attribution only (use heuristics)
- **Tier 3 (Acceptable):** Neither (lower precision, manual validation)

**Implementation:**
- `INSTRUMENTATION.md` includes git hook setup
- `metadata.json` tracks instrumentation level
- Processing scripts adapt based on tier

---

## Decision 10: Versioning Strategy

**Decision:** Semantic versioning for schemas, dataset snapshots for releases

**Schema Versioning:**
- `data/projects.json` includes `schema_version`
- Taxonomies include `version` field
- Breaking changes → increment major version, add migration script

**Dataset Versioning:**
- Tag releases: `v1.0` (initial release), `v1.1` (added project), etc.
- Archive snapshots: `data/archived/v1.0/` for reproducibility
- Document in `CHANGELOG.md`

**Implications:**
- Reproducible experiments (pin to dataset version)
- Can evolve schema without breaking old code

---

## Decision Summary Table

| Decision | Choice | Rationale | Phase |
|----------|--------|-----------|-------|
| Architecture | Multi-project | Scalability, diversity | 0.2 |
| Session storage | Reference in place | Avoid duplication | 0.3 |
| Git storage | Shallow clone + metadata | Balance size and utility | 0.3 |
| Episode format | JSONL | Human-readable, streamable | 0.1 |
| Taxonomy format | JSON schema | Structured, versionable | 0.1 |
| Registry | JSON file | Simple, sufficient | 0.2 |
| Correlation threshold | >0.7 precision | Quality gate | 1.4 |
| Instrumentation | Recommended, not required | Flexibility | 0.4 |
| Versioning | Semantic + snapshots | Reproducibility | 0.1 |

---

## Open Questions (To Resolve)

### Q1: How to handle subagent sessions?
**Context:** Subagents create nested session directories

**Options:**
- A) Treat as separate episodes (link to parent)
- B) Merge into parent session timeline
- C) Track delegation as action, results as observation update

**Recommendation:** TBD in Phase 2.1 (session parsing)

### Q2: Should we extract file content snapshots?
**Context:** Episodes reference files, but files change over time

**Options:**
- A) Store full file content per episode (large but complete)
- B) Store file hashes only (small but need git repo to retrieve)
- C) Store diffs only (compact, reconstructable)

**Recommendation:** Option B (hashes) initially, can upgrade later

### Q3: How to handle deleted files or broken sessions?
**Context:** Session may reference files later deleted, sessions may be corrupted

**Options:**
- A) Skip episodes with missing data
- B) Mark as incomplete but include
- C) Attempt recovery (git history, backups)

**Recommendation:** Log in `parse-errors.log`, skip from training set

---

## Next Steps

1. ✅ Create directory structure (completed)
2. ✅ Document decisions (this file)
3. → Get user approval on decisions
4. → Implement Phase 0.3 (infrastructure)
5. → Create validation scripts (Phase 0.4)

---

## User Approval Required

**Please review the decisions above and confirm:**
- ✅ Multi-project architecture is correct
- ✅ Storage strategies (reference sessions, shallow clone git) are acceptable
- ✅ JSONL format for episodes is appropriate
- ✅ Correlation threshold (0.7) is reasonable
- ✅ Any decisions you disagree with or want to revise

**Once approved, we'll proceed to Phase 0.3 implementation.**
