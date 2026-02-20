# Objectivism Library Project Pre-Mortem

## Failure Stories

### Story 1: pybreaker for Circuit Breaker
We tried using pybreaker 1.4.1 for the upload pipeline circuit breaker. The library tracks consecutive failures via a state machine (fail_max), but the requirement was percentage-based rate degradation over a rolling window (5% 429 rate over 100 requests). Resolution was a hand-rolled circuit breaker using collections.deque(maxlen=100) with a three-state machine: CLOSED, OPEN at 5% threshold, and HALF_OPEN after 5-minute cooldown.

### Story 2: Single-Step Upload Assumption
The planning documents assumed upload_to_file_search_store() could attach custom_metadata in a single call. The SDK method does not expose custom_metadata in its config parameter in google-genai v1.63.0. The resolution was a two-step pattern: files.upload() to get the raw file object, wait for ACTIVE state, then file_search_stores.import_file() with custom_metadata containing string_list_value wrappers.

### Story 3: Mistral SDK Import Path
Research documentation suggested using from mistralai.client import MistralClient, which is the pre-1.0 SDK import path. The Mistral SDK v1.0+ changed the import to from mistralai import Mistral. This caused immediate ImportError on first execution. The fix was straightforward once the correct v1.0+ import was identified, but cost an unnecessary debugging cycle.

### Story 4: Using request_options in Gemini Search
An attempt was made to add request_options to GenerateContentConfig for search calls to control timeouts. The parameter does not exist in the SDK GenerateContentConfig and caused an immediate runtime error. The SDK handles timeouts at the client level, not in per-request configuration. The invalid parameter was simply removed.

### Story 5: Sync sqlite3 in Async Upload Pipeline
Using synchronous sqlite3 calls within the async upload orchestrator was considered for simplicity. SQLite has a single-writer constraint, and sync writes would block the event loop, degrading concurrency to sequential execution. The resolution was using aiosqlite throughout the async pipeline with a critical rule: commit state writes immediately and never hold transactions open across await boundaries.

### Story 6: JSON Mode and Magistral Thinking Blocks Conflict
The assumption was that response_format={"type": "json_object"} would produce a plain JSON string in response.content. With magistral-medium-latest, thinking blocks appear even in JSON mode, and the content field is always an array of objects, not a string. A two-phase parser was required: first filter for TextChunk objects with type='text', then parse the combined text as JSON, with regex extraction as a last-resort fallback.

### Story 7: Phase 6 Processing Only Unknown Files
Phase 6 AI metadata extraction was declared complete after building the infrastructure (5 plans) even though only approximately 96 of the target 473 unknown-category files had been processed. The false completion signal in STATE.md caused subsequent phases to build on incomplete work. The Metadata-First Strategy rationale collapsed because the majority of files were uploaded without enriched metadata, contradicting the entire reason for executing Phase 6 before the full library upload.

### Story 8: Reversion from Batch to Sequential Processing
After Phase 6 infrastructure was built using a synchronous orchestrator with asyncio.Semaphore(3), a later session discovered the Mistral Batch API which eliminated 429 errors and reduced costs by 50%. However, the batch client was added as a parallel implementation rather than replacing the synchronous orchestrator. Subsequent sessions running the standard metadata extract command continued using the inferior synchronous method with its 24% 429 error rate.

### Story 9: Unknown Files Only Constraint vs Full Pipeline
The constraint limiting AI metadata extraction to files with category='unknown' was encoded in a SQL query but never recorded as an explicit scope decision. Entity extraction (Phase 6.1) correctly processed all 1,748 files, creating an asymmetry where files had entity mentions but no AI-extracted topics or semantic descriptions. The scope boundary decision lived only in code, making it invisible to future sessions.

### Story 10: Metadata-First Strategy Rationale Lost
The Metadata-First Strategy justified executing Phase 6 before Phases 4 and 5 to avoid re-uploading 1,721 files just to update metadata. By completion, only 54% of files had AI enrichment. The remaining 731 files were uploaded with basic Phase 1 metadata, which meant the strategic rationale for the out-of-order execution had been contradicted without acknowledgment. The agent never recognized that uploading non-enriched files undermined the strategy's core promise.

### Story 11: 48-Hour Gemini TTL Forgotten
The Gemini File Search API enforces a 48-hour TTL on uploaded files, a constraint known from Phase 2. When Phase 6.2 attempted to reset existing files by deleting and re-uploading them with enriched metadata, the delete call raised exceptions for already-expired files and halted the reset operation. The constraint was present in Phase 2 decisions but was not carried forward into the Phase 6.2 implementation, requiring re-discovery through failure and a post-hoc bug fix.

## Key Assumptions

- Actual scan result counts must be verified by machine-checkable queries against the production database, not by unit tests on synthetic fixtures
- File counts after upload must be enforced programmatically by comparing database status columns against expected totals
- Full upload completion must be gated before proceeding to any dependent phase that queries the uploaded corpus
- Extraction scope must be machine-verified by running count queries before and after each batch processing run
- Agent self-imposed count gates must not accept partial results as complete when the target count is explicitly defined
- Uploaded status must be verified against remote store state to detect idempotency-induced status column drift
- Failed operations must never be accepted as terminal without automated retry across at least two distinct retry windows
- Edge case failures must never be classified as permanent without individual investigation of each failing item
- Uncertain state operations must not proceed without explicit resolution through a status consistency gate
- Scope decisions must be recorded in a machine-readable DECISIONS.md format with explicit completion signal definitions
- Method decisions must include the specific command or code path that implements the chosen method and deprecation warnings on superseded approaches
- Constraint violations must never be silently overridden without recording the override and its justification in an audit trail
- Database state changes must be verified against external service state using post-run consistency queries
- Prior session decisions must be loaded and cross-checked at session start before any continuation work begins
- TTL and expiry constraints must never rely on human memory but must be enforced by automated checks with defensive exception handling
