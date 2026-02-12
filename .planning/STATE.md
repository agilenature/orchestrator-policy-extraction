# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-10)

**Core value:** Episodes capture how to decide what to do next (orchestrator decisions), not just what was delivered (commits), enabling policy learning that scales human judgment.
**Current focus:** Phase 6 IN PROGRESS - Mission Control Integration

## Current Position

Phase: 6 of 6 (Mission Control Integration)
Plan: 3 of 4 in current phase (Plans 01, 02, 03 complete)
Status: In progress
Last activity: 2026-02-12 -- Completed 06-02-PLAN.md (Episode capture from task lifecycle)

Progress: [################........] 75% (Phase 6 Plans 1-3)
Overall:  [████████████████████████████░] ~95% (19/20 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 19
- Average duration: 5.2 min
- Total execution time: 1.65 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-event-stream-foundation | 5 | 29 min | 5.8 min |
| 02-episode-population-storage | 4 | 19 min | 4.8 min |
| 03-constraint-management | 2 | 7 min | 3.5 min |
| 04-validation-quality | 2 | 11 min | 5.5 min |
| 05-training-infrastructure | 3 | 21 min | 7.0 min |
| 06-mission-control-integration | 3 | 12 min | 4.0 min |

**Recent Trend:**
- Last 5 plans: 9 min, 7 min, 5 min, 3 min, 4 min
- Trend: stable to decreasing

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Phase 0: DuckDB chosen as primary storage (incremental updates, analytical queries)
- Phase 0: Session backup via copy + commit to git (data loss prevention)
- Phase 0: Decision-point episodes (not turn-level) as correct unit
- Roadmap: 6-phase structure derived from 23 requirements across 6 categories
- Plan 01-01: Merged existing config patterns (tags, mode_inference, gates) into locked-decision config structure
- Plan 01-01: LabelDefinition sub-model for classification labels (not bare dict)
- Plan 01-01: CombinationModeConfig sub-model for risk_model.combination_mode
- Plan 01-01: episode_segments table has 16 columns (plan said 15, research SQL spec defines 16)
- Plan 01-02: DuckDB read_json_auto with union_by_name=true; message.content comes back as JSON string requiring re-parsing
- Plan 01-02: Resilient column detection via information_schema.columns for varying JSONL schemas
- Plan 01-02: Staging table upsert pattern for DuckDB (CREATE TEMP -> UPDATE -> INSERT -> DROP)
- Plan 01-02: Git log parser uses separator-detection rather than blank-line splitting
- Plan 01-03: Word-boundary regex matching for O_DIR mode inference keywords (prevents 'PR' matching 'production')
- Plan 01-03: Pre-compiled regex patterns in OrchestratorTagger for O_CORR and O_DIR matching
- Plan 01-03: tool_result inherits classifications from linked tool_use via tool_use_id map with source='inferred'
- Plan 01-04: O_CORR added as start trigger alongside O_DIR/O_GATE (corrections open new episodes)
- Plan 01-04: Context switches only counted after first body event (start trigger transition is normal flow)
- Plan 01-04: Last event timestamp tracked on segmenter instance, not as dynamic Pydantic attribute
- Plan 01-05: Validation measures invalid rate against filtered records, not raw count (excludes legitimately skipped types)
- Plan 01-05: Resilient isSidechain column detection in validation query for small JSONL files
- Plan 01-05: Fresh EpisodeSegmenter per session for clean state isolation
- Plan 01-05: Config hash from Pydantic model_dump_json() for deterministic provenance
- Plan 02-01: ConstraintScope separate from Scope (JSON Schema Constraint.scope has only paths, no avoid)
- Plan 02-01: EpisodePopulationConfig wired into PipelineConfig with defaults: 20 events, 300 seconds
- Plan 02-02: Position-based tie-breaking for same-priority mode inference keywords (earliest match in text wins)
- Plan 02-02: Observation derived from context events only (preceding episode), never from segment body events
- Plan 02-03: Refined ^NO block pattern to standalone-only (^NO[!.\s]*$) to prevent false-blocking corrections
- Plan 02-03: Why-question pattern broadened to \bwhy\b.*\? for natural language coverage
- Plan 02-04: Staging table + struct_pack() for STRUCT column insertion (avoids DuckDB binding issues)
- Plan 02-04: _find_next_human_message builds tag list from tag_by_event_id for ReactionLabeler compatibility
- Plan 02-04: Episode validation gates storage: invalid episodes logged but never written to episodes table
- Plan 03-01: Text normalization strips conversational prefixes via compiled regex (no NLP)
- Plan 03-01: Forbidden keywords take precedence over preferred when both present (hard correction not downgraded)
- Plan 03-01: Examples array populated with source episode as first entry during extraction
- Plan 03-02: ConstraintStore path configurable via constraints_path param for test isolation
- Plan 03-02: Duplicate constraints enrich existing examples array (new episode references appended)
- Plan 03-02: Constraint store saved only when extraction produced results (avoids unnecessary writes)
- Plan 04-01: Warnings use prefix convention (warning:type:) to distinguish from hard errors in message list
- Plan 04-01: Scope overlap uses bidirectional prefix matching (ep.startswith(cp) or cp.startswith(ep))
- Plan 04-01: Evidence grounding and non-contradiction layers always return is_valid=True (warnings only)
- Plan 04-01: GenusValidator.default() factory method creates all 5 layers with lazy EpisodeValidator import
- Plan 04-02: Stratified sampling with min 5 per stratum for mode/reaction coverage
- Plan 04-02: Zero-denominator returns None (not exception) for graceful metrics handling
- Plan 04-02: Constraint extraction rate links via examples array episode_ids (not constraint text)
- Plan 04-02: CLI refactored from direct-invoke to click.group with extract+validate subcommands
- Plan 04-02: Parquet export uses DuckDB native COPY TO (no pyarrow dependency)
- Plan 05-01: FTS index install/load in rebuild_fts_index() rather than create_schema() to avoid extension dependency
- Plan 05-01: VSS extension loaded in create_schema() with try/except for already-installed scenarios
- Plan 05-01: HNSW index deferred to Plan 02 (requires data to be present first)
- Plan 05-01: observation_to_text maps to DuckDB STRUCT field names (tests_status) not Pydantic names (tests.status)
- Plan 05-02: Bidirectional prefix matching for scope violation detection (rec path under constraint dir OR constraint dir under rec path)
- Plan 05-02: Parameterized SQL with IS NULL OR != pattern for exclude_episode_id (avoids SQL injection)
- Plan 05-02: Over-fetch top_k*2 from each search strategy before RRF fusion for better recall
- Plan 05-02: Pydantic frozen models for Recommendation and SourceEpisodeRef (immutable, serializable)
- Plan 05-03: Jaccard similarity for scope overlap: |intersection|/|union|, 1.0 when both empty, 0.0 when one empty
- Plan 05-03: shadow_run_id as UUID primary key (not episode_id) to allow multiple runs per episode across batches
- Plan 05-03: Gate agreement uses exact set match (both sets must be equal) not subset
- Plan 05-03: Reporter threshold: 70% mode agreement rate and 50 session minimum as PASS/FAIL gates
- Plan 06-01: SQLite column names use snake_case matching Pydantic Episode model exactly (no camelCase in DB)
- Plan 06-01: JSON columns stored as TEXT in SQLite; parsed via json.loads on Python side
- Plan 06-01: WAL mode + busy_timeout=5000 for concurrent read/write access
- Plan 06-01: MCBridgeReader uses short-lived attach/query/detach to avoid holding SQLite locks
- Plan 06-01: Constraint dedup uses same SHA-256(text + scope_paths) pattern as Python ConstraintStore
- Plan 06-01: .gitignore negation added for mission-control/src/lib/ (Rule 3 auto-fix)
- Plan 06-02: Hybrid planningOutputToAction: JSON.parse first, prose keyword heuristic fallback
- Plan 06-02: Status progression guards for idempotent lifecycle methods (skip if past expected state)
- Plan 06-02: Next.js 15 async params pattern: { params: Promise<{ id: string }> }
- Plan 06-02: getDb() singleton with MC_DB_PATH env var override for database access
- Plan 06-02: Input validation via allowlists matching schema CHECK constraints (not zod)
- Plan 06-02: db/index.ts connection module created (Rule 3 auto-fix, routes needed it)
- Plan 06-03: classifyTool inspects Bash command content for git/test/lint/build sub-classification
- Plan 06-03: tool_result events not counted as separate tool_calls in aggregation (they are responses)
- Plan 06-03: Failed flush re-adds events to buffer for retry rather than dropping them
- Plan 06-03: AggregationResult uses snake_case field names (executor_effects) matching Pydantic model

### Pending Todos

None.

### Blockers/Concerns

- Phase 6 (Mission Control Integration) requires access to Mission Control repository (external blocker noted in PROJECT.md constraints)
- Phases 1-5 are independent of this blocker and can proceed

## Phase 1 Completion Summary

Phase 1 delivered a working end-to-end extraction pipeline:
- **90 tests** passing across 3 test suites (tagger: 47, segmenter: 35, integration: 8)
- **10 real sessions** processed: 1264 events, 22 episodes, 9 tag types, 5 outcome types
- **CLI**: `python -m src.pipeline.cli.extract <path> [--db] [--config] [--repo] [-v]`
- **Idempotent**: Re-running produces no duplicates
- **Components**: config models, JSONL/git adapters, normalizer, tagger, segmenter, writer, runner, CLI

## Phase 2 Completion Summary

Phase 2 extended the pipeline with episode population and storage:
- **198 tests** passing across 6 test suites (tagger: 47, segmenter: 35, validator: 14, populator: 30, reaction: 48, storage: 12, integration: 12)
- **Episode model**: 24 frozen Pydantic v2 models mirroring orchestrator-episode.schema.json
- **DuckDB episodes table**: hybrid flat + STRUCT + JSON columns with 5 indexes, MERGE upsert
- **EpisodePopulator**: populate(segment, events, context_events) -> schema-valid episode dict
- **ReactionLabeler**: 5 reaction labels + unknown with two-tier confidence
- **EpisodeValidator**: jsonschema Draft 2020-12 + business rule checks
- **Full pipeline**: JSONL -> events -> segments -> episodes (populated, labeled, validated, stored)
- **CLI**: episode stats (populated/valid/invalid) + reaction label distribution

## Phase 3 Completion Summary

Phase 3 added constraint extraction and management:
- **270 tests** passing across 8 test suites (tagger: 47, segmenter: 35, validator: 14, populator: 30, reaction: 48, storage: 12, constraint extractor: 50, constraint store: 18, integration: 16)
- **ConstraintExtractor**: correct/block reactions -> structured constraints with 3-tier severity, narrowest-scope inference, deterministic IDs
- **ConstraintStore**: JSON file manager with dedup, schema validation, examples enrichment
- **Pipeline Step 12**: constraint extraction wired after episode storage
- **CLI**: constraint stats (extracted, duplicate, total in store)
- **Idempotent**: re-running produces no duplicate constraints in data/constraints.json

## Phase 4 Completion Summary

Phase 4 added validation layers and gold-standard quality workflow:
- **352 tests** passing across 12 test suites (+42 new in phase 4)
- **GenusValidator**: Five-layer validation (Schema, Evidence Grounding, Non-Contradiction, Constraint Enforcement, Episode Integrity)
- **Gold-standard workflow**: export episodes -> human review -> import labels -> compute metrics
- **Quality metrics**: mode accuracy, reaction accuracy, reaction confidence, constraint extraction rate with threshold gates
- **Parquet export**: DuckDB native COPY TO (no pyarrow dependency)
- **CLI**: `python -m src.pipeline.cli validate export|metrics|export-parquet`
- **CLI refactored**: click.group() with extract + validate subcommands

## Phase 5 Completion Summary

Phase 5 delivered training infrastructure for RAG retrieval and shadow mode testing:
- **Plan 01 COMPLETE**: Episode embedding infrastructure (EpisodeEmbedder, observation_to_text, DuckDB schema extensions)
- **Plan 02 COMPLETE**: Hybrid retriever and recommender (HybridRetriever, Recommender, danger detection)
- **Plan 03 COMPLETE**: Shadow mode testing framework (ShadowModeRunner, ShadowEvaluator, ShadowReporter, CLI train subcommand)
- **426 tests** passing across 16 test suites (+32 new in plan 05-03)
- **RAG module**: src/pipeline/rag/ with embedder.py, retriever.py, recommender.py
- **Shadow module**: src/pipeline/shadow/ with evaluator.py, runner.py, reporter.py
- **CLI train**: embed, recommend, shadow-run, shadow-report subcommands
- **Dependencies added**: sentence-transformers 5.2.2

## Phase 6 Completion Summary (In Progress)

Phase 6 is adding Mission Control integration:
- **Plan 01 COMPLETE**: SQLite episode schema (5 tables) + TypeScript CRUD + Python MCBridgeReader + 13 tests
- **Plan 02 COMPLETE**: EpisodeBuilder (6 lifecycle methods) + mapper (hybrid JSON/prose) + API routes (CRUD + events)
- **Plan 03 COMPLETE**: ProvenanceCapture adapter (Gateway WS) + ProvenanceAggregator (episode outcome)
- **Plan 04**: Dashboard integration with DuckDB bridge (pending)
- **439 tests** passing across 17 test suites (+13 new in plan 06-01)

## Session Continuity

Last session: 2026-02-12
Stopped at: Phase 6 Plans 01-03 complete. Plan 04 remaining.
Resume file: .planning/phases/06-mission-control-integration/06-02-SUMMARY.md
