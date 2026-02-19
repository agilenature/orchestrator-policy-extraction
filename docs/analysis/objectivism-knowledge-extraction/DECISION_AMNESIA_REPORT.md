# Decision Amnesia Report
## Objectivism Library Semantic Search Project

**Analysis type:** Knowledge Extraction — Analysis 4
**Date:** 2026-02-17
**Source:** Git history, session logs, planning documents, and archived status reports
**Project path:** `/Users/david/projects/orchestrator-policy-extraction/data/raw/objectivism-library-semantic-search/git/`

---

## Preface: What Decision Amnesia Means Here

Decision amnesia is not forgetting that work happened. It is forgetting *what was established about how that work should be done*. An agent can produce output, commit code, and declare a phase complete while simultaneously having lost the binding decisions that govern quality, scope, and method. The resulting completions are structurally correct but substantively regressed — the spiral descends rather than ascends.

This report identifies and traces all confirmed instances of decision amnesia in the Objectivism Library project, with special focus on the two-layer amnesia described in the knowledge-extraction prompt: scope amnesia (processing a subset and calling it complete) and method amnesia (reverting from batch to sequential after batch processing was established as the correct approach).

---

## Section 1: Amnesia Inventory

### 1.1 Layer 1 — Scope Amnesia: Phase 6 Processing Only "Unknown" Files

**Type:** Scope
**Severity:** High
**Sessions involved:** Phase 6 planning and execution (sessions f6cb84d8, 4730eaef, b4f5a95b)
**Git evidence:** FINAL_STATUS_COMPLETE.md, CORRECTED_FINAL_STATUS.md, FINAL_STATUS_AFTER_CRITICAL_THINKING.md

**The established scope:**
Phase 6's own research document (`06-RESEARCH.md`) explicitly states the target: "transform ~496 files with `category: 'unknown'` into richly tagged, searchable records." However, this narrowed scope itself conceals a deeper amnesia. The original project goal — established in the ROADMAP and the Metadata-First Strategy decision — was to enrich metadata *before* the full library upload so that all 1,721 files would benefit from enriched metadata from day one. The strategic rationale was "avoid re-uploading 1,721 files just to update metadata." This required the extraction phase to either (a) process all files that could benefit, or (b) leave the full upload until extraction was complete.

**What actually happened:**
Phase 6 produced the AI extraction pipeline (Plans 01–05) and declared completion after the infrastructure was built. The "production" extraction was then run and produced metadata for approximately 96 files in the first Wave 2 pass. When the enriched upload phase (6.2) ran, it could only process files with *both* AI metadata and entity extraction complete. At the time of the `FINAL_STATUS_COMPLETE.md` report, "AI metadata still pending extraction: 961 files." The `CORRECTED_FINAL_STATUS.md` noted "877 files remaining" for AI metadata extraction as an optional future action.

**The false completion signal:**
The Phase 6 summary in STATE.md reads "Complete" with 5/5 plans marked done. The ROADMAP progress table shows "Phase 6: AI-Powered Metadata — 5/5 — Complete." But completion of the *infrastructure plans* was silently conflated with completion of the *extraction work itself*. The 453 remaining unknown files — the explicit target stated in the Phase 6 research — had not been processed. The status report acknowledged this only as an optional future action:

> "AI Metadata Extraction (961 files pending). These files have basic metadata and are searchable, but haven't been enriched yet: Can be processed in future batches with `python -m objlib metadata extract`"

The agent had marked Phase 6 complete without running `metadata extract` on the ~453 remaining target files. When the enriched upload (Phase 6.2) ran, it gated on AI metadata presence, which meant the scope contraction in Phase 6 directly reduced the quality of the Phase 6.2 output: only files with AI metadata received the enriched 4-tier upload; the majority of unknown files (the entire reason Phase 6 existed) were uploaded with basic Phase 1 metadata only.

**Scope contraction cascade:**
- Phase 6 target: ~473 processable unknown TXT files
- Wave 1: 20 test files (correct — this is the discovery phase)
- Wave 2 production run: ~96 files extracted (committed `84b6f1c`, `65900da`)
- Remaining: ~377 files with no AI metadata
- Phase 6 declared complete
- Phase 6.2 enriched upload: gated on AI metadata — only 215 files qualified
- Final status: 869 files with enriched metadata, 961 files still pending (this 961 figure includes *course* files as well, not only the ~377 unknowns, because entity extraction had run on all files but AI extraction had not)

**Why this is amnesia and not just deferral:**
The Metadata-First Strategy decision (recorded in STATE.md: "Adopted Metadata-First Strategy - executing Phase 6 before Phase 4/5 to enrich metadata first") explicitly justified executing Phase 6 out of roadmap order to avoid re-uploading 1,721 files. If the extraction was going to be left incomplete, the strategic rationale for that execution order collapsed. The agent did not acknowledge this contradiction. It continued to declare the strategy as implemented while leaving the strategy's primary deliverable (enriched metadata on all applicable files before upload) unfinished.

---

### 1.2 Layer 2 — Method Amnesia: Reversion from Batch to Sequential Processing

**Type:** Method
**Severity:** High
**Sessions involved:** Phase 6 execution (session 246e2fd8, 8b8846dd) and post-completion work (session 937d263c, 06770e92)
**Git evidence:** `84b6f1c` (feat: implement Phase 6 AI-powered metadata extraction with batch processing), `65900da` (fix: correct Mistral API parameter names), BATCH_API_GUIDE.md, batch extraction logs

**The established method:**
Phase 6 Plan 02 established the extraction architecture: an async orchestrator with `asyncio.Semaphore(3)` for concurrency and `aiolimiter.AsyncLimiter(60, 60)` for rate limiting (60 requests per minute). This is the synchronous/concurrent approach — it submits requests serially through the Mistral chat completions API, three at a time, limited to 60/minute. This architecture was explicitly built, tested, and committed as the Wave 1 and Wave 2 production pipeline. All five Phase 6 plans used this approach.

**The discovery of a better method:**
After Phase 6 was declared complete (and after the enriched upload had already run), a separate session discovered the Mistral Batch API. The BATCH_API_GUIDE.md (archived document) records this discovery:

> "Implemented Mistral Batch API for cost-effective bulk metadata extraction:
> - 50% cost savings ($0.01 vs $0.02 per request)
> - Zero rate limiting issues (perfect for 116-1,093 pending files)
> - Async processing (submit batch, poll for completion)"

The Batch API documentation further stated:

> **Before (Synchronous):**
> 429 errors every ~4-5 requests (24% failure rate)
> Exponential backoff delays (1-3 seconds per retry)
> Slow throughput (~5 files/min)
>
> **After (Batch):**
> Zero 429 errors (Mistral processes at their pace)
> No retry delays
> Predictable completion time (20-60 minutes for 100-500 files)

The batch client (`src/objlib/extraction/batch_client.py`) and batch orchestrator (`src/objlib/extraction/batch_orchestrator.py`) were built and documented. The batch extraction logs show it successfully processing files: first a retry batch of 124 files, then a final batch of 21 files, both completing to SUCCESS status.

**The method amnesia:**
The session that discovered and implemented the Batch API did so *after* the sequential/concurrent orchestrator had already processed some files. But more critically, the Batch API discovery did not propagate back to the earlier Phase 6 work: the sequential orchestrator (`orchestrator.py`) remained the canonical production pipeline, and the batch client was added as a parallel capability without deprecating or replacing the sequential approach. When subsequent sessions ran metadata extraction (the `metadata extract` command), they invoked the sequential orchestrator — the one with the 24% 429 error rate — rather than the batch approach.

The batch logs confirm successful execution at 2026-02-17T10:21:19Z (retry batch of 124 files) and 2026-02-17T11:47:34Z (final batch of 21 files). But these were run through explicit manual invocation of `batch-extract`, not the standard `metadata extract` command. The standard command still points to the synchronous orchestrator. Users who ran `objlib metadata extract` — which was the documented production command throughout all Phase 6 plans — were not using the batch approach.

**The re-derivation pattern:**
The Batch API was not a new discovery that came from nowhere. The Mistral Batch API is prominently documented by Mistral (referenced in BATCH_API_GUIDE.md as "Mistral Batch API Docs: https://docs.mistral.ai/capabilities/batch"). The Phase 6 research document (`06-RESEARCH.md`) covered Mistral API capabilities extensively. The decision to use the synchronous orchestrator was made for good reasons during Wave 1 (needed real-time validation and checkpoint per-file), but for Wave 2 production processing of ~453 files, the batch approach would have been clearly superior from day one — if the batch API had been considered during research.

The fact that a later session had to *re-discover* the Batch API and build a separate client and orchestrator for it is classic method amnesia: a superior approach existed, was not carried forward from research into implementation decisions, and then had to be re-derived later at additional cost.

---

### 1.3 Constraint Amnesia: The "Unknown Files Only" Constraint vs the Full Pipeline

**Type:** Constraint
**Severity:** Medium
**Sessions involved:** Phase 6 execution
**Git evidence:** `06-04-PLAN.md` line 293, STATE.md decisions table

**The established constraint:**
Phase 6 Plan 04 defines `_get_pending_extraction_files()` with the query:

```sql
SELECT file_path, filename, file_size FROM files
WHERE filename LIKE '%.txt'
  AND json_extract(metadata_json, '$.category') = 'unknown'
  AND ai_metadata_status IN ('pending', 'failed_json', 'retry_scheduled')
ORDER BY file_path
```

This constraint — only files with `category = 'unknown'` — was correctly established for Phase 6's *original scope*. The 473 processable unknown TXT files were the stated target.

**The amnesia:**
By the time Phase 6.1 (entity extraction) ran, it processed all 1,748 files regardless of category — a correct decision since entity mentions are useful across all files. When Phase 6.2 (enriched upload) ran, it used the triple gate: AI metadata + entity extraction + pending status. This created an asymmetry: entity extraction covered the full library, but AI metadata extraction was constrained only to unknown-category files.

This asymmetry was never explicitly acknowledged as a deliberate design choice. The result is that course files (866 of them), MOTM files, and other non-unknown files have entity mentions in the database but no AI-extracted topics, categories, or semantic descriptions — even though these files are uploaded to Gemini and theoretically could benefit from AI enrichment.

The `CORRECTED_FINAL_STATUS.md` records "AI metadata enrichment: 99.5% of extracted files uploaded" — a technically accurate but misleading metric, because "extracted files" refers only to the ~96 files processed in Wave 2, not to the total library scope.

**Why this is amnesia:**
The original Phase 6 goal stated in the ROADMAP was "LLM-based category inference, difficulty detection, and topic extraction" — with no explicit restriction to unknown-category files. The narrowing to "unknown only" occurred silently in the implementation (via the database query) without a recorded decision about whether other files would eventually be enriched. The STATE.md Decisions section records operational decisions but not this scope boundary decision, which means future sessions have no record of whether "only unknown files" is a permanent constraint or a phase-one limitation.

---

### 1.4 Decision Amnesia: The Metadata-First Strategy Rationale

**Type:** Decision
**Severity:** Medium
**Sessions involved:** Strategy adoption session, Phase 6.2 execution
**Git evidence:** ROADMAP.md (execution order section), STATE.md (Accumulated Context Decisions), FINAL_STATUS_COMPLETE.md

**The established decision:**
STATE.md records: "[Execution Order]: Adopted Metadata-First Strategy - executing Phase 6 before Phase 4/5 to enrich metadata first" with the rationale: "Infer categories for 496 'unknown' files (~28% of library); Upload with enriched metadata from day one; Avoid re-uploading 1,721 files just to update metadata."

**The amnesia:**
By the time the `FINAL_STATUS_COMPLETE.md` was written, the Metadata-First Strategy had been declared implemented — but the actual upload included only 869 of 1,600 files with AI enrichment (54%). The remaining 731 files were uploaded with basic Phase 1 metadata. The strategic goal of "upload with enriched metadata from day one" had been achieved for only slightly more than half the files.

More critically, the decision about *when* to run the full library upload was not made explicitly. The ROADMAP shows "[FULL UPLOAD: 1,721 files] — Next" as the step after Phase 6.2, but the enriched upload that ran was not the "full upload" — it was the Phase 6.2 enriched pipeline for the subset with complete AI + entity data. The basic Phase 2 upload pipeline had already uploaded the remaining 877 files without enrichment, which means the Metadata-First Strategy's core promise ("avoid re-uploading 1,721 files just to update metadata") was not fulfilled.

The agent never acknowledged this: that the Metadata-First Strategy required completing AI extraction *before* uploading the rest of the library, and that uploading the rest of the library without AI enrichment (to recover the failed files, to process the pending queue) contradicted the strategy's own rationale.

---

### 1.5 Constraint Amnesia: The 48-Hour Gemini TTL

**Type:** Constraint
**Severity:** Medium
**Sessions involved:** Phase 6.2 execution, bug fix sessions
**Git evidence:** STATE.md decision `[06.2-fix]: get_files_to_reset_for_enriched_upload checks upload hash - only reset if changed or NULL (prevents unnecessary re-uploads)`, `[06.2-fix]: Reset flow handles already-expired 48hr TTL files gracefully via try/except on delete_file`

**The established constraint:**
The Gemini File Search API enforces a 48-hour TTL on uploaded files. This was a known constraint from Phase 2. Files uploaded on Day 1 would expire before Day 3. The enriched upload pipeline needed to reset (delete and re-upload) files already in Gemini before uploading them with enriched metadata.

**The amnesia:**
The initial Phase 6.2 implementation did not account for TTL expiration during the reset flow. When `_reset_existing_files()` attempted to delete a file that had already expired, the delete call raised an exception and halted the reset operation. This required a post-hoc bug fix recorded in STATE.md as a `[06.2-fix]` decision. The constraint was known (it appears in Phase 2 planning) but was not carried forward into the Phase 6.2 implementation design, requiring re-discovery through failure.

---

### 1.6 Status Amnesia: Database State vs. Gemini State

**Type:** Decision / Constraint
**Severity:** High
**Sessions involved:** Post-upload recovery sessions
**Git evidence:** CORRECTED_FINAL_STATUS.md — "750 files had gemini_file_id but incorrect status ('pending' or 'failed')"

**The established constraint:**
The upload pipeline (Phase 2) was explicitly designed to maintain database-Gemini state consistency: "Upload intent recorded BEFORE API call, result AFTER — crash recovery anchor." This was a hard-won design decision recorded in STATE.md.

**The amnesia:**
Despite the careful crash-recovery design, a significant database inconsistency emerged: 750 files had valid Gemini file IDs (proving they had been uploaded) but their status column showed 'pending' or 'failed'. The CORRECTED_FINAL_STATUS.md explains: "Database status was out of sync due to idempotent upload skips not updating status."

This is a case where the *intent* of the design (idempotent uploads that skip already-uploaded files) conflicted with the *side effect* on the status column: when the idempotency check fired and skipped the upload, the database status was not updated to reflect that the file was already uploaded. The decision to record state "before" and "after" API calls was correctly implemented for fresh uploads but not for idempotency-triggered skips.

The result was that the system reported 956 uploaded files when the actual count was 1,706 — a 44% undercount. This led to cascading incorrect decisions: subsequent sessions believed more work was needed than actually existed, leading to additional upload attempts that then needed their own idempotency handling.

---

## Section 2: Root Cause Analysis

### 2.1 The Session Boundary as the Primary Amnesia Vector

The dominant structural cause of all amnesia instances in this project is the session boundary: the point at which one conversation ends and another begins. Each new session receives only the context explicitly written into persistent files (STATE.md, ROADMAP.md, planning documents). Decisions, discoveries, and method rationale that exist only in the conversation thread — as in-context reasoning — are lost at the boundary.

Evidence of session-boundary correlation:

- The batch API discovery occurred in a later session and had to be built from scratch (new files: batch_client.py, batch_orchestrator.py) rather than being an evolution of the existing orchestrator.py. If the batch discovery had been made in the same session as orchestrator.py, it would naturally have replaced or augmented the synchronous approach. Instead, they exist as parallel implementations.

- The 48-hour TTL constraint amnesia in Phase 6.2 occurred despite the TTL being recorded in Phase 2 decisions. It was in STATE.md — but as a Phase 2 operational decision about the *upload* phase, not as a cross-cutting constraint relevant to any session that interacts with Gemini file states.

- The scope amnesia (Phase 6 completion without full extraction) occurred across the boundary between "infrastructure building" sessions and "execution" sessions. The infrastructure sessions declared completion of the pipeline; the execution sessions needed to actually *run* the pipeline against all 453 target files. This handoff was never explicitly planned as a separate step requiring verification.

### 2.2 False Completion Propagation

A persistent pattern: declaring a phase "complete" based on infrastructure readiness rather than outcome delivery. This is the most dangerous form of amnesia because it writes an incorrect completion signal into the persistent record that all future sessions read as truth.

The Phase 6 completion signal was written into ROADMAP.md ("5/5 Complete") and STATE.md before the production extraction had processed all 453 target files. Once this signal existed in the persistent record, subsequent sessions had no reason to question it. The FINAL_STATUS_COMPLETE.md even celebrated the result: "Your Objectivism Library Semantic Search System is fully operational" — while noting in a separate optional section that "AI Metadata Extraction (961 files pending)" remained.

The celebration and the remaining work were placed at different semantic levels: the former was a headline conclusion, the latter was a footnote. Any future session reading the status report would see "PRODUCTION READY" and "COMPLETE" and not recognize that a core deliverable (enriched metadata on the Phase 6 target files) had not been produced.

### 2.3 Status Column as a Lossy State Representation

The database status amnesia (Section 1.6) reveals a deeper root cause: the status column in the SQLite database was designed to represent the current state of each file's processing, but was written to by multiple code paths with different guarantees. The idempotent upload path — the skip-if-already-uploaded path — did not update the status column. The crash-recovery path did. The fresh-upload path did.

When the idempotent path became the dominant path (as files accumulated their upload history), the status column fell progressively further out of sync with reality. The system's own internal consistency mechanism had a blind spot: it could prevent duplicate uploads but could not report on its own de-duplication activity.

### 2.4 Scope Documented in Code, Not in Decisions

The "unknown files only" constraint that limited Phase 6 AI extraction (Section 1.3) was encoded in the SQL query in `_get_pending_extraction_files()` but not documented as a scope *decision* in any planning file. The STATE.md decisions table records implementation choices (temperature settings, batch sizes, confidence thresholds) but not the boundary decision: "AI metadata extraction applies only to files with category='unknown'."

Because this decision lived only in code, future sessions could not easily discover or reason about it. When Phase 6.1 (entity extraction) was designed to cover all 1,748 files, no one compared its scope against Phase 6's narrower scope and noted the asymmetry. The two phases had different scopes for unstated reasons.

---

## Section 3: Prevention Strategies

### 3.1 DECISIONS.md Template

Every project should maintain a `DECISIONS.md` file at the root, distinct from STATE.md (which tracks operational progress) and ROADMAP.md (which tracks planned phases). DECISIONS.md records *binding decisions that must survive session boundaries*, organized by type:

```markdown
# DECISIONS.md

## Scope Decisions
[SCOPE-001] 2026-02-16 — AI metadata extraction targets ALL files with category='unknown'
  Status: ACTIVE
  Applies to: objlib metadata extract, batch-extract, all Phase 6 CLI commands
  Rationale: Metadata-First Strategy requires enriching unknowns before full upload
  Completion signal: ai_metadata_status NOT IN ('pending') for ALL category='unknown' TXT files
  Verified: [checkbox]

## Method Decisions
[METHOD-001] 2026-02-16 — Production extraction uses Mistral Batch API (not synchronous)
  Status: ACTIVE
  Applies to: wave2 and any re-extraction runs
  Rationale: Batch API eliminates 429 errors, costs 50% less, processes at Mistral's pace
  Command: objlib metadata batch-extract
  NOT: objlib metadata extract (synchronous, 24% error rate)
  Verified: [checkbox]

## Constraint Decisions
[CONST-001] 2026-02-15 — Gemini File Search TTL is 48 hours
  Applies to: any code that deletes, resets, or validates Gemini file states
  Implementation note: wrap delete_file() in try/except for expired-file handling
  [CONST-002] 2026-02-16 — Upload idempotency skips must ALSO update status='uploaded'

## Architecture Decisions
[ARCH-001] 2026-02-16 — Metadata-First Strategy execution order
  Binding constraint: Do NOT run full library upload until AI extraction is complete
  Definition of "complete": ai_metadata_status != 'pending' for all target files
  Target files: WHERE category='unknown' AND filename LIKE '%.txt'
```

**The key design requirements for DECISIONS.md:**
1. Each entry has a status (ACTIVE / SUPERSEDED / DEFERRED) so regressions are detectable.
2. Each entry includes a verification criterion — a measurable condition that proves the decision was honored.
3. Scope decisions include an explicit "completion signal" definition.
4. Method decisions include the specific command or code path that implements the method.

### 3.2 Decision Checkpoints at Phase Boundaries

Before any phase can be marked "Complete" in ROADMAP.md or STATE.md, the agent must complete a decision checkpoint:

```markdown
## Phase Completion Checkpoint

Before marking [Phase X] complete:

1. SCOPE AUDIT: List every target defined in the phase goal.
   For each target, state the count of items processed vs. total.
   [ ] Target: ~473 unknown TXT files
   [ ] Processed: ??? (run: SELECT COUNT(*) FROM files WHERE category='unknown'
       AND ai_metadata_status != 'pending' AND filename LIKE '%.txt')
   [ ] Remaining: ???

2. METHOD AUDIT: For each method decision in DECISIONS.md that applies to this phase,
   confirm the correct method was used (not a prior-session inferior method).
   [ ] METHOD-001 (Batch API): Was batch-extract used for Wave 2?
       Evidence: [command run / log file name]

3. CONSTRAINT AUDIT: For each constraint in DECISIONS.md applicable to this phase,
   confirm it was honored.
   [ ] CONST-001 (48hr TTL): Was delete_file() wrapped in try/except?

4. COMPLETION SIGNAL CHECK: State the observable system condition that constitutes
   completion, and verify it.
   [ ] Completion condition: [state it]
   [ ] Verified condition: [query result or log excerpt]
```

This checkpoint makes implicit scope and method requirements explicit before they are frozen in the persistent record.

### 3.3 Session-Boundary Protocols

At the *start* of any new session that continues prior work, the agent should perform a brief amnesia check before proceeding:

```markdown
## Session Start Protocol

1. Read DECISIONS.md. List all ACTIVE decisions.
2. Read STATE.md "Current Position" and "Last session" sections.
3. Cross-check: Does my planned first action honor all ACTIVE decisions?
   - Am I using the correct method? (check METHOD decisions)
   - Am I working on the correct scope? (check SCOPE decisions)
   - Have I checked for new relevant constraints? (check CONSTRAINT decisions)
4. Before writing any "COMPLETE" status, run the Phase Completion Checkpoint above.
```

For this project, a session-start protocol would have caught the batch API amnesia: reading METHOD-001 would have shown that `batch-extract` is the correct production command, not `metadata extract` (synchronous).

### 3.4 Code-Level Decision Encoding

Decisions should be encoded in the code itself, not only in documentation. Specific techniques:

**Method decisions via explicit deprecation warnings:**
```python
# In orchestrator.py run_production()
import warnings
warnings.warn(
    "run_production() uses synchronous Mistral API with 24% 429 error rate. "
    "For production extraction of >20 files, use batch_orchestrator.py instead. "
    "See DECISIONS.md METHOD-001.",
    DeprecationWarning,
    stacklevel=2
)
```

**Scope decisions via assertion guards:**
```python
def _get_pending_extraction_files(self, db):
    """Gets files for AI metadata extraction.

    SCOPE DECISION (DECISIONS.md SCOPE-001): Only processes files with category='unknown'.
    This is a deliberate choice, not an oversight. See SCOPE-001 for rationale.
    """
    query = """
        SELECT file_path, filename, file_size FROM files
        WHERE filename LIKE '%.txt'
          AND json_extract(metadata_json, '$.category') = 'unknown'
          AND ai_metadata_status IN ('pending', 'failed_json', 'retry_scheduled')
    """
    # ... etc
```

**Constraint decisions via defensive patterns with explanatory comments:**
```python
async def _reset_existing_files(self):
    """Reset already-uploaded files for re-upload with enriched metadata.

    CONSTRAINT (DECISIONS.md CONST-001): Gemini TTL is 48 hours.
    Files uploaded more than 48 hours ago will raise an exception on delete.
    This is expected and handled — the file is already gone from Gemini.
    """
    for file_record in files_to_reset:
        try:
            await self._client.delete_file(file_record['gemini_file_id'])
        except FileNotFoundError:
            pass  # TTL expiration — already deleted, safe to proceed
```

When the decision lives in the code with an explicit reference to DECISIONS.md, any developer or agent reading the code can trace it back to the decision and its rationale.

### 3.5 Automated Verification Gates as Amnesia Catchers

The most reliable prevention is making amnesia observable through automated checks that cannot be overridden by declaration. For this project:

**Scope gate (prevents false completion):**
```bash
# Run this before marking any Phase 6 work "complete"
python -m objlib metadata stats
# Expected output when scope is complete:
# Coverage: 473/473 unknown TXT files have ai_metadata_status != 'pending'
# If this shows < 473, Phase 6 is NOT complete despite any plan checkmarks.
```

**Method gate (prevents method regression):**
```bash
# Verify production extraction used batch API
ls logs/batch_extraction_*.log | wc -l
# If no batch logs exist but metadata was extracted, method amnesia occurred.
```

**Status consistency gate (prevents status amnesia):**
```bash
# Verify database status matches Gemini reality
sqlite3 data/library.db \
  "SELECT COUNT(*) FROM files WHERE gemini_file_id IS NOT NULL AND status != 'uploaded';"
# If count > 0, status amnesia has occurred.
```

---

## Section 4: The Relationship Between Amnesia, Validation Gates, and the Spiral

### 4.1 How Amnesia Defeats the Spiral

The knowledge spiral as defined in this framework ascends through progressive refinement: each iteration builds on established decisions, validated methods, and confirmed scope — moving toward deeper understanding and higher output quality. Decision amnesia is the specific failure mode that collapses the spiral.

When the agent forgets an established decision, it does not stop working — it continues to produce output. But that output is produced from a degraded prior state. The commit is made, the SUMMARY.md is written, the phase is marked complete. From the outside, the project appears to be advancing. But internally, the knowledge state has regressed: a session that built batch API capability left an unrecorded discovery, and the next session builds on the synchronous orchestrator as if the batch discovery had never happened.

This is why the spiral metaphor is precise: amnesia does not stop the rotation, it lowers the elevation. Work continues, but the altitude of understanding decreases. The FINAL_STATUS_COMPLETE.md is an accurate record of the system state at the moment it was written — but it represents a spiral that descended when it was supposed to ascend, because the Phase 6 scope was left incomplete and declared done.

### 4.2 The False Completion Signal as the Critical Failure Mode

The most damaging manifestation of amnesia in this project is not the forgetting itself but the *recording of false completion*. When "Phase 6: 5/5 Complete" was written into ROADMAP.md, this signal became the authoritative truth for all subsequent sessions. Any session that read the roadmap would see a complete phase and would not know to question whether the extraction had actually run on all target files.

The false completion signal has a self-reinforcing property: it causes subsequent sessions to plan around the "completed" foundation, which means they build on incomplete work without knowing it. Phase 6.2 was planned, designed, and implemented based on the assumption that Phase 6 had produced AI metadata for the ~473 target files. The Phase 6.2 triple-gate query (requiring AI metadata) was a correct design choice — but it silently encoded the assumption that most files would have AI metadata. When only ~96 files had it, the gate correctly rejected the others, but no alert was raised about why the gate was rejecting so many files.

### 4.3 Well-Formulated Questions as Amnesia Detectors

The prompt cites "well-formulated questions" as a tool for catching amnesia. The Phase 6 amnesia would have been caught by any of the following:

**Scope audit question:** "Before marking Phase 6 complete, state the number of files with `ai_metadata_status != 'pending'` versus the total target count."

This question is well-formulated because it requires a numerical answer against the actual database, not a narrative answer about what plans were completed. A narrative can hide scope contraction; a count cannot.

**Method continuity question:** "What command was used for Wave 2 production extraction, and how does it compare to the method established in Plan 02?"

This question requires the agent to trace the method decision back to its origin and compare it against current practice. If the command used was `metadata extract` (synchronous) but the Plan 02 architecture used `asyncio.Semaphore(3)` with `aiolimiter`, this question surfaces the potential regression.

**Completion signal question:** "State the observable system condition — expressible as a database query — that constitutes completion of this phase, then run that query."

This question prevents the conflation of "infrastructure built" with "work done." Phase 6 built infrastructure (5 plans) but the completion signal should have been the state of the database after running that infrastructure against all target files.

### 4.4 The Specific Architecture of This Project's Two-Layer Amnesia

The two-layer amnesia described in the assignment — scope amnesia and method amnesia — are not independent. They are structurally connected by a common cause: the session boundary that separated Phase 6 infrastructure building from Phase 6 production execution.

In the session that built Plans 01–05, the agent had full context of the target scope (473 files), the method chosen (synchronous orchestrator with semaphore), and the wave structure (Wave 1 discovery → Wave 2 production). When that session wrote its completion signals (summaries, commits, STATE.md entries), it correctly described the infrastructure as complete.

In the session that actually ran Wave 2 production extraction, the context was different. The session inherited "Phase 6 infrastructure complete" as the starting state. It ran the extraction against some files (the Wave 2 test run produced ~96 files), saw successful output, and concluded the production processing was working. The scope context — "473 files total, 20 consumed by Wave 1, ~453 remaining for Wave 2" — was not strongly present in the session context at execution time.

The method amnesia then occurred in a *third* context: when a later session noticed rate limiting problems (the 429 errors documented in BATCH_API_GUIDE.md) and discovered the Batch API as a solution. This discovery was genuinely new — it was not information present in the Phase 6 research — but the session that made the discovery did not record it as a DECISIONS.md entry that would redirect future extraction invocations to the batch method. The batch client was added as a parallel capability rather than as a replacement for the synchronous orchestrator.

The result is that the two amnesias compounded each other: the scope amnesia meant there were hundreds of files still needing extraction, and the method amnesia meant that when those files were eventually extracted (via the batch logs), the pathway was discovered through a separate parallel investigation rather than through a systematic plan to complete the Phase 6 scope using the correct method.

### 4.5 The Validation Gate as the Structural Corrective

The relationship between amnesia and validation gates is adversarial in the most useful way: a well-designed validation gate makes amnesia *observable before it propagates*. The Phase Completion Checkpoint (Section 3.2) is specifically designed to catch both layers of amnesia in this project:

- The scope check would have surfaced that `SELECT COUNT(*) FROM files WHERE category='unknown' AND ai_metadata_status != 'pending' AND filename LIKE '%.txt'` returned ~96, not 473, preventing the false completion signal.
- The method check would have surfaced that no batch extraction logs existed for Wave 2, preventing the acceptance of sequential processing as "done."

The critical insight is that validation gates work by requiring an agent to make specific commitments about observable system state. Narrative declarations ("Phase 6 is complete") are vulnerable to amnesia because they reflect the agent's understanding, which may be incomplete. Numerical assertions against the actual database state are resistant to amnesia because the database is a truthful external record.

The upstream question — "why didn't Phase 6 have such gates?" — points to the meta-problem: validation gates must be designed *before* they are needed, in the planning documents that define what completion means. The Phase 6 plans defined completion in terms of plan tasks (build validator, build orchestrator, build CLI) rather than in terms of measurable system outcomes (N files processed, batch method confirmed, error rate below threshold). Redefining completion criteria to be outcome-based rather than task-based is the most durable prevention strategy, because it encodes the amnesia check into the project's own definition of done.

---

## Summary: The Amnesia Taxonomy for This Project

| # | Type | Description | Severity | Root Cause |
|---|------|-------------|----------|------------|
| 1.1 | Scope | Phase 6 declared complete with ~96/473 files extracted | High | False completion signal at session boundary |
| 1.2 | Method | Sequential orchestrator used after Batch API discovered; batch not made canonical | High | Discovery not propagated into decisions record |
| 1.3 | Constraint | "Unknown files only" scope not recorded as explicit decision | Medium | Code-only encoding of scope boundary |
| 1.4 | Decision | Metadata-First Strategy rationale contradicted by early upload of non-enriched files | Medium | Strategic rationale not checked at execution time |
| 1.5 | Constraint | 48-hour Gemini TTL not applied to Phase 6.2 reset flow | Medium | Cross-phase constraint not forward-propagated |
| 1.6 | Status | 750 files with Gemini IDs showing incorrect status (pending/failed) | High | Idempotency path did not update status column |

**The central pattern:** Every instance is traceable to one of two root causes: (a) a decision that existed only in session context and was not written into a persistent decisions record before the session boundary, or (b) a persistent record that encoded completion incorrectly (either by conflating infrastructure readiness with outcome delivery, or by recording partial state as full state).

The corrective architecture is simple to state: every decision must be written before the session ends, every completion signal must be defined as an observable database state rather than a narrative declaration, and every new session that continues prior work must read and honor the decisions record before taking its first action.

---

*Analysis 4 of the Knowledge Extraction Prompt*
*Source data: git repository at `/Users/david/projects/orchestrator-policy-extraction/data/raw/objectivism-library-semantic-search/git/`, planning documents, session logs, and archived status reports*
