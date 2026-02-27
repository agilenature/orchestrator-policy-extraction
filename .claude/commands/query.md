Search the OPE knowledge graph — docs, sessions, and code — using the unified query interface.

## Live index status

`python scripts/query_status.py`

---

## Handling this invocation

**Arguments received:** `$ARGUMENTS`

- **If arguments are empty or `--help`:** Present the orientation guide below. Do not run a query.
- **Otherwise:** Run `python -m src.pipeline.cli query $ARGUMENTS` and display the results. After the results, note which source(s) returned matches and whether the query hit an indexed CCD axis (for `--source docs`) or fell back to ILIKE (for `--source sessions` when BM25 has no match).

---

## Orientation guide

### Three knowledge stores

| Source | What it contains | Best query shape |
|--------|-----------------|------------------|
| `--source docs` | Architecture docs, guides, analysis — indexed by CCD axis | Axis name or concept phrase |
| `--source sessions` | 964 decision-point episodes — BM25 fulltext | Problem description or component name |
| `--source code` | All `src/` files — ripgrep by default, grep fallback | Function name, class name, or symbol |
| `--source all` | All three combined | Broad exploration before narrowing |

### Indexed CCD axes

Query any of these by name to retrieve the architectural rationale for that axis. This is the fastest way to load the governing principle before writing code.

| Axis | Docs | What it covers |
|------|------|----------------|
| `run-id-dissolves-repo-boundary` | 28 | Cross-repo causal chain via shared run_id |
| `decision-boundary-externalization` | 13 | 5-property decision artifacts |
| `fallacy-as-process-failure` | 11 | Hallucination as structural fallacy category |
| `closed-loop-to-specification` | 8 | Validation failures enrich specs, not warning logs |
| `ground-truth-pointer` | 7 | Every abstraction needs a perceptual anchor |
| `epistemological-layer-hierarchy` | 7 | 6-layer artifact validity stack |
| `raven-cost-function-absent` | 6 | AI's missing retrieval cost = no selection pressure |
| `temporal-closure-dependency` | 4 | Episode boundaries defined by what follows |
| `causal-chain-completeness` | 3 | Explicit parent→child links between decisions |
| `identity-firewall` | 2 | Generator and validator must be structurally separated |
| `deposit-not-detect` | 2 | Detection without deposit is instrumentation noise |
| `terminal-vs-instrumental` | 2 | Deposit is terminal; detection is instrumental |
| `reconstruction-not-accumulation` | 1 | Constitution change, not chat drift |

### Real examples

```
# Architectural rationale — query by CCD axis name
/project:query --source docs "raven cost function"
/project:query --source docs "decision-boundary-externalization"
/project:query --source docs "fallacy as process failure"

# Past decision episodes — what we actually did
/project:query --source sessions "segmenter fix"
/project:query --source sessions "constraint amnesia"
/project:query --source sessions "FTS index"

# Code location — where something lives
/project:query --source code "deposit_to_memory_candidates"
/project:query --source code "query_sessions"
/project:query --source code "GovernorDaemon"

# Cross-source — broad search before narrowing
/project:query --source all "episode boundary"
/project:query --source all "BM25"

# Cross-project — query another supervised project via DuckDB ATTACH
/project:query --project modernizing-tool --source docs "causal chain"

# Limit results per source (default: 5)
/project:query --top 3 --source sessions "constraint store"
```

### When to use which source

| Situation | Recommended query |
|-----------|------------------|
| Starting a new phase — need governing rationale | `--source docs "axis-name"` |
| Debugging a component — need past decisions | `--source sessions "component name"` |
| Implementing a feature — need to find existing code | `--source code "function or class"` |
| Unknown territory — exploring a topic | `--source all "topic"` |
| Cross-project architectural alignment | `--project <id> --source docs "axis"` |

### Axis-query pattern (highest precision)

Querying by exact CCD axis name retrieves all indexed artifacts for that axis in one shot:

```
/project:query --source docs "closed-loop-to-specification"
/project:query --source docs "fallacy-as-process-failure"
/project:query --source docs "ground-truth-pointer"
```

This is the equivalent of "look up the governing principle before writing code" — the fastest path from cold session to architectural context.
