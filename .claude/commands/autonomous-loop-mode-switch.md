Diagnose and recover from an EBC (External Behavioral Contract) drift alert.

## Handling this invocation

**Arguments received:** `$ARGUMENTS`

- **If arguments are empty or `--help`:** Present the orientation guide below.
- **If arguments are `check`:** Scan `data/alerts/` for recent drift alert files. For each, summarize the drift score, unexpected files, and missing expected files. If no alerts exist, say so.
- **If arguments are `recover <session_id>`:** Read the alert file `data/alerts/<session_id>-ebc-drift.json`, analyze the drift signals, and recommend one of:
  1. **Resume Execution Mode** -- the drift was minor (e.g., only infrastructure files). Suggest continuing with the current plan.
  2. **Switch to Discovery Mode** -- the drift indicates the session explored significantly outside the plan contract. Suggest pausing plan execution, documenting findings, and re-planning.
  3. **Amend the Plan** -- the drift reveals legitimate scope that was missing from the PLAN.md. Suggest updating `files_modified` and re-running extraction.
- **If arguments are `clear`:** Remove the EBC Drift Alerts section from `.planning/STATE.md` by deleting content between `<!-- EBC_DRIFT_ALERTS_START -->` and `<!-- EBC_DRIFT_ALERTS_END -->` sentinels (inclusive).

---

## Orientation guide

### What is EBC Drift?

An **External Behavioral Contract (EBC)** is the implicit contract declared in a PLAN.md's frontmatter: `files_modified`, `must_haves.artifacts`, `autonomous` flag. When a session's actual behavior diverges from this contract -- writing files outside scope, leaving expected files unmodified -- the EBC Drift Detector flags a **mode switch** from Execution Mode to Discovery Mode.

### Why it matters

In Discovery Mode, the agent is exploring rather than executing the plan. Completions reported during Discovery Mode are unreliable -- they may solve a different problem than the plan intended, or accumulate partial work that the next session cannot continue from.

### Drift signals

| Signal | Meaning | Weight |
|--------|---------|--------|
| `unexpected_file` | A file was modified that is NOT in `files_modified` or `must_haves.artifacts` | 1.0 |
| `missing_expected_file` | A file in the contract was NOT modified during the session | 0.3 |

### Drift score

`sum(signal_weights) / max(expected_file_count, 1)`, capped at 1.0. Threshold: 0.5 (configurable in `data/config.yaml` under `ebc_drift.threshold`).

### Quick commands

```
# Check for active drift alerts
/project:autonomous-loop-mode-switch check

# Diagnose a specific session's drift
/project:autonomous-loop-mode-switch recover <session_id>

# Clear drift alerts from STATE.md
/project:autonomous-loop-mode-switch clear
```

### When you see a drift alert

1. **Read the alert:** `cat data/alerts/<session_id>-ebc-drift.json`
2. **Assess the cause:** Were unexpected files infrastructure (low concern) or new features (high concern)?
3. **Decide recovery path:** Resume / Switch to Discovery / Amend Plan
4. **Clear the alert** from STATE.md once resolved: `/project:autonomous-loop-mode-switch clear`
