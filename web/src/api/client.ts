import {
  ApiError,
  type Artifact,
  type ChunkDetail,
  type ConfigResponse,
  type CreateSessionRequest,
  type ErrorEnvelope,
  type HealthDeps,
  type PostMessageRequest,
  type Session,
  type SessionDetail,
  type SessionListResponse,
} from "./types";

/**
 * Typed client for the `api` service, matching contracts/openapi.yaml.
 * Every method here corresponds to one operationId in that document.
 *
 * The frontend never talks to `agent` directly (architecture.md §2) — this
 * is the only HTTP boundary the app crosses.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let envelope: ErrorEnvelope | null = null;
    try {
      envelope = (await res.json()) as ErrorEnvelope;
    } catch {
      // Body wasn't JSON (e.g. a proxy 502) — envelope stays null, the
      // ApiError still carries the HTTP status so callers can react.
    }
    throw new ApiError(res.status, envelope, envelope?.error.message ?? res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  getConfig(): Promise<ConfigResponse> {
    return request<ConfigResponse>("/config");
  },

  getHealthDeps(): Promise<HealthDeps> {
    return request<HealthDeps>("/health/deps");
  },

  listSessions(limit = 50, offset = 0): Promise<SessionListResponse> {
    return request<SessionListResponse>(`/sessions?limit=${limit}&offset=${offset}`);
  },

  createSession(body: CreateSessionRequest = {}): Promise<Session> {
    return request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  getSession(id: string): Promise<SessionDetail> {
    return request<SessionDetail>(`/sessions/${id}`);
  },

  deleteSession(id: string): Promise<void> {
    return request<void>(`/sessions/${id}`, { method: "DELETE" });
  },

  /**
   * Sends a turn. Returns the raw fetch Response so the caller can stream
   * the SSE body via src/sse/parser.ts — this method deliberately does not
   * consume the body itself.
   */
  async postMessageStream(sessionId: string, body: PostMessageRequest, signal?: AbortSignal): Promise<Response> {
    const res = await fetch(`${BASE_URL}/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok) {
      let envelope: ErrorEnvelope | null = null;
      try {
        envelope = (await res.json()) as ErrorEnvelope;
      } catch {
        // non-JSON error body; envelope stays null
      }
      throw new ApiError(res.status, envelope, envelope?.error.message ?? res.statusText);
    }

    return res;
  },

  getChunk(id: number): Promise<ChunkDetail> {
    return request<ChunkDetail>(`/chunks/${id}`);
  },

  getArtifact(id: string): Promise<Artifact> {
    return request<Artifact>(`/artifacts/${id}`);
  },
};

export { ApiError } from "./types";
export type * from "./types";
