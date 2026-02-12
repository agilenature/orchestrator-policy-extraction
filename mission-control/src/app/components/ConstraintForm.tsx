'use client';

import { useState, useEffect } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Structured constraint data extracted from a review correction. */
export interface ConstraintData {
  text: string;
  severity: 'warning' | 'requires_approval' | 'forbidden';
  scope_paths: string[];
  detection_hints: string[];
}

export interface ConstraintFormProps {
  /** Pre-populated constraint text (from the review message textarea). */
  initialText: string;
  /** Default severity based on reaction type (requires_approval for correct, forbidden for block). */
  initialSeverity: 'warning' | 'requires_approval' | 'forbidden';
  /** Called on every field change so parent has current state. */
  onChange: (constraint: ConstraintData) => void;
  /** Called when user explicitly skips constraint extraction. */
  onSkip: () => void;
}

// ---------------------------------------------------------------------------
// Severity options
// ---------------------------------------------------------------------------

const SEVERITY_OPTIONS: { value: ConstraintData['severity']; label: string; description: string }[] = [
  { value: 'warning', label: 'Warning', description: 'Flagged but allowed to proceed' },
  { value: 'requires_approval', label: 'Requires Approval', description: 'Must get human sign-off' },
  { value: 'forbidden', label: 'Forbidden', description: 'Never allowed, auto-blocked' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Inline constraint extraction form.
 *
 * Rendered within ReviewWidget when the user selects a 'correct' or 'block'
 * reaction. Pre-populates text and severity from the parent's context.
 * Surfaced inline (not modal) per Pitfall 4 guidance -- corrections should
 * always prompt for constraint extraction to capture durable rules.
 */
export function ConstraintForm({
  initialText,
  initialSeverity,
  onChange,
  onSkip,
}: ConstraintFormProps) {
  const [text, setText] = useState(initialText);
  const [severity, setSeverity] = useState<ConstraintData['severity']>(initialSeverity);
  const [scopePathsInput, setScopePathsInput] = useState('');
  const [detectionHintsInput, setDetectionHintsInput] = useState('');

  // Parse comma-separated inputs into arrays
  const parseCsv = (input: string): string[] =>
    input
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

  // Notify parent of every change
  useEffect(() => {
    onChange({
      text,
      severity,
      scope_paths: parseCsv(scopePathsInput),
      detection_hints: parseCsv(detectionHintsInput),
    });
  }, [text, severity, scopePathsInput, detectionHintsInput]);

  return (
    <div className="border border-yellow-300 bg-yellow-50 rounded p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-yellow-800">
          Extract Constraint from Correction
        </h4>
        <button
          type="button"
          onClick={onSkip}
          className="text-xs text-gray-500 hover:text-gray-700 underline"
        >
          Skip constraint extraction
        </button>
      </div>

      {/* Constraint text */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Constraint Text
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:ring-1 focus:ring-yellow-400 focus:border-yellow-400"
          placeholder="Describe the constraint (e.g., 'Never modify production database without backup')"
        />
      </div>

      {/* Severity */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Severity
        </label>
        <div className="flex gap-4">
          {SEVERITY_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name="constraint-severity"
                value={opt.value}
                checked={severity === opt.value}
                onChange={() => setSeverity(opt.value)}
                className="text-yellow-600 focus:ring-yellow-400"
              />
              <span className="text-xs">
                <span className="font-medium">{opt.label}</span>
                <span className="text-gray-500 ml-1">- {opt.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Scope paths */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Scope Paths <span className="text-gray-400 font-normal">(comma-separated)</span>
        </label>
        <input
          type="text"
          value={scopePathsInput}
          onChange={(e) => setScopePathsInput(e.target.value)}
          className="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:ring-1 focus:ring-yellow-400 focus:border-yellow-400"
          placeholder="e.g., src/api/, src/db/migrations/"
        />
      </div>

      {/* Detection hints */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Detection Hints <span className="text-gray-400 font-normal">(comma-separated, optional)</span>
        </label>
        <input
          type="text"
          value={detectionHintsInput}
          onChange={(e) => setDetectionHintsInput(e.target.value)}
          className="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:ring-1 focus:ring-yellow-400 focus:border-yellow-400"
          placeholder="e.g., DROP TABLE, rm -rf, force push"
        />
      </div>
    </div>
  );
}
