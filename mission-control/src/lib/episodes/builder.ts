/**
 * EpisodeBuilder tracks the full task lifecycle and creates structured
 * episode records in SQLite via the CRUD layer.
 *
 * Lifecycle transitions:
 *   CREATED -> PLANNING -> EXECUTION -> TESTING -> REVIEW -> COMPLETED
 *
 * Each transition method:
 *   1. Validates the episode is in the expected state (idempotent -- warns on skip)
 *   2. Updates the episode record via CRUD functions
 *   3. Inserts a 'lifecycle' event for provenance
 *   4. All writes are wrapped in try/catch (never crashes the task lifecycle)
 *
 * @module builder
 */

import { randomUUID } from "crypto";
import type Database from "better-sqlite3";

import {
  createEpisode,
  updateEpisodeReaction,
  insertEpisodeEvent,
  getEpisode,
} from "../db/episodes";

import {
  taskToObservation,
  planningOutputToAction,
  executionToOutcome,
} from "./mapper";

import type {
  MCTask,
  RepoState,
  Reaction,
  ConstraintRef,
  Outcome,
  TestResult,
} from "./mapper";

// Re-export types that consumers of builder will need
export type { MCTask, Reaction, ConstraintRef, TestResult };

// ---------------------------------------------------------------------------
// Status progression for idempotency checks
// ---------------------------------------------------------------------------

/** Ordered lifecycle statuses. Higher index = further along. */
const STATUS_ORDER: Record<string, number> = {
  pending: 0,
  in_progress: 1,
  review: 2,
  completed: 3,
};

// ---------------------------------------------------------------------------
// EpisodeBuilder
// ---------------------------------------------------------------------------

/**
 * Tracks episode lifecycle from Mission Control task transitions.
 *
 * Each method corresponds to a task state change and populates the
 * corresponding episode fields. Methods are idempotent: calling them
 * when the episode is already at or past the expected state logs a
 * warning and returns without error.
 */
export class EpisodeBuilder {
  private db: Database.Database;

  constructor(db: Database.Database) {
    this.db = db;
  }

  // -----------------------------------------------------------------------
  // Lifecycle methods
  // -----------------------------------------------------------------------

  /**
   * Handle CREATED transition: create a new episode from a task.
   *
   * Creates the episode record with:
   *   - episode_id: crypto.randomUUID()
   *   - task_id: from the MC task
   *   - status: 'pending'
   *   - observation: derived from task via taskToObservation()
   *
   * @param task - The MC task that was just created.
   * @param repoState - Optional repository state snapshot.
   * @returns The generated episode_id, or null on error.
   */
  onTaskCreated(task: MCTask, repoState?: RepoState): string | null {
    try {
      const episodeId = randomUUID();
      const now = new Date().toISOString();
      const observation = taskToObservation(task, repoState);

      createEpisode(this.db, {
        episode_id: episodeId,
        task_id: task.id,
        timestamp: now,
        status: "pending",
        observation,
        project: {
          repo_path: ".",
        },
      });

      this.insertLifecycleEvent(episodeId, "created", {
        task_id: task.id,
        task_title: task.title,
        task_status: task.status,
      });

      return episodeId;
    } catch (err) {
      console.warn(
        `[EpisodeBuilder] onTaskCreated failed for task ${task.id}:`,
        err
      );
      return null;
    }
  }

  /**
   * Handle PLANNING COMPLETE transition: populate orchestrator_action.
   *
   * Parses planning output via planningOutputToAction() (hybrid JSON/prose)
   * and updates the episode's orchestrator_action JSON column plus flat
   * mode and risk columns.
   *
   * @param episodeId - The episode to update.
   * @param planningOutput - Raw planning output string.
   */
  onPlanningComplete(episodeId: string, planningOutput: string): void {
    try {
      if (!this.checkAndWarnStatus(episodeId, "pending")) return;

      const action = planningOutputToAction(planningOutput);

      const stmt = this.db.prepare(`
        UPDATE episodes SET
          orchestrator_action = @orchestrator_action,
          mode = @mode,
          risk = @risk,
          updated_at = datetime('now')
        WHERE episode_id = @episode_id
      `);

      stmt.run({
        orchestrator_action: JSON.stringify(action),
        mode: action.mode,
        risk: action.risk,
        episode_id: episodeId,
      });

      this.insertLifecycleEvent(episodeId, "planning_complete", {
        mode: action.mode,
        risk: action.risk,
        scope_paths: action.scope.paths,
      });
    } catch (err) {
      console.warn(
        `[EpisodeBuilder] onPlanningComplete failed for ${episodeId}:`,
        err
      );
    }
  }

  /**
   * Handle EXECUTION STARTED transition: set status to in_progress.
   *
   * @param episodeId - The episode to update.
   */
  onExecutionStarted(episodeId: string): void {
    try {
      if (!this.checkAndWarnStatus(episodeId, "pending")) return;

      this.db
        .prepare(
          `UPDATE episodes SET status = 'in_progress', updated_at = datetime('now') WHERE episode_id = ?`
        )
        .run(episodeId);

      this.insertLifecycleEvent(episodeId, "execution_started", {});
    } catch (err) {
      console.warn(
        `[EpisodeBuilder] onExecutionStarted failed for ${episodeId}:`,
        err
      );
    }
  }

  /**
   * Handle TESTING COMPLETE transition: update outcome quality with test results.
   *
   * @param episodeId - The episode to update.
   * @param testResults - Test execution results.
   */
  onTestingComplete(episodeId: string, testResults: TestResult): void {
    try {
      if (!this.checkAndWarnStatus(episodeId, "in_progress")) return;

      // Update or create outcome JSON with quality.tests_status
      const episode = getEpisode(this.db, episodeId);
      const existingOutcome = episode?.outcome
        ? JSON.parse(episode.outcome as string)
        : {};

      const quality = existingOutcome.quality ?? {};
      quality.tests_status = testResults.status;

      existingOutcome.quality = quality;

      this.db
        .prepare(
          `UPDATE episodes SET outcome = @outcome, updated_at = datetime('now') WHERE episode_id = @episode_id`
        )
        .run({
          outcome: JSON.stringify(existingOutcome),
          episode_id: episodeId,
        });

      this.insertLifecycleEvent(episodeId, "testing_complete", {
        tests_status: testResults.status,
        failing: testResults.failing,
        command: testResults.command,
      });
    } catch (err) {
      console.warn(
        `[EpisodeBuilder] onTestingComplete failed for ${episodeId}:`,
        err
      );
    }
  }

  /**
   * Handle REVIEW READY transition: populate outcome and set status to review.
   *
   * @param episodeId - The episode to update.
   * @param outcomeData - Partial outcome data to merge into the episode.
   */
  onReviewReady(
    episodeId: string,
    outcomeData: Partial<Outcome>
  ): void {
    try {
      if (!this.checkAndWarnStatus(episodeId, "in_progress")) return;

      // Merge with existing outcome (preserves test results from onTestingComplete)
      const episode = getEpisode(this.db, episodeId);
      const existingOutcome = episode?.outcome
        ? JSON.parse(episode.outcome as string)
        : {};

      const merged = { ...existingOutcome, ...outcomeData };

      this.db
        .prepare(
          `UPDATE episodes SET outcome = @outcome, status = 'review', updated_at = datetime('now') WHERE episode_id = @episode_id`
        )
        .run({
          outcome: JSON.stringify(merged),
          episode_id: episodeId,
        });

      this.insertLifecycleEvent(episodeId, "review_ready", {
        status: "review",
      });
    } catch (err) {
      console.warn(
        `[EpisodeBuilder] onReviewReady failed for ${episodeId}:`,
        err
      );
    }
  }

  /**
   * Handle REVIEW COMPLETE transition: store reaction and set status to completed.
   *
   * Calls updateEpisodeReaction() from the CRUD layer to update the flat
   * reaction columns and merge into outcome JSON.
   *
   * @param episodeId - The episode to update.
   * @param reaction - Human reaction to the outcome.
   * @param constraintRefs - Optional constraints extracted from this reaction.
   */
  onReviewComplete(
    episodeId: string,
    reaction: Reaction,
    constraintRefs?: ConstraintRef[]
  ): void {
    try {
      if (!this.checkAndWarnStatus(episodeId, "review")) return;

      updateEpisodeReaction(this.db, episodeId, {
        label: reaction.label,
        message: reaction.message,
        confidence: reaction.confidence,
      });

      // Store extracted constraints if any
      if (constraintRefs && constraintRefs.length > 0) {
        this.db
          .prepare(
            `UPDATE episodes SET constraints_extracted = @constraints, updated_at = datetime('now') WHERE episode_id = @episode_id`
          )
          .run({
            constraints: JSON.stringify(constraintRefs),
            episode_id: episodeId,
          });
      }

      this.insertLifecycleEvent(episodeId, "review_complete", {
        reaction_label: reaction.label,
        reaction_confidence: reaction.confidence,
        constraints_extracted: constraintRefs?.length ?? 0,
      });
    } catch (err) {
      console.warn(
        `[EpisodeBuilder] onReviewComplete failed for ${episodeId}:`,
        err
      );
    }
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  /**
   * Check if episode is at or past the expected status.
   *
   * If the episode is already past the expected status, logs a warning
   * and returns false (caller should skip the update). If the episode
   * is at the expected status or earlier, returns true (proceed).
   *
   * @param episodeId - Episode to check.
   * @param expectedStatus - The minimum status required.
   * @returns true if the update should proceed, false to skip.
   */
  private checkAndWarnStatus(
    episodeId: string,
    expectedStatus: string
  ): boolean {
    const episode = getEpisode(this.db, episodeId);
    if (!episode) {
      console.warn(
        `[EpisodeBuilder] Episode ${episodeId} not found, skipping update`
      );
      return false;
    }

    const currentOrder = STATUS_ORDER[episode.status as string] ?? -1;
    const expectedOrder = STATUS_ORDER[expectedStatus] ?? -1;

    if (currentOrder > expectedOrder) {
      console.warn(
        `[EpisodeBuilder] Episode ${episodeId} already at '${episode.status}' ` +
          `(past expected '${expectedStatus}'), skipping`
      );
      return false;
    }

    return true;
  }

  /**
   * Insert a lifecycle event for provenance tracking.
   *
   * @param episodeId - Episode to attach the event to.
   * @param transition - Name of the lifecycle transition.
   * @param details - Additional details for the event payload.
   */
  private insertLifecycleEvent(
    episodeId: string,
    transition: string,
    details: Record<string, unknown>
  ): void {
    const now = new Date().toISOString();
    try {
      insertEpisodeEvent(this.db, {
        event_id: randomUUID(),
        episode_id: episodeId,
        timestamp: now,
        received_at: now,
        event_type: "lifecycle",
        payload: { transition, ...details },
      });
    } catch (err) {
      // Non-fatal: lifecycle events are for provenance, not correctness
      console.warn(
        `[EpisodeBuilder] Failed to insert lifecycle event for ${episodeId}:`,
        err
      );
    }
  }
}
