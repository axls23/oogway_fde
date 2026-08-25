/**
 * Hand-written types matching contracts/openapi.yaml exactly. Keep this file
 * in lockstep with that document — it is the source of truth, not this one.
 */

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    trace_id: string;
    retryable: boolean;
  };
}

export type Provider = "ollama" | "anthropic";

export interface Session {
  id: string;
  title: string | null;
  provider: string;
  model: string;
  /** Root CLAUDE.md invariant #4: null = every discovered skill active
   * (default); a non-null array is an explicit per-session allowlist by
   * skill name. Skills carry no tools — this can only narrow prompt
   * content, never grant capability. */
  enabled_skills: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateSessionCapabilitiesRequest {
  enabled_skills: string[] | null;
}

export interface CreateExtensionProposalRequest {
  title: string;
  description: string;
  tool_names: string[];
  code: string;
}

export type ExtensionProposalStatus = "pending" | "approved" | "rejected";

/** A user-drafted proposal for a new agent/.pi/extensions/ entry — a review
 * queue row, never a deployment. See CreateExtensionProposalRequest and
 * root CLAUDE.md invariant #4. */
export interface ExtensionProposal {
  id: string;
  title: string;
  description: string;
  tool_names: string[];
  code: string;
  sha256: string;
  status: ExtensionProposalStatus;
  session_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  chunk_id: number;
  episode: string;
  guest: string;
  youtube_url: string | null;
  /** Nearest preceding speaker-turn timestamp; append as &t={start_seconds}s
   *  to youtube_url to deep-link. */
  start_seconds: number | null;
  rank: number;
  score: number;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  rewritten_query?: string | null;
  trace_id?: string;
  provider?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  abstained: boolean;
  created_at: string;
  citations?: Citation[];
}

export interface SessionDetail extends Session {
  messages: Message[];
}

export interface CreateSessionRequest {
  title?: string | null;
}

export interface PostMessageRequest {
  content: string;
}

export interface ChunkDetail {
  id: number;
  text: string;
  ordinal?: number;
  episode: {
    id: number;
    guest: string;
    title: string;
    youtube_url: string | null;
    publish_date?: string | null;
    source_path: string;
  };
  start_seconds?: number | null;
}

export interface Artifact {
  id: string;
  session_id: string;
  message_id: string | null;
  kind: "markdown" | "html";
  title: string | null;
  content: string;
  sanitized: boolean;
  created_at: string;
}

export interface SkillSummary {
  name: string;
  description: string;
}

export interface ExtensionSummary {
  path: string;
  tools: string[];
}

/** Root CLAUDE.md invariant #4: what's actually active on the agent right
 * now. `agent_reachable: false` means this is an empty default, not a
 * confirmed empty state — the ActiveCapabilities panel must tell those apart. */
export interface Capabilities {
  skills: SkillSummary[];
  extensions: ExtensionSummary[];
  extensions_enabled: boolean;
  tools: string[];
  agent_reachable: boolean;
}

export interface ConfigResponse {
  provider: Provider;
  model: string;
  cloud_available: boolean;
  corpus: {
    episode_count: number;
    chunk_count: number;
  };
  capabilities: Capabilities;
}

export type DepStatus = "ok" | "degraded" | "down";

export interface HealthDeps {
  db: DepStatus;
  ollama: DepStatus;
  agent: DepStatus;
}

export interface SessionListResponse {
  items: Session[];
  total: number;
}

/** Thrown by the API client for any non-2xx response. Carries the parsed
 * ErrorEnvelope when the server returned one. */
export class ApiError extends Error {
  readonly status: number;
  readonly envelope: ErrorEnvelope | null;

  constructor(status: number, envelope: ErrorEnvelope | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.envelope = envelope;
  }

  get retryable(): boolean {
    return this.envelope?.error.retryable ?? this.status === 503;
  }

  get code(): string {
    return this.envelope?.error.code ?? `HTTP_${this.status}`;
  }
}
