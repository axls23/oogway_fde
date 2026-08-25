// Wire event types for POST /turn. See the header comment in server.ts for
// the full protocol writeup and the rationale for each field. This file
// exists only so events.ts (the pure mapper) and server.ts (the HTTP layer)
// share one definition instead of two drifting copies.

export type Stage = "thinking" | "retrieving" | "drafting" | "outlining" | "assembling";

export interface CitationChunk {
  chunk_id: number;
  episode: string;
  guest: string;
  youtube_url: string | null;
  start_seconds: number | null;
  rank: number;
  score: number;
}

export type WireEvent =
  | { type: "stage"; stage: Stage; detail: string | null }
  | { type: "token"; delta: string }
  | { type: "citation"; chunks: CitationChunk[] }
  | { type: "artifact"; artifact_id: string; kind: "markdown" | "html"; title: string }
  | { type: "error"; code: string; message: string; retryable: boolean; partial: boolean }
  | { type: "done"; latency_ms: number };

/** Details shape our search_transcripts tool puts on its AgentToolResult — read back out of `tool_execution_end.result.details` in events.ts. */
export interface SearchTranscriptsDetails {
  abstained: boolean;
  chunks: CitationChunk[];
}

/** Details shape our create_artifact tool puts on its AgentToolResult. */
export interface CreateArtifactDetails {
  artifact_id: string;
  kind: "markdown" | "html";
  title: string;
}
