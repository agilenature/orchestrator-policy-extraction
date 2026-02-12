/**
 * Mapper functions that convert Mission Control task data into structured
 * episode schema fields.
 *
 * All interfaces use snake_case field names matching the Pydantic Episode
 * model in src/pipeline/models/episodes.py for SQLite-DuckDB compatibility.
 *
 * Three main mappers:
 *   - taskToObservation: MC task -> Observation (what the orchestrator sees)
 *   - planningOutputToAction: planning output string -> OrchestratorAction
 *   - executionToOutcome: execution metrics -> OutcomeQuality
 *
 * @module mapper
 */

// ---------------------------------------------------------------------------
// Interfaces (snake_case, matching Pydantic Episode model)
// ---------------------------------------------------------------------------

/** Repository diff statistics. */
export interface DiffStat {
  files: number;
  insertions: number;
  deletions: number;
}

/** Repository state at the decision point. */
export interface RepoState {
  changed_files: string[];
  diff_stat: DiffStat;
  hotspots: string[];
}

/** Test execution state. */
export interface TestState {
  status: "unknown" | "pass" | "fail" | "not_run";
  last_command: string | null;
  failing: string[];
}

/** Lint execution state. */
export interface LintState {
  status: "unknown" | "pass" | "fail" | "not_run";
  last_command: string | null;
  issues_count: number | null;
}

/** Build execution state. */
export interface BuildState {
  status: "unknown" | "pass" | "fail" | "not_run";
  last_command: string | null;
}

/** Code quality state (tests, lint, build). */
export interface QualityState {
  tests: TestState;
  lint: LintState;
  build: BuildState | null;
}

/** Contextual state at the decision point. */
export interface ContextState {
  recent_summary: string;
  open_questions: string[];
  constraints_in_force: string[];
}

/** What the orchestrator observes before making a decision. */
export interface Observation {
  repo_state: RepoState;
  quality_state: QualityState;
  context: ContextState;
}

/** File/path scope for an action. */
export interface Scope {
  paths: string[];
  avoid: string[];
}

/** A gate/check required before proceeding. */
export interface Gate {
  type:
    | "require_human_approval"
    | "run_tests"
    | "run_lint"
    | "diff_size_cap"
    | "no_write_before_plan"
    | "protected_paths"
    | "no_network"
    | "no_secrets_access";
  params: Record<string, unknown> | null;
}

/** The orchestrator's decision/action at a decision point. */
export interface OrchestratorAction {
  mode:
    | "Explore"
    | "Plan"
    | "Implement"
    | "Verify"
    | "Integrate"
    | "Triage"
    | "Refactor";
  goal: string;
  scope: Scope;
  executor_instruction: string;
  gates: Gate[];
  risk: "low" | "medium" | "high" | "critical";
  expected_artifacts: string[];
}

/** Quality metrics after executor execution. */
export interface OutcomeQuality {
  tests_status: "unknown" | "pass" | "fail" | "not_run";
  lint_status: "unknown" | "pass" | "fail" | "not_run";
  diff_stat: DiffStat;
  build_status: "unknown" | "pass" | "fail" | "not_run" | null;
}

/** What the executor actually did. */
export interface ExecutorEffects {
  tool_calls_count: number;
  files_touched: string[];
  commands_ran: string[];
  git_events: Array<{
    type: string;
    ref: string | null;
    message: string | null;
  }>;
}

/** Result of executor execution. */
export interface Outcome {
  executor_effects: ExecutorEffects;
  quality: OutcomeQuality;
  reaction: Reaction | null;
  reward_signals: Record<string, unknown>;
}

/** Human reaction to the outcome. */
export interface Reaction {
  label:
    | "approve"
    | "correct"
    | "redirect"
    | "block"
    | "question"
    | "unknown";
  message: string;
  confidence: number;
}

/** A constraint reference. */
export interface ConstraintRef {
  constraint_id: string;
  text: string;
  severity: "warning" | "requires_approval" | "forbidden";
  scope: { paths: string[] };
  detection_hints: string[];
}

/** Test result from execution. */
export interface TestResult {
  status: "pass" | "fail" | "not_run";
  command: string;
  failing: string[];
}

/** Mission Control task structure. */
export interface MCTask {
  id: string;
  title: string;
  description: string;
  status: string;
  planning_output?: string;
  agent_id?: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Mode keywords for heuristic extraction from prose
// ---------------------------------------------------------------------------

const MODE_KEYWORDS: Record<OrchestratorAction["mode"], string[]> = {
  Explore: ["explore", "investigate", "research", "understand", "analyze"],
  Plan: ["plan", "design", "architect", "outline", "structure"],
  Implement: ["implement", "build", "create", "add", "write", "develop"],
  Verify: ["verify", "test", "validate", "check", "confirm"],
  Integrate: ["integrate", "merge", "connect", "wire", "compose"],
  Triage: ["triage", "debug", "diagnose", "troubleshoot", "fix"],
  Refactor: ["refactor", "clean", "reorganize", "restructure", "simplify"],
};

/** File path regex: matches paths like src/foo/bar.ts, ./lib/index.js */
const FILE_PATH_REGEX = /(?:\.\/|[a-zA-Z][\w-]*\/)[^\s,;)'"]+\.[a-zA-Z]{1,5}/g;

// ---------------------------------------------------------------------------
// Mapper functions
// ---------------------------------------------------------------------------

/**
 * Map a Mission Control task to an Observation.
 *
 * Derives the observation (what the orchestrator sees) from task title,
 * description, and optional repo state. Quality state defaults to unknown
 * when not provided.
 *
 * @param task - The MC task to map.
 * @param repoState - Optional repository state snapshot.
 * @param constraintsInForce - Optional list of active constraint IDs.
 * @returns Observation with repo_state, quality_state, and context.
 */
export function taskToObservation(
  task: MCTask,
  repoState?: RepoState,
  constraintsInForce?: string[]
): Observation {
  const defaultRepoState: RepoState = {
    changed_files: [],
    diff_stat: { files: 0, insertions: 0, deletions: 0 },
    hotspots: [],
  };

  const defaultQualityState: QualityState = {
    tests: { status: "unknown", last_command: null, failing: [] },
    lint: { status: "unknown", last_command: null, issues_count: null },
    build: null,
  };

  // Build recent_summary from task title and description
  const summary = task.description
    ? `${task.title}: ${task.description}`
    : task.title;

  return {
    repo_state: repoState ?? defaultRepoState,
    quality_state: defaultQualityState,
    context: {
      recent_summary: summary,
      open_questions: [],
      constraints_in_force: constraintsInForce ?? [],
    },
  };
}

/**
 * Parse planning output into a structured OrchestratorAction.
 *
 * Uses a HYBRID approach:
 *   1. Try JSON.parse first (for structured planning output)
 *   2. Fall back to heuristic extraction from prose text
 *
 * Heuristic extraction scans for:
 *   - Mode keywords (Explore/Plan/Implement/Verify/Integrate/Triage/Refactor)
 *   - File paths for scope
 *   - Default risk to 'medium'
 *
 * @param planningOutput - Raw planning output string (JSON or prose).
 * @returns Structured OrchestratorAction.
 */
export function planningOutputToAction(
  planningOutput: string
): OrchestratorAction {
  // --- Attempt 1: Structured JSON parse ---
  try {
    const parsed = JSON.parse(planningOutput);
    if (parsed && typeof parsed === "object" && parsed.mode && parsed.goal) {
      return {
        mode: parsed.mode,
        goal: parsed.goal,
        scope: parsed.scope ?? { paths: [], avoid: [] },
        executor_instruction: parsed.executor_instruction ?? parsed.goal,
        gates: parsed.gates ?? [],
        risk: parsed.risk ?? "medium",
        expected_artifacts: parsed.expected_artifacts ?? [],
      };
    }
  } catch {
    // Not valid JSON -- fall through to heuristic
  }

  // --- Attempt 2: Heuristic extraction from prose ---
  const lowerText = planningOutput.toLowerCase();

  // Detect mode from keywords (first match wins)
  let detectedMode: OrchestratorAction["mode"] = "Implement";
  for (const [mode, keywords] of Object.entries(MODE_KEYWORDS)) {
    const found = keywords.some((kw) => {
      const regex = new RegExp(`\\b${kw}\\b`, "i");
      return regex.test(lowerText);
    });
    if (found) {
      detectedMode = mode as OrchestratorAction["mode"];
      break;
    }
  }

  // Extract file paths for scope
  const pathMatches = planningOutput.match(FILE_PATH_REGEX) ?? [];
  const uniquePaths = [...new Set(pathMatches)];

  // Use the full planning output as the goal
  const goal =
    planningOutput.length > 200
      ? planningOutput.slice(0, 200) + "..."
      : planningOutput;

  return {
    mode: detectedMode,
    goal,
    scope: { paths: uniquePaths, avoid: [] },
    executor_instruction: planningOutput,
    gates: [],
    risk: "medium",
    expected_artifacts: [],
  };
}

/**
 * Aggregate execution data into OutcomeQuality fields.
 *
 * Maps tool call counts, file touches, and test results into the
 * standardized quality metrics structure.
 *
 * @param toolCalls - Number of tool calls made during execution.
 * @param filesTouched - List of files modified during execution.
 * @param commandsRan - List of commands executed.
 * @param testResults - Optional test execution results.
 * @returns OutcomeQuality with aggregated metrics.
 */
export function executionToOutcome(
  toolCalls: number,
  filesTouched: string[],
  commandsRan: string[],
  testResults?: TestResult
): OutcomeQuality {
  return {
    tests_status: testResults?.status ?? "not_run",
    lint_status: "unknown",
    diff_stat: {
      files: filesTouched.length,
      insertions: 0,
      deletions: 0,
    },
    build_status: null,
  };
}
