# Pitfalls Research

**Domain:** Episode extraction & policy learning for agentic orchestration
**Researched:** 2026-02-10
**Confidence:** MEDIUM-HIGH (domain-specific analysis grounded in project design docs + external research; some pitfalls verified against published literature, others derived from first-principles analysis of design decisions)

---

## Critical Pitfalls

Mistakes that cause rewrites, corrupt training data, or train the wrong policy.

### Pitfall 1: Training the Executor Instead of the Orchestrator (Genus Violation)

**What goes wrong:**
The episode extraction pipeline captures tool-call sequences (Read/Grep/Edit/Bash) as the "action" in episodes, producing episodes that train OpenClaw to mimic Claude Code's micro-steps instead of the human orchestrator's strategic decisions (mode/scope/gates/constraints).

**Why it happens:**
Tool calls are the most visible, structured data in session logs. They have clear timestamps, typed parameters, and deterministic outputs. It is natural to treat them as the "action" because they are easy to extract. The orchestrator's decisions (choose Explore mode, set scope to `auth/`, require tests before commit) are embedded in natural language directives that require inference.

**How to avoid:**
- Enforce the three-layer architecture at the data model level: Orchestrator episodes (primary), Executor episodes (secondary), Deliverable episodes (validation). Never mix layers.
- The `orchestrator_action` field must contain mode/scope/gates/constraints/executor_instruction -- not tool call names.
- Add a validator assertion: if `orchestrator_action.mode` is empty or `orchestrator_action.executor_instruction` looks like a tool call signature, reject the episode.
- During manual validation, ask: "Could OpenClaw act on this action without knowing which tools to call?" If yes, it is orchestrator-level. If no, it is executor-level.

**Warning signs:**
- Episode `orchestrator_action.executor_instruction` fields contain tool names ("Read src/parser.h") rather than strategic directives ("Scan repo for existing XML parsing patterns")
- Episode count roughly equals tool call count (should be 5-20x fewer)
- Mode field is always "Implement" (no Explore/Plan/Verify/Triage variety)
- Learned policy recommends specific tool calls instead of mode+scope+gates

**Phase to address:**
Phase 0.5 (schema validation) and Phase 1 (episode builder). The schema must structurally prevent this. The episode builder's field populator (Stage D) is where the genus violation either happens or is caught.

---

### Pitfall 2: Decision-Point vs. Turn Confusion (Wrong Segmentation Unit)

**What goes wrong:**
Episodes are segmented at every user-assistant message boundary ("turns") instead of at genuine decision points (where the orchestrator rationally chooses among alternatives after new evidence). This produces noisy episodes: many contain no real decision (just continuation), while others split a single complex decision across multiple episodes.

**Why it happens:**
Turn boundaries are trivially detectable in JSONL logs (message type changes). Decision-point boundaries require understanding the *semantic content* of events: did new evidence arrive? Was a proposal made? Did a test complete? This is harder to implement and harder to validate.

**How to avoid:**
- Implement the decision-point detection rubric from the design spec: episode start on O_DIR/O_GATE, episode end on X_PROPOSE/X_ASK/T_TEST result/T_RISKY/T_GIT_COMMIT/timeout.
- Validate episode density: target ~3-5 episodes per session (not 1:1 with turns). If episode count equals turn count, segmentation is wrong.
- Spot-check 20 episodes: each should represent a moment where the orchestrator had a nontrivial choice to make.
- Over-segmentation test: if two consecutive episodes have the same mode, scope, and no intervening evidence/proposal/test result, they should probably be one episode.

**Warning signs:**
- Episode count approximately equals user message count
- Many episodes have empty or trivial observations ("continuation of previous")
- Episodes lack decision-boundary triggers in provenance (no X_PROPOSE, T_TEST, etc.)
- Learned policy outputs "continue" as its most common recommendation

**Phase to address:**
Phase 1 (Episode Builder, Stage C segmentation). This is the most technically challenging stage and the one most likely to need iteration. Budget extra time for validation.

---

### Pitfall 3: Approval Bias / Survivorship Bias in Training Data

**What goes wrong:**
The training dataset is dominated by successful episodes (approve reactions) because: (a) commits only exist for things that worked, (b) corrections are harder to label than approvals, (c) abandoned paths and mistakes are often not captured in final logs. The resulting policy is overconfident and cannot handle failure states, novel situations, or the need to escalate.

**Why it happens:**
This is a structural property of interaction traces. When a human orchestrator corrects Claude, the correction often happens verbally ("No, use libxml2") and the corrected path replaces the wrong one. The *mistake* is rarely preserved as a distinct episode -- only the recovery appears. Additionally, sessions that went poorly may have been abandoned entirely (no commits, incomplete logs).

**How to avoid:**
- Explicitly extract negative episodes from corrections. When reaction = "correct" or "block", the *preceding* episode (the one that was wrong) is the high-value training signal. Ensure the episode builder captures both the mistake episode AND the recovery episode.
- Target: negative examples (correct/block/redirect) should be >= 20% of the dataset. If below 15%, the dataset is dangerously skewed.
- Mine abandoned sessions: sessions with no commits may contain valuable failure patterns.
- Augment with synthetic negative examples: take approved episodes and hypothesize what would have been wrong (e.g., "what if Implement was chosen without Explore first?").

**Warning signs:**
- Reaction label distribution: >85% approve, <10% correct/block
- Policy never recommends Explore or Plan modes (always jumps to Implement)
- Policy never recommends escalation or human approval gates
- Shadow mode: policy agrees with human on easy cases but diverges on hard ones

**Phase to address:**
Phase 1 (reaction labeling, Stage E) and Phase 3 (reaction taxonomy refinement). The reaction labeler must correctly identify implicit approvals vs. explicit approvals, and must not default to "approve" on ambiguous cases.

---

### Pitfall 4: Reaction Label Noise (Misclassifying Human Feedback)

**What goes wrong:**
The keyword-based reaction labeler misclassifies human messages, producing noisy supervision signal. Common errors: "looks good, but change the variable name" classified as "approve" (should be "correct"), or "let's move on to auth" classified as "redirect" (could be an implicit approval of previous work). Noisy labels corrupt both the episode dataset and the downstream preference model.

**Why it happens:**
Human language is ambiguous. Reactions are often implicit (moving to next task = approval), mixed (partial approval + minor correction), or contextual (same words mean different things in different situations). Keyword matching catches only the most explicit cases.

**How to avoid:**
- Assign confidence scores to every reaction label. Low-confidence labels (< 0.7) should be flagged for manual review, not treated as ground truth.
- Implement a "mixed reaction" category: "approve with minor correction" is different from pure "approve" and pure "correct". The constraint extraction pipeline must distinguish: corrections that indicate a policy failure vs. minor style preferences.
- Create a manual validation set of 100+ labeled episodes. Measure reaction labeler accuracy against this gold standard. Target: >= 80% accuracy on the validation set before using labels for training.
- Never train directly on low-confidence labels. Use them for retrieval (RAG) but not for preference model supervision.

**Warning signs:**
- Reaction label distribution doesn't match intuitive expectations (e.g., 0% "question" labels when sessions clearly contain questions)
- Manual spot-check reveals >20% mislabeled reactions
- Preference model achieves suspiciously high accuracy (>95%) -- likely overfitting to label noise rather than learning real preferences
- Constraint store contains trivial or wrong constraints ("avoid variable naming" extracted from a style comment)

**Phase to address:**
Phase 1 (Stage E, reaction labeling) and Phase 3 (taxonomy refinement and validation). The validation set must be created early and used as a continuous quality gate.

---

### Pitfall 5: Constraint Extraction False Positives (Overly Strict Rules Block Valid Work)

**What goes wrong:**
The constraint extractor creates rules that are too broad or too strict, causing the validator to block legitimate work. Example: a correction "don't use regex for XML" gets extracted as a blanket constraint "avoid regex" (scope: entire repo), which then blocks valid uses of regex for log parsing, URL matching, etc.

**Why it happens:**
Natural language corrections are often contextual ("don't do X *here*") but get extracted as universal rules ("never do X"). The scope inference (which paths/modules does this apply to?) is the weakest link: when the correction doesn't explicitly name a scope, the extractor defaults to repo-wide.

**How to avoid:**
- Always extract scope explicitly. If the correction mentions specific files/modules, scope to those. If not, default to the files currently being worked on (from episode context), NOT repo-wide.
- Implement severity carefully: "block" reactions -> forbidden, "correct" reactions -> requires_approval (NOT forbidden). Only escalate to forbidden on repeated corrections about the same issue.
- Add a constraint review step: new constraints are "proposed" and require human confirmation before becoming active. This prevents automated overcorrection.
- Test constraints against historical episodes: if a proposed constraint would have flagged >10% of previously-approved episodes, it is probably too broad.
- Track constraint false positive rate: when the validator flags a violation and the human overrides it, count that as a false positive. Target: <5% false positive rate.

**Warning signs:**
- Constraints block work that was previously approved in similar episodes
- Number of active constraints grows rapidly (>50 in first month) without corresponding corrections
- Validators produce many "violation" flags that humans routinely override
- Constraint scopes are mostly repo-wide (should be module/file-level)

**Phase to address:**
Phase 2 (constraint extractor and validator). The constraint store design must include a "proposed" state and a false-positive tracking mechanism from day one.

---

### Pitfall 6: Distribution Shift When Deploying Learned Policy

**What goes wrong:**
The learned policy performs well on historical episodes (offline evaluation) but fails when actually making decisions (online deployment), because the states it encounters during autonomous operation differ from the states in the training data. Small errors compound: one wrong decision leads to an unfamiliar state, leading to another wrong decision, cascading into failure.

**Why it happens:**
This is a fundamental problem in imitation learning, proven to cause exponential error compounding in continuous-action settings (Simchowitz et al., 2025). The training data only covers states the human orchestrator visited. When the policy makes a slightly different choice, it enters states the human never visited, and the policy has no training signal for those states.

**How to avoid:**
- Start with RAG baseline (not learned policy) for initial deployment. Retrieval-based systems degrade gracefully: when no similar episode exists, they return low-confidence results instead of hallucinating an action.
- Implement shadow mode testing extensively: run the policy in parallel with human orchestrator for >= 50 sessions before any autonomous operation. Measure not just agreement rate but *divergence severity* (how bad are the disagreements?).
- Use DAgger-style interactive correction: when the policy acts autonomously and makes mistakes, capture those mistakes as new training episodes. This fills in the distribution gap.
- Design the governing execution harness to catch cascading failures: if the policy's confidence drops below threshold for 3 consecutive decisions, force escalation to human.
- Never deploy autonomously on high-risk tasks regardless of policy confidence. The graduated autonomy ladder must be enforced by the harness, not by the policy itself.

**Warning signs:**
- Offline evaluation accuracy is high (>80%) but shadow mode agreement is low (<60%)
- Policy performance degrades rapidly after the first few autonomous decisions
- Policy repeatedly selects the same mode (e.g., always "Implement") regardless of context
- Error rate increases over time rather than stabilizing

**Phase to address:**
Phase 4 (training infrastructure) and Phase 5 (graduated autonomy). Shadow mode testing is the critical gate. Budget 2-3 months for shadow mode before any autonomous operation.

---

### Pitfall 7: Mode Inference Accuracy Below Threshold

**What goes wrong:**
The deterministic keyword-based mode inference (Stage D) fails to reach the 85% accuracy target. Common failure modes: "investigate this bug" classified as Explore instead of Triage; "clean up the auth module" classified as Implement instead of Refactor; directives that combine modes ("explore options, then implement the best one") get classified as only the first or last mode mentioned.

**Why it happens:**
Natural language directives don't map cleanly to a 7-mode taxonomy. Many directives are multi-modal ("explore then plan"), implicit ("fix the tests" could be Triage, Verify, or Implement), or domain-specific ("do the migration" is Implement but "start the migration" might be Plan). Keyword matching is brittle.

**How to avoid:**
- Build the manual validation set FIRST (before iterating on the mode classifier). Label 100+ episodes manually to establish ground truth.
- Measure confusion matrix, not just accuracy: which modes are confused with which? If Explore/Plan confusion is high, consider merging them for v0.
- Accept multi-modal episodes: some episodes legitimately span Explore -> Plan. Rather than forcing single-mode classification, allow mode sequences.
- Fallback strategy: if keyword rules produce <85% accuracy, switch to a lightweight LLM classifier (Claude Haiku) for mode inference on ambiguous cases. This is a known design upgrade path from the spec.
- Don't block on perfection: 85% is the target but 80% is acceptable for v0 if the 20% errors are distributed across modes (not systematically wrong for one mode).

**Warning signs:**
- One mode dominates (>50% of episodes) -- likely misclassification
- Confusion matrix shows systematic errors (e.g., all Triage classified as Verify)
- Manual review of 20 random episodes shows >3 mode errors
- Mode distribution doesn't match intuitive workflow patterns (should see Explore/Plan early, Implement/Verify/Integrate later)

**Phase to address:**
Phase 1 (Stage D, field populator). This is flagged as a known risk in the design phase. The upgrade path (keyword -> LLM classifier) should be planned from the start.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skipping provenance tracking | Faster episode extraction, simpler code | Cannot debug episodes, cannot trace policy decisions back to source logs, auditing impossible | Never -- provenance is load-bearing for the entire system |
| Keyword-only reaction labeling without confidence scores | Simpler implementation, no manual validation needed | Noisy labels corrupt preference model, constraint store fills with false positives | Only in initial prototyping (< 2 weeks), must add confidence before any training |
| Repo-wide constraint scope as default | Simpler extraction logic, no scope inference needed | False positive explosion, valid work blocked, human trust in system erodes | Never -- always scope to at least the files mentioned in the correction |
| Skipping the manual validation set | Faster iteration, no labeling effort | No ground truth, can't measure accuracy, silently degrading quality | Never -- 100-episode validation set is the minimum viable quality gate |
| Storing episodes as untyped JSON blobs | Flexible, no schema migration needed | Can't query efficiently, schema drift across episodes, training pipeline breaks silently | Only for first week of prototyping; switch to typed DuckDB tables immediately |
| Using commit timestamps as episode timestamps | No clock skew calculation needed | Commits can be hours after the actual decision, temporal ordering of episodes is wrong | Never for episode timestamps; acceptable for commit-link validation layer only |

## Integration Gotchas

Common mistakes when connecting system components.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| JSONL session log parsing | Assuming consistent message structure across Claude Code versions | Version-detect the log format; handle missing fields gracefully; store raw message alongside parsed fields |
| Git metadata extraction | Using commit author timestamp (can be rebased/amended) vs. committer timestamp | Use both timestamps; prefer the tool-call timestamp from session logs when a `git commit` tool event exists in provenance |
| DuckDB episode storage | Treating DuckDB as a transactional database (concurrent writes) | DuckDB is single-writer OLAP; use batch inserts; never write from multiple processes simultaneously |
| Mission Control SQLite | Assuming Mission Control's schema is stable | Pin to a specific Mission Control version; create migration scripts; isolate episode tables from MC's core tables |
| Constraint store + validator | Running constraint checks against raw diffs (expensive, slow) | Pre-compute changed file list and diffstat; check constraints against file paths and summary first, then only load full diffs for detected violations |
| OpenClaw Gateway WebSocket | Assuming reliable message delivery and ordering | Implement sequence numbers on events; handle reconnection; buffer events client-side; use at-least-once delivery with deduplication |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full session JSONL into memory for each episode extraction run | Works fine for 10 sessions, OOM or multi-minute processing at 500+ sessions | Streaming parser; process one session at a time; incremental processing (only new sessions) | > 200 sessions or > 500 MB total JSONL |
| Re-scanning all episodes for constraint checks | Fast with 100 episodes, slow at 10,000 | Index episodes by file paths and constraint IDs; only re-check episodes affected by new constraints | > 5,000 episodes |
| Embedding-based episode retrieval with brute-force similarity | Fine for 500 episodes, slow for 10,000+ | Use FAISS or similar ANN index; pre-compute embeddings at insert time | > 5,000 episodes for RAG baseline |
| Full git diff computation for every episode observation | Acceptable for small repos | Cache diff stats per commit; compute incrementally | > 1,000 commits in dataset |
| Running all constraint patterns on every file change | Quick with 10 constraints | Index constraints by path glob; only check relevant constraints per changed file | > 50 active constraints |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing API keys/secrets found in session logs in the episode database | Credential exposure in training data; if episodes are ever shared or used for model training, secrets leak | Redact known secret patterns (API_KEY=, SECRET=, PASSWORD=, Bearer tokens) during JSONL normalization (Stage A); add a post-processing scrub step |
| Constraint store contains examples of "what not to do" that include actual exploit patterns | Training a model on "avoid doing X" inadvertently teaches it X | Store detection_hints as abstract patterns (globs, regex), not as concrete exploit code |
| OpenClaw executing autonomously without sandboxing during graduated autonomy | Agent makes irreversible changes to production repos or systems | Hard-enforce sandbox/worktree isolation at the harness level; never allow direct main-branch writes regardless of policy confidence |
| Session logs capture user passwords or PII typed into Claude Code | Privacy violation; data subject to GDPR/CCPA if shared | Apply PII scrubbing to session logs during normalization; never commit session logs containing identified PII |

## UX Pitfalls

Common user experience mistakes in this domain (the "user" is the human orchestrator reviewing system output).

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing raw episode JSON in review interface | Orchestrator can't quickly assess episode quality; cognitive overload | Summarize each episode as: Mode -> Goal -> Outcome (pass/fail) -> Reaction, with drill-down to raw data |
| Constraint violations shown without context | Orchestrator doesn't understand *why* the constraint exists or whether this violation is a genuine problem | Show the original correction episode that created the constraint alongside the current violation |
| Preference model confidence displayed as a bare number (0.87) | Number is meaningless without calibration context | Show as: "Similar to Episode #52 which you approved" with the confidence as a secondary signal |
| Shadow mode disagreements listed without severity | All disagreements look equally important; orchestrator wastes time on trivial ones | Rank disagreements by: (1) risk level of the decision, (2) magnitude of disagreement, (3) historical accuracy of the policy on similar decisions |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Episode extraction "works":** Often missing provenance links -- verify every episode has non-empty `provenance.sources` pointing to actual log lines and/or commit hashes
- [ ] **Reaction labeling "works":** Often missing confidence calibration -- verify that high-confidence labels (>0.8) are actually correct >80% of the time on the validation set
- [ ] **Constraint extraction "works":** Often missing scope inference -- verify that constraints have specific path scopes, not all repo-wide
- [ ] **Mode inference "works":** Often missing the Triage/Refactor modes entirely -- verify all 7 modes appear in the dataset with reasonable frequency
- [ ] **Preference model "trained":** Often missing calibration -- verify that a predicted 80% approve probability actually corresponds to ~80% approval in held-out data
- [ ] **Shadow mode "tested":** Often tested only on easy/low-risk tasks -- verify testing includes medium and high-risk decisions where the policy is most likely to fail
- [ ] **DuckDB database "populated":** Often missing update_log tracking -- verify incremental processing actually works (re-run and confirm no duplicate episodes)
- [ ] **Validator "catches violations":** Often missing false-positive tracking -- verify the override rate and ensure it's <5%
- [ ] **Mission Control integration "done":** Often missing bidirectional sync -- verify that episode data flows *back* to Mission Control for display, not just *from* it

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Trained wrong policy (executor instead of orchestrator) | HIGH | Must re-extract all episodes with correct action schema; re-validate; re-train. Prevention is far cheaper. |
| Reaction labels are noisy | MEDIUM | Create manual validation set; re-label low-confidence episodes; retrain preference model on cleaned data. Historical labels can be preserved and re-scored. |
| Constraint store has false positives | LOW | Audit constraints against approved episodes; deactivate constraints that flag >10% of approved work; add manual review step. Constraints are individually addressable. |
| Distribution shift in deployed policy | MEDIUM | Revert to shadow mode; collect DAgger-style corrections on the states the policy actually visited; retrain with expanded dataset. |
| Episode segmentation is wrong | HIGH | Must re-segment all sessions. Mitigation: build segmentation rules as configurable parameters (not hardcoded) so re-segmentation is a config change + re-run, not a rewrite. |
| Mode inference below threshold | LOW | Upgrade from keyword rules to LLM classifier. Historical episodes can be re-classified without re-extracting. |
| Provenance tracking gaps | HIGH | Cannot retroactively add provenance. Must re-process from raw logs. This is why provenance must never be skipped. |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Training executor instead of orchestrator | Phase 0.5 (schema) + Phase 1 (episode builder) | Schema validation rejects episodes where orchestrator_action contains tool call signatures; manual review of 20 episodes confirms orchestrator-level actions |
| Decision-point vs. turn confusion | Phase 1 (Stage C segmentation) | Episode density is 3-5x fewer than user messages; every episode has a decision boundary trigger in provenance |
| Approval bias / survivorship bias | Phase 1 (Stage E) + Phase 3 (taxonomy) | Negative examples (correct/block/redirect) are >= 20% of dataset; abandoned sessions are processed |
| Reaction label noise | Phase 1 (Stage E) + Phase 3 (validation) | Manual validation set shows >= 80% accuracy; confidence scores are calibrated |
| Constraint false positives | Phase 2 (constraint extractor + validator) | Constraints have specific path scopes; false positive rate < 5%; backtest against approved episodes |
| Distribution shift at deployment | Phase 4 (shadow mode) + Phase 5 (graduated autonomy) | Shadow mode tested on >= 50 sessions including medium/high-risk; DAgger corrections collected |
| Mode inference accuracy | Phase 1 (Stage D) | >= 85% accuracy on manual validation set; all 7 modes appear in dataset |
| Provenance tracking gaps | Phase 1 (Stage A, normalization) | Every episode has non-empty provenance; source refs point to real log lines |
| Clock skew / temporal ordering | Phase 1 (Stage A, time handling) | Episode timestamps derived from log events, not commit times; clock skew estimate computed |
| Mission Control state sync | Phase 3 (integration) | Bidirectional sync tested; episodes round-trip from MC -> episode store -> MC display |
| Preference model overconfidence | Phase 4 (preference model training) | Calibration curve plotted; Brier score < 0.25; model confidence matches actual approval rate |
| Safety net bypassing | Phase 5 (governing harness) | Harness enforces gates regardless of policy; attempted bypass in test produces E_POLICY_DENIED |

## Sources

- Simchowitz et al. (2025), "Exponential Compounding Error in Continuous-Action Imitation Learning" (arXiv:2503.09722) -- distribution shift and compounding error in imitation learning
- BlueDot Impact (2024), "RLHF Limitations for AI Safety" -- approval bias, sycophancy, feedback scalability
- Lakera (2024), "Reinforcement Learning from Human Feedback" -- reward hacking, human bias in feedback
- UiPath (2025), "Common Challenges Deploying AI Agents" -- multi-agent coordination, observability gaps
- Project design documents: `docs/design/AUTHORITATIVE_DESIGN.md`, `docs/design/WHY_TURN_LEVEL - Improved.md`, `docs/design/The Genus Method - Justification.md`, `docs/design/Mission Control - supervisory control layer.md`
- Project planning: `.planning/PHASE-0-DECISIONS.md`, `.planning/DESIGN_INTEGRATION_REVIEW.md`
- Project risk register: Known risks from design phase (mode inference <85%, reaction label noise, constraint false positives, Mission Control integration complexity)

---
*Pitfalls research for: Episode extraction & policy learning for agentic orchestration*
*Researched: 2026-02-10*
