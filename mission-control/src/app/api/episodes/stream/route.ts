/**
 * SSE endpoint for live episode event broadcasting.
 *
 * Maintains a set of connected writers and broadcasts episode lifecycle
 * events to all of them. Other modules call broadcastEpisodeEvent() to
 * push events to connected dashboard clients.
 *
 * Event types: episode_created, episode_provenance, episode_reviewed,
 * constraint_extracted (matching research Pattern 5).
 *
 * Sends keep-alive comments every 30 seconds to prevent connection timeout.
 *
 * @module api/episodes/stream
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** SSE event types for episode lifecycle broadcasting. */
export type EpisodeSSEEventType =
  | 'episode_created'
  | 'episode_provenance'
  | 'episode_reviewed'
  | 'constraint_extracted';

/** Structured SSE event payload. */
export interface EpisodeSSEEvent {
  type: EpisodeSSEEventType;
  episode_id: string;
  timestamp: string;
  data: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// In-memory event bus
// ---------------------------------------------------------------------------

/** Active SSE writers. Each connected client gets a writer in this set. */
const activeWriters = new Set<WritableStreamDefaultWriter<Uint8Array>>();

const encoder = new TextEncoder();

/**
 * Broadcast an episode event to all connected SSE clients.
 *
 * Called by other modules (e.g., constraint API, episode lifecycle hooks)
 * to push real-time updates to the dashboard.
 */
export function broadcastEpisodeEvent(event: EpisodeSSEEvent): void {
  const message = `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
  const encoded = encoder.encode(message);

  for (const writer of activeWriters) {
    writer.write(encoded).catch(() => {
      // Writer is closed/broken -- will be cleaned up by the close handler
      activeWriters.delete(writer);
    });
  }
}

// ---------------------------------------------------------------------------
// SSE GET handler
// ---------------------------------------------------------------------------

/**
 * GET /api/episodes/stream
 *
 * Returns a Server-Sent Events stream. The client connects via EventSource
 * and receives episode lifecycle events as they occur.
 *
 * Keep-alive comments are sent every 30 seconds to prevent proxy/browser
 * timeout of idle connections.
 */
export async function GET(): Promise<Response> {
  const stream = new TransformStream<Uint8Array, Uint8Array>();
  const writer = stream.writable.getWriter();

  // Register this writer in the active set
  activeWriters.add(writer);

  // Send initial connection confirmation
  const welcome = encoder.encode(`:connected\n\n`);
  writer.write(welcome).catch(() => {
    activeWriters.delete(writer);
  });

  // Keep-alive interval (30 seconds)
  const keepAliveInterval = setInterval(() => {
    const keepAlive = encoder.encode(`:keep-alive\n\n`);
    writer.write(keepAlive).catch(() => {
      // Connection broken, clean up
      clearInterval(keepAliveInterval);
      activeWriters.delete(writer);
    });
  }, 30_000);

  // Clean up on client disconnect
  writer.closed
    .then(() => {
      clearInterval(keepAliveInterval);
      activeWriters.delete(writer);
    })
    .catch(() => {
      clearInterval(keepAliveInterval);
      activeWriters.delete(writer);
    });

  return new Response(stream.readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
