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

## Decision 2: Session Data Storage and Backup Strategy

**Decision:** ALWAYS COPY sessions to `data/raw/PROJECT/sessions/` and COMMIT TO GIT

**Rationale:**
- **Data loss prevention:** Raw session data is irreplaceable research data - losing it would be catastrophic
- **Reproducibility:** Anyone cloning the repo gets complete dataset (sessions + DuckDB)
- **Portability:** Self-contained project can be zipped, moved, or shared
- **Size is manageable:** 250 MB - 1 GB total sessions across 5 projects fits comfortably in Git
- **Sessions are append-only:** Git handles this efficiently (no repeated changes to old files)
- **Simple backup strategy:** No need for external S3/Dropbox/LFS setup

**Implementation:**
```bash
# When adding a project
scripts/add-project.py --name "My Project" --copy-sessions
# Copies ~/.claude/projects/PROJECT-HASH/* to data/raw/PROJECT/sessions/

# Sessions committed to git (NOT in .gitignore)
git add data/raw/PROJECT/sessions/*.jsonl
git commit -m "data: Add PROJECT sessions (X files, Y MB)"
```

**Git Strategy:**
- Sessions in `data/raw/*/sessions/` are **committed normally** (not excluded)
- New sessions added as project progresses (incremental commits)
- `.gitignore` excludes other temporary/large files, but NOT sessions

**Backup Layers:**
1. **Primary:** `~/.claude/projects/` (original)
2. **Local backup:** `data/raw/PROJECT/sessions/` (copy)
3. **Remote backup:** GitHub (via git push)
4. **Extracted data:** `data/ope.db` (DuckDB - can reconstruct if needed)

**Implications:**
- ✅ Safe from local data loss (3 copies: original + local backup + GitHub)
- ✅ Reproducible research (others can clone and verify)
- ✅ Portable project (can move/share entire repo)
- ⚠️ Git repo grows to ~500 MB - 1.5 GB (sessions + code + DuckDB)
- ⚠️ Initial clone takes longer (~2-5 minutes vs. seconds)
- ⚠️ Need to be mindful of session size when adding projects (>200 MB/project → consider Git LFS)

**Alternatives Considered:**
- ❌ Reference in place → Risky, not portable, data loss if ~/.claude/ deleted
- ❌ Copy but exclude from git → No remote backup, need external strategy
- ❌ Git LFS → Unnecessary complexity for current data size, bandwidth limits
- ❌ Extract to DB only → Loses raw format, can't re-run extraction with different logic

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

## Decision 4: Episode Dataset Format and Query Engine

**Decision:** DuckDB as primary database with persistent storage, JSONL/Parquet exports for specific use cases

**Rationale:**
- **Daily incremental updates:** New sessions/commits added daily → incremental database updates are much faster than re-processing all JSONL files
- **Analytical query performance:** DuckDB is optimized for OLAP (aggregations, filtering, joins) which matches our read-heavy analytical access patterns
- **Direct JSONL querying:** DuckDB can query JSONL files directly without pre-loading, enabling flexible exploration early on
- **Format flexibility:** Can export to JSONL (human inspection), Parquet (ML pipelines), or keep in DuckDB (analytical queries)
- **Proven for this use case:** Demonstrated effective for Claude Code log analysis (see: liambx.com/blog/claude-code-log-analysis-with-duckdb)

**Architecture:**
```
Daily workflow:
1. Detect new sessions/commits (modified since last update)
2. Process ONLY new data
3. INSERT/UPDATE into DuckDB database (incremental)
4. Database always current, no full re-scan

Ad-hoc queries:
- SELECT from DuckDB database (fast, indexed)
- Export subsets when needed (training data, validation sets)
```

**Implementation:**
- **Primary storage:** `data/ope.db` (DuckDB database file)
- **Tables:**
  - `sessions` - Raw session data (session_id, project_id, timestamp, message, etc.)
  - `commits` - Git commit metadata
  - `correlations` - Session-commit correlation results
  - `episodes` - Extracted turn-level episodes
  - `update_log` - Track processing timestamps for incremental updates
- **Optional exports:**
  - `data/processed/training_episodes.parquet` - ML training data
  - `data/validation/low_confidence.jsonl` - Manual review cases
  - Raw JSONL kept as archival backup (not primary working copy)

**Schema (DuckDB episodes table):**
```sql
CREATE TABLE episodes (
  episode_id VARCHAR PRIMARY KEY,
  project_id VARCHAR,
  session_id VARCHAR,
  turn_index INTEGER,
  timestamp TIMESTAMP,
  observation JSON,          -- Nested: conversation_context, file_state, phase_label, test_status, current_task
  claude_action JSON,        -- Nested: tool, parameters, reasoning
  user_reaction JSON,        -- Nested: type, message, next_action
  correlated_commit VARCHAR, -- SHA if available
  created_at TIMESTAMP,
  INDEX (project_id, timestamp),
  INDEX (session_id)
);
```

**Example queries:**
```sql
-- Find all test-running episodes
SELECT * FROM episodes
WHERE json_extract(claude_action, '$.tool') = 'Bash'
  AND json_extract(claude_action, '$.parameters.command') LIKE '%test%';

-- Count episodes by phase
SELECT json_extract(observation, '$.phase_label') as phase, COUNT(*)
FROM episodes
GROUP BY phase;

-- Export training data to Parquet
COPY (SELECT * FROM episodes WHERE timestamp < '2026-01-01')
TO 'data/processed/training_episodes.parquet' (FORMAT PARQUET);
```

**Implications:**
- ✅ Fast incremental updates (only process new sessions daily)
- ✅ Fast analytical queries (pre-indexed, no JSON parsing each time)
- ✅ Compact storage (DuckDB compression)
- ✅ Can export to any format (JSONL, Parquet, CSV) when needed
- ✅ Scales well as dataset grows (GB-range data)
- ⚠️ Need migration script if schema changes (ALTER TABLE)
- ⚠️ Single-writer limitation (fine for daily batch updates)

**Alternatives Considered:**
- ❌ JSONL only → Slow as dataset grows (full re-scan for every query)
- ❌ SQLite → Slower for analytical queries (OLTP-optimized, not OLAP)
- ❌ Parquet files only → No SQL interface, harder to query ad-hoc
- ❌ Re-query raw JSONL every time → Acceptable for exploration, but inefficient for production

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
| **Session backup** | **Copy + commit to git** | **Data loss prevention, reproducibility** | **0.1** |
| Git storage | Shallow clone + metadata | Balance size and utility | 0.3 |
| Query engine & storage | **DuckDB database** | Incremental updates, analytical queries | **0.1** |
| Episode format | DuckDB tables + exports | Fast queries, flexible exports | 0.1 |
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
