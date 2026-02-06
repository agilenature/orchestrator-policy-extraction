# Planning Policy for Orchestrator Policy Extraction

## Reference Document Policy

**CRITICAL:** When planning any phase of this project, ALWAYS reference:

📄 **`docs/design/WHY_TURN_LEVEL - Improved.md`**

This document contains the authoritative specification for:
- Decision-point episode architecture
- JSON schema for orchestrator episodes
- Event tagging and segmentation algorithms
- Worked examples showing correct implementation

## Why This Matters

The "Improved.md" document identifies a **critical error** in the original turn-level approach:

❌ **Wrong:** Training the executor (Claude's tool calls: Read/Edit/Bash)
✅ **Correct:** Training the orchestrator (OpenClaw's policy: mode/scope/gates/constraints)

This is a fundamental architectural shift that must be followed in every phase.

## Planning Checklist

Before planning any phase, ensure you have:

1. ✅ Read relevant sections of "Improved.md"
2. ✅ Understood the orchestrator vs. executor distinction
3. ✅ Verified alignment with decision-point (not turn-level) approach
4. ✅ Checked against worked example (lines 1544-1949)
5. ✅ Confirmed action is orchestrator directive, not tool call

## Key Sections by Phase

| Phase | Relevant "Improved.md" Sections |
|-------|-------------------------------|
| 0.5 Schema | Lines 353-829 (JSON Schema) |
| 1 Event Normalization | Lines 1090-1246 (Input/Stage A) |
| 2 Segmentation | Lines 890-958 (Decision-point triggers) |
| 2 Orchestrator Action | Lines 1262-1286 (Mode inference, risk model) |
| 3 Reactions | Lines 959-995 (Reaction labeling), 996-1022 (Constraints) |
| 4 Database | Lines 1120-1130 (Episode schema in DuckDB) |
| 5 Validation | Lines 1544-1949 (Worked example) |

## Implementation Rule

**Before writing code for any component, ask:**

> "Does this extract orchestrator directives (mode/scope/gates/instruction) or executor tool calls?"

If the answer is "executor tool calls," **STOP** and redesign to focus on orchestrator decisions.

## Reference Pattern

When creating plans or designs, include:

```markdown
**Reference:** docs/design/WHY_TURN_LEVEL - Improved.md, lines X-Y

**Key insight:** [Quote relevant section]

**How this applies:** [Explain alignment]
```

## Validation

Every major design decision should be validated against "Improved.md":
- Does it support orchestrator-first learning?
- Does it extract constraints as first-class artifacts?
- Does it preserve decision-point granularity?
- Does it support human-absent operation (objective rewards)?

---

**Status:** ACTIVE - This policy remains in effect for entire project lifecycle.

**Last Updated:** 2026-02-05
**Next Review:** Phase 5 completion
