import { isSseEventName, type SseFrame } from "./types";

/**
 * Incremental SSE parser. Feed it raw text chunks as they arrive from a
 * fetch() ReadableStream (which does not respect frame boundaries), and it
 * emits fully-parsed, schema-validated SseFrame objects as soon as a
 * complete event ("event:" + "data:" + blank line) has been buffered.
 *
 * Frames whose event name is not one of the six known types, or whose data
 * fails to parse as JSON, are dropped with a console warning rather than
 * thrown — a forward-compatible server should not crash the tab.
 */
export class SseStreamParser {
  private buffer = "";

  /** Push a raw text chunk (already UTF-8 decoded). Returns any frames that
   * became complete as a result. */
  push(chunk: string): SseFrame[] {
    this.buffer += chunk;
    const frames: SseFrame[] = [];

    // SSE events are separated by a blank line (\n\n). Normalize CRLF first.
    this.buffer = this.buffer.replace(/\r\n/g, "\n");

    let boundary = this.buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const frame = parseOneEvent(rawEvent);
      if (frame) frames.push(frame);
      boundary = this.buffer.indexOf("\n\n");
    }

    return frames;
  }

  /** Flush any trailing buffered event that wasn't terminated by a final
   * blank line (some servers omit the trailing separator on stream close). */
  flush(): SseFrame[] {
    if (!this.buffer.trim()) {
      this.buffer = "";
      return [];
    }
    const frame = parseOneEvent(this.buffer);
    this.buffer = "";
    return frame ? [frame] : [];
  }
}

function parseOneEvent(rawEvent: string): SseFrame | null {
  let eventName: string | null = null;
  const dataLines: string[] = [];

  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
    // Comments (lines starting with ":") and ids are ignored — the protocol
    // in contracts/sse-frames.schema.json doesn't use them.
  }

  if (!eventName || dataLines.length === 0) return null;
  if (!isSseEventName(eventName)) {
    console.warn(`[sse] unknown event name, dropping frame: ${eventName}`);
    return null;
  }

  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch (err) {
    console.warn(`[sse] failed to parse data JSON for event "${eventName}"`, err);
    return null;
  }

  // Construct the discriminated frame. TypeScript can't narrow `data`'s shape
  // from a runtime string, so we assert the pairing here; the discriminant
  // itself came from the same validated enum, and callers switch on it.
  return { event: eventName, data } as SseFrame;
}

/** Parse a complete, static SSE text blob in one shot (fixtures, tests). */
export function parseSseText(text: string): SseFrame[] {
  const parser = new SseStreamParser();
  const frames = parser.push(text);
  frames.push(...parser.flush());
  return frames;
}

/**
 * Read a fetch Response's body as an SSE stream, invoking `onFrame` for each
 * parsed frame in arrival order. Resolves when the stream closes.
 */
export async function consumeSseResponse(
  response: Response,
  onFrame: (frame: SseFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.body) {
    throw new Error("Response has no body to stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseStreamParser();

  const abortListener = () => {
    void reader.cancel();
  };
  signal?.addEventListener("abort", abortListener);

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      for (const frame of parser.push(text)) onFrame(frame);
    }
    for (const frame of parser.flush()) onFrame(frame);
  } finally {
    signal?.removeEventListener("abort", abortListener);
  }
}
