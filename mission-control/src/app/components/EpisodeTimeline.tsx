'use client';

import { useState, useEffect, useRef } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single entry in the episode timeline. */
interface TimelineEntry {
  timestamp: string;
  event_type: string;
  summary: string;
}

export interface EpisodeTimelineProps {
  episodeId: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a timestamp as a relative time string (e.g., "2m ago"). */
function relativeTime(isoTimestamp: string): string {
  const now = Date.now();
  const then = new Date(isoTimestamp).getTime();
  const diffMs = now - then;

  if (diffMs < 0) return 'just now';

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Map event_type to a display color for the timeline dot. */
function eventColor(eventType: string): string {
  switch (eventType) {
    case 'episode_created':
      return 'bg-green-500';
    case 'episode_provenance':
      return 'bg-blue-500';
    case 'episode_reviewed':
      return 'bg-yellow-500';
    case 'constraint_extracted':
      return 'bg-red-500';
    default:
      return 'bg-gray-400';
  }
}

/** Extract a human-readable summary from event data. */
function extractSummary(data: Record<string, unknown>): string {
  if (typeof data.summary === 'string') return data.summary;
  if (typeof data.event_type === 'string' && typeof data.data === 'object' && data.data !== null) {
    const inner = data.data as Record<string, unknown>;
    if (typeof inner.summary === 'string') return inner.summary;
  }
  // Fallback: use event_type as summary
  if (typeof data.event_type === 'string') {
    return data.event_type.replace(/_/g, ' ');
  }
  return 'Event';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Live episode event timeline using Server-Sent Events.
 *
 * On mount, backfills existing events via GET /api/episodes/{id}/events,
 * then connects to /api/episodes/stream via EventSource to receive live
 * episode_provenance events matching the episodeId prop.
 *
 * Renders events as a vertical timeline with colored dots, type labels,
 * summaries, and relative timestamps. Auto-scrolls to the latest entry.
 */
export function EpisodeTimeline({ episodeId }: EpisodeTimelineProps) {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest entry
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries]);

  // Backfill existing events on mount
  useEffect(() => {
    async function backfill() {
      try {
        const response = await fetch(`/api/episodes/${episodeId}/events`);
        if (!response.ok) return;

        const events = await response.json() as Record<string, unknown>[];
        const backfilled: TimelineEntry[] = events.map((ev) => ({
          timestamp: (ev.timestamp as string) ?? new Date().toISOString(),
          event_type: (ev.event_type as string) ?? 'unknown',
          summary: typeof ev.payload === 'string'
            ? extractSummary(JSON.parse(ev.payload))
            : extractSummary(ev.payload as Record<string, unknown> ?? {}),
        }));

        setEntries(backfilled);
      } catch (err) {
        console.error('[EpisodeTimeline] Failed to backfill events:', err);
      }
    }

    backfill();
  }, [episodeId]);

  // SSE connection for live events
  useEffect(() => {
    const eventSource = new EventSource('/api/episodes/stream');

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    eventSource.onerror = () => {
      setIsConnected(false);
    };

    // Listen for all episode event types
    const eventTypes = [
      'episode_created',
      'episode_provenance',
      'episode_reviewed',
      'constraint_extracted',
    ];

    for (const eventType of eventTypes) {
      eventSource.addEventListener(eventType, (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data) as Record<string, unknown>;

          // Only show events for this episode
          if (data.episode_id !== episodeId) return;

          const entry: TimelineEntry = {
            timestamp: (data.timestamp as string) ?? new Date().toISOString(),
            event_type: (data.type as string) ?? eventType,
            summary: extractSummary(data),
          };

          setEntries((prev) => [...prev, entry]);
        } catch (err) {
          console.error('[EpisodeTimeline] Failed to parse SSE event:', err);
        }
      });
    }

    // Cleanup on unmount
    return () => {
      eventSource.close();
      setIsConnected(false);
    };
  }, [episodeId]);

  return (
    <div className="border border-gray-200 rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">Episode Timeline</h3>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-300'}`}
          />
          <span className="text-xs text-gray-500">
            {isConnected ? 'Live' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Timeline */}
      <div
        ref={scrollRef}
        className="relative border-l-2 border-gray-200 pl-4 space-y-3 max-h-96 overflow-y-auto"
      >
        {entries.length === 0 ? (
          <p className="text-xs text-gray-400 py-2">No events yet</p>
        ) : (
          entries.map((entry, index) => (
            <div key={`${entry.timestamp}-${index}`} className="relative">
              {/* Timeline dot */}
              <span
                className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full border-2 border-white ${eventColor(entry.event_type)}`}
              />

              {/* Event content */}
              <div className="text-sm">
                <span className="inline-block px-1.5 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded mr-2">
                  {entry.event_type.replace(/_/g, ' ')}
                </span>
                <span className="text-gray-700">{entry.summary}</span>
                <span className="text-xs text-gray-400 ml-2">
                  {relativeTime(entry.timestamp)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
