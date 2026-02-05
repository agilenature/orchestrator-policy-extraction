# Orchestrator Policy Extraction - Roadmap

## Overview

This roadmap follows the GSD (Get Stuff Done) framework with atomic, verifiable phases.

**Timeline:** ~6-8 weeks for Phases 0-5, then evaluation-driven progression

---

## Phase 0: Data Infrastructure Design

**Goal:** Establish optimal multi-project data architecture before building pipeline

**Duration:** 3-5 days

**Why Critical:** Prevents costly refactoring; enables clean multi-project scaling

### Milestones

#### 0.1: Storage Format & Organization Decisions
**Deliverables:**
- Decision document for:
  - Per-project vs. unified storage strategy
  - Session data: copy JSONL vs. reference in place vs. extract to DB
  - Git data: full clone vs. commit metadata extraction
  - Episode format: JSONL vs. SQLite vs. Parquet
  - Directory structure specification
- Rationale for each decision with tradeoffs

**Success Criteria:**
- All storage decisions documented
- Directory structure diagram created
- Format choices justified with performance/maintainability tradeoffs

#### 0.2: Project Registry Design
**Deliverables:**
- `data/projects.json` schema defined
- Project metadata fields specified:
  - Project ID, name, description
  - Repository URL and commit range
  - Session directory path and date range
  - Data collection settings (hash extraction, phase labeling)
  - Quality metrics (correlation precision, episode count)
- Validation rules for registry entries

**Success Criteria:**
- JSON schema validates registry structure
- Initial 2 projects (modernizing-tool, orchestrator-policy-extraction) registered
- Validation script prevents malformed entries

#### 0.3: Data Infrastructure Implementation
**Deliverables:**
- `data/` directory structure created
- `data/raw/` with per-project subdirectories
- `data/processed/` for extracted artifacts
- `data/merged/` for cross-project analysis
- `.gitignore` rules (exclude large raw data, include processed summaries)

**Success Criteria:**
- Directory structure matches specification
- README in each subdirectory explains purpose
- Initial projects have placeholder directories

#### 0.4: Instrumentation Guide Creation
**Deliverables:**
- `INSTRUMENTATION.md` with step-by-step instructions:
  - **Pre-requisites:** Git hooks for session ID tracking
  - **Required metadata:** What IDs/timestamps to capture
  - **Data collection checklist:** Session export, git clone, metadata creation
  - **Quality validation:** Scripts to verify data completeness
  - **Adding to registry:** How to register new project
  - **Correlation run:** Commands to process new project
- Templates for:
  - Git commit message trailers (session ID, Claude attribution)
  - Project metadata.json
  - Validation checklist

**Success Criteria:**
- Following the guide, a user can add a new project in <30 minutes
- Guide includes troubleshooting section
- Templates are copy-paste ready

**Phase 0 Exit Criteria:**
- ✅ All storage format decisions documented and implemented
- ✅ Project registry initialized with 2 projects
- ✅ `INSTRUMENTATION.md` complete and tested
- ✅ Data infrastructure ready for ingestion

---

## Phase 1: Session-Commit Correlation (Multi-Project)

**Goal:** Build hash-based correlation pipeline that achieves >90% precision

**Duration:** 5-7 days

**Dependencies:** Phase 0 complete

### Milestones

#### 1.1: Data Ingestion for modernizing-tool
**Deliverables:**
- `data/raw/modernizing-tool/sessions/` populated (copy or symlink)
- `data/raw/modernizing-tool/git/` with cloned repository
- `data/raw/modernizing-tool/metadata.json` created

**Success Criteria:**
- All 142 session JSONL files accessible
- Git repository at correct commit range (Feb 3-5, 2026)
- Metadata includes session date range, commit count, author

#### 1.2: Hash Extraction from Sessions
**Deliverables:**
- `src/correlation/hash_extractor.py`
- Extracts file hashes from:
  - Read tool calls (file content → hash)
  - Edit tool calls (old_string, new_string → infer hash)
  - Write tool calls (content → hash)
- Output: `data/processed/modernizing-tool/session-hashes.json`
  - Format: `{session_id: {timestamp: [(file_path, hash), ...]}}`

**Success Criteria:**
- Extracts hashes from >95% of Read/Edit/Write tool calls
- Timestamps preserved for temporal matching
- Handles edge cases (binary files, empty files)

#### 1.3: Hash Extraction from Git Commits
**Deliverables:**
- `src/correlation/git_hash_extractor.py`
- Extracts from commit diffs:
  - File paths
  - Pre-commit hashes (from git object database)
  - Post-commit hashes
- Output: `data/processed/modernizing-tool/commit-hashes.json`
  - Format: `{commit_sha: {timestamp, files: [(path, pre_hash, post_hash)]}}`

**Success Criteria:**
- Extracts hashes for all 119 commits
- Matches git's native hash computation
- Preserves commit timestamps and metadata

#### 1.4: Hash-Based Correlation Algorithm
**Deliverables:**
- `src/correlation/correlator.py`
- Matching algorithm:
  1. For each commit, find sessions in [t_commit - 4h, t_commit]
  2. Compute hash overlap: |session_hashes ∩ commit_hashes| / |commit_hashes|
  3. Temporal proximity score: exp(-Δt / 1 hour)
  4. Combined score: 0.7 * hash_overlap + 0.3 * temporal_score
  5. Threshold: score > 0.6 for high-confidence match
- Output: `data/processed/modernizing-tool/session-commit-map.json`
  - Format: `{commit_sha: {session_id, confidence, matched_files, timestamp_delta}}`

**Success Criteria:**
- Correlation precision >90% on manual validation set (20 commits)
- Confidence scores calibrated (high confidence → correct match)
- Handles many-to-one (multiple sessions → one commit)

#### 1.5: Multi-Project Correlation Index
**Deliverables:**
- `data/merged/all-correlations.json` combining all projects
- Cross-project statistics dashboard
- Validation report per project

**Success Criteria:**
- Unified index with project labels
- Per-project precision/recall metrics
- Identifies low-quality projects needing re-processing

**Phase 1 Exit Criteria:**
- ✅ modernizing-tool correlation achieves >90% precision
- ✅ session-commit-map.json generated and validated
- ✅ Pipeline documented and reusable for new projects
- ✅ Correlation statistics logged in project metadata

---

## Phase 2: Turn-Level Episode Extraction (Multi-Project)

**Goal:** Parse sessions into (observation, action, reaction) tuples

**Duration:** 5-7 days

**Dependencies:** Phase 1 complete

### Milestones

#### 2.1: Session Parser
**Deliverables:**
- `src/extraction/session_parser.py`
- Parses JSONL logs into structured turns:
  - User prompts (observations)
  - Assistant responses (reasoning + tool calls = actions)
  - User reactions (next prompt = ground truth)
- Handles:
  - Multi-turn conversations
  - Subagent delegations (Task tool)
  - Tool call failures
  - Session interruptions

**Success Criteria:**
- Parses all 21 parent sessions without errors
- Extracts >95% of user-assistant-user triplets
- Preserves conversation context (prior N turns)

#### 2.2: Observation Feature Extraction
**Deliverables:**
- `src/extraction/observation_builder.py`
- Extracts features for each turn:
  - **Conversation context:** Last 3 user/assistant turns
  - **File state:** Files recently Read/Edited (from prior tool calls)
  - **Phase label:** Parse from `.planning/STATE.md` references or session metadata
  - **Test status:** Extract from Bash tool results (pytest outputs)
  - **Error logs:** References to `.ralph/errors.log`
  - **Current task:** Infer from user prompt keywords
- Output schema: `Observation` dataclass

**Success Criteria:**
- Feature extraction runs on all episodes
- Phase labels extracted for 80%+ of turns
- Test status detected when present in Bash outputs

#### 2.3: Action Taxonomy Mapping
**Deliverables:**
- `src/extraction/action_mapper.py`
- `data/action-taxonomy.json` defining categories:
  - **Inspect codebase:** Read, Grep, Glob sequences
  - **Run tests:** Bash with pytest/ctest/make test
  - **Modify code:** Edit tool calls
  - **Create artifact:** Write to `.planning/` or `.ralph/`
  - **Delegate task:** Task tool with subagent
  - **Git operations:** Bash with git commands
  - **Search web:** WebFetch, WebSearch
  - **Ask question:** Clarifying prompts
- Maps raw tool calls to taxonomy labels

**Success Criteria:**
- >90% of tool calls mappable to taxonomy
- Taxonomy covers all major orchestration patterns
- Human review confirms labels are intuitive

#### 2.4: Reaction Categorization
**Deliverables:**
- `src/extraction/reaction_categorizer.py`
- `data/reaction-taxonomy.json` defining types:
  - **Approve:** User continues without correction
  - **Correct:** User points out mistake, requests fix
  - **Redirect:** User changes direction/scope
  - **Block:** User stops action (e.g., denies risky tool call)
  - **Question:** User asks for clarification
- Categorizes user's next prompt based on:
  - Keywords (e.g., "no", "actually", "instead")
  - Sentiment analysis
  - Tool call approval/denial logs

**Success Criteria:**
- Categorization accuracy >75% on manual validation set
- Inter-rater agreement >85% on reaction labels
- Handles ambiguous cases with confidence scores

#### 2.5: Episode Dataset Generation
**Deliverables:**
- `data/processed/modernizing-tool/episodes/` directory
- One JSONL file per session with episodes:
  ```json
  {
    "episode_id": "session_abc_turn_05",
    "project": "modernizing-tool",
    "session_id": "abc123",
    "turn_index": 5,
    "timestamp": "2026-02-01T14:23:00Z",
    "observation": { ... },
    "claude_action": { ... },
    "user_reaction": { ... },
    "correlated_commit": "sha256_if_available"
  }
  ```
- `data/merged/all-episodes.jsonl` combining all projects

**Success Criteria:**
- >150 episodes extracted from modernizing-tool
- All episodes have complete observation/action/reaction
- Chronological ordering preserved

**Phase 2 Exit Criteria:**
- ✅ Turn-level episodes extracted from all projects
- ✅ Action taxonomy validated (>90% coverage)
- ✅ Reaction taxonomy validated (>75% accuracy)
- ✅ Episode dataset ready for policy learning

---

## Phase 3: Reaction Taxonomy Development

**Goal:** Refine and validate reaction categorization for policy evaluation

**Duration:** 3-5 days

**Dependencies:** Phase 2 complete

### Milestones

#### 3.1: Manual Validation Dataset
**Deliverables:**
- 100 randomly sampled episodes manually labeled
- `data/validation/reaction-labels.json` with gold standard reactions
- Inter-rater agreement study (2+ labelers)

**Success Criteria:**
- 100 episodes labeled by 2 independent reviewers
- Cohen's kappa >0.80 (substantial agreement)
- Disagreements resolved through discussion

#### 3.2: Taxonomy Refinement
**Deliverables:**
- Updated `data/reaction-taxonomy.json` based on validation findings
- New categories if needed (e.g., "partial approval")
- Clearer decision rules for edge cases

**Success Criteria:**
- Updated taxonomy improves categorization accuracy to >85%
- Decision tree documented for ambiguous cases

#### 3.3: Automated Categorizer Training
**Deliverables:**
- `src/taxonomy/reaction_classifier.py`
- Uses validation set to train/tune categorizer:
  - Keyword-based rules
  - Sentiment features
  - Contextual embeddings (optional)
- Cross-validation on validation set

**Success Criteria:**
- Automated categorizer achieves >80% accuracy
- Precision/recall balanced across all reaction types
- Fast inference (<100ms per episode)

**Phase 3 Exit Criteria:**
- ✅ Reaction taxonomy validated and refined
- ✅ Automated categorizer achieves >80% accuracy
- ✅ Documentation for adding new reaction types

---

## Phase 4: RAG-Based Baseline Orchestrator

**Goal:** Build retrieval-based policy for action recommendation

**Duration:** 5-7 days

**Dependencies:** Phases 2-3 complete

### Milestones

#### 4.1: Episode Indexing
**Deliverables:**
- `src/orchestrator/episode_indexer.py`
- Indexes episodes by:
  - Phase labels (semantic grouping)
  - File context (trigram similarity)
  - Task keywords (TF-IDF or embeddings)
- Storage: FAISS or simple JSON with BM25

**Success Criteria:**
- All episodes indexed
- Retrieval latency <500ms for top-k=10
- Supports filtering by project, phase, date range

#### 4.2: Retrieval Policy
**Deliverables:**
- `src/orchestrator/rag_policy.py`
- Given current observation:
  1. Retrieve top-k=10 most similar past episodes
  2. Extract actions from those episodes
  3. Rank by frequency and success (reactions != "correct")
  4. Return top-3 recommended actions
- Evaluation on held-out test set (20% of episodes)

**Success Criteria:**
- Top-1 action accuracy >40% on test set
- Top-3 action accuracy >70% on test set
- Retrieval relevance: retrieved episodes have similar context

#### 4.3: Explainability & Provenance
**Deliverables:**
- Recommendations include:
  - Retrieved episode IDs (for human review)
  - Similarity scores
  - Rationale: "In similar situations (phase X, files Y), Claude did Z"
- Web UI or CLI for interactive exploration

**Success Criteria:**
- Each recommendation traceable to source episodes
- Explanations are human-understandable
- UI allows filtering by confidence threshold

#### 4.4: Shadow Mode Framework
**Deliverables:**
- `src/orchestrator/shadow_mode.py`
- Runs orchestrator on NEW sessions (not in training set)
- Logs recommendations vs. actual Claude actions
- Metrics:
  - Agreement rate (% of times recommendation matches actual)
  - Reaction quality (when recommended action is taken, is reaction positive?)
  - False positive rate (dangerous recommendations)

**Success Criteria:**
- Framework tested on 5 held-out sessions
- Metrics dashboard implemented
- No dangerous action recommendations (verified manually)

**Phase 4 Exit Criteria:**
- ✅ RAG baseline achieves >40% top-1, >70% top-3 accuracy
- ✅ Shadow mode framework operational
- ✅ Explainability features implemented
- ✅ Zero dangerous recommendations in testing

---

## Phase 5: Evaluation & Shadow Mode Testing

**Goal:** Validate orchestrator on real sessions, measure effectiveness

**Duration:** 2-3 weeks (includes data collection)

**Dependencies:** Phase 4 complete

### Milestones

#### 5.1: Offline Evaluation
**Deliverables:**
- Comprehensive metrics on test set:
  - Action prediction accuracy (top-1, top-3, top-5)
  - Reaction quality (when recommendations followed, % positive reactions)
  - Per-phase performance (which phases work best?)
  - Per-action-type performance (which actions are predictable?)
- `analysis/evaluation/offline-results.md` report

**Success Criteria:**
- All metrics computed and documented
- Identifies strengths and weaknesses of policy
- Recommendations for improvement (e.g., "needs more data for phase X")

#### 5.2: Live Shadow Mode on New Sessions
**Deliverables:**
- Run orchestrator on 10 NEW modernizing-tool sessions (or orchestrator-policy-extraction sessions)
- Log recommendations in real-time
- Compare to actual actions taken
- User feedback: "Was this recommendation helpful?"

**Success Criteria:**
- 10 sessions processed
- Agreement rate >60% on action type (not exact parameters)
- User feedback: >70% of recommendations rated "somewhat helpful" or better
- No dangerous recommendations

#### 5.3: Error Analysis & Iteration
**Deliverables:**
- Analysis of disagreements:
  - Why did orchestrator recommend X when Y was taken?
  - Common failure modes
  - Missing context or features
- Updated taxonomy or indexing strategy based on findings
- Re-run evaluation to measure improvement

**Success Criteria:**
- Top 5 failure modes identified and documented
- Mitigation strategies proposed (e.g., add feature, collect more data)
- Iteration improves accuracy by >5 percentage points

**Phase 5 Exit Criteria:**
- ✅ Orchestrator validated on 10+ new sessions
- ✅ Agreement rate >60%, no dangerous recommendations
- ✅ Failure modes understood and documented
- ✅ Path forward identified (more data vs. better features vs. advanced models)

---

## Phase 6: Instrumentation & Dataset Growth

**Goal:** Make it easy to add new projects, grow dataset organically

**Duration:** 2-3 days

**Dependencies:** Phases 1-5 complete

### Milestones

#### 6.1: Git Hook Templates
**Deliverables:**
- `.git/hooks/prepare-commit-msg.sample` template
- Automatically adds to commit messages:
  ```
  X-Claude-Session: {session_id}
  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
  ```
- Instructions for installing hook in `INSTRUMENTATION.md`

**Success Criteria:**
- Template works on macOS, Linux
- Session ID sourced from environment variable or Claude Code API
- Existing commit messages not broken

#### 6.2: Project Onboarding Automation
**Deliverables:**
- `scripts/add-project.py` CLI tool:
  - Prompts for project name, repo URL, session directory
  - Validates data completeness
  - Adds to `data/projects.json`
  - Runs correlation pipeline automatically
  - Generates project report
- End-to-end test on orchestrator-policy-extraction project

**Success Criteria:**
- Onboarding script runs without errors
- New project added to registry and processed in <10 minutes
- Generated report includes correlation precision, episode count

#### 6.3: Continuous Data Collection
**Deliverables:**
- Documented workflow for periodic data updates:
  - Weekly: Export new Claude sessions
  - Weekly: Pull new commits from tracked projects
  - Weekly: Re-run correlation on incremental data
  - Monthly: Retrain/re-index orchestrator
- Cron job or GitHub Actions template (optional)

**Success Criteria:**
- Workflow documented and tested manually
- Incremental processing avoids re-processing old data
- Dataset growth tracked in metadata

**Phase 6 Exit Criteria:**
- ✅ orchestrator-policy-extraction project added to dataset
- ✅ Git hooks installed and tested
- ✅ Onboarding script functional
- ✅ Continuous collection workflow documented

---

## Phase 7+: OpenClaw Integration (Future)

**Status:** DEFERRED until Phases 0-6 demonstrate success

**Prerequisites:**
- RAG orchestrator achieves >70% agreement in shadow mode
- Dataset includes 5+ projects with 500+ episodes total
- No dangerous recommendations in extensive testing

**High-Level Plan:**

### 7.1: OpenClaw Sandbox Configuration
- Set up `agents.defaults.sandbox.mode: "all"`
- Define exec allowlists (safe-git-*, test runners)
- Implement risk scoring for actions

### 7.2: Staged Promotion Ladder
- **Stage 1 (Shadow):** Recommendations only, no execution
- **Stage 2 (Read-only):** Execute inspection tools (Read, Grep, Glob)
- **Stage 3 (Write-in-branch):** Allow edits in feature branches
- **Stage 4 (PR Autopilot):** Create PRs, require human review
- **Stage 5 (Limited Merge):** Merge low-risk PRs automatically

### 7.3: Governance & Monitoring
- Audit trail for all autonomous actions
- Approval gates for high-risk operations
- Anomaly detection (unusual action patterns)
- Kill switch for immediate shutdown

**Exit Criteria TBD** based on Phase 5 results.

---

## Success Metrics Summary

| Phase | Key Metric | Target |
|-------|------------|--------|
| 0 | Infrastructure complete | All decisions documented |
| 1 | Correlation precision | >90% |
| 2 | Episode extraction | >150 episodes |
| 3 | Reaction categorization | >80% accuracy |
| 4 | RAG top-3 accuracy | >70% |
| 5 | Shadow mode agreement | >60% |
| 6 | Projects in dataset | ≥2 |
| 7+ | Autonomous merge rate | TBD |

---

## Timeline Overview

```
Week 1:     Phase 0 (Infrastructure)
Week 2-3:   Phase 1 (Correlation)
Week 4-5:   Phase 2 (Extraction)
Week 6:     Phase 3 (Taxonomy)
Week 7-8:   Phase 4 (RAG Orchestrator)
Week 9-11:  Phase 5 (Evaluation)
Week 12:    Phase 6 (Instrumentation)
Future:     Phase 7+ (OpenClaw)
```

**Total estimated duration for Phases 0-6:** ~12 weeks

---

## Dependencies & Risks

### Critical Path
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

Phase 6 can happen in parallel with Phase 5.

### Risks
- **Phase 1:** Hash extraction may miss edge cases (binary files, large files)
- **Phase 2:** Session parsing complexity (nested subagents, interruptions)
- **Phase 3:** Low inter-rater agreement on reactions (taxonomy too ambiguous)
- **Phase 4:** RAG accuracy too low to be useful (need more data or better features)
- **Phase 5:** Shadow mode reveals safety issues (dangerous recommendations)

### Go/No-Go Gates
- **After Phase 1:** If correlation precision <70%, revisit algorithm before proceeding
- **After Phase 4:** If RAG accuracy <50%, collect more data before evaluation
- **After Phase 5:** If agreement <50% or ANY dangerous recommendations, do NOT proceed to Phase 7

---

## Next Steps

1. ✅ Review this roadmap with user
2. → Execute Phase 0.1: Storage format decisions
3. → Execute Phase 0.2-0.4: Registry, infrastructure, instrumentation
4. → Get user approval before proceeding to Phase 1
