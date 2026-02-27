---
phase: 21-doc-index-floating-corpus-bridge
plan: 02
subsystem: pipeline
tags: [duckdb, yaml, frontmatter, regex, keyword-matching, ccd-axes, cli]

requires:
  - phase: 21-01
    provides: doc_index DuckDB schema (DDL + create_doc_schema)
provides:
  - 3-tier CCD axis extraction engine (frontmatter -> regex -> keyword)
  - doc_indexer.py with 9 independently testable functions
  - docs CLI group with reindex command
  - load_axis_vocabulary with DuckDB primary / MEMORY.md fallback
affects: [21-03, 21-04]

tech-stack:
  added: [pyyaml (already available)]
  patterns: [3-tier extraction cascade, bus safety gate before DuckDB writes, DELETE+INSERT idempotent refresh]

key-files:
  created:
    - src/pipeline/doc_indexer.py
    - src/pipeline/cli/docs.py
    - tests/test_doc_indexer.py
  modified:
    - src/pipeline/cli/__main__.py

key-decisions:
  - "Frontmatter axes accepted even if not in known_axes vocabulary (allows forward-declaring new axes)"
  - "Bus safety check via AF_UNIX socket connect with 1.0s timeout"
  - "MEMORY.md regex pattern reused from nversion.py: r'\\*\\*CCD axis:\\*\\*\\s+`([^`]+)`'"
  - "load_axis_vocabulary always includes 'always-show' (doc_index-only concept)"
  - "Description extraction joins consecutive prose lines, truncates at 200 chars with ... suffix"

patterns-established:
  - "3-tier axis extraction: frontmatter (1.0) -> regex (0.7) -> keyword (0.4) -> unclassified (0.0)"
  - "Bus safety gate pattern: check socket before DuckDB write operations"

duration: 3min
completed: 2026-02-27
---

# Phase 21 Plan 02: Doc Indexer Summary

**3-tier CCD axis extraction engine with frontmatter/regex/keyword cascade, docs CLI reindex command, and 31 passing tests**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-27T15:25:23Z
- **Completed:** 2026-02-27T15:28:54Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- 3-tier axis extraction cascade: Tier 1 (frontmatter, conf=1.0), Tier 2 (H1/H2 headers + HTML CCD comments, conf=0.7), Tier 3 (token frequency with stopword exclusion, conf=0.4)
- 9 independently testable functions in doc_indexer.py including bus safety gate, axis vocabulary loader, description extractor
- CLI `python -m src.pipeline.cli docs reindex` populates doc_index table via idempotent DELETE+INSERT refresh
- 31 passing tests covering all 3 tiers, Pitfall 4 (frontmatter line 0), Pitfall 5 (stopwords), cascade integration, DuckDB reindex, and CLI

## Task Commits

Each task was committed atomically:

1. **Task 1: Create doc_indexer.py with 3-tier axis extraction** - `4901620` (feat)
2. **Task 2: Create docs CLI group + register in __main__.py + tests** - `7e63254` (feat)

## Files Created/Modified
- `src/pipeline/doc_indexer.py` - 3-tier axis extraction engine (9 functions: load_axis_vocabulary, _parse_frontmatter_axes, _axis_in_headers_or_comments, _axis_token_match, extract_axes, _extract_description, _content_hash, _bus_is_running, reindex_docs)
- `src/pipeline/cli/docs.py` - Click group with reindex command following bus.py pattern
- `src/pipeline/cli/__main__.py` - Added docs_group import and registration
- `tests/test_doc_indexer.py` - 31 tests across 7 test classes

## Decisions Made
- Frontmatter axes accepted even if not in known_axes vocabulary (allows forward-declaring new axes before they appear in memory_candidates)
- Bus safety check via AF_UNIX socket connect with 1.0s timeout (matches existing bus detection pattern)
- MEMORY.md regex pattern reused from nversion.py for consistency
- load_axis_vocabulary always includes 'always-show' as doc_index-only concept
- Tier 3 token matching requires min 2 non-stopword tokens matched AND min 3 total occurrences

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- doc_index table can be populated via CLI: `python -m src.pipeline.cli docs reindex`
- Plan 21-03 (CheckResponse relevant_docs wiring) can now query doc_index for axis-matched docs
- Plan 21-04 (session-start briefing extension) can deliver relevant_docs in constraint briefings

---
*Phase: 21-doc-index-floating-corpus-bridge*
*Completed: 2026-02-27*
