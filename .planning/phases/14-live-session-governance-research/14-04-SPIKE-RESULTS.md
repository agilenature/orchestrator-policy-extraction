# Phase 14 Plan 04: OpenClaw Bus Spike Results

**Spike date:** 2026-02-24
**Spike type:** Validation (not selection) -- all transport/architecture decisions locked by 14-01/14-02
**Session file:** `~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/d3573799-dd26-4856-b59d-b5396bd9e76e.jsonl`
**Session size:** 3.9MB, 498 JSONL events, session ID `d3573799-dd26-4856-b59d-b5396bd9e76e`

---

## 1. OPE Post-Task Memory Layer Validation

**Spike question:** Does `python -m src.pipeline.cli extract` work as the governing orchestrator's post-task memory ingestion step?

**Test file:** `~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/d3573799-dd26-4856-b59d-b5396bd9e76e.jsonl` (3.9MB, 498 JSONL lines)

**Command:**
```bash
python -m src.pipeline.cli extract \
  ~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/d3573799-dd26-4856-b59d-b5396bd9e76e.jsonl \
  --db data/ope.db -v
```

**Result:**
- Events ingested: 360 (of 498 JSONL lines; remainder are non-message metadata)
- Episodes populated: 15
- Episodes valid: 0 (see note below)
- Episodes invalid: 15 (all failed JSON Schema validation due to `parent_episode_id` not in schema)
- Escalation episodes written: 9 (inserted via separate escalation writer, bypasses JSON Schema validation)
- Reaction labels (from populated episodes): correct:6, unknown:6, approve:2, question:1
- Tag distribution: untagged:324, O_CORR:11, T_GIT_COMMIT:7, T_LINT:5, X_ASK:5, O_DIR:4, T_TEST:4
- Constraints extracted: 0 new (all duplicates of existing 419 constraints in store)
- Constraint evaluations: 131 constraints evaluated against this session
- Amnesia events: 38 detected
- Processing time: 3.3s (wall clock 4.1s including Python startup)
- Fatal errors: none

**Cumulative database state after run:**
- Total episodes in DB: 913
- Reaction label distribution (all sessions): correct:262, null:211, approve:203, unknown:197, question:37, block:3
- Episodes with observation populated: 790/913 (86.5%)
- Total constraints in store: 419
- Escalation episodes: 123
- Constraint-generating episodes (correct+block): 265

**Validation issue (not a blocker):**
All 15 populated episodes failed JSON Schema validation because `parent_episode_id` (added in Phase 14.1-01) is not yet in the `orchestrator-episode.schema.json` definition. The episodes were fully populated with observation, orchestrator_action, outcome, reaction_label, and scope -- they are structurally complete. The validation failure is a schema drift bug, not a pipeline functionality issue. The escalation writer (which bypasses JSON Schema validation) stored 9 episodes successfully, confirming the pipeline's DuckDB write path works.

**Finding:** CONFIRMED (with minor schema drift note)

The extract pipeline processes worker session JSONL files end-to-end: ingests events, tags them, segments into episodes, populates episode fields (observation, action, outcome, reaction_label, scope), extracts constraints, detects escalation sequences, evaluates constraint compliance, and detects amnesia events. All of this happens in a single `python -m src.pipeline.cli extract` invocation in ~3.3s.

**Architectural decision:** The governing orchestrator DOES NOT need a new memory ingestion component. After a worker session reaches CONFIRMED_END, the orchestrator runs:
```bash
python -m src.pipeline.cli extract <worker_jsonl_path> --db <shared_db_path>
```
This is the post-task memory ingestion step. The output (episodes with reaction labels, constraint evaluations, amnesia events) constitutes fidelity=2 memory-candidates-quality data. Phase 15 wires this to the CONFIRMED_END trigger in the stream processor.

**Pre-Phase 15 fix required:** Update `orchestrator-episode.schema.json` to include `parent_episode_id` (optional string) so episode validation passes. This is a Rule 1 bug fix, not an architectural change.
