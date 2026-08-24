/**
 * Discriminated union matching contracts/sse-frames.schema.json exactly.
 * The `event` field is the discriminant, mirroring the SSE `event:` name.
 */

export type StageName = "thinking" | "retrieving" | "drafting" | "outlining" | "assembling";

export interface StageFrame {
  event: "stage";
  data: {
    stage: StageName;
    detail: string | null;
  };
}

export interface TokenFrame {
  event: "token";
  data: {
    text: string;
  };
}

export interface CitationFrame {
  event: "citation";
  data: {
    chunk_id: number;
    episode: string;
    guest: string;
    rank: number;
    score: number;
  };
}

export interface ArtifactFrame {
  event: "artifact";
  data: {
    artifact_id: string;
    kind: "markdown" | "html";
    title: string;
  };
}

export interface ErrorFrame {
  event: "error";
  data: {
    code: string;
    message: string;
    retryable: boolean;
    partial?: boolean;
  };
}

export interface DoneFrame {
  event: "done";
  data: {
    message_id: string;
    latency_ms: number;
    abstained: boolean;
  };
}

export type SseFrame = StageFrame | TokenFrame | CitationFrame | ArtifactFrame | ErrorFrame | DoneFrame;

export const SSE_EVENT_NAMES = ["stage", "token", "citation", "artifact", "error", "done"] as const;
export type SseEventName = (typeof SSE_EVENT_NAMES)[number];

export function isSseEventName(value: string): value is SseEventName {
  return (SSE_EVENT_NAMES as readonly string[]).includes(value);
}
