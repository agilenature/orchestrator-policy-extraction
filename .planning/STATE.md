# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-10)
**Cross-project sequencing:** See `.planning/PROGRAM-SEQUENCE.md` — canonical tracker for OPE + Modernizing Tool execution order, wave dependencies, and step verification criteria.

**Core value:** Episodes capture how to decide what to do next (orchestrator decisions), not just what was delivered (commits), enabling policy learning that scales human judgment.
**Current focus:** Phase 18 (Bridge-Warden Structural Integrity Detection) — in progress. Plans 01-03 complete.

## Current Position

Phase: 18 (Bridge-Warden Structural Integrity Detection)
Plan: 3 of ~4 in current phase
Status: In progress
Last activity: 2026-02-25 -- Completed 18-03-PLAN.md (integration tests for BRIDGE-01 through BRIDGE-03)

Progress: [████████████████████████░░░░░░░░] 75% (3/4 plans in phase 18)
Overall:  [███████████████████████████████████████████████████████████████████████████░] 74/75 plans total

## Performance Metrics

**Velocity:**
- Total plans completed: 74
- Average duration: 5.5 min
- Total execution time: 7.58 hours

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
| 13-policy-to-constraint-feedback-loop | 3 | 19 min | 6.3 min |
| 13.3-identification-transparency | 4 | 31 min | 7.8 min |
| 14.1-premise-registry-premise-assertion-gate | 3 | 33 min | 11.0 min |
| 14-live-session-governance-research | 4 | 28 min | 7.0 min |
| 15-ddf-detection-substrate | 7 | 49 min | 7.0 min |
| 16.1-topological-edge-generation | 4 | 22 min | 5.5 min |
| 16-sacred-fire-intelligence-system | 4 | 18 min | 4.5 min |

| 17-candidate-assessment-system | 4 | 41 min | 10.3 min |
| 18-bridge-warden-structural-integrity | 3/4 | 19 min | 6.3 min |

**Recent Trend:**
- Last 5 plans: 12 min, 11 min, 4 min, 11 min, 4 min
- Trend: steady execution pace

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
- Plan 13-03: Pre-surfacing check uses PolicyViolationChecker.build_recommendation_text() for hint matching
- Plan 13-03: Suppressed recs skip evaluation (continue) and are NOT in shadow_mode_results
- Plan 13-03: Surfaced-and-blocked detected via reaction_label in (block, correct) after evaluation
- Plan 13-03: Batch constraint write and promotion AFTER run_all completes (not during sessions)
- Plan 13-03: Policy error rate denominator = evaluated + suppressed (includes suppressed in denominator)
- Plan 13-03: CLI exit code 2 for rate >= 5%, 0 for clean or no data
- Plan 13-03: 889 tests passing (873 baseline + 16 new)
- Plan 13.3-01: identification_reviews UNIQUE on identification_instance_id enforces at-most-once verdicts at DB level
- Plan 13.3-01: memory_candidates table created (not ALTER TABLE) with CCD format CHECK constraints (non-empty ccd_axis, scope_rule, flood_example)
- Plan 13.3-01: Pool builder reads L5 from data/constraints.json, L7 from episodes table escalation columns (adapted from plan's nonexistent tables)
- Plan 13.3-01: Instance IDs use composite natural key: {source_table}:{primary_key}:{point_type}
- Plan 13.3-01: memory_candidates status enum: pending, validated, suspended, rejected, split_required
- Plan 13.3-01: BalancedLayerSampler uses coverage-based priority (lowest reviewed/available ratio selected first)
- Plan 13.3-01: 49 tests passing for review module (models, schema, pool builder, sampler)
- Plan 13.3-02: VerdictCollector.input_fn injectable for test isolation (default=input, mock in tests)
- Plan 13.3-02: ReviewWriter has no update()/delete() methods -- append-only contract at API level
- Plan 13.3-02: CLI --constraints option added for test isolation from real filesystem data
- Plan 13.3-02: duckdb.ConstraintException (not IntegrityError) is the correct exception for UNIQUE violations
- Plan 13.3-02: session_id left as None -- extension point for Phase 14+ session tracking
- Plan 13.3-02: 80 tests passing for review module (49 baseline + 31 new)
- Plan 13.3-03: Adapted plan schema to match existing memory_candidates (id not candidate_id, status not verdict, no epistemological_origin)
- Plan 13.3-03: Rejected verdicts without opinion still record in TrustAccumulator (reject_count increments)
- Plan 13.3-03: ON CONFLICT DO NOTHING (DuckDB syntax) for idempotent routing, not INSERT OR IGNORE (SQLite)
- Plan 13.3-03: Trust level degrades on rejects (established->provisional at 10 accepts + 1 reject)
- Plan 13.3-03: 134 tests passing for review module (80 baseline + 54 new)
- Plan 13.3-04: Harness is read-only on identification_reviews; writes only layer_coverage_snapshots for monotonicity tracking
- Plan 13.3-04: delta_retrieval uses status='validated' (matching actual memory_candidates CHECK constraint, not plan's 'accepted')
- Plan 13.3-04: N-version consistency regex co-dependent with MEMORY.md format (if format changes, both break together)
- Plan 13.3-04: Exit codes: 0=pass, 1=runtime-error, 2=invariant-violation (consistent with existing OPE CLI conventions)
- Plan 13.3-04: Metamorphic testing uses separate metamorphic_test_reviews table to allow multiple verdicts per instance
- Plan 13.3-04: 176 tests passing for review module (134 baseline + 42 new)
- Plan 14.1-01: DuckDB expression indexes (json_extract_string) not supported -- stained premise queries use WHERE clause filtering
- Plan 14.1-01: Lazy import of create_premise_schema in storage/schema.py to avoid circular imports
- Plan 14.1-01: parent_episode_id set in runner.py segment loop via prev_episode_id tracking variable
- Plan 14.1-01: write_episodes() MERGE includes parent_episode_id in staging table, SELECT, UPDATE SET, and INSERT
- Plan 14.1-01: 64 premise tests (12 models, 22 parser, 20 registry, 10 schema)
- Plan 14.1-01: 1094 total tests passing (excluding pre-existing segmenter X_ASK end-trigger change)
- Plan 14.1-02: JSONL staging file (not DuckDB) for hook writes to avoid two-writer conflict
- Plan 14.1-02: Hook always exits 0 (fail-open) -- Phase 14.1 never blocks tool calls
- Plan 14.1-02: Ad Ignorantiam exempt for UNVALIDATED premises (already declare unknown status)
- Plan 14.1-02: High-risk paths: schema.py, constraints.json, settings.json, models/ directory
- Plan 14.1-02: 60 new tests (18 transcript, 12 staging, 30 hook), 1154 total tests passing
- Plan 14.1-03: Keyword search uses CASE WHEN ILIKE positional counting (not full-text search)
- Plan 14.1-03: Divergence detection uses simplified adjacent-tool-change heuristic for Phase 14.1
- Plan 14.1-03: Staining propagation uses string matching on JSON column for derivation chain child lookup
- Plan 14.1-03: Runner integration uses lazy imports (try/except ImportError) to keep premise module optional
- Plan 14.1-03: 40 new tests (13 foil + 13 staining + 14 ingestion), 134 premise tests, 1227 total tests passing
- Plan 14-01: CCD Constraint Architecture: all constraints carry ccd_axis and epistemological_origin; briefings group by axis (12-15 axes cover 80%+ of 332 active constraints)
- Plan 14-01: Fail-open hook design: every failure mode in PreToolUse/SessionStart exits 0 (governance is advisory, not security)
- Plan 14-01: GovernanceSignal boundary_dependency: event_level fires immediately, episode_level buffers until CONFIRMED_END
- Plan 14-01: TTL episodes (30-min timeout) excluded from constraint extraction training (inferred outcome, completeness=4/5)
- Plan 14-01: X_ASK excluded from end triggers in stream processor (consistent with post-hoc segmenter locked decision)
- Plan 14-01: scopes_overlap() is in src/pipeline/utils.py (plan referenced durability/utils.py which does not exist)
- Plan 14-02: Governor is Python daemon co-located with bus process (not a Claude Code session): zero LLM tokens for routine monitoring
- Plan 14-02: Bus uses Unix domain socket at /tmp/ope-governance-bus.sock (sub-ms latency, local-only, no port conflicts)
- Plan 14-02: Pull-based broadcast delivery: interventions piggybacked on /api/check responses at natural tool-call cadence
- Plan 14-02: Policy Automatization Detector differentiates by epistemological_origin: principled at 10 sessions (<1%), reactive at 20 sessions (<2%)
- Plan 14-02: Three DDF co-pilot intervention types: O_AXS (post-naming, 0.8), Fringe (pre-naming negative, 0.6), Affect Spike (pre-naming positive, 0.75)
- Plan 14-02: AI-side DDF deposits at lower confidence (0.7) than human-side (0.8) per raven-cost-function-absent CCD axis
- Plan 14-02: memory_candidates schema extended with session_id, subject, origin, confidence, perception_pointer for co-pilot deposits
- Plan 14-03: Phase 15 scope: LIVE-01 through LIVE-05 only; LIVE-06 (DDF co-pilot) deferred to Wave 6+ or Phase 16
- Plan 14-03: Phase 15 has 9 plans across 5 waves: hooks(2), stream(2), bus(2), governor(1), integration(2)
- Plan 14-03: Models placed in hooks/models.py for standalone hook execution (no shared models module)
- Plan 14-03: DuckDB single-writer: bus process owns all writes; stream processor writes via bus API
- Plan 14-03: SSE endpoint (/api/events/stream) starts as polling, upgrade to SSE in Wave 5 if needed
- Plan 14-04: OPE extract pipeline IS the post-task memory ingestion layer (no new component needed; 3.3s for 498-event session)
- Plan 14-04: Two-tier fidelity model validated: fidelity=1 (real-time heuristic stub) + fidelity=2 (post-task OPE enrichment)
- Plan 14-04: Hook stdout visibility: PreToolUse = protocol JSON (context injection, not user-visible); SessionStart = user-visible
- Plan 14-04: Bus transport LOCKED at Unix socket + uvicorn/starlette: PolicyViolationChecker.check() 0.082ms, bus p99 ~1.6ms
- Plan 14-04: Phase 15 Wave 1 = deposit-first: flame_events + write-on-detect to memory_candidates (no scaffolding)
- Plan 14-04: Pre-Phase 15 fix required: orchestrator-episode.schema.json needs parent_episode_id (schema drift from 14.1-01)
- Plan 15-01: FlameEvent model frozen=True with make_id(session_id, prompt_number, marker_type) -> SHA-256[:16]
- Plan 15-01: DDF schema integrated into create_schema() via create_ddf_schema() call at end
- Plan 15-01: memory_candidates extended with source_flame_event_id, fidelity, detection_count columns (ALTER TABLE)
- Plan 15-02: L0-L2 regex detectors are HIGH RECALL by design; false positives filtered downstream by Tier 2
- Plan 15-02: OAxsDetector requires BOTH granularity drop AND novel concept (dual-signal to reduce false positives)
- Plan 15-02: deposit_to_memory_candidates uses soft dedup on normalized (ccd_axis, scope_rule) with detection_count increment
- Plan 15-02: write_flame_events uses INSERT OR REPLACE for idempotent DuckDB writes
- Plan 15-02: detect_markers filters by actor=human_orchestrator and event_type in (user_msg, human_msg, message)
- Plan 15-02: 1236 tests passing (1227 baseline + 30 new: 18 tier1 + 12 writer, excluding pre-existing segmenter failure)
- Plan 15-03: FlameEventExtractor enriches Tier 1 stubs to L3-7 using episode scope paths, outcomes, reactions
- Plan 15-03: L6+ upgrades unconditionally set flood_confirmed=True (required for deposit path)
- Plan 15-03: AI marker detection: assertive causal -> L2 subject='ai', concretization flood (3+) -> L6 subject='ai' flood_confirmed=True
- Plan 15-03: CausalIsolationRecorder reads premise_registry.foil_path_outcomes; ALL events use subject='ai'
- Plan 15-03: FalseIntegrationDetector dual output: always writes hypothesis, flame event only above threshold (default 0.6)
- Plan 15-03: Confidence formula: min(0.9, 0.3 * distinct_scope_prefixes)
- Plan 15-03: deposit_level6 filters on marker_level >= 6 AND flood_confirmed = True (both required)
- Plan 15-03: 1262 tests passing (1236 baseline + 26 new, excluding pre-existing segmenter failure)
- Plan 15-04: Epistemological origin uses first-match cascade (reactive > principled > inductive > default principled) not weighted scoring
- Plan 15-04: ESCALATE mode blocks reactive classification (escalation episodes are structural, not corrective)
- Plan 15-04: GeneralizationRadius from COUNT(DISTINCT scope_path_prefix) in evidence_json, 'root' fallback for missing scope
- Plan 15-04: Stagnation = radius==1 AND firing_count >= stagnation_min_firing_count (default 10)
- Plan 15-04: Spiral detection skips first session from growth check (baseline, not growth event)
- Plan 15-04: Spiral depth counts ascending levels (transitions + 1), so L1->L2->L3 = depth 3
- Plan 15-04: Spiral promotion uses WisdomStore.upsert() for idempotent re-runs, lazy import for optional dependency
- Plan 15-04: ConstraintStore backward compatibility: setdefault() in _load() for epistemological_origin/confidence
- Plan 15-04: 1180 tests passing (1159 baseline + 39 new: 18 epistemological + 21 generalization/spiral, excluding pre-existing segmenter failure)
- Plan 15-05: Spiral depth counts ascending transitions (N levels in streak = N-1 depth), not streak length
- Plan 15-05: Python-side iteration for spiral depth (avoids complex DuckDB window functions)
- Plan 15-05: AI profile uses human_id='ai' sentinel value for IntelligenceProfile model compatibility
- Plan 15-05: avg_marker_level rounded to 4 decimal places to avoid floating-point display noise
- Plan 15-05: 1153 tests passing (1141 baseline + 12 new, excluding pre-existing segmenter failure)
- Plan 15-06: DDF schema lazily created in Step 15 (first DDF step) rather than __init__, keeping DDF optional
- Plan 15-06: TaggedEvent objects converted to dicts for AI marker detection in Tier 2
- Plan 15-06: CLI profile opens DuckDB read-only; create_ddf_schema wrapped in try/except for compatibility
- Plan 15-06: Step 19 spiral promotion uses self._db_path with `:memory:` fallback to data/ope.db
- Plan 15-06: 1201 tests passing (1180 baseline + 21 new, excluding pre-existing segmenter failure)
- Plan 15-07: Integration tests organized by DDF requirement number for traceability (TestDDF01 through TestDDF10)
- Plan 15-07: File-based DuckDB used only where structurally required (WisdomStore, CLI); all others in-memory
- Plan 15-07: 1219 tests passing (1201 baseline + 18 new, excluding pre-existing segmenter failure)
- Plan 16.1-01: ActivationCondition is a Pydantic model (not raw dict) for structural enforcement at model boundary
- Plan 16.1-01: EdgeWriter validates activation_condition non-emptiness at write time as defense-in-depth
- Plan 16.1-01: axis_edges dropped before ai_flame_events view in drop_schema (dependency order)
- Plan 16.1-01: 1231 tests passing (1219 baseline + 12 new, excluding pre-existing segmenter failure)
- Plan 16.1-02: Baseline computed from events PRIOR to current event (prevents self-inflation)
- Plan 16.1-02: 5-minute window check is caller responsibility; detector checks axes count only
- Plan 16.1-02: For N axes, generate C(N,2) pairs with sorted axis names for deterministic edge_id
- Plan 16.1-02: 1379 tests passing (1364 baseline + 15 new, excluding pre-existing segmenter failure)
- Plan 16.1-03: FrontierChecker uses sorted(set(active_axes)) + combinations for deterministic pair ordering
- Plan 16.1-03: CrossAxisVerifier foil level threshold: edge_level > premise_level + 1 (strict >, not >=)
- Plan 16.1-03: Activation matching treats goal_type=["any"] as universal match for any goal_type including None
- Plan 16.1-03: PAG gate axis extraction uses memory_candidates ccd_axis for known axis lookup (case-insensitive substring)
- Plan 16.1-03: PAG gate now has 6 check types: high-risk, stained, foil, Ad Ignorantiam, frontier, cross-axis
- Plan 16.1-03: 1391 tests passing (1379 baseline + 12 new, excluding pre-existing segmenter failure)
- Plan 16.1-04: CLI is Layer 6 scaffolding (instrumental); integration tests verifying deposit flow are terminal
- Plan 16.1-04: Nested Click subgroup pattern: @parent_group.group(name='edges') for n-level CLI hierarchy
- Plan 16.1-04: FrontierChecker goal_type filtering tested explicitly (edge goal_type=['refactor'] does NOT suppress for goal_type='document')
- Plan 16.1-04: 1406 tests passing (1391 baseline + 15 new integration tests, excluding pre-existing segmenter failure)
- Plan 16-01: transport_efficiency_sessions DDL has 12 columns: te_id, session_id, human_id, subject, raven_depth, crow_efficiency, transport_speed, trunk_quality, composite_te, trunk_quality_status, fringe_drift_rate, created_at
- Plan 16-01: memory_candidates extended with 6 new ALTER TABLE columns: pre_te_avg, post_te_avg, te_delta (TE tracking) + confidence, subject, session_id (review CLI)
- Plan 16-01: memory-review CLI uses _memory_review_impl() with injectable input_fn for test isolation
- Plan 16-01: Accept flow writes CCD format entry and updates status to 'validated' (matches CHECK constraint)
- Plan 16-01: Dedup check is case-insensitive substring match of ccd_axis in full MEMORY.md text
- Plan 16-01: 1431 tests passing (1406 baseline + 25 new: 10 schema + 15 CLI)
- Plan 16-02: DuckDB returns decimal.Decimal for SQL literal 0.5; all sub-metrics cast to float() before multiplication
- Plan 16-02: te_id = SHA-256("session_id:subject")[:16] for deterministic idempotent writes
- Plan 16-02: backfill_trunk_quality: no Level 0 events = keep 0.5 value but mark confirmed (not perpetually pending)
- Plan 16-02: Pipeline Step 20 (TE computation + backfill) inserted between Step 19 (spiral promotion) and Step 21 (stats)
- Plan 16-02: 1456 tests passing (1431 baseline + 25 new TE computation tests)
- Plan 16-03: TE display is pure CLI formatting from SQL queries; IntelligenceProfile model NOT modified
- Plan 16-03: Moved conn.close() after TE display to keep connection open for TE queries
- Plan 16-03: All TE queries wrapped in try/except for graceful fallback on older DBs without transport_efficiency_sessions
- Plan 16-03: 1466 tests passing (1456 baseline + 10 new TE profile display tests)
- Plan 16-04: Integration tests organized by DDF requirement number (TestDDF06_*, TestDDF07_*, TestDDF08_*, TestDDF09_*) for traceability to roadmap success criteria
- Plan 16-04: File-based DuckDB used for CLI tests because memory-review opens its own connection (in-memory DB not shareable)
- Plan 16-04: CliRunner with stdin input for memory-review tests (input='a\n') tests actual CLI path
- Plan 16-04: 1519 tests passing (1517 total + 2 pre-existing segmenter failures, zero Phase 16 regressions)
- Plan 17-01: Claude CLI --session-id flag exists -- enables deterministic JSONL path derivation before session launch
- Plan 17-01: MEMORY.md pre-seeding via ~/.claude/projects/{encoded}/memory/ verified working for handicap injection
- Plan 17-01: ai_flame_events view requires CREATE OR REPLACE VIEW refresh after ALTER TABLE on flame_events (DuckDB caches SELECT * column types)
- Plan 17-01: source_type validated in Pydantic only (not DuckDB CHECK) per DuckDB ALTER TABLE limitation
- Plan 17-01: Assessment dir encoding: all slashes replaced with dashes (/tmp/foo -> -tmp-foo)
- Plan 17-01: 1533 tests passing (1517 baseline + 16 new, excluding pre-existing segmenter failures)
- Plan 17-02: ScenarioGenerator uses default RuntimeError template when no scenario_seed provided
- Plan 17-02: L5-L7 handicap uses generic wrong-cause template (configuration handling / parameter ordering)
- Plan 17-02: list-scenarios opens DB read-only with graceful error when assessment schema columns missing
- Plan 17-02: assess group nested under intelligence_group (access: `intelligence assess <command>`)
- Plan 17-02: 1518 tests passing (1500 baseline + 18 new, excluding pre-existing segmenter failure)
- Plan 17-03: Assessment TE uses 3-metric formula (no transport_speed) because sessions are too short
- Plan 17-03: Rejection threshold uses strict > (not >=): candidate at exactly threshold is stubbornness
- Plan 17-03: Fringe-signal rejections bypass outcome gate entirely (fringe_L5)
- Plan 17-03: Observer uses lazy imports for PipelineRunner/load_config to avoid circular dependencies
- Plan 17-03: assessment_session_id IS NULL filter added to all 5 IntelligenceProfile flame_events queries
- Plan 17-03: 1558 tests passing (1518 baseline + 40 new, excluding pre-existing segmenter failure)
- Plan 17-04: Direct INSERT into memory_candidates (not deposit_to_memory_candidates) for terminal deposit -- that function lacks source_type, fidelity, confidence
- Plan 17-04: DELETE+INSERT for idempotent upsert matching project-wide DuckDB convention
- Plan 17-04: Auto-calibration deposits proposal to memory_candidates for human review (never auto-updates project_wisdom.ddf_target_level)
- Plan 17-04: math.erf for percentile rank computation (no scipy dependency)
- Plan 17-04: 1615 tests passing (1593 baseline + 22 new, excluding pre-existing segmenter failure)
- Plan 17-gap: rejection_detector.py queried ccd_axis and differential from flame_events -- columns absent from FLAME_EVENTS_DDL; tests masked this via manual fixture ALTER TABLE. Fix: added both columns to ASSESSMENT_ALTER_EXTENSIONS in assessment/schema.py (idempotent ALTER TABLE applied at schema chain time). Live ope.db migrated via create_ddf_schema(). 19 tests passing post-fix.
- Plan 18-02: Main Cable detector uses axis_edges presence only (flame_events lacks generalization_radius column)
- Plan 18-02: Spiral reinforcement queries project_wisdom.metadata JSON (no source_session_id column on table)
- Plan 18-02: Assessment filter dual clause: assess_clause_f (aliased f.) for main queries, assess_clause (bare) for sub-queries
- Plan 18-02: Op-8 deposits: INSERT OR REPLACE with SHA-256("op8:{session_id}:{axis}")[:16] for idempotent dedup
- Plan 18-02: Pipeline Step 21 (structural analysis) after Step 20 (TE), renumbered stats to Step 22
- Plan 18-02: 1645 tests passing (1619 baseline + 26 new, excluding pre-existing segmenter failure)
- Plan 18-03: Integration tests organized by bridge contract (TestBridge01, TestBridge02, TestBridge03) with shared _run_detect_and_write helper
- Plan 18-03: Assessment isolation test verifies assessment_session_id IS NULL filtering through evidence string inspection
- Plan 18-03: End-to-end chain test: mixed grounded + floating events -> detect -> write -> compute -> deposit -> verify memory_candidates
- Plan 18-03: 1663 tests passing (1645 baseline + 18 new integration tests, excluding pre-existing segmenter failure)

### Pending Todos

**Premise-Assertion Architecture — gap list (designed 2026-02-23):**

Four components required for real-time premise validation. Architecture: three temporal modes — retrospective (existing OPE), introspective (premise validation at tool-call boundary), projective (foil path instantiation from historical episodes).

| # | Component | Status | Phase target |
|---|-----------|--------|--------------|
| 1 | **Episode causal links** — `parent_episode_id` on `episodes` table, linking each episode to the prior episode whose outcome became its observation. LAG window backfill SQL for existing episodes. runner.py sets parent_episode_id in population loop. writer.py MERGE propagates it. | ✓ **Complete** — 2026-02-23 (Plan 14.1-01) | Phase 14.1-01 |
| 2 | **Premise Registry table** — `premise_registry` in `data/ope.db`. 20-column schema with PremiseRecord model, PremiseRegistry CRUD, PREMISE block parser, create_schema() integration. 64 tests. | ✓ **Complete** — 2026-02-23 (Plan 14.1-01) | Phase 14.1-01 |
| 3 | **PAG hook** (Premise-Assertion Gate) — PreToolUse hook extension. Reads PREMISE blocks from AI output at write-class tool calls; emits PROJECTION_WARNING when foil_path_outcomes non-empty; warns UNVALIDATED high-risk mutations. Stained premise check + foil lookup + Ad Ignorantiam detection. Always exits 0 (fail-open). | ✓ **Complete** — 2026-02-23 (Plan 14.1-02) | Phase 14.1-02 |
| 4 | **CLAUDE.md premise declaration rule** — Global forcing function. Defines write-class vs. validation-class distinction, PREMISE block format, FOIL_VERIFIED format, staleness rule. Prerequisite for items 2 and 3. | ✓ **Complete** — 2026-02-23. Located at `~/.claude/CLAUDE.md` | — |

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

## Phase 13 Completion Summary

Phase 13 delivered the policy-to-constraint feedback loop (all 3 plans):
- **Plan 01 COMPLETE**: PolicyErrorEvent model, policy_error_events DuckDB table, write_policy_error_events, PolicyFeedbackConfig, forward-only ID break in ConstraintExtractor, 23 new tests
- **Plan 02 COMPLETE**: PolicyViolationChecker (regex hint matching, forbidden/requires_approval suppression), PolicyFeedbackExtractor (constraint generation from blocked recs, dedup, promote_confirmed), ConstraintStore.find_by_hints(), 28 new tests
- **Plan 03 COMPLETE**: ShadowModeRunner integration (pre-surfacing check, batch extraction, promote_confirmed), ShadowReporter policy_error_rate metric, CLI audit policy-errors, 16 integration tests
- **889 tests** passing (873 baseline + 16 new Phase 13 Plan 03 tests, zero regressions)
- **Full feedback loop**: policy violations suppressed -> error events recorded -> constraints extracted -> candidates promoted
- **Key modules**: src/pipeline/feedback/ (models.py, checker.py, extractor.py), modified shadow/runner.py + shadow/reporter.py + cli/audit.py

## Session Continuity

Last session: 2026-02-25
Stopped at: Phase 18 Plan 03 complete. Integration tests for BRIDGE-01, BRIDGE-02, BRIDGE-03.
Resume file: .planning/phases/18-bridge-warden-structural-integrity/18-04-PLAN.md

## Phase 15 Completion Summary

Phase 15 delivered the DDF Detection Substrate (all 7 plans, all 10 DDF requirements verified):
- **Plan 01 COMPLETE**: DDF DuckDB schema (flame_events, ai_flame_events view, axis_hypotheses, constraint_metrics), FlameEvent/AxisHypothesis/ConstraintMetric/IntelligenceProfile frozen Pydantic models, DDFConfig with OAxsConfig, 12 tests
- **Plan 02 COMPLETE**: Tier 1 marker detectors (L0 trunk, L1 causal, L2 assertive), OAxsDetector (dual-signal), write_flame_events (idempotent), deposit_to_memory_candidates (soft dedup), 30 tests
- **Plan 03 COMPLETE**: Tier 2 FlameEventExtractor (L3-7 enrichment, AI markers), CausalIsolationRecorder (premise_registry), FalseIntegrationDetector (dual axis_hypotheses + flame_events output), 26 tests
- **Plan 04 COMPLETE**: Epistemological origin classification (reactive/principled/inductive), GeneralizationRadius (scope_path prefix counting), stagnation detection, spiral tracking, project_wisdom promotion, 39 tests
- **Plan 05 COMPLETE**: IntelligenceProfile aggregation (per-human, per-AI), spiral depth computation (Python-side), list_available_humans, 12 tests
- **Plan 06 COMPLETE**: Pipeline Steps 15-19 (Tier 1, Tier 2, deposit, false integration, metrics+spirals), O_AXS start trigger, intelligence CLI (profile + stagnant), 21 tests
- **Plan 07 COMPLETE**: 18 integration tests covering all 10 DDF requirements end-to-end, module import smoke test
- **1219 tests** passing (1201 baseline + 18 new Plan 07 tests, excluding pre-existing segmenter failure)
- **DDF-01**: O_AXS valid episode mode (segmenter START_TRIGGERS + OAxsDetector)
- **DDF-02**: flame_events human markers with detection_source (stub/opeml)
- **DDF-03**: ai_flame_events view + Level 6 write-on-detect deposit to memory_candidates
- **DDF-04**: IntelligenceProfile for human and AI subjects (6 aggregate metrics)
- **DDF-05**: GeneralizationRadius + stagnation detection (floating abstraction flagging)
- **DDF-06**: Spiral tracking + project_wisdom promotion (ascending scope diversity -> breakthrough)
- **DDF-07**: Epistemological origin on all constraints (reactive/principled/inductive classification)
- **DDF-08**: Intelligence CLI profile display
- **DDF-09**: False integration detection (Package Deal fallacy proxy)
- **DDF-10**: Causal isolation markers from premise_registry (Post Hoc detection)
- **Key modules**: src/pipeline/ddf/ (models, schema, writer, deposit, tier1/, tier2/, epistemological, generalization, spiral, intelligence_profile), src/pipeline/cli/intelligence.py

## Phase 14 Completion Summary

Phase 14 delivered live session governance research (all 4 plans):
- **Plan 01 COMPLETE**: CCD Constraint Architecture design -- hooks, stream processor, GovernanceSignal boundary_dependency, 6 LIVE components specified
- **Plan 02 COMPLETE**: Multi-session coordination layer design -- 10 bus API routes, governing daemon with Policy Automatization Detector, DDF co-pilot with 3 intervention types
- **Plan 03 COMPLETE**: Phase 15 implementation blueprint -- 5 waves, 9 plans, 33 file targets, 86 API contracts, ~125 tests
- **Plan 04 COMPLETE**: OpenClaw bus spike -- OPE pipeline validated as post-task memory layer (3.3s/498 events), bus transport 1.6ms p99, hook stdout resolved (SessionStart only), two-tier fidelity model validated
- **Key artifact**: 14-04-SPIKE-RESULTS.md (5 sections, all 4 spike questions resolved with empirical evidence)
- **Key decisions**: OPE extract IS the memory layer, real-time=stubs + post-task=enrichment, SessionStart=user-visible channel, Unix socket transport LOCKED

## Phase 14.1 Completion Summary

Phase 14.1 delivered the Premise Registry + Premise-Assertion Gate (all 3 plans):
- **Plan 01 COMPLETE**: DuckDB premise_registry table (20 columns), PremiseRecord/ParsedPremise models, PREMISE block regex parser, PremiseRegistry CRUD, episodes.parent_episode_id causal links, 64 tests
- **Plan 02 COMPLETE**: PAG PreToolUse hook with backward transcript scanner, JSONL staging, staining check, foil lookup, Ad Ignorantiam detection, 60 new tests
- **Plan 03 COMPLETE**: FoilInstantiator (three-tier matching + divergence detection), StainingPipeline (amnesia staining + derivation propagation), staging ingestion (Begging the Question detection), runner integration, 40 new tests
- **134 premise tests**, 1227 total tests passing
- **Key modules**: src/pipeline/premise/ (schema, models, parser, registry, staging, transcript, foil, staining, ingestion), src/hooks/pag/ (hook.py, scanner.py)
- **Full pipeline**: PREMISE blocks parsed -> staged to JSONL -> ingested to DuckDB -> foil matched -> stained from amnesia -> propagated through derivation chains
- **Three temporal modes operational**: retrospective (existing OPE), introspective (premise validation at tool-call boundary via PAG hook), projective (foil path instantiation from historical episodes)

## Phase 13.3 Completion Summary

Phase 13.3 delivered the Identification Transparency Layer (all 4 plans):
- **Plan 01 COMPLETE**: Data foundation (identification_reviews, memory_candidates, layer_coverage_snapshots tables), PoolBuilder, BalancedLayerSampler, 49 tests
- **Plan 02 COMPLETE**: Review CLI (next command), VerdictCollector, ReviewWriter (append-only), Presenter, 80 tests
- **Plan 03 COMPLETE**: VerdictRouter (reject->memory_candidates, accept->trust), TrustAccumulator, CLI route/trust commands, 134 tests
- **Plan 04 COMPLETE**: Harness out-of-band oracle (4 structural invariants + N-version consistency), MetamorphicTester, HarnessRunner, CLI harness/stats commands, 176 tests
- **Two-layer validation architecture**: Agent B (classification judge) + Harness (independent trust anchor)
- **Bootstrap circularity resolved**: Harness has no memory, only structural checks against durable artifacts
- **Key modules**: src/pipeline/review/ (models, schema, pool_builder, sampler, presenter, collector, writer, router, trust, invariants, metamorphic, nversion, harness), src/pipeline/cli/review.py
- **Full CLI**: `python -m src.pipeline.cli review next|route|trust|harness|stats`

## Phase 16.1 Completion Summary

Phase 16.1 delivered topological edge-generation (all 4 plans):
- **Plan 01 COMPLETE**: axis_edges DuckDB schema with DDL/indexes, ActivationCondition + EdgeRecord Pydantic models, EdgeWriter with idempotent writes + degradation + retirement, topology schema integrated into create_schema() chain, 12 tests
- **Plan 02 COMPLETE**: ConjunctiveFlameDetector (Level>=5 AND Delta>=2 AND >=2 axes), EdgeGenerator (C(N,2) pairs), rolling median baseline, 15 tests
- **Plan 03 COMPLETE**: FrontierChecker (uncharted axis pair detection with activation_condition filtering), CrossAxisVerifier (foil level-matching for Equivocation detection), PAG gate extension (frontier + cross-axis checks), 12 tests
- **Plan 04 COMPLETE**: intelligence edges CLI subgroup (list/frontier/show), 15 end-to-end integration tests (deposit flow, frontier lifecycle, retirement flow, CLI commands)
- **1406 tests** passing (1391 baseline + 15 new integration tests, excluding pre-existing segmenter failure)
- **Full topology pipeline**: FlameEvent -> ConjunctiveFlameDetector -> EdgeGenerator -> EdgeWriter -> axis_edges -> FrontierChecker/CrossAxisVerifier -> PAG gate
- **Key modules**: src/pipeline/ddf/topology/ (models.py, schema.py, writer.py, detector.py, generator.py, frontier.py, verifier.py), src/pipeline/cli/intelligence.py (edges subgroup)
- **CLI**: `python -m src.pipeline.cli intelligence edges list|frontier|show`

## Phase 16 Completion Summary

Phase 16 delivered the Sacred Fire Intelligence System (all 4 plans):
- **Plan 01 COMPLETE**: transport_efficiency_sessions DuckDB schema (12 columns), memory_candidates TE extensions (pre_te_avg, post_te_avg, te_delta) + review extensions (confidence, subject, session_id), memory-review CLI command with CCD-format MEMORY.md writes, 25 tests
- **Plan 02 COMPLETE**: TE computation engine (compute_te_for_session, compute_fringe_drift, write_te_rows), backfill_trunk_quality (3+ newer sessions), backfill_te_delta (5+ post-acceptance AI sessions), Pipeline Step 20, 25 tests
- **Plan 03 COMPLETE**: Extended intelligence profile CLI with TE breakdown display, fringe drift display, trunk quality status indicators, 10 tests
- **Plan 04 COMPLETE**: 18 integration tests covering all 4 DDF requirements (DDF-06 TE computation, DDF-07 MEMORY.md closed loop, DDF-08 fringe drift, DDF-09 trunk quality backfill), full regression check (1517 passed, zero regressions)
- **1519 tests** total (1517 passed + 2 pre-existing segmenter failures)
- **DDF-06 verified**: TE composite computed per session for human and AI with unified formula
- **DDF-07 verified**: Level 6 FlameEvent -> memory_candidates -> memory-review accept -> MEMORY.md CCD entry
- **DDF-08 verified**: Fringe drift rate (0.0/1.0/None) per session+subject
- **DDF-09 verified**: trunk_quality starts 0.5/pending, backfills to confirmed with 3+ downstream sessions; te_delta computed with 5+ post-acceptance AI sessions
- **Terminal test**: End-to-end closed loop from FlameEvent through deposit, review, to persistent MEMORY.md entry
- **Key modules**: src/pipeline/ddf/transport_efficiency.py, src/pipeline/cli/intelligence.py (memory-review command)
- **CLI**: `python -m src.pipeline.cli intelligence memory-review [--db] [--memory-file]`

## Phase 17 Completion Summary

Phase 17 delivered the Candidate Assessment System (all 4 plans):
- **Plan 01 COMPLETE**: Assessment schema (assessment_te_sessions, assessment_baselines, ALTER TABLE extensions), ScenarioSpec/AssessmentSession/AssessmentReport Pydantic models, 16 tests
- **Plan 02 COMPLETE**: ScenarioGenerator (wisdom-to-scenario with handicap templates), CLI annotate-scenarios + list-scenarios, 18 tests
- **Plan 03 COMPLETE**: AssessmentSessionRunner (Actor lifecycle), AssessmentObserver (pipeline bridging), RejectionDetector (outcome-gated L5+ classification), 3-metric TE computation, 40 tests
- **Plan 04 COMPLETE**: AssessmentReporter (comprehensive markdown reports), terminal deposit (source_type='simulation_review', fidelity=3, confidence=0.85), auto-calibration proposals, CLI report command, 22 tests
- **1615 tests** total (1593 baseline + 22 new Plan 04 tests, excluding pre-existing segmenter failure)
- **Terminal deposit mechanism**: Assessment sessions produce CCD-quality memory_candidates entries that appear in the memory-review queue
- **3-metric TE**: raven_depth * crow_efficiency * trunk_quality (no transport_speed for short sessions)
- **Auto-calibration**: Deposits proposals for human review when last 3 ratios consistently too easy (>1.3) or too hard (<0.5)
- **Production isolation**: assessment_session_id IS NULL filter on all 5 IntelligenceProfile queries
- **Key modules**: src/pipeline/assessment/ (schema.py, models.py, scenario_generator.py, session_runner.py, observer.py, rejection_detector.py, te_assessment.py, reporter.py), src/pipeline/cli/assess.py
- **CLI**: `python -m src.pipeline.cli intelligence assess annotate-scenarios|list-scenarios|run|calibrate|report`
