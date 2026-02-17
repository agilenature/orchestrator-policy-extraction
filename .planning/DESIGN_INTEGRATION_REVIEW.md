# Design Integration & Planning Review

**Date:** 2026-02-10
**Reviewer:** Claude Sonnet 4.5
**Status:** Ready for user approval

---

## Executive Summary

The design documents in `docs/design/` have been integrated into a single authoritative specification (`AUTHORITATIVE_DESIGN.md`). The evolution from initial "turn-level" thinking to "decision-point orchestrator episodes" is now complete and coherent.

**Key Achievement:** The design has successfully moved from a **floating abstraction** ("turn-level is better") to a **grounded specification** ("decision-point orchestrator episodes enable policy learning").

---

## Design Evolution Summary

### Document Chronology & Synthesis

1. **WHY_TURN_LEVEL.md** (Feb 5)
   - **Core claim:** Turn-level episodes beat commit-only correlation
   - **Strengths:** Identified that commits hide mistakes, corrections, exploration
   - **Blind spots:** Confused executor (tool calls) with orchestrator (directives)

2. **WHY_TURN_LEVEL - Revision.md** (Feb 5)
   - **Critique:** Original approach would train executor, not orchestrator
   - **Key insights:**
     - Orchestrator actions = mode/scope/gates/constraints (not Read/Edit/Bash)
     - "Turn" is wrong unit; "decision point" is correct
     - User reactions must convert to preference model + objective proxies
     - Constraints must be extracted as first-class artifacts

3. **WHY_TURN_LEVEL - Improved.md** (Feb 6) **← AUTHORITATIVE**
   - **Status:** Complete v2 specification
   - **Includes:**
     - Strict JSON schema for orchestrator episodes
     - Decision-point detection rubric with event tagging
     - Episode builder specification with field derivation rules
     - Configuration (risk model, tags, keywords)
     - Constraint extraction patterns
     - Full pipeline stages (A-I)

4. **The Genus Method.md** & **The Genus Method - Justification.md** (Feb 6, Feb 10)
   - **Purpose:** Provide philosophical grounding for validation
   - **Key contribution:** Validator as "conceptual reality-checker" that prevents category errors
   - **Integration point:** Ensures orchestrator actions are properly classified and evidence-grounded

5. **Mission Control - supervisory control layer.md** (Feb 7)
   - **Discovery:** Mission Control is the missing operationalization layer
   - **Key insight:** Real-time episode capture beats post-hoc correlation
   - **Upgrade strategy:**
     - Task structure → orchestrator action schema
     - Planning Q&A → structured decision output
     - Review → reaction labels + constraint extraction
     - Tool provenance → episode outcome tracking

---

## Unified Design (No Contradictions)

### Core Architecture

**Three-layer model (clean separation):**
1. **Orchestrator episodes** (OpenClaw training target)
2. **Executor episodes** (Claude optimization, separate)
3. **Deliverable episodes** (commit/PR validation layer)

**Decision-point episodes structure:**
```
Observation (repo/quality/context) →
Orchestrator Action (mode/scope/gates/constraints/instruction/risk) →
Outcome (executor effects + quality + reaction + rewards + constraints extracted)
```

**Operationalization:** Mission Control + Validator + Episode Builder

### Key Design Principles (Consistent Across All Documents)

1. **Genus method applied:**
   - System genus: "Supervised governance-and-learning system for agentic orchestration"
   - Episode genus: "Decision-point orchestrator directive with validated structure"
   - Prevents floating abstractions ("turn-level" → "decision-point episodes")

2. **Orchestrator ≠ Executor:**
   - Never train on tool calls as if they were orchestrator decisions
   - Mode/scope/gates/constraints are the learnable action space

3. **Reactions → Durable Signals:**
   - While human present: approve/correct/redirect/block/question labels
   - When human absent: objective proxies + preference model + constraint store

4. **Evidence grounding:**
   - Validator ensures decisions justified by observation
   - Non-contradiction checks prevent epistemic errors
   - Provenance links every episode to source logs/commits

5. **Real-time beats post-hoc:**
   - Mission Control captures episodes as they happen
   - No need for probabilistic correlation (task_id is the join key)
   - Event-sourcing architecture (not log scraping)

---

## What's Complete

### ✅ Design Documents
- [x] Authoritative specification written (`AUTHORITATIVE_DESIGN.md`)
- [x] Decision-point episode schema (JSON Schema in Improved.md, referenced in spec)
- [x] Event tagging taxonomy (O_DIR, X_PROPOSE, T_TEST, etc.)
- [x] Episode segmentation rules (start/end triggers)
- [x] Reaction labeling rubric
- [x] Constraint extraction patterns
- [x] Risk model (protected paths, diff thresholds, risky commands)
- [x] Configuration spec (YAML structure)
- [x] Mission Control integration strategy
- [x] Validator specification (genus-based, multi-layer)
- [x] Three-layer architecture (orchestrator/executor/deliverable)

### ✅ Conceptual Coherence
- [x] Genus correctly identified (no category errors)
- [x] Orchestrator vs executor distinction clear
- [x] Decision points vs turns distinction clear
- [x] Reaction → preference model transition understood
- [x] Commit correlation positioned as validation layer (not learning core)

---

## What's Missing (Implementation Priorities)

### Phase 0.5: Schema & Config Finalization
**Status:** Nearly complete, needs file creation

1. **Create `data/schemas/orchestrator-episode.schema.json`**
   - Extract full schema from Improved.md (lines 353-829)
   - Add validation examples
   - **Effort:** 1 hour

2. **Create `data/config.yaml`**
   - Risk model configuration
   - Event tag definitions
   - Reaction keywords
   - Mode inference rules
   - **Effort:** 30 minutes

3. **Update `data/projects.json`** (if needed)
   - Ensure schema includes instrumentation level tracking
   - **Effort:** 15 minutes

### Phase 1: Episode Builder (Core Pipeline)
**Status:** Design complete, implementation pending

Priority order from AUTHORITATIVE_DESIGN.md:

1. Event stream normalizer (JSONL + git → unified events)
2. Event tagger (classification layer)
3. Episode segmenter (decision-point detection)
4. Field populator (observation, action, outcome derivation)
5. Reaction labeler (keyword matching + confidence)

**Estimated effort:** 2-3 weeks (can use `/gsd:quick` for some parts)

### Phase 2: Constraint Store & Validator
**Status:** Design complete, implementation pending

6. Constraint extractor (corrections → durable rules)
7. Validator (genus-based, multi-layer checks)
8. Reward signal calculator (objective proxies)

**Estimated effort:** 1 week

### Phase 3: Mission Control Integration
**Status:** Design complete, requires Mission Control repo access

11. Task structure enhancement (add orchestrator fields)
12. Planning output structuring (emit orchestrator action JSON)
13. Review widget (reaction UI + constraint extraction)
14. Tool provenance recording (OpenClaw Gateway integration)
15. Episode tables in SQLite

**Estimated effort:** 2-3 weeks (depends on Mission Control codebase complexity)

**Blocker:** Need access to Mission Control repository
- GitHub: https://github.com/crshdn/mission-control
- Or ClawDeck: https://clawdeck.io

### Phase 4: Training Infrastructure
**Status:** Design outlined, requires Phase 1-3 complete

16. RAG baseline orchestrator
17. Preference model training
18. Shadow mode testing
19. Learned policy training

**Estimated effort:** 4-6 weeks (research + experimentation)

---

## Recommendations

### Immediate Next Steps (Week 1)

**Option A: Complete Phase 0.5 (Schema & Config)**
- Create JSON schema file
- Create config.yaml
- Validate against worked example from Improved.md
- **Why:** Unblocks all future implementation
- **Command:** `/gsd:quick "Create data/schemas/orchestrator-episode.schema.json and data/config.yaml from design spec"`

**Option B: Start Phase 1 (Episode Builder MVP)**
- Focus on stages A-C (normalize, tag, segment)
- Process one historical session end-to-end
- Validate output episodes manually
- **Why:** Proves the design works on real data
- **Command:** `/gsd:discuss-phase 1` (if setting up GSD structure first)

**Option C: Set Up GSD Structure**
- Run `/gsd:new-project` to create PROJECT.md, ROADMAP.md
- Migrate existing planning documents
- Create formal phase breakdown
- **Why:** Systematic execution with state tracking
- **Command:** `/gsd:new-project`

### Medium-Term Strategy (Month 1-2)

1. **Build Episode Builder incrementally:**
   - Week 1: Stages A-C (normalize, tag, segment)
   - Week 2: Stages D-F (populate, react, constrain)
   - Week 3: Stages G-I (rewards, delegation, commit link)
   - Week 4: Testing on multiple projects, quality metrics

2. **Parallel track: Mission Control exploration**
   - Clone Mission Control repository
   - Map existing schema to required upgrades
   - Identify API integration points
   - Prototype structured planning output

3. **Validation track: Manual episode review**
   - Extract 100 episodes from modernizing-tool
   - Manual quality check (mode accuracy, reaction labels, constraints)
   - Refine rules based on errors
   - Target: ≥85% mode accuracy, ≥80% reaction confidence

### Long-Term Path (Month 3-6)

1. **Complete Mission Control integration**
   - Real-time episode capture
   - Structured task/planning workflow
   - Review UI with reaction labels
   - Constraint store integration

2. **Build baseline orchestrator (RAG)**
   - Vector embeddings of observations
   - Retrieve top-k similar episodes
   - Recommend orchestrator action
   - Shadow mode testing

3. **Train preference model**
   - Dataset: (observation, action, reaction) tuples
   - Model: Classifier → approve/correct/block probability
   - Validation: Hold-out test set accuracy ≥80%

4. **Graduated autonomy rollout**
   - Low-risk tasks: full autonomy
   - Medium-risk: preference model approval
   - High-risk: human approval required

---

## Critical Decisions Needed

### 1. Prioritization: Which Phase First?

**Question:** Start with Episode Builder (batch processing) or Mission Control integration (real-time capture)?

**Arguments for Episode Builder first:**
- ✅ Can process historical data immediately
- ✅ Validates design on real sessions
- ✅ Generates training dataset for future models
- ✅ No external dependencies

**Arguments for Mission Control first:**
- ✅ Future-facing (captures new data)
- ✅ Governance benefits available immediately
- ✅ Higher quality episodes (structured at creation time)
- ❌ Requires Mission Control repo access
- ❌ More complex integration

**Recommendation:** **Episode Builder first** (Phase 1), then Mission Control (Phase 3). Reason: Prove the design works, then scale to real-time.

### 2. GSD Structure: Yes or No?

**Question:** Should this project use standard GSD workflow (PROJECT.md, ROADMAP.md, phases)?

**Arguments for GSD:**
- ✅ Systematic execution with state tracking
- ✅ Clear phase boundaries and deliverables
- ✅ Automatic commits and documentation
- ✅ Progress visibility

**Arguments against GSD:**
- ❌ Current planning structure is already detailed (.planning/ documents)
- ❌ Research project may not fit phase model cleanly
- ❌ Overhead of maintaining two planning systems

**Recommendation:** **Lightweight GSD hybrid**:
- Don't create full ROADMAP.md (keep design docs as-is)
- Do create PROJECT.md (problem statement + goals)
- Use `/gsd:quick` for discrete implementation tasks
- Use manual planning for research/design phases

### 3. DuckDB Database: Create Now or Later?

**Question:** Set up `data/ope.db` (DuckDB) now or wait until Episode Builder produces JSONL?

**Arguments for now:**
- ✅ Forces schema finalization
- ✅ Can incrementally populate as builder improves
- ✅ Table design feedback loop

**Arguments for later:**
- ✅ Avoid premature optimization
- ✅ JSONL is easier to inspect/debug initially
- ✅ Schema may evolve during implementation

**Recommendation:** **JSONL first, DuckDB later**. Reason: JSONL episodes are human-readable for validation. Once quality is high, bulk import to DuckDB.

---

## Design Quality Assessment

### Strengths

1. **Conceptually grounded:** Genus method prevents floating abstractions
2. **Architecturally clean:** Three layers, no confusion
3. **Operationally complete:** Mission Control integration is realistic path
4. **Learning-ready:** Schema supports supervised learning, RL, RAG, preference modeling
5. **Safety-conscious:** Validator + harness + constraints prevent disasters
6. **Evidence-based:** Every decision justified by observation, provenance tracked

### Potential Risks

1. **Complexity:** Full system is ambitious (Episode Builder + Mission Control + Validator + Training)
   - **Mitigation:** Incremental rollout, prove each piece works

2. **Mode inference accuracy:** Deterministic keyword rules may not reach 85% target
   - **Mitigation:** Start with rules, upgrade to ML classifier if needed

3. **Reaction label noise:** Manual labeling from text is error-prone
   - **Mitigation:** Confidence scores, manual spot-checks, iterative refinement

4. **Mission Control integration effort:** Unknown codebase complexity
   - **Mitigation:** Explore repo first, prototype before committing

5. **Data volume:** Processing all sessions may be slow
   - **Mitigation:** Start with 1-2 projects, optimize pipeline, then scale

---

## Conclusion

**Design status:** ✅ **Complete and coherent**

The design documents have been successfully integrated into `AUTHORITATIVE_DESIGN.md` with:
- No contradictions
- Clear architecture (three layers)
- Operationalization path (Mission Control)
- Implementation roadmap (4 phases)
- Validation strategy (genus-based)

**Next action required:** User must choose prioritization:

1. **Option A:** Create schemas/config (Phase 0.5) → `/gsd:quick` to implement
2. **Option B:** Start Episode Builder (Phase 1) → `/gsd:discuss-phase 1` or manual planning
3. **Option C:** Set up GSD structure → `/gsd:new-project` then proceed

**No design work remaining.** Implementation can begin immediately upon user decision.

---

## Appendix: File Status

### Design Documents (docs/design/)
- ✅ `AUTHORITATIVE_DESIGN.md` — **NEW: Single source of truth**
- ℹ️ `WHY_TURN_LEVEL - Improved.md` — **Reference: Full technical details**
- ℹ️ `The Genus Method - Justification.md` — **Reference: Validator rationale**
- ℹ️ `Mission Control - supervisory control layer.md` — **Reference: Integration strategy**
- ⚠️ `WHY_TURN_LEVEL.md` — **Obsolete: Superseded by Improved.md**
- ⚠️ `WHY_TURN_LEVEL - Revision.md` — **Obsolete: Superseded by Improved.md**
- ⚠️ `The Genus Method.md` — **Reference: Background only**

**Recommendation:** Mark obsolete files with prefix `ARCHIVE_` or move to `docs/design/archive/`

### Planning Documents (.planning/)
- ✅ `STATE.md` — Current (but pre-integration)
- ✅ `PHASE-0-DECISIONS.md` — Current (infrastructure decisions)
- ✅ `config.json` — Current (workflow config)
- ⚠️ Missing: `PROJECT.md`, `ROADMAP.md` (if using GSD)

### Data Artifacts (data/)
- ⚠️ Missing: `schemas/orchestrator-episode.schema.json` **(Priority 1)**
- ⚠️ Missing: `config.yaml` (risk model, tags, keywords) **(Priority 2)**
- ✅ `projects.json` — Exists (may need schema update)

---

**Ready for user approval and next-step decision.**
