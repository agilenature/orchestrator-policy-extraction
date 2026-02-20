# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-10)

**Core value:** Episodes capture how to decide what to do next (orchestrator decisions), not just what was delivered (commits), enabling policy learning that scales human judgment.
**Current focus:** Phase 13 IN PROGRESS (Policy-to-Constraint Feedback Loop) — Plans 01-02 complete, 1 remaining.

## Current Position

Phase: 13 of 13 (Policy-to-Constraint Feedback Loop)
Plan: 2 of 3 in current phase
Status: In progress
Last activity: 2026-02-20 -- Completed 13-02-PLAN.md (PolicyViolationChecker, PolicyFeedbackExtractor, find_by_hints). 1022 tests passing.

Progress: [████████████████████░░░░░░░░░░░░] 67% (2/3 plans in phase 13)
Overall:  [██████████████████████████████████████████████████████░░] 98% (40/41 plans total)

## Performance Metrics

**Velocity:**
- Total plans completed: 40
- Average duration: 5.1 min
- Total execution time: 3.44 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-event-stream-foundation | 5 | 29 min | 5.8 min |
| 02-episode-population-storage | 4 | 19 min | 4.8 min |
| 03-constraint-management | 2 | 7 min | 3.5 min |
| 04-validation-quality | 2 | 11 min | 5.5 min |
| 05-training-infrastructure | 3 | 21 min | 7.0 min |
| 06-mission-control-integration | 4 | 15 min | 3.8 min |
| 09-obstacle-escalation-detection | 5 | 29 min | 5.8 min |
| 10-cross-session-decision-durability | 3 | 21 min | 7.0 min |
| 11-project-level-wisdom-layer | 6 | 35 min | 5.8 min |

| 12-governance-protocol-integration | 4 | ~30 min | 7.5 min |
| 13-policy-to-constraint-feedback-loop | 2 | 11 min | 5.5 min |

**Recent Trend:**
- Last 5 plans: 5 min, 4 min, 9 min, 4 min, 7 min
- Trend: stable

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
- Plan 06-04: ConstraintForm rendered inline (not modal) per Pitfall 4 guidance for high constraint capture rate
- Plan 06-04: Default severity mapping: correct -> requires_approval, block -> forbidden
- Plan 06-04: SSE event bus uses in-memory Set of writers with write-catch for cleanup
- Plan 06-04: Constraint API generates SHA-256(text + JSON.stringify(scope_paths)) matching Python ConstraintStore
- Plan 06-04: EpisodeTimeline backfills existing events on mount, then receives live updates via SSE
- Plan 06-04: Keep-alive comments every 30s to prevent proxy/browser timeout
- Plan 09-01: EscalationConfig defined inline in config.py (same pattern as EpisodePopulationConfig, RiskModelConfig)
- Plan 09-01: O_ESC added to Classification valid_labels with escalation_detector as new valid source
- Plan 09-01: Idempotent ALTER TABLE with try/except for DuckDB escalation column additions
- Plan 09-01: Constraint status enum: active, candidate, retired (lifecycle for human vs inferred constraints)
- Plan 09-01: EscalationCandidate.block_event_tag validated to only allow O_GATE or O_CORR
- Plan 09-02: Two-layer bypass eligibility: tag-based (T_RISKY/T_GIT_COMMIT/T_TEST) AND tool-name-based (Write/Edit/Bash) -- either triggers bypass
- Plan 09-02: Exempt tools transparent to window (no turn decrement, never trigger bypass)
- Plan 09-02: X_ASK/X_PROPOSE resets ALL pending windows via pending.clear()
- Plan 09-02: Sequential block dedup: oldest window consumed per bypass event, at most 1 candidate per bypass
- Plan 09-02: Window expiry uses > comparison so window_turns=5 allows exactly 5 non-exempt events
- Plan 09-02: Always-bypass pattern matching uses case-insensitive substring containment
- Plan 09-03: Operation type inferred from command regex patterns with tool_name fallback (Write->write, Edit->write, default->execute)
- Plan 09-03: find_matching_constraint requires 2+ hint overlap OR tool_name + path prefix for robust matching
- Plan 09-03: bypassed_constraint_id added to constraint.schema.json as optional string|null (Rule 3 auto-fix)
- Plan 09-03: Generator is stateless; caller handles ConstraintStore.add() in pipeline integration
- Plan 09-04: Escalation detection runs as Step 13 after constraint extraction (Step 12) in run_session()
- Plan 09-04: _determine_approval_status() maps reactions: approve->APPROVED, block/correct->REJECTED, else->UNAPPROVED
- Plan 09-04: write_escalation_episodes() uses separate staging table for clean MERGE with escalate_* columns
- Plan 09-04: Escalation metrics in ShadowReporter: escalation_count_per_session, rejection_adherence_rate, unapproved_escalation_rate
- Plan 09-04: unapproved_escalation_rate is headline PASS/FAIL gate metric (target: 0.0%)
- Plan 09-05: JSONL comment lines (# prefix) used for fixture provenance headers
- Plan 09-05: tool_result events from exempt tools (Read) are non-exempt because they lack tool_name in payload
- Plan 09-05: Window_turns must be tuned per real session; only 1 of 4 positive fixtures works with default window_turns=5
- Plan 10-01: status_history uses datetime.fromisoformat() comparison (not string) for timezone safety
- Plan 10-01: Empty status_history falls back to current status field (backward-compatible)
- Plan 10-01: scopes_overlap() in utils.py treats EITHER empty list as repo-wide (differs from validation/layers.py)
- Plan 10-01: DurabilityConfig defaults: min_sessions_for_score=3, evidence_excerpt_max_chars=500
- Plan 10-02: Evaluator operates on raw constraint dicts (no ConstraintStore dependency) for flexibility
- Plan 10-02: Detection hints scan: case-insensitive substring containment, pre-compiled per constraint
- Plan 10-02: AmnesiaDetector is stateless; detected_at set to current UTC at detection time
- Plan 10-02: write_constraint_evals/write_amnesia_events use INSERT OR REPLACE for idempotency
- Plan 10-03: Pipeline Step 14 inserted between Step 13 (escalation) and Step 15 (stats)
- Plan 10-03: CLI exit code 2 = amnesia events found, 0 = clean, 1 = runtime error
- Plan 10-03: ShadowReporter amnesia_rate PASS/FAIL gate: PASS iff rate == 0.0
- Plan 10-01: status_history uses datetime.fromisoformat() comparison (not string) for timezone safety
- Plan 10-01: Empty status_history falls back to current status field (backward-compatible)
- Plan 10-01: get_active_constraints() treats missing status as active (behavioral default)
- Plan 10-01: Shared scopes_overlap() in utils.py treats EITHER empty list as repo-wide (differs from validation/layers.py)
- Plan 10-01: DurabilityConfig defaults: min_sessions_for_score=3, evidence_excerpt_max_chars=500
- Plan 10-01: 557 tests passing (542 baseline + 15 new)
- Plan 10-02: Evaluator operates on raw constraint dicts (no ConstraintStore dependency) for pipeline+CLI flexibility
- Plan 10-02: Detection hints scan uses case-insensitive substring containment (re.escape + re.IGNORECASE), matching Phase 9
- Plan 10-02: Pre-compile hint patterns once per constraint (not per event) per research pitfall
- Plan 10-02: One match per event is sufficient (break after first hint match to avoid redundant evidence)
- Plan 10-02: AmnesiaDetector is stateless; detected_at uses current UTC at detection time
- Plan 10-02: 616 tests passing (557 baseline + 59 new)
- Plan 10-03: Step 14 placed after escalation detection (Step 13), before stats computation (now Step 15)
- Plan 10-03: CLI audit session writes eval results to DB during audit (not read-only)
- Plan 10-03: Exit code convention: 0=clean, 1=error, 2=amnesia detected
- Plan 10-03: ShadowReporter amnesia_rate = sessions_with_amnesia / audited_sessions (left join SQL)
- Plan 10-03: PASS/FAIL gate on amnesia_rate: PASS if 0.0%, FAIL otherwise (zero tolerance)
- Plan 10-03: avg_durability_score excludes constraints with < 3 sessions from average
- Plan 10-03: 643 tests passing (616 baseline + 27 new)
- Plan 11-01: WisdomEntity uses Any type for EnrichedRecommendation.recommendation to avoid circular import with rag/recommender.py
- Plan 11-01: Wisdom ID: w- prefix + 16 hex chars from SHA-256(entity_type + title) -- deterministic and collision-resistant
- Plan 11-01: search_by_scope returns entities with empty scope_paths as repo-wide matches alongside exact path matches
- Plan 11-01: search_by_tags uses DuckDB list_has_any() for OR-semantics: any tag match is sufficient
- Plan 11-01: WisdomStore._ensure_schema() creates table inline for standalone usage independent of schema.py
- Plan 11-01: delete() is idempotent; update() raises ValueError on nonexistent (asymmetric by design)
- Plan 11-01: 672 tests passing (643 baseline + 29 new)
- Plan 11-02: WisdomRetriever accesses store._conn for raw SQL (same-package access pattern)
- Plan 11-02: Vector search returns empty when no embeddings present (BM25-only fallback)
- Plan 11-02: Dead end detection uses abs(bm25_score) >= 0.6 threshold (DuckDB FTS returns negative scores)
- Plan 11-02: Scope overlap boosts relevance by 1.5x for matching paths
- Plan 11-02: Lazy import of EnrichedRecommendation in recommender._maybe_enrich() to avoid circular imports
- Plan 11-02: FTS index auto-built on first retrieve() if not explicitly rebuilt
- Plan 11-02: 687 tests passing (672 baseline + 15 new)
- Plan 11-03: IngestResult uses Pydantic model_copy(update={}) for immutable result accumulation
- Plan 11-03: ingest_file accepts both bare JSON arrays and {entries:[]} format
- Plan 11-03: Invalid entries skipped with error messages (not raised), enabling partial ingestion
- Plan 11-03: Upsert semantics for idempotent re-running of seed files
- Plan 11-03: 692 tests passing (687 baseline + 5 new)
- Plan 11-04: wisdom_group registered alongside existing extract/validate/train/audit groups
- Plan 11-04: check-scope filters search_by_scope results to scope_decision entities only
- Plan 11-04: list shows first 80 chars of description with ellipsis truncation
- Plan 11-04: 8 tests instead of planned 5 for better coverage (list-after-ingest, filter-by-type, check-scope-with-match)
- Plan 11-04: 700 tests passing (692 baseline + 8 new)
- Plan 11-05: EpisodeEmbedder imported via TYPE_CHECKING to keep lazy-load pattern (sentence-transformers is heavy)
- Plan 11-05: Vector search uses DOUBLE[] cast matching project_wisdom.embedding column (not FLOAT[384])
- Plan 11-05: Dead end vector threshold at 0.3 cosine similarity; dual BM25+vector agreement required when vector available
- Plan 11-05: 707 tests passing (700 baseline + 7 new)
- Plan 11-06: check-scope rewritten from display-only to validation command with 0/1/2 exit codes
- Plan 11-06: Title words > 3 chars extracted for text-based constraint matching (2+ word overlap required)
- Plan 11-06: except SystemExit: raise pattern for try blocks containing sys.exit calls
- Plan 11-06: All wisdom CLI commands use exit code 2 for runtime errors (was 1)
- Plan 11-06: Severity filter: only "forbidden" and "requires_approval" count as violations
- Plan 11-06: 712 tests passing (707 baseline + 5 new)
- Plan 12-01: WisdomEntity.metadata stored as DuckDB JSON column, serialized via json.dumps/json.loads
- Plan 12-01: stability_outcomes table uses CHECK constraint for status IN ('pass', 'fail', 'error')
- Plan 12-01: Governance columns on episodes are nullable BOOLEAN/VARCHAR for backward compatibility
- Plan 12-01: 733 tests passing (712 baseline + 21 new)
- Plan 12-03: stdout/stderr truncated to 10000 chars to prevent DuckDB storage bloat
- Plan 12-03: Git actor info cached once in StabilityRunner.__init__ (not per-check) for consistency
- Plan 12-03: TimeoutExpired produces exit_code=-1 as sentinel value (not a real process exit)
- Plan 12-03: flag_missing_validation/mark_validated accept optional conn parameter for flexible targeting
- Plan 12-03: 792 tests passing (733 baseline + 45 from plan 12-02 + 14 new)
- Plan 12-04: govern CLI group registered in __main__.py following wisdom.py pattern (lazy imports, _setup_logging)
- Plan 12-04: Reuse wisdom_store._conn for bulk episode flagging to avoid DuckDB two-writer IOException
- Plan 12-04: Exit codes: 0=clean, 1=runtime-error, 2=failure/violation (consistent with audit CLI)
- Plan 12-04: CliRunner() without mix_stderr (not supported in installed Click version)
- Plan 12-04: 822 tests passing (792 baseline + 30 new)
- Plan 13-01: Single PolicyErrorEvent model for both domain and storage (no separate PolicyError)
- Plan 13-01: Forward-only ID break: _make_constraint_id appends `:source`, old constraints keep old IDs
- Plan 13-01: Pipe separator kept in ConstraintExtractor per locked decision; JSON separator for PolicyFeedbackExtractor in Plan 02
- Plan 13-01: PolicyFeedbackConfig defaults: promote_after_sessions=3, error_rate_target=0.05, rolling_window_sessions=100
- Plan 13-01: 845 tests passing (822 baseline + 23 new)
- Plan 13-02: Scope overlap without detection_hints intentionally NOT matched (deferred to future gap closure)
- Plan 13-02: Warning-severity constraints logged but never suppressed (return (False, constraint))
- Plan 13-02: Dedup threshold: 2+ shared detection_hints (case-insensitive) to match existing human constraints
- Plan 13-02: Promotion threshold: 3+ distinct sessions with surfaced_and_blocked events
- Plan 13-02: SHA-256 constraint ID with :policy_feedback suffix for namespace isolation from human_correction IDs
- Plan 13-02: 1022 tests passing (994 baseline + 28 new)

### Pending Todos

None.

### Blockers/Concerns

- External blocker: Mission Control repository access needed for integration of mission-control/ code into actual MC codebase

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

## Phase 6 Completion Summary

Phase 6 delivered Mission Control integration (all 4 MC requirements):
- **Plan 01 COMPLETE**: SQLite episode schema (5 tables) + TypeScript CRUD + Python MCBridgeReader + 13 tests
- **Plan 02 COMPLETE**: EpisodeBuilder (6 lifecycle methods) + mapper (hybrid JSON/prose) + API routes (CRUD + events)
- **Plan 03 COMPLETE**: ProvenanceCapture adapter (Gateway WS) + ProvenanceAggregator (episode outcome)
- **Plan 04 COMPLETE**: ReviewWidget (5 reactions + inline constraint form) + EpisodeTimeline (SSE + backfill) + Constraint API + SSE endpoint
- **MC-01**: Episode schema with SQLite storage and DuckDB bridge
- **MC-02**: Real-time episode capture from task lifecycle with provenance
- **MC-03**: Review widget with reaction labeling and constraint extraction
- **MC-04**: Live event streaming via SSE with 30s keep-alive
- **Mission Control files**: 14 TypeScript files across lib/db, lib/episodes, lib/openclaw, app/api, app/components

## Phase 7 Completion Summary

Phase 7 delivered four analysis documents via parallel agent analysis (no formal plan files):
- **REUSABLE_KNOWLEDGE_GUIDE.md**: 10 patterns, 6 dead ends, 8 breakthrough moments, cost/scale reference
- **PROBLEM_FORMULATION_RETROSPECTIVE.md**: 5 breakthroughs analyzed via question reformulation framework
- **VALIDATION_GATE_AUDIT.md**: 8+ missing gate categories, concrete gate queries, gate design principles
- **DECISION_AMNESIA_REPORT.md**: 6 amnesia instances (scope, method, constraint, status), root cause analysis, prevention strategies
- All documents in: `docs/analysis/objectivism-knowledge-extraction/`

## Phase 8 Completion Summary

Phase 8 delivered the synthesis and new roadmap (conversation-driven, no formal plan files):
- **PHASE_8_SYNTHESIS.md**: mapping, 10 new requirements, 4 new phases, "what to start with" answer
- New requirements: AMNESIA-01/02/03, ESCALATE-01/02/03, WISDOM-01/02/03, GOVERN-01/02
- New phases added to ROADMAP.md: 9 (Obstacle Escalation), 10 (Decision Durability), 11 (Wisdom Layer), 12 (Governance)
- Deliverable: `docs/analysis/knowledge-architecture-conciliation/PHASE_8_SYNTHESIS.md`
- Key finding: the critical missing element is O_ESC (obstacle escalation) — the event type for "agent bypassed authorization constraint via alternative path"

## Phase 9 Completion Summary

Phase 9 delivered obstacle escalation detection (all 5 plans, including gap closure):
- **Plan 01 COMPLETE**: Data models (EscalationCandidate, EscalationConfig), DuckDB schema extensions (6 escalate_* columns), constraint status lifecycle
- **Plan 02 COMPLETE**: EscalationDetector with sliding window, two-layer bypass eligibility, 40 tests
- **Plan 03 COMPLETE**: EscalationConstraintGenerator with three-tier severity, SHA-256 IDs, 38 tests
- **Plan 04 COMPLETE**: Pipeline integration (Step 13 in run_session), write_escalation_episodes, ShadowReporter escalation metrics, 12 integration tests
- **Plan 05 COMPLETE**: Real session fixture extraction (5 JSONL files from ope.db), 13 real-fixture tests
- **542 tests** passing (529 baseline + 13 new real-fixture tests)
- **Key capability**: Running `python -m src.pipeline.cli extract` now detects escalation sequences and stores them as mode=ESCALATE episodes with auto-generated candidate constraints
- **Headline gate**: unapproved_escalation_rate with PASS/FAIL indicator in shadow report
- **Gap closed**: VERIFICATION.md Truth 5 now confirmed with real objectivism session data

## Phase 10 Completion Summary

Phase 10 delivered cross-session decision durability (all 3 plans, verified 5/5):
- **Plan 01 COMPLETE**: Constraint schema extended (type/status_history/supersedes), DuckDB session_constraint_eval + amnesia_events tables, DurabilityConfig, ConstraintStore temporal methods, shared scopes_overlap(), 15 new tests
- **Plan 02 COMPLETE**: SessionConstraintEvaluator (HONORED/VIOLATED/UNKNOWN with temporal+scope+O_ESC+hints), AmnesiaDetector (SHA-256 IDs), DurabilityIndex (SQL aggregation), writer functions, 59 new tests
- **Plan 03 COMPLETE**: Pipeline Step 14 wired (evaluates constraint compliance after escalation), CLI `audit session` (exit 2 on amnesia) + `audit durability`, ShadowReporter amnesia_rate/avg_durability_score PASS/FAIL, 27 new tests
- **Gap closure**: Migrated 185 existing constraints with type=behavioral_constraint and bootstrapped status_history
- **643 tests** passing (542 baseline + 101 new Phase 10 tests, zero regressions)
- **Real data**: 1309 amnesia events detected across 167 sessions in data/ope.db; 96/166 constraints have durability scores

## Phase 11 Completion Summary

Phase 11 delivered the project-level wisdom layer (all 6 plans including gap closure):
- **Plan 01 COMPLETE**: WisdomEntity/WisdomRef/EnrichedRecommendation models, WisdomStore (8 CRUD+search methods), 29 tests
- **Plan 02 COMPLETE**: WisdomRetriever (BM25 + RRF + dead end detection), Recommender enrichment integration, 15 tests
- **Plan 03 COMPLETE**: WisdomIngestor (bulk JSON loader with upsert), data/seed_wisdom.json (17 entries), 5 tests
- **Plan 04 COMPLETE**: CLI wisdom subcommands (ingest, check-scope, reindex, list), __main__.py registration, 8 tests
- **Plan 05 COMPLETE (gap closure)**: Vector search in WisdomRetriever, dual-signal dead end detection, 7 new tests
- **Plan 06 COMPLETE (gap closure)**: check-scope rewritten to validation command with 0/1/2 exit codes, constraint violation detection, 5 new tests
- **712 tests** passing (643 baseline + 69 new Phase 11 tests, zero regressions)
- **Full wisdom pipeline**: `python -m src.pipeline.cli wisdom ingest|check-scope|reindex|list`
- **Key modules**: src/pipeline/wisdom/ (models.py, store.py, retriever.py, ingestor.py), src/pipeline/cli/wisdom.py
- **All verification gaps closed**: Gap 1 (vector search) and Gap 2 (check-scope validation) both addressed

## Phase 12 Completion Summary

Phase 12 delivered governance protocol integration (all 4 plans):
- **Plan 01 COMPLETE**: GovernanceConfig/StabilityCheckDef models, WisdomEntity.metadata field, DuckDB stability_outcomes table, episodes governance columns, 21 new tests
- **Plan 02 COMPLETE**: GovDocParser (H2/H3 keyword classification), GovDocIngestor (dual-store sequential writes, forbidden severity heuristic, co-occurrence linkage), objectivism_premortem.md fixture, 45 new tests
- **Plan 03 COMPLETE**: StabilityRunner (subprocess execution, DuckDB persistence, episode flagging), flag_missing_validation/mark_validated, 14 new tests
- **Plan 04 COMPLETE**: govern CLI group (ingest + check-stability), __main__.py registration, 10 CLI tests + 20 integration tests
- **GOVERN-01**: `python -m src.pipeline.cli govern ingest <file>` ingests pre-mortem/DECISIONS.md
- **GOVERN-02**: `python -m src.pipeline.cli govern check-stability` runs registered commands
- **822 tests** passing (712 baseline from Phase 11 + 110 new Phase 12 tests)
- **Key modules**: src/pipeline/governance/ (parser.py, ingestor.py, stability.py), src/pipeline/cli/govern.py
- **Reference data**: objectivism_premortem.md produces 11 dead_end wisdom + 15 behavioral constraints

## Session Continuity

Last session: 2026-02-20
Stopped at: Phase 13 Plan 02 complete (PolicyViolationChecker, PolicyFeedbackExtractor, find_by_hints). Plan 03 next (pipeline integration).
Resume file: .planning/phases/13-policy-to-constraint-feedback-loop/13-03-PLAN.md
