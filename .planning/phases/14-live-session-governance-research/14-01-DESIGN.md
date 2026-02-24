# Phase 14 Plan 01: Single-Session Governance Layer Design

**Phase:** 14 (Live Session Governance Research)
**Plan:** 01
**Components:** LIVE-01 (PreToolUse Hook), LIVE-02 (SessionStart Hook), LIVE-03 (JSONL Stream Processor)
**Status:** Design specification (no implementation code)
**Date:** 2026-02-23

---

## 1. Hook Contracts and Data Models

### 1.1 PreToolUse Hook Contract (LIVE-01)

#### Purpose

A synchronous hook invoked by Claude Code before every state-changing tool call. The hook checks the proposed tool call against active constraints and returns allow, warn, or deny. It operates within a single session with no multi-session coordination required.

#### Hook Input JSON Schema (stdin)

The hook receives a JSON object on stdin from Claude Code. This is the formalized schema based on the verified protocol from 14-RESEARCH.md.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "ope://schemas/pretooluse-hook-input.json",
  "title": "PreToolUseHookInput",
  "description": "JSON object delivered to PreToolUse hook on stdin by Claude Code",
  "type": "object",
  "required": ["session_id", "cwd", "hook_event_name", "tool_name", "tool_input"],
  "properties": {
    "session_id": {
      "type": "string",
      "description": "UUID of the current Claude Code session"
    },
    "transcript_path": {
      "type": "string",
      "description": "Absolute path to the session's JSONL transcript file"
    },
    "cwd": {
      "type": "string",
      "description": "Current working directory of the Claude Code session"
    },
    "permission_mode": {
      "type": "string",
      "enum": ["default", "plan", "bypassPermissions"],
      "description": "Current permission mode of the session"
    },
    "hook_event_name": {
      "type": "string",
      "const": "PreToolUse",
      "description": "Always 'PreToolUse' for this hook type"
    },
    "tool_name": {
      "type": "string",
      "description": "Name of the tool about to be called (Bash, Write, Edit, Read, Glob, Grep, etc.)"
    },
    "tool_input": {
      "type": "object",
      "description": "The complete input object for the tool call. Structure varies by tool_name.",
      "additionalProperties": true
    },
    "tool_use_id": {
      "type": "string",
      "description": "Unique ID for this specific tool use (toolu_... format)"
    }
  }
}
```

#### Hook Output JSON Schemas

**Variant A: Deny (block tool call)**

Exit code: 0. Stdout contains deny JSON. Claude Code prevents the tool call and shows the reason to the user.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "ope://schemas/pretooluse-output-deny.json",
  "title": "PreToolUseOutputDeny",
  "description": "Output that blocks a tool call with a reason",
  "type": "object",
  "required": ["hookSpecificOutput"],
  "properties": {
    "hookSpecificOutput": {
      "type": "object",
      "required": ["hookEventName", "permissionDecision", "permissionDecisionReason"],
      "properties": {
        "hookEventName": {
          "type": "string",
          "const": "PreToolUse"
        },
        "permissionDecision": {
          "type": "string",
          "const": "deny"
        },
        "permissionDecisionReason": {
          "type": "string",
          "description": "Human-readable reason for blocking. Shown to Claude and the user."
        }
      }
    }
  }
}
```

Example deny output:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "GOVERNANCE: Blocked by constraint bbd376a2 (forbidden): Do not modify schema without explicit approval. [ccd_axis: destructive_irreversible_operations]"
  }
}
```

**Variant B: Allow with warning context**

Exit code: 0. Stdout contains warning context JSON. Claude Code proceeds with the tool call but injects the warning into Claude's context.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "ope://schemas/pretooluse-output-warn.json",
  "title": "PreToolUseOutputWarn",
  "description": "Output that allows a tool call but injects governance warning into context",
  "type": "object",
  "required": ["hookSpecificOutput"],
  "properties": {
    "hookSpecificOutput": {
      "type": "object",
      "required": ["hookEventName", "additionalContext"],
      "properties": {
        "hookEventName": {
          "type": "string",
          "const": "PreToolUse"
        },
        "additionalContext": {
          "type": "string",
          "description": "Governance warning injected into Claude's context. Should be concise."
        }
      }
    }
  }
}
```

Example warn output:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "GOVERNANCE WARNING: Constraint e5f6g7h8 (warning): Always run tests after code changes. [ccd_axis: verification_before_commit]"
  }
}
```

**Variant C: Silent allow**

Exit code: 0. No stdout output (empty). Claude Code proceeds normally. This is the common path (most tool calls match no constraints).

```
# No JSON output. Process exits with code 0.
# Claude Code interprets this as: allow, no additional context.
```

#### Decision Logic

The PreToolUse hook follows this decision sequence:

```
HOOK INVOKED (stdin JSON arrives)
    |
    v
[1] Parse stdin JSON -> HookInput model
    |  FAIL -> stderr log, exit 0 (fail-open)
    v
[2] Extract tool_name from HookInput
    |
    v
[3] Extract searchable text from tool_input (see Text Extraction below)
    |  EMPTY text -> exit 0 (nothing to check)
    v
[4] Load constraints:
    |  TRY: HTTP POST to bus /api/check (if bus socket exists)
    |  FAIL: Load ConstraintStore from data/constraints.json directly
    |  FAIL: exit 0, log warning to stderr (fail-open)
    v
[5] Run PolicyViolationChecker.check(search_text)
    |
    +---> (True, constraint)  -> severity is forbidden/requires_approval
    |         -> Output Variant A (deny), exit 0
    |
    +---> (False, constraint) -> severity is warning
    |         -> Output Variant B (warn), exit 0
    |
    +---> (False, None)       -> no constraint matched
              -> Output Variant C (silent allow), exit 0
```

Decision table:

| PolicyViolationChecker Result | Constraint Severity | Hook Output | Exit Code |
|-------------------------------|-------------------|-------------|-----------|
| `(True, constraint)` | `forbidden` | Deny JSON | 0 |
| `(True, constraint)` | `requires_approval` | Deny JSON | 0 |
| `(False, constraint)` | `warning` | Warn JSON | 0 |
| `(False, None)` | N/A | No output | 0 |
| Parse/load error | N/A | No output | 0 |

#### Text Extraction Strategy

Text is extracted from `tool_input` based on `tool_name`. The goal is to build a string that PolicyViolationChecker can match against detection_hints.

| tool_name | Fields Extracted | Truncation | Rationale |
|-----------|-----------------|------------|-----------|
| `Bash` | `tool_input.command` | First 500 chars | Commands are the primary constraint surface; 500 chars captures the full command in >99% of cases while bounding memory |
| `Write` | `tool_input.file_path` + `tool_input.content` | file_path: none; content: first 500 chars | file_path is a scope signal; content is where forbidden patterns appear but can be very large (full files) |
| `Edit` | `tool_input.file_path` + `tool_input.old_string` + `tool_input.new_string` | file_path: none; each string: first 500 chars | Both old and new strings matter (the change and its target) |
| `Read` | `tool_input.file_path` | None | Read is low-risk; file_path is sufficient for scope-based constraints |
| `Glob` | `tool_input.pattern` + `tool_input.path` | None | Pattern + path are small strings; used for scope-based constraints |
| `Grep` | `tool_input.pattern` + `tool_input.path` | None | Same as Glob |
| Other | `str(tool_input)` | First 500 chars | Fallback for unknown tools; serialized dict provides some matching surface |

**Why 500 chars:** The PolicyViolationChecker uses `re.escape(hint)` patterns that match substring positions. Detection hints are typically short (10-50 chars). Truncating content at 500 chars captures the meaningful prefix of any file content while preventing large payloads (e.g., a 50KB Write content) from consuming processing time in regex matching. The 500-char limit is applied after extraction, before the check call.

**Concatenation:** Extracted fields are joined with a single space: `" ".join(text_parts)`. This produces a single string that PolicyViolationChecker.check() scans against all detection_hint patterns.

#### Fallback Behavior

| Failure | Behavior | Rationale |
|---------|----------|-----------|
| Bus unreachable (socket missing or connection refused) | Fall back to direct file load: `ConstraintStore(path=Path("data/constraints.json"))` | Standalone-first design; bus is an optimization, not a requirement |
| `data/constraints.json` missing or unparseable | Allow all (exit 0), log warning to stderr: `"[OPE] constraints.json not found, governance disabled"` | Fail-open: governance cannot block work when constraints are unavailable |
| Python import fails (missing module, syntax error) | Exit 0, error to stderr | Fail-open: a broken governance script must not block tool execution |
| Hook exceeds timeout (5s) | Killed by Claude Code; tool proceeds as if hook returned allow | Claude Code enforces the timeout externally; no hook-side handling needed |
| stdin JSON parse failure | Exit 0, log parse error to stderr | Fail-open: malformed input should not block |
| PolicyViolationChecker raises exception | Catch at top level, exit 0, log to stderr | Fail-open: checker bugs must not block work |

**Fail-open principle:** Every failure mode results in "allow." The governance hook is advisory infrastructure, not a security boundary. Blocking legitimate work due to a governance bug is worse than missing a constraint violation (which the JSONL stream processor will catch post-hoc).

#### Error Handling

- **stdout:** Reserved exclusively for hook output JSON. No log messages, no Python warnings, no print statements.
- **stderr:** All error and diagnostic output goes here. Claude Code captures stderr for `exit 2` (blocking error) but ignores it for `exit 0`.
- **Exit code 0:** Success (allow, warn, or deny -- all are "successful" hook executions).
- **Exit code 2:** Blocking error -- Claude Code feeds stderr to Claude. Reserved for situations where the hook itself has a critical failure that should be surfaced to the user (not used for governance decisions).
- **Environment:** Set `PYTHONDONTWRITEBYTECODE=1` in the hook command to prevent `.pyc` warnings. Suppress loguru default stdout sink.

#### Hook Configuration

Project-level `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit|Read|Glob|Grep",
        "hooks": [
          {
            "type": "command",
            "command": "PYTHONDONTWRITEBYTECODE=1 python3 \"$CLAUDE_PROJECT_DIR/src/pipeline/live/hooks/governance_check.py\"",
            "timeout": 5,
            "statusMessage": "Checking governance constraints..."
          }
        ]
      }
    ]
  }
}
```

**Matcher:** `Bash|Write|Edit|Read|Glob|Grep` covers all tool types that interact with the filesystem. Read/Glob/Grep are included for scope-based constraint checking (e.g., "do not read files in /secrets/") even though they are non-destructive.

**Timeout:** 5 seconds. The target latency is <200ms. 5s provides a generous margin for slow disk I/O or bus connectivity issues without blocking indefinitely.

**statusMessage:** Displayed to the user while the hook runs. Provides visibility that governance checking is active.

#### Latency Budget (LIVE-01)

| Component | Estimated Latency | Notes |
|-----------|------------------|-------|
| Shell spawn + Python startup | 50-80ms | Python 3.13, minimal imports (json, sys, pathlib) |
| stdin JSON parse | <1ms | Small payload (~500 bytes) |
| ConstraintStore load (JSON file) | 10-20ms | 419 constraints, ~200KB |
| PolicyViolationChecker init (regex compile) | 5-10ms | ~332 active constraints with hints |
| PolicyViolationChecker.check() | <1ms | Pre-compiled regex matching |
| stdout JSON serialize | <1ms | Small response |
| **Total (direct file mode)** | **~70-115ms** | **Within 200ms budget** |

With bus (if running):

| Component | Estimated Latency | Notes |
|-----------|------------------|-------|
| Shell spawn + Python startup | 50-80ms | Minimal imports (json, sys, httpx) |
| httpx Unix socket POST | 1-5ms | Local IPC, no network |
| Bus constraint check (in-memory) | <1ms | Pre-loaded, pre-compiled |
| **Total (bus mode)** | **~55-90ms** | **Well within budget** |

---

### 1.2 SessionStart Hook Contract (LIVE-02)

#### Purpose

A hook invoked by Claude Code at session startup and resume. It loads active constraints, filters by project scope, ranks by durability and severity, and injects a structured briefing into Claude's context via `additionalContext`. This is the primary mechanism by which Claude "knows" what constraints are in force for the current project.

#### Hook Input JSON Schema (stdin)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "ope://schemas/sessionstart-hook-input.json",
  "title": "SessionStartHookInput",
  "description": "JSON object delivered to SessionStart hook on stdin by Claude Code",
  "type": "object",
  "required": ["session_id", "cwd", "hook_event_name"],
  "properties": {
    "session_id": {
      "type": "string",
      "description": "UUID of the new Claude Code session"
    },
    "transcript_path": {
      "type": "string",
      "description": "Absolute path to the session's JSONL transcript file"
    },
    "cwd": {
      "type": "string",
      "description": "Current working directory of the Claude Code session"
    },
    "permission_mode": {
      "type": "string",
      "enum": ["default", "plan", "bypassPermissions"],
      "description": "Current permission mode of the session"
    },
    "hook_event_name": {
      "type": "string",
      "const": "SessionStart",
      "description": "Always 'SessionStart' for this hook type"
    }
  }
}
```

Note: SessionStart input does NOT include `tool_name`, `tool_input`, or `tool_use_id` (those are PreToolUse-specific).

#### Hook Output JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "ope://schemas/sessionstart-output.json",
  "title": "SessionStartOutput",
  "description": "Output that injects governance briefing into Claude's context",
  "type": "object",
  "required": ["hookSpecificOutput"],
  "properties": {
    "hookSpecificOutput": {
      "type": "object",
      "required": ["hookEventName", "additionalContext"],
      "properties": {
        "hookEventName": {
          "type": "string",
          "const": "SessionStart"
        },
        "additionalContext": {
          "type": "string",
          "description": "Governance briefing text injected into Claude's context. Contains constraint summary grouped by CCD axis."
        }
      }
    }
  }
}
```

#### Briefing Content Specification

The briefing is a structured text string with four sections. It follows the CCD Architecture Decision (section 1.4): constraints are grouped by axis, not listed as flat concretes.

**Section layout:**

```
GOVERNANCE BRIEFING: {total_scoped} constraints active for {project_name}
==========================================================================

CRITICAL ({critical_count} axes):
  [destructive_irreversible_operations] covers {N} constraints: {principle statement}
    Lowest durability: {score}% ({constraint_id})
  [schema_modification_control] covers {N} constraints: {principle statement}
    Lowest durability: {score}% ({constraint_id})
  ...

ACTIVE ({active_count} axes):
  [verification_before_commit] covers {N} constraints: {principle statement}
  [dependency_management] covers {N} constraints: {principle statement}
  ...

UNGROUPED ({ungrouped_count} constraints without CCD axis):
  - [{constraint_id}] {text} ({severity})
  ...
```

**Section rules:**

| Section | Contents | Sort Order |
|---------|----------|------------|
| CRITICAL | (a) All constraints with severity=`forbidden`; (b) All constraints with durability_score < 0.3; (c) All axis groups containing at least one forbidden/low-durability constraint | By axis name, then by lowest durability score within axis |
| ACTIVE | Remaining constraints with a `ccd_axis` value, grouped by axis | By axis name, then by severity (forbidden > requires_approval > warning) within axis |
| UNGROUPED | Constraints with `ccd_axis = null` that did not appear in CRITICAL | By severity descending, then by constraint_id |

**Truncation strategy:** If the total briefing exceeds 2000 characters:
1. CRITICAL section is never truncated (it contains the most important information).
2. ACTIVE section: show only axis headers with counts, omit individual constraints. Format: `[axis_name] covers {N} constraints`.
3. UNGROUPED section: show only the count. Format: `{N} additional ungrouped constraints in force.`
4. If still over 2000 chars after steps 2-3: truncate ACTIVE to top 10 axes by constraint count. Append: `... and {remaining} more axes.`

**Design goal:** The briefing occupies minimal Crow (Desktop) slots by presenting axes, not concretes. A briefing with 12 axes and 332 constraints should compress to ~12 Desktop entries.

#### Constraint Filtering Logic

```
LOAD ConstraintStore from data/constraints.json
    |
    v
FILTER by status == "active"
    |
    v
FILTER by scope:
    For each constraint:
        scope_paths = constraint["scope"]["paths"]
        session_paths = [cwd]  # from hook input
        INCLUDE if scopes_overlap(scope_paths, session_paths)
    |
    Note: scopes_overlap() is in src/pipeline/utils.py
    Note: Empty scope_paths means repo-wide (matches everything)
    |
    v
GROUP by ccd_axis (null axis goes to UNGROUPED)
    |
    v
LOAD DurabilityIndex scores (if available)
    |  FAIL: proceed without durability scores (all scores default to None)
    v
CLASSIFY groups:
    If any constraint in group has severity="forbidden" -> CRITICAL
    If any constraint in group has durability_score < 0.3 -> CRITICAL
    Otherwise -> ACTIVE
    |
    v
FORMAT briefing text (see Section layout above)
    |
    v
OUTPUT JSON with hookSpecificOutput.additionalContext = briefing text
```

#### Durability Score Integration

The DurabilityIndex (from `src/pipeline/durability/`) provides per-constraint durability scores based on cross-session evaluation. The SessionStart briefing uses these scores to surface low-durability constraints (those frequently violated) in the CRITICAL section.

- **Score range:** 0.0 (violated in every evaluated session) to 1.0 (never violated).
- **Threshold for CRITICAL:** durability_score < 0.3 (violated in >70% of sessions).
- **Display format:** `{score * 100:.0f}% durability` (e.g., "3% durability" for a score of 0.03).
- **Missing scores:** If DurabilityIndex is unavailable or a constraint has no score, the constraint is treated as having no durability data. It is classified by severity only, not promoted to CRITICAL by durability.

#### Fallback Behavior

Same fail-open pattern as PreToolUse:

| Failure | Behavior |
|---------|----------|
| `data/constraints.json` missing | Output briefing: `"GOVERNANCE BRIEFING: No constraints file found. Governance inactive."` |
| DurabilityIndex unavailable | Proceed without durability scores; omit durability from briefing |
| Python import fails | Exit 0, no stdout (Claude starts without briefing) |
| Hook exceeds timeout | Killed by Claude Code; session starts without briefing |
| Zero constraints match scope | Output: `"GOVERNANCE BRIEFING: 0 constraints active for this project scope."` |

#### Hook Configuration

Project-level `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "PYTHONDONTWRITEBYTECODE=1 python3 \"$CLAUDE_PROJECT_DIR/src/pipeline/live/hooks/constraint_briefing.py\"",
            "timeout": 10,
            "statusMessage": "Loading governance briefing..."
          }
        ]
      }
    ]
  }
}
```

**Matcher:** `startup|resume` fires on both new sessions and resumed sessions. Resumed sessions need the briefing because they start with a fresh context window.

**Timeout:** 10 seconds. More generous than PreToolUse because SessionStart runs once (not per tool call) and may need to load both constraints and durability data.

#### Latency Budget (LIVE-02)

| Component | Estimated Latency | Notes |
|-----------|------------------|-------|
| Shell spawn + Python startup | 50-80ms | Python 3.13 |
| stdin JSON parse | <1ms | Small payload |
| ConstraintStore load | 10-20ms | 419 constraints |
| Scope filtering | <5ms | Bidirectional prefix match on ~332 active constraints |
| DurabilityIndex load | 10-50ms | DuckDB query for scores |
| CCD axis grouping | <5ms | Dict grouping |
| Briefing text formatting | <5ms | String concatenation |
| stdout JSON serialize | <1ms | |
| **Total** | **~90-170ms** | **Within 500ms budget** |

---

### 1.3 Shared Data Models (Pydantic v2)

These models are shared across LIVE-01, LIVE-02, and LIVE-03. They define the data contracts between components.

#### HookInput

```python
class HookInput(BaseModel, frozen=True):
    """Parsed hook input from Claude Code stdin.

    Covers both PreToolUse and SessionStart events.
    PreToolUse provides tool_name, tool_input, tool_use_id.
    SessionStart provides only session-level fields.
    """
    session_id: str
    transcript_path: str = ""
    cwd: str
    permission_mode: str = "default"
    hook_event_name: Literal["PreToolUse", "SessionStart", "PostToolUse", "SessionEnd"]
    tool_name: str | None = None          # PreToolUse only
    tool_input: dict[str, Any] | None = None  # PreToolUse only
    tool_use_id: str | None = None        # PreToolUse only
```

#### GovernanceDecision

```python
class GovernanceDecision(BaseModel, frozen=True):
    """Result of checking a tool call against active constraints.

    Produced by PolicyViolationChecker, consumed by hook output formatting.
    """
    decision: Literal["allow", "warn", "deny"]
    constraint_id: str | None = None
    constraint_text: str | None = None
    reason: str | None = None
    severity: Literal["warning", "requires_approval", "forbidden"] | None = None
    ccd_axis: str | None = None
    epistemological_origin: Literal["reactive", "principled", "inductive"] | None = None
```

#### ConstraintBriefing

```python
class AxisGroup(BaseModel, frozen=True):
    """A group of constraints sharing a CCD axis."""
    ccd_axis: str
    principle_statement: str           # The algebraic principle (e.g., "Require approval for irreversible writes")
    constraint_count: int
    constraint_ids: list[str]
    severities: list[str]              # Unique severities in group
    lowest_durability: float | None = None
    lowest_durability_constraint_id: str | None = None

class ConstraintBriefing(BaseModel, frozen=True):
    """Structured briefing for SessionStart hook output.

    Groups constraints by CCD axis for algebraic Desktop compression.
    """
    total_constraints: int             # Total active constraints matching scope
    critical_groups: list[AxisGroup]   # Axes containing forbidden or low-durability constraints
    active_groups: list[AxisGroup]     # Remaining axis-grouped constraints
    ungrouped_constraints: list[dict]  # Constraints with no ccd_axis
    project_scope: str                 # cwd from hook input
    generated_at: str                  # ISO 8601 timestamp
```

#### GovernanceSignal

```python
class GovernanceSignal(BaseModel, frozen=True):
    """Signal emitted by the JSONL stream processor when a governance event is detected.

    Used by LIVE-03 (stream processor) for event_level and episode_level dispatch.
    """
    signal_type: Literal[
        "escalation_detected",
        "amnesia_detected",
        "constraint_violated",
        "constraint_graduated"
    ]
    session_id: str
    timestamp: str                     # ISO 8601
    details: dict[str, Any]            # Signal-specific payload (varies by signal_type)
    boundary_dependency: Literal["event_level", "episode_level"]
    constraint_id: str | None = None   # For constraint_violated and amnesia_detected
    ccd_axis: str | None = None        # For CCD-aware signal routing
    episode_id: str | None = None      # Populated on episode_level signals at CONFIRMED_END
```

**boundary_dependency classification:**

| Signal Type | boundary_dependency | Rationale |
|------------|-------------------|-----------|
| `escalation_detected` | `event_level` | Fires on the bypass event itself; no episode context needed |
| `constraint_violated` | `event_level` | Fires on the specific tool call that matches a constraint; immediate |
| `constraint_graduated` | `event_level` | Fires when cumulative violation_rate crosses threshold; computed from aggregate, not episode |
| `amnesia_detected` | `episode_level` | Requires knowing the full episode span (observation through outcome) to confirm a constraint was active at episode start and violated by episode end. Emitting at event time produces false positives when the constraint read and the violation are part of the same episode's normal flow. |

#### LiveEvent (used by LIVE-03 stream processor)

```python
class LiveEvent(BaseModel, frozen=True):
    """Lightweight tagged representation of a raw JSONL event.

    Produced by LiveEventAdapter from raw JSONL. Consumed by incremental
    detector adapters. This is NOT a full TaggedEvent -- it carries only
    the fields needed for real-time governance decisions.
    """
    event_type: Literal["user", "assistant", "tool_use", "tool_result", "system", "unknown"]
    timestamp: str                     # ISO 8601 from JSONL
    session_id: str
    tool_name: str | None = None       # For tool_use events
    tool_input: dict[str, Any] | None = None  # For tool_use events
    text_content: str = ""             # Extracted text from message.content
    file_path: str | None = None       # Extracted from tool_input when present
    inferred_tag: Literal[
        "O_DIR", "O_GATE", "O_CORR", "O_ESC",
        "X_ASK", "X_PROPOSE",
        "T_TEST", "T_RISKY", "T_GIT_COMMIT",
        None
    ] = None
    raw_event_type: str = ""           # Original 'type' field from JSONL (e.g., "assistant", "user")
```

---

### 1.4 CCD Constraint Architecture Decision

**This is the binding architectural decision for all Phase 14+ governance components.**

#### The Problem

The constraint store currently holds 419 constraints (332 active). The severity distribution:
- `requires_approval`: 265 (80%)
- `warning`: 64 (19%)
- `forbidden`: 3 (1%)

If the SessionStart briefing lists these as flat concretes, Claude's Desktop (7 +/- 2 slots) is immediately saturated. The briefing becomes noise. The governance system scales linearly: more constraints = longer briefing = less effective governance.

#### The Decision

Every constraint that flows through the hook contracts MUST carry two fields:

```python
ccd_axis: str | None
# The conceptual common denominator -- the algebraic variable that covers
# the scope of this constraint. Example: "destructive_irreversible_operations"
# covers "don't rm -rf", "don't drop database", "don't force push".
# None for constraints not yet classified.

epistemological_origin: Literal["reactive", "principled", "inductive"]
# How this constraint was derived:
# - "reactive": from a single correction/block (narrow scope, exact-match)
# - "principled": from a Level 3+ DDF insight (broad scope, generalizes)
# - "inductive": from cross-session pattern detection (intermediate scope)
```

These fields are OPTIONAL in the JSON schema (backward-compatible) but REQUIRED for the briefing's axis-grouping logic. Constraints without a `ccd_axis` fall into the UNGROUPED section.

#### Compression Ratio Design Goal

**Target:** 12-15 principle axes should cover 80%+ of the 332 active constraints.

This means the SessionStart briefing delivers ~12 Desktop entries instead of ~332, each with a principle statement that activates the full scope of its constituent constraints.

**Briefing format for axis-grouped constraints:**

```
[destructive_irreversible_operations] covers 28 constraints:
    "Require explicit approval before any irreversible state change"
```

This is the algebraic format from 14-CONTEXT.md: one Crow slot, 28 concretes covered.

**Contrast with the flat format (wrong):**

```
- [abc123] "Don't use rm -rf" (requires_approval)
- [def456] "Don't drop database tables" (requires_approval)
- [ghi789] "Don't force push to main" (requires_approval)
... 25 more constraints in this category
```

28 Crow slots consumed for the same coverage. Linear, not algebraic.

#### Impact on Constraint Schema

The existing constraint JSON schema (`data/schemas/constraint.schema.json`) needs two new optional fields:

```json
{
  "ccd_axis": {
    "type": ["string", "null"],
    "description": "Conceptual Common Denominator axis. The algebraic principle that covers this constraint's scope. Example: 'destructive_irreversible_operations'. Null for unclassified constraints."
  },
  "epistemological_origin": {
    "type": ["string", "null"],
    "enum": ["reactive", "principled", "inductive", null],
    "description": "How this constraint was derived. reactive=single correction, principled=DDF Level 3+ insight, inductive=cross-session pattern."
  }
}
```

These fields are added as optional to maintain backward compatibility with the existing 419 constraints. A migration task (Phase 15 or later) will classify existing constraints by axis.

#### Impact on PolicyViolationChecker

The `PolicyViolationChecker.check()` interface does not change. It returns `(bool, dict | None)` where the dict is the matched constraint. The constraint dict now MAY contain `ccd_axis` and `epistemological_origin` fields, which the hook scripts read and include in their output messages. No changes to the checker's matching logic are needed.

#### Impact on DurabilityIndex

The DurabilityIndex uses `constraint_id` as its lookup key. No changes needed for CCD axis support. The briefing groups constraints by axis first, then decorates each group with the lowest durability score from its members.

#### Impact on Policy Automatization Detector (Future)

The `epistemological_origin` field enables differential graduation thresholds:

| Origin | Graduation Threshold | Rationale |
|--------|---------------------|-----------|
| `principled` | violation_rate = 0 for 5 sessions | Principled constraints generalize earlier; the principle was grasped, not just the instance |
| `inductive` | violation_rate = 0 for 10 sessions | Pattern-derived constraints have intermediate generalization |
| `reactive` | violation_rate = 0 for 20 sessions | Single-correction constraints fire on exact-match only; more evidence needed before graduation |

This is designed here but implemented in Phase 15 (Policy Automatization Detector).

---

## 2. JSONL Stream Processor Architecture (LIVE-03)

### 2.1 Stream Processor Overview

#### Purpose

A long-running Python process that monitors Claude Code JSONL session files, processes new events as they arrive, runs existing detectors incrementally, and emits governance signals. This is the real-time counterpart to the batch pipeline: while the batch pipeline processes complete sessions post-hoc, the stream processor detects governance events as they happen.

#### Deployment Model

- **Process type:** Background daemon, started via CLI command (`ope stream start`) or by the governance bus.
- **Cardinality:** One processor per project directory. Multiple projects can run independent processors.
- **Lifecycle:** Starts on demand, runs until explicitly stopped or the system shuts down. Survives Claude Code session restarts (it monitors files, not sessions).
- **Resource footprint:** Single-threaded Python process with watchdog's FSEvents thread. Memory: ~50-100MB (constraint store + detector state + event buffers). CPU: negligible (event-driven, not polling).

#### File Discovery

Claude Code stores session transcripts at:
```
~/.claude/projects/-{project_path_encoded}/*.jsonl
```

**Path encoding convention:** Forward slashes in the project path are replaced with hyphens. Example:
```
Project: /Users/david/projects/orchestrator-policy-extraction
Encoded: -Users-david-projects-orchestrator-policy-extraction
JSONL dir: ~/.claude/projects/-Users-david-projects-orchestrator-policy-extraction/
```

The stream processor resolves this path from the project's `cwd`:
```python
def session_dir_for_project(cwd: str) -> Path:
    encoded = cwd.replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded
```

Each `.jsonl` file in this directory is one session's transcript. New files appear when new sessions start. Existing files grow as events are appended.

---

### 2.2 watchdog Integration Design

#### FileSystemEventHandler

```python
class SessionFileHandler(FileSystemEventHandler):
    """Handles JSONL file create/modify events from watchdog."""

    def on_created(self, event: FileSystemEvent) -> None:
        """Register a new session file for tracking."""
        ...

    def on_modified(self, event: FileSystemEvent) -> None:
        """Read new events from a modified session file."""
        ...

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle session file deletion (rare but possible)."""
        ...
```

#### Observer Configuration

```python
observer = Observer()
observer.schedule(
    handler,
    path=str(session_dir),
    recursive=False  # JSONL files are directly in the session directory
)
observer.start()
```

`recursive=False` because JSONL files are stored flat in the session directory, not in subdirectories.

#### Position Tracking

The processor maintains a position map to track how far it has read into each file:

```python
# Data structure: maps file path -> byte offset
file_positions: dict[str, int] = {}

# On each on_modified callback:
def read_new_events(filepath: str) -> list[dict]:
    pos = file_positions.get(filepath, 0)
    with open(filepath, "r") as f:
        f.seek(pos)
        raw = f.read()
        new_pos = f.tell()

    # Split into lines, handle partial
    lines = raw.split("\n")
    complete_lines = lines[:-1]  # All but last (which may be partial)
    remainder = lines[-1]        # Empty string if raw ended with \n

    if remainder:
        # Incomplete line: buffer it, adjust position
        partial_buffers[filepath] = remainder
        new_pos -= len(remainder.encode("utf-8"))
    else:
        partial_buffers.pop(filepath, None)

    file_positions[filepath] = new_pos

    # Parse complete lines
    events = []
    for line in complete_lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # Log and skip malformed lines
            pass
    return events
```

**Key design points:**
- Read all content from last position to EOF on each notification.
- Split by newline; the last element is either empty (clean end) or a partial line (buffer it).
- Adjust the tracked position to exclude buffered partial content.
- On the next notification, the partial content is re-read and combined with new data.

#### Partial Line Handling

```python
# Data structure for partial line buffers
partial_buffers: dict[str, str] = {}
# Key: file path
# Value: incomplete trailing content from last read
```

When a partial line is detected:
1. Store it in `partial_buffers[filepath]`.
2. Set `file_positions[filepath]` to the byte position BEFORE the partial line.
3. On next `on_modified`, `f.seek()` re-reads from that position, producing the now-complete line.

This approach is simpler than prepending buffered content: the file position naturally includes the partial data on re-read.

#### Session Lifecycle

| Event | Handler | Action |
|-------|---------|--------|
| New JSONL file appears (`on_created`) | `SessionFileHandler.on_created` | Initialize position tracking (pos=0), register session_id (extracted from first event), initialize detector state |
| JSONL file modified (`on_modified`) | `SessionFileHandler.on_modified` | Read new events, process through detectors, emit signals |
| JSONL file deleted (`on_deleted`) | `SessionFileHandler.on_deleted` | Transition session to CONFIRMED_END(outcome="session-end"), clean up state |
| SessionEnd event in JSONL | Event processing logic | Transition to CONFIRMED_END(outcome="session-end"), keep position tracking (file may still receive events) |
| Inactivity timeout (30 min configurable) | Background timer | Transition to CONFIRMED_END(outcome="timeout-inferred") |

#### FSEvents Coalescing Mitigation

macOS FSEvents coalesces rapid file modifications into a single notification. The processor handles this by design:

- **Never assume 1 notification = 1 new line.** Always read from tracked position to EOF.
- **Never assume notifications arrive in write order.** Events are parsed from the file, which is append-only and therefore in write order regardless of notification timing.
- **Process ALL new content on each notification.** Even if 50 events were written between notifications, the single read captures all of them.

---

### 2.3 LiveEventAdapter Design

#### Purpose

Convert raw JSONL event dicts into lightweight `LiveEvent` objects usable by the incremental detector adapters. This adapter replaces the full batch tagger pipeline (CanonicalEvent -> OrchestratorTagger -> TaggedEvent) with a fast, single-pass conversion that infers tags from structural properties of the event.

#### Input

Raw JSON dict from a JSONL line. Structure varies by event type:

```json
// User message
{"type": "user", "sessionId": "uuid", "message": {"content": "..."}, "timestamp": "..."}

// Assistant message with tool calls
{"type": "assistant", "sessionId": "uuid", "message": {"content": [
  {"type": "text", "text": "..."},
  {"type": "tool_use", "id": "toolu_...", "name": "Bash", "input": {"command": "..."}}
]}, "timestamp": "..."}

// System/progress events
{"type": "progress", ...}
{"type": "file-history-snapshot", ...}
```

#### Output

A `LiveEvent` instance (defined in section 1.3) with inferred tag.

#### Conversion Logic

```
RAW JSONL DICT
    |
    v
[1] Extract top-level fields: type, sessionId, timestamp
    |
    v
[2] Classify event_type:
    | "user" -> event_type = "user"
    | "assistant" with tool_use content -> event_type = "tool_use"
    | "assistant" without tool_use -> event_type = "assistant"
    | "tool_result" -> event_type = "tool_result"
    | anything else -> event_type = "system" or "unknown"
    |
    v
[3] Extract fields based on event_type:
    | tool_use: tool_name, tool_input, file_path from input
    | user: text_content from message.content
    | assistant: text_content from message.content text blocks
    | tool_result: text_content from result content
    |
    v
[4] Infer tag (see Tag Inference Rules below)
    |
    v
[5] Construct LiveEvent
```

**For assistant messages with multiple content items:** If the content array contains both text and tool_use items, emit ONE LiveEvent per tool_use item (each gets its own tag inference). Text-only content items contribute to text_content but do not generate separate LiveEvents.

#### Tag Inference Rules

All patterns are pre-compiled at adapter initialization (`__init__`). No regex compilation occurs per-event.

| Priority | Condition | Inferred Tag | Pre-compiled Pattern |
|----------|-----------|-------------|---------------------|
| 1 | `tool_use` + `name == "Bash"` + command matches `git\s+commit` | `T_GIT_COMMIT` | `re.compile(r"git\s+commit", re.IGNORECASE)` |
| 2 | `tool_use` + `name == "Bash"` + command matches `pytest\|npm\s+test\|make\s+test\|cargo\s+test` | `T_TEST` | `re.compile(r"pytest\|npm\s+test\|make\s+test\|cargo\s+test", re.IGNORECASE)` |
| 3 | `tool_use` + `name == "Bash"` + command matches `rm\s+-rf\|sudo\|chmod\|chown\|DROP\s+TABLE\|TRUNCATE` | `T_RISKY` | `re.compile(r"rm\s+-rf\|sudo\|chmod\|chown\|DROP\s+TABLE\|TRUNCATE", re.IGNORECASE)` |
| 4 | `tool_use` + `name in ("Write", "Edit")` | `T_RISKY` | (tool name check, no regex) |
| 5 | `user` message + text matches `approve\|yes.*proceed\|go ahead\|LGTM\|looks good` | `X_ASK` | `re.compile(r"approve\|yes.*proceed\|go ahead\|LGTM\|looks good", re.IGNORECASE)` |
| 6 | `user` message + text matches `^/` (slash command) | `O_DIR` | `re.compile(r"^/")` |
| 7 | `assistant` text matches `I'll stop\|I need your\|should I\|would you like me to` | `X_PROPOSE` | `re.compile(r"I'll stop\|I need your\|should I\|would you like me to", re.IGNORECASE)` |
| 8 | All other events | `None` | (default) |

**Priority order matters:** A Bash command with `git commit` is T_GIT_COMMIT (priority 1), not T_RISKY (priority 3), even though it could match both.

**Performance constraint:** Each rule is a pre-compiled regex applied to a string. At 7 regex matches per event, each taking <0.1ms, the total is <1ms per event.

**False positive tolerance:** These are heuristic tags for real-time governance, not ground-truth labels. False positives are acceptable because:
- T_RISKY false positives only cause additional monitoring (no blocking).
- T_GIT_COMMIT false positives only affect episode boundary confidence scoring.
- The batch pipeline produces authoritative tags post-hoc for training data.

---

### 2.4 Incremental Detector Adapters

#### IncrementalEscalationAdapter

**Purpose:** Wraps the existing `EscalationDetector` to accept one `LiveEvent` at a time, maintaining sliding window state across calls.

**Interface:**

```python
class IncrementalEscalationAdapter:
    """Incremental wrapper for EscalationDetector.

    Maintains _PendingWindow state across per-event calls.
    Converts LiveEvent to the minimal representation needed
    by the escalation detection algorithm.
    """

    def __init__(self, config: PipelineConfig) -> None:
        """Initialize with pipeline config for escalation settings."""
        ...

    def process_event(self, event: LiveEvent) -> list[EscalationCandidate]:
        """Process a single event and return any escalation candidates detected.

        Returns empty list if no escalation detected on this event.
        """
        ...

    def reset(self) -> None:
        """Clear all pending windows (e.g., on session end)."""
        ...
```

**Internal design:**

The adapter replicates the EscalationDetector's algorithm but operates on one event at a time instead of a list:

1. Maintain `pending: list[_PendingWindow]` as instance state (persists across calls).
2. On each `process_event(event)`:
   - Extract `inferred_tag` from LiveEvent.
   - If tag in `{O_GATE, O_CORR}`: open new window.
   - If tag in `{X_ASK, X_PROPOSE}`: clear all pending windows (approval sought).
   - If tool_name is exempt (Read, Glob, Grep, WebFetch, WebSearch, Task): skip.
   - Otherwise: increment non_exempt_turns on all windows, check for bypass eligibility, check for window expiry.
3. Return any `EscalationCandidate` objects produced.

**LiveEvent to detector-compatible conversion:**
- `event.inferred_tag` maps directly to the tag checks (O_GATE, O_CORR, X_ASK, X_PROPOSE, T_RISKY, T_GIT_COMMIT, T_TEST).
- `event.tool_name` maps to exempt tool checks and bypass eligibility.
- `event.text_content` maps to command text for always_bypass_patterns.
- `event.file_path` maps to resource path for candidate building.

**Session resume:** If a session is resumed after a gap, the adapter's `pending` windows may contain stale entries. The inactivity timeout (30 min) handles this: stale windows expire naturally when the gap exceeds `window_turns` worth of non-exempt events.

#### IncrementalAmnesiaAdapter

**Purpose:** Performs per-event constraint checking against active constraints. Buffers candidate amnesia signals until CONFIRMED_END (episode_level dispatch).

**Interface:**

```python
class IncrementalAmnesiaAdapter:
    """Per-event constraint checking with episode-level signal buffering.

    Unlike the batch AmnesiaDetector which operates on ConstraintEvalResult
    objects, this adapter checks each tool_use event directly against
    PolicyViolationChecker and buffers candidates until episode confirmation.

    IMPORTANT: This adapter does NOT emit signals immediately. All candidate
    amnesia signals are held in pending_signals until flush_pending() is
    called at CONFIRMED_END. This prevents false positives from mid-episode
    constraint reads followed by violations in the same episode's normal flow.
    """

    def __init__(self, checker: PolicyViolationChecker) -> None:
        """Initialize with a pre-loaded PolicyViolationChecker."""
        ...

    def process_event(self, event: LiveEvent) -> None:
        """Check event against constraints. Buffer any matches.

        Does NOT return signals. Signals are retrieved via flush_pending().
        """
        ...

    def flush_pending(self, episode_id: str) -> list[GovernanceSignal]:
        """Flush all buffered amnesia signals for the current episode.

        Called at CONFIRMED_END. Attaches episode_id to each signal.
        Returns the signals and clears the buffer.
        """
        ...

    def discard_pending(self) -> int:
        """Discard all buffered signals (REOPENED -- false positive boundary).

        Returns the count of discarded signals.
        """
        ...
```

**Internal design:**

1. On each `process_event(event)`:
   - Skip if `event.event_type != "tool_use"` (only tool calls can violate constraints).
   - Build search text from `event.tool_name`, `event.file_path`, `event.text_content` (same extraction as PreToolUse hook).
   - Run `self._checker.check(search_text)`.
   - If match found: create a candidate `GovernanceSignal` with `signal_type="amnesia_detected"`, `boundary_dependency="episode_level"`, and store in `self._pending_signals`.
2. On `flush_pending(episode_id)`:
   - Attach `episode_id` to all pending signals.
   - Return the signals and clear `self._pending_signals`.
3. On `discard_pending()`:
   - Clear `self._pending_signals` and return the count (for logging).

**Why buffering is mandatory:** The batch AmnesiaDetector works on complete `ConstraintEvalResult` objects that represent entire session evaluations. The incremental adapter sees individual events in real-time. A tool call that matches a constraint detection_hint is not necessarily a violation -- it might be the agent deliberately reading a constrained file as part of compliance. Only the full episode context (observation through outcome) can distinguish "violated despite knowing" from "checking to comply." The buffer holds candidates until CONFIRMED_END when the episode context is available.

#### IncrementalPolicyCheckAdapter

**Purpose:** Wraps PolicyViolationChecker for per-event constraint checking in the stream processor. Unlike the PreToolUse hook (which checks BEFORE execution), this checks the JSONL record AFTER execution -- providing a second-pass detection for events that bypassed the hook or occurred in sessions without hooks enabled.

**Interface:**

```python
class IncrementalPolicyCheckAdapter:
    """Post-execution constraint checking for JSONL events.

    Checks each tool_use event against PolicyViolationChecker and emits
    event_level governance signals for constraint violations.
    """

    def __init__(self, checker: PolicyViolationChecker) -> None:
        """Initialize with a pre-loaded PolicyViolationChecker."""
        ...

    def process_event(self, event: LiveEvent) -> GovernanceSignal | None:
        """Check event against constraints. Return signal if violation found.

        Returns None if no violation detected.
        This is event_level: signals are emitted immediately.
        """
        ...
```

**Internal design:**

1. On each `process_event(event)`:
   - Skip if `event.event_type != "tool_use"`.
   - Build search text (same as PreToolUse extraction).
   - Run `self._checker.check(search_text)`.
   - If `(True, constraint)`: return `GovernanceSignal(signal_type="constraint_violated", boundary_dependency="event_level", ...)`.
   - If `(False, constraint)`: return `GovernanceSignal(signal_type="constraint_violated", boundary_dependency="event_level", severity="warning", ...)`.
   - If `(False, None)`: return `None`.

**Distinction from IncrementalAmnesiaAdapter:** The policy check adapter emits immediately (`event_level`) because it detects a concrete violation at a specific tool call. The amnesia adapter detects a *pattern* (constraint active but violated over an episode) which requires episode context.

---

### 2.5 Governance Signal Emission

When a detector fires, the stream processor emits a `GovernanceSignal` (defined in section 1.3) to one or more targets.

#### Emission Targets

| Target | Transport | When | Format |
|--------|-----------|------|--------|
| stdout | JSON lines (one signal per line) | Always (default) | `json.dumps(signal.model_dump())` + newline |
| Bus HTTP POST | `POST /api/events` on Unix socket | If bus socket exists at `/tmp/ope-governance-bus.sock` | JSON body: signal dict |
| DuckDB | INSERT into `governance_signals` table | Always (persistent) | Signal fields mapped to table columns |

**Target priority:** DuckDB is always written (persistence). stdout is always written (monitoring). Bus POST is best-effort (emit if available, skip if not).

#### Signal Deduplication

To prevent duplicate signals for the same underlying event:

```python
# Dedup hash: SHA-256(signal_type + session_id + constraint_id + tool_use_id)[:16]
emitted_hashes: set[str] = set()

def emit_signal(signal: GovernanceSignal, tool_use_id: str) -> bool:
    dedup_key = hashlib.sha256(
        f"{signal.signal_type}:{signal.session_id}:{signal.constraint_id}:{tool_use_id}".encode()
    ).hexdigest()[:16]

    if dedup_key in emitted_hashes:
        return False  # Already emitted

    emitted_hashes.add(dedup_key)
    # ... emit to targets ...
    return True
```

The dedup set is cleared on session end to bound memory. For long sessions, a dedup set of ~10,000 hashes consumes <1MB.

#### DuckDB Schema for governance_signals

```sql
CREATE TABLE IF NOT EXISTS governance_signals (
    signal_id       VARCHAR PRIMARY KEY,  -- SHA-256 dedup hash
    signal_type     VARCHAR NOT NULL,
    session_id      VARCHAR NOT NULL,
    timestamp       TIMESTAMP NOT NULL,
    boundary_dependency VARCHAR NOT NULL,  -- 'event_level' or 'episode_level'
    constraint_id   VARCHAR,
    ccd_axis        VARCHAR,
    episode_id      VARCHAR,              -- populated at CONFIRMED_END for episode_level
    details         JSON,
    emitted_at      TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX idx_governance_signals_session ON governance_signals(session_id);
CREATE INDEX idx_governance_signals_type ON governance_signals(signal_type);
CREATE INDEX idx_governance_signals_axis ON governance_signals(ccd_axis);
```

---

### 2.6 Latency Analysis

#### Per-Event Processing Budget

| Stage | Component | Estimated Latency | Notes |
|-------|-----------|------------------|-------|
| 1 | JSONL line read (from tracked position) | <1ms | Sequential file read, small payload |
| 2 | JSON parse | <1ms | `json.loads()` on single line |
| 3 | LiveEventAdapter conversion | <1ms | 7 pre-compiled regex checks |
| 4 | IncrementalEscalationAdapter.process_event() | <1ms | Window state check, tag comparison |
| 5 | IncrementalAmnesiaAdapter.process_event() | <1ms | PolicyViolationChecker.check() with pre-compiled patterns |
| 6 | IncrementalPolicyCheckAdapter.process_event() | <1ms | Same checker, different signal routing |
| 7 | Signal emission (stdout + DuckDB) | <5ms | DuckDB insert dominates |
| 7a | Signal emission (bus POST, if running) | 1-5ms | Unix socket HTTP, non-blocking |
| **Total per event** | | **<10ms** | |

#### End-to-End Latency

```
Claude Code writes JSONL line (~0ms from Claude's perspective)
    |
    v  (macOS FSEvents notification)
watchdog on_modified callback (~10ms from file write)
    |
    v  (event processing)
Stream processor processes event (~10ms, see breakdown above)
    |
    v
Signal emitted (~0ms stdout, <5ms DuckDB, <5ms bus)
    |
    === Total: ~20-25ms from JSONL write to governance signal ===
```

This is well within the 200ms target. The stream processor adds negligible latency to the governance feedback loop.

#### Throughput

- **Peak Claude Code output:** ~10 events/second during tool bursts (rapid Read/Grep sequences).
- **Processor capacity:** At 10ms/event, the processor handles 100 events/second.
- **Headroom:** 10x headroom over peak load.

#### Episode-Level Signal Dispatch Overhead

Episode-level signals (amnesia_detected) add NO per-event latency. They are buffered in a list during normal processing. The flush occurs at CONFIRMED_END, which is driven by:
- A start-trigger detection (next episode opens, confirming the previous one closed).
- A TTL timer expiring (30 minutes of inactivity).

Neither of these is a blocking wait. The start-trigger check happens during normal event processing. The TTL timer runs on a separate asyncio/threading timer.

---

### 2.7 Episode Boundary State Machine (TENTATIVE_END / CONFIRMED_END)

#### Motivation

The post-hoc episode segmenter (src/pipeline/segmenter.py) operates on complete event streams with full temporal context. It can look ahead to determine if an apparent episode boundary is real.

The stream processor cannot look ahead. It processes events as they arrive. When an end-trigger event appears, the processor cannot know if the next event will be a continuation (same episode) or a new start-trigger (new episode, confirming the boundary).

This asymmetry requires a state machine with tentative and confirmed states.

#### State Machine

Each tracked session maintains an independent boundary state:

```
                                          +-----------------+
                                          |     INITIAL     |
                                          +--------+--------+
                                                   |
                                          first event arrives
                                                   |
                                                   v
                        +-------------------->  OPEN  <-------------------+
                        |                      /     \                    |
                        |          end-trigger /       \ session close    |
                        |            event   /         \  (file deleted   |
                        |                   v           \  or hard EOF)   |
                        |           TENTATIVE_END        \                |
                        |          /      |      \        v               |
                        |  start- /       |       \ continuation          |
                        | trigger/     TTL |       \ (non-start-         |
                        |       /   expires |       \  trigger)           |
                        |      v          v        v                     |
                        | CONFIRMED_END  CONFIRMED_END  REOPENED --------+
                        |  (outcome=     (outcome=
                        |   from end     "timeout-
                        |   trigger)     inferred")
                        |
                        +--- new OPEN state opens after CONFIRMED_END
```

**State definitions:**

| State | Meaning | Data |
|-------|---------|------|
| `INITIAL` | No events processed for this session yet | None |
| `OPEN` | An episode is in progress | `episode_start_event`, `observation_events: list` |
| `TENTATIVE_END` | An end-trigger was seen but not confirmed | `end_trigger_event`, `confidence: float`, `tentative_timestamp` |
| `CONFIRMED_END` | The boundary is confirmed | `episode_record`, `outcome`, `outcome_confidence` |
| `REOPENED` | A tentative end was a false positive | Transitions immediately to `OPEN` (extends existing episode) |

#### Transitions

**OPEN -> TENTATIVE_END** (end-trigger event arrives):

```python
# Triggered by: inferred_tag in END_TRIGGERS (T_TEST, T_RISKY, T_GIT_COMMIT, X_PROPOSE)
# NOTE: X_ASK is NOT an end trigger (see segmenter.py)
tentative_state = TentativeEnd(
    end_trigger_event=event,
    confidence=compute_confidence(event, recent_events),
    tentative_timestamp=event.timestamp,
)
```

**TENTATIVE_END -> CONFIRMED_END** (start-trigger arrives):

```python
# Triggered by: next event has inferred_tag in START_TRIGGERS (O_DIR, O_GATE, O_CORR)
# The new start-trigger confirms the previous episode ended.
confirmed_episode = finalize_episode(
    start=episode_start_event,
    end=tentative_state.end_trigger_event,
    outcome=determine_outcome(tentative_state.end_trigger_event),
    outcome_confidence="confirmed",
)
# Flush episode_level signals
amnesia_adapter.flush_pending(confirmed_episode.episode_id)
# Write episode to DuckDB
write_episode_to_duckdb(confirmed_episode)
# Open new episode starting with the current start-trigger
transition_to_open(current_event)
```

**TENTATIVE_END -> CONFIRMED_END** (TTL expires):

```python
# Triggered by: 30 minutes of inactivity (configurable)
confirmed_episode = finalize_episode(
    start=episode_start_event,
    end=tentative_state.end_trigger_event,
    outcome="timeout-inferred",
    outcome_confidence="inferred",
    completeness_score=4,  # out of 5: property 4 (outcome) is inferred
)
# Flush episode_level signals with timeout caveat
amnesia_adapter.flush_pending(confirmed_episode.episode_id)
# Write to DuckDB with completeness flag
write_episode_to_duckdb(confirmed_episode)
```

**TENTATIVE_END -> REOPENED -> OPEN** (continuation event):

```python
# Triggered by: next event has NO inferred_tag in START_TRIGGERS
# (could be another tool call, a user message, etc.)
# The tentative end was a false positive.
log_false_positive(tentative_state)
amnesia_adapter.discard_pending()  # Candidates were from an incomplete episode
boundary_false_positives_counter += 1
# Extend observation window to include post-tentative events
transition_to_open_extended()
```

**OPEN -> CONFIRMED_END** (session file closed):

```python
# Triggered by: watchdog on_deleted, or SessionEnd event in JSONL
confirmed_episode = finalize_episode(
    start=episode_start_event,
    end=last_event,
    outcome="session-end",
    outcome_confidence="confirmed",
)
amnesia_adapter.flush_pending(confirmed_episode.episode_id)
write_episode_to_duckdb(confirmed_episode)
```

#### Confidence Scoring at TENTATIVE_END

Confidence scores are used for logging and future calibration, NOT for dispatch decisions. All TENTATIVE_END states are treated equally for dispatch routing.

| End-Trigger Pattern | Confidence | Rationale |
|--------------------|-----------|-----------|
| `T_GIT_COMMIT` following `X_PROPOSE` in prior 3 events | 0.90 | Strong signal: proposal accepted and committed |
| TTL expiry (30-minute inactivity) | 0.95 | Very high: 30 minutes without activity almost certainly means the episode ended |
| `T_GIT_COMMIT` standalone | 0.75 | Good signal: commit usually ends a work unit, but could be followed by more work |
| `X_PROPOSE` standalone | 0.65 | Moderate: proposal may lead to more discussion in the same episode |
| `T_TEST` (pass) | 0.60 | Moderate: test pass may end an episode, but often followed by commit or next task |
| `T_TEST` (fail) | 0.40 | Low: test failure typically leads to more work within the same episode |
| `T_RISKY` | 0.50 | Low: risky action is mid-episode; only a boundary if followed by nothing |

**Note:** `X_ASK` does NOT appear in this table. It is structurally mid-episode (a question within an episode, never a boundary). This matches the post-hoc segmenter's explicit exclusion from END_TRIGGERS.

#### Signal Dispatch by boundary_dependency

```
EVENT ARRIVES
    |
    v
ADAPTER PROCESSES EVENT
    |
    +-- adapter returns event_level signal(s)
    |       |
    |       v
    |   EMIT IMMEDIATELY (to stdout, DuckDB, bus)
    |   (No state machine dependency)
    |
    +-- adapter buffers episode_level candidate(s)
            |
            v
        HELD in pending_signals[session_id]
            |
            +---> CONFIRMED_END transition
            |         |
            |         v
            |     FLUSH: emit all pending with episode_id attached
            |
            +---> REOPENED transition
                      |
                      v
                  DISCARD: candidates were from incomplete episode
```

#### On CONFIRMED_END

1. **Finalize episode window:**
   - `observation`: first event to last event before TENTATIVE_END.
   - `outcome`: inferred from end-trigger type (see outcome mapping below).
2. **Emit all buffered episode_level signals** with the completed episode context.
3. **Write episode record to DuckDB** (`episodes` table). This is the ONLY point at which an episode enters the training store from the stream processor.
4. **Clear session's pending_signals buffer.**
5. **Open new OPEN state** for the session (ready for next episode).

**Outcome mapping** (from end-trigger):

| End Trigger | Outcome |
|------------|---------|
| `T_TEST` (pass) | `success` |
| `T_TEST` (fail) | `failure` |
| `T_RISKY` | `risky_action` |
| `T_GIT_COMMIT` | `committed` |
| `X_PROPOSE` | `executor_handoff` |
| TTL timeout | `timeout-inferred` |
| Session end | `session-end` |

#### On REOPENED (False Positive)

1. **Extend observation window** to include post-TENTATIVE_END events (they are part of the same episode).
2. **Discard buffered episode_level signals** (they were generated from an incomplete episode).
3. **Log the false positive boundary** for detector calibration:
   ```python
   boundary_false_positives.append({
       "session_id": session_id,
       "trigger_event": tentative_state.end_trigger_event,
       "confidence": tentative_state.confidence,
       "reopened_by": current_event,
       "timestamp": current_event.timestamp,
   })
   ```
4. **event_level signals already emitted remain valid.** They operated on correct event data (the specific tool call that matched a constraint). The episode boundary does not invalidate event-level detections.

#### TTL Episode Handling

Episodes confirmed via TTL timeout have special handling:

| Property | Value | Rationale |
|----------|-------|-----------|
| `episode.outcome` | `"timeout-inferred"` | The actual outcome is unknown; timeout is inferred, not observed |
| `episode.outcome_confidence` | `"inferred"` | Distinguishes from confirmed outcomes |
| `completeness_score` | `4/5` | Property 4 (outcome) is inferred; properties 1 (trigger), 2 (observation), 3 (action), 5 (provenance) are present |
| Training data eligibility | NOT eligible for constraint extraction training | Inferred outcome corrupts reaction labels: we don't know if the agent succeeded or failed |
| Pattern detection eligibility | Eligible for observation-state analysis | Patterns in the observation (what tools were used, what files were touched) are valid regardless of outcome |

---

## 3. Cross-Cutting Concerns

### 3.1 Existing Code Integration Points

| Existing Component | Location | How Used |
|-------------------|----------|----------|
| `PolicyViolationChecker` | `src/pipeline/feedback/checker.py` | Used directly by PreToolUse hook and both stream processor adapters. Interface: `check(text) -> (bool, dict\|None)`. No modification needed. |
| `ConstraintStore` | `src/pipeline/constraint_store.py` | Used by PreToolUse hook (loads constraints), SessionStart hook (loads + filters). Interface: `get_active_constraints() -> list[dict]`. No modification needed. |
| `EscalationDetector` | `src/pipeline/escalation/detector.py` | Algorithm replicated in IncrementalEscalationAdapter. The adapter maintains its own `_PendingWindow` state. The batch detector's `detect(tagged_events)` interface is not called directly. |
| `AmnesiaDetector` | `src/pipeline/durability/amnesia.py` | NOT used directly. The incremental adapter performs a simplified per-event check using PolicyViolationChecker instead of the batch evaluator pipeline. |
| `scopes_overlap()` | `src/pipeline/utils.py` | Used by SessionStart hook for scope filtering. Bidirectional prefix match: `a.startswith(b) or b.startswith(a)`. Empty paths = repo-wide. |
| `EpisodeSegmenter` | `src/pipeline/segmenter.py` | Reference only: START_TRIGGERS and END_TRIGGERS sets are replicated in the stream processor's state machine. The segmenter itself is not called (it operates on complete streams). |

### 3.2 Configuration

All configurable values for the live governance layer:

| Parameter | Default | Location | Description |
|-----------|---------|----------|-------------|
| `pretooluse_timeout` | 5s | `.claude/settings.json` | Max time for PreToolUse hook |
| `sessionstart_timeout` | 10s | `.claude/settings.json` | Max time for SessionStart hook |
| `stream_processor_ttl` | 1800s (30 min) | `PipelineConfig` or env var | Inactivity timeout for episode boundary confirmation |
| `bus_socket_path` | `/tmp/ope-governance-bus.sock` | Env var `OPE_BUS_SOCKET` | Unix socket path for governance bus |
| `constraints_path` | `data/constraints.json` | `ConstraintStore` default | Path to constraint store |
| `durability_critical_threshold` | 0.3 | Config | Durability score below which constraints are CRITICAL |
| `briefing_max_chars` | 2000 | Config | Max length for SessionStart briefing text |
| `escalation_window_turns` | (from PipelineConfig) | `PipelineConfig` | Number of non-exempt events in escalation window |

### 3.3 File Structure for Phase 15 Implementation

```
src/pipeline/live/
    __init__.py
    hooks/
        __init__.py
        governance_check.py       # LIVE-01: PreToolUse hook script
        constraint_briefing.py    # LIVE-02: SessionStart hook script
    stream/
        __init__.py
        processor.py              # LIVE-03: Main stream processor (watchdog + event loop)
        adapters.py               # LiveEventAdapter + incremental detector adapters
        boundary.py               # Episode boundary state machine
        signals.py                # GovernanceSignal emission (stdout, DuckDB, bus)
    models.py                     # Shared Pydantic models (HookInput, GovernanceDecision, etc.)
```

---

## Appendix A: Complete Hook Configuration Example

Combined `.claude/settings.json` with all governance hooks:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit|Read|Glob|Grep",
        "hooks": [
          {
            "type": "command",
            "command": "PYTHONDONTWRITEBYTECODE=1 python3 \"$CLAUDE_PROJECT_DIR/src/pipeline/live/hooks/governance_check.py\"",
            "timeout": 5,
            "statusMessage": "Checking governance constraints..."
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [
          {
            "type": "command",
            "command": "PYTHONDONTWRITEBYTECODE=1 python3 \"$CLAUDE_PROJECT_DIR/src/pipeline/live/hooks/constraint_briefing.py\"",
            "timeout": 10,
            "statusMessage": "Loading governance briefing..."
          }
        ]
      }
    ]
  }
}
```

## Appendix B: GovernanceSignal Details Payloads

Example `details` dict contents for each signal type:

**escalation_detected:**
```json
{
  "block_event_tag": "O_GATE",
  "bypass_tool_name": "Bash",
  "bypass_command": "rm -rf /tmp/build",
  "window_turns_used": 2,
  "confidence": 1.0
}
```

**amnesia_detected:**
```json
{
  "constraint_id": "bbd376a2",
  "constraint_text": "Do not modify schema without approval",
  "violation_tool_name": "Edit",
  "violation_file_path": "data/schemas/constraint.schema.json",
  "episode_observation_count": 15
}
```

**constraint_violated:**
```json
{
  "constraint_id": "a1b2c3d4",
  "constraint_text": "Always run tests after code changes",
  "severity": "warning",
  "matched_text": "pytest src/tests/",
  "ccd_axis": "verification_before_commit"
}
```

**constraint_graduated:**
```json
{
  "constraint_id": "e5f6g7h8",
  "constraint_text": "Use loguru for logging",
  "violation_rate": 0.0,
  "sessions_evaluated": 25,
  "epistemological_origin": "reactive",
  "proposed_destination": "project_wisdom"
}
```
