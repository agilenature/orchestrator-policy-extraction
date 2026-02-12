'use client';

import { useState } from 'react';
import { ConstraintForm, type ConstraintData } from './ConstraintForm';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Episode summary context displayed alongside the review widget. */
export interface EpisodeSummary {
  mode: string;
  goal: string;
  filesChanged: number;
  testsStatus: string;
  lintStatus: string;
}

export interface ReviewWidgetProps {
  episodeId: string;
  taskId: string;
  episodeSummary: EpisodeSummary;
}

/** Reaction label values matching the Python ReactionLabeler taxonomy. */
type ReactionLabel = 'approve' | 'correct' | 'redirect' | 'block' | 'question';

// ---------------------------------------------------------------------------
// Reaction button config
// ---------------------------------------------------------------------------

const REACTIONS: { label: ReactionLabel; icon: string; description: string; color: string }[] = [
  { label: 'approve', icon: '\u2713', description: 'Looks good', color: 'bg-green-100 hover:bg-green-200 text-green-800' },
  { label: 'correct', icon: '\u270E', description: 'Needs correction', color: 'bg-yellow-100 hover:bg-yellow-200 text-yellow-800' },
  { label: 'redirect', icon: '\u21BB', description: 'Wrong direction', color: 'bg-orange-100 hover:bg-orange-200 text-orange-800' },
  { label: 'block', icon: '\u2717', description: 'Stop this', color: 'bg-red-100 hover:bg-red-200 text-red-800' },
  { label: 'question', icon: '?', description: 'Need info', color: 'bg-blue-100 hover:bg-blue-200 text-blue-800' },
];

/** Reactions that trigger inline constraint extraction. */
const CONSTRAINT_REACTIONS: ReactionLabel[] = ['correct', 'block'];

/** Default severity mapping for constraint-triggering reactions. */
const DEFAULT_SEVERITY: Record<string, ConstraintData['severity']> = {
  correct: 'requires_approval',
  block: 'forbidden',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Review widget for episode reaction labeling.
 *
 * Displays 5 reaction buttons (approve, correct, redirect, block, question)
 * with an optional message field. When the user selects 'correct' or 'block',
 * an inline ConstraintForm is surfaced (not modal, per Pitfall 4) to extract
 * durable constraints from the correction feedback.
 *
 * Submits the reaction + optional constraint via PATCH /api/episodes/{id}.
 */
export function ReviewWidget({ episodeId, taskId, episodeSummary }: ReviewWidgetProps) {
  // --- State ---
  const [selectedReaction, setSelectedReaction] = useState<ReactionLabel | null>(null);
  const [message, setMessage] = useState('');
  const [showConstraintForm, setShowConstraintForm] = useState(false);
  const [constraintData, setConstraintData] = useState<ConstraintData | null>(null);
  const [constraintSkipped, setConstraintSkipped] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitted, setIsSubmitted] = useState(false);

  // --- Handlers ---

  const handleReactionSelect = (label: ReactionLabel) => {
    setSelectedReaction(label);
    setSubmitError(null);

    // Show constraint form for correct/block reactions
    if (CONSTRAINT_REACTIONS.includes(label)) {
      setShowConstraintForm(true);
      setConstraintSkipped(false);
    } else {
      setShowConstraintForm(false);
      setConstraintData(null);
      setConstraintSkipped(false);
    }
  };

  const handleConstraintSkip = () => {
    setShowConstraintForm(false);
    setConstraintData(null);
    setConstraintSkipped(true);
  };

  const handleSubmit = async () => {
    if (!selectedReaction) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      // Build request body
      const body: Record<string, unknown> = {
        reaction: {
          label: selectedReaction,
          message,
          confidence: 1.0,
        },
      };

      // Include constraint data if extracted (not skipped)
      if (constraintData && !constraintSkipped && showConstraintForm) {
        body.constraint = constraintData;
      }

      const response = await fetch(`/api/episodes/${episodeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(err.error || `HTTP ${response.status}`);
      }

      // If constraint was provided, also submit to constraint API
      if (constraintData && !constraintSkipped && showConstraintForm) {
        const constraintResponse = await fetch('/api/constraints', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: constraintData.text,
            severity: constraintData.severity,
            scope_paths: constraintData.scope_paths,
            detection_hints: constraintData.detection_hints,
            source_episode_id: episodeId,
            source_reaction_label: selectedReaction,
          }),
        });

        if (!constraintResponse.ok) {
          console.error('Failed to save constraint, but reaction was recorded');
        }
      }

      setIsSubmitted(true);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to submit reaction');
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Success state ---
  if (isSubmitted) {
    return (
      <div className="border border-green-300 bg-green-50 rounded p-4">
        <div className="flex items-center gap-2">
          <span className="text-green-600 text-lg">{'\u2713'}</span>
          <span className="text-sm font-medium text-green-800">
            Reaction recorded: {selectedReaction}
            {constraintData && !constraintSkipped ? ' (constraint extracted)' : ''}
          </span>
        </div>
      </div>
    );
  }

  // --- Render ---
  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-4">
      {/* Episode summary context */}
      <div className="text-xs text-gray-500 space-y-1">
        <div className="flex gap-4">
          <span>Mode: <span className="font-medium text-gray-700">{episodeSummary.mode}</span></span>
          <span>Files: <span className="font-medium text-gray-700">{episodeSummary.filesChanged}</span></span>
          <span>Tests: <span className="font-medium text-gray-700">{episodeSummary.testsStatus}</span></span>
          <span>Lint: <span className="font-medium text-gray-700">{episodeSummary.lintStatus}</span></span>
        </div>
        <div className="text-gray-600">{episodeSummary.goal}</div>
      </div>

      {/* Reaction buttons */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-2">Reaction</label>
        <div className="flex gap-2">
          {REACTIONS.map((r) => (
            <button
              key={r.label}
              type="button"
              disabled={isSubmitting}
              onClick={() => handleReactionSelect(r.label)}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium
                transition-colors border
                ${
                  selectedReaction === r.label
                    ? 'bg-blue-600 text-white border-blue-600'
                    : `${r.color} border-transparent`
                }
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
              title={r.description}
            >
              <span>{r.icon}</span>
              <span className="capitalize">{r.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Message textarea */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Feedback Message <span className="text-gray-400 font-normal">(optional)</span>
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={2}
          disabled={isSubmitting}
          className="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:ring-1 focus:ring-blue-400 focus:border-blue-400 disabled:opacity-50"
          placeholder="Add context about your reaction..."
        />
      </div>

      {/* Inline constraint form for correct/block reactions */}
      {selectedReaction && CONSTRAINT_REACTIONS.includes(selectedReaction) && !constraintSkipped && (
        <div className="space-y-2">
          {!showConstraintForm ? (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-yellow-700">Extract a constraint from this correction?</span>
              <button
                type="button"
                onClick={() => setShowConstraintForm(true)}
                className="px-2 py-1 bg-yellow-100 hover:bg-yellow-200 text-yellow-800 rounded text-xs font-medium"
              >
                Yes, extract constraint
              </button>
              <button
                type="button"
                onClick={handleConstraintSkip}
                className="px-2 py-1 text-gray-500 hover:text-gray-700 text-xs underline"
              >
                Skip constraint extraction
              </button>
            </div>
          ) : (
            <ConstraintForm
              initialText={message}
              initialSeverity={DEFAULT_SEVERITY[selectedReaction] ?? 'requires_approval'}
              onChange={setConstraintData}
              onSkip={handleConstraintSkip}
            />
          )}
        </div>
      )}

      {/* Error display */}
      {submitError && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {submitError}
        </div>
      )}

      {/* Submit button */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!selectedReaction || isSubmitting}
          className={`
            px-4 py-2 rounded text-sm font-medium transition-colors
            ${
              selectedReaction && !isSubmitting
                ? 'bg-blue-600 hover:bg-blue-700 text-white'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }
          `}
        >
          {isSubmitting ? 'Submitting...' : 'Submit Reaction'}
        </button>
      </div>
    </div>
  );
}
