import {
  FIXTURE_ARTIFACT,
  FIXTURE_CHUNK,
  FIXTURE_CONFIG,
  FIXTURE_EMPTY_SESSION,
  FIXTURE_HTML_ARTIFACT,
  FIXTURE_SESSION,
  FIXTURE_SESSION_WITH_HISTORY,
} from "../test/fixtures/apiFixtures";
import { SSE_ABSTENTION, SSE_GROUNDED_QA, SSE_SHIP30_ESSAY } from "../test/fixtures/sseFixtures";
import type { ExtensionProposal, Session, SessionDetail } from "../api/types";

/**
 * A hand-rolled fetch mock, not a network-level interceptor (no MSW
 * dependency to pin). It monkey-patches `window.fetch`, so it only works for
 * requests this app itself makes through src/api/client.ts — which is all
 * the frontend ever does (architecture.md §2: web never calls `agent`
 * directly). Installed only when VITE_USE_MOCKS=true, wired up in main.tsx.
 *
 * Good enough for a manual dev-mode smoke test of every flow in design.md
 * without the real `api` service running. Not a substitute for the
 * Schemathesis conformance gate that runs against the real service.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

const sessions = new Map<string, SessionDetail>([
  [FIXTURE_SESSION.id, FIXTURE_SESSION_WITH_HISTORY],
  [FIXTURE_EMPTY_SESSION.id, FIXTURE_EMPTY_SESSION],
]);

const extensionProposals = new Map<string, ExtensionProposal>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function notFound(traceId = "mock-trace"): Response {
  return jsonResponse(
    { error: { code: "NOT_FOUND", message: "Not found", trace_id: traceId, retryable: false } },
    404,
  );
}

function pickSseFixture(content: string): string {
  const lower = content.toLowerCase();
  if (lower.includes("essay") || lower.includes("ship 30") || lower.includes("ship30")) {
    return SSE_SHIP30_ESSAY;
  }
  if (lower.includes("semiconductor") || lower.includes("tax law") || lower.includes("nonsense")) {
    return SSE_ABSTENTION;
  }
  return SSE_GROUNDED_QA;
}

/** Turns a static SSE fixture string into a Response whose body streams a
 * few bytes at a time, so the UI's incremental rendering is genuinely
 * exercised rather than resolved in one microtask. */
function streamingSseResponse(fixtureText: string): Response {
  const chunks: string[] = [];
  // Split on frame boundaries first, then dribble each frame out in two
  // pieces so the parser's incremental buffering is exercised too.
  const frames = fixtureText.split("\n\n").filter((f) => f.trim().length > 0);
  for (const frame of frames) {
    const mid = Math.max(1, Math.floor(frame.length / 2));
    chunks.push(frame.slice(0, mid));
    chunks.push(frame.slice(mid) + "\n\n");
  }

  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (i >= chunks.length) {
        controller.close();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 15));
      controller.enqueue(encoder.encode(chunks[i]));
      i += 1;
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

async function handleMockRequest(url: URL, init: RequestInit | undefined): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const path = url.pathname;

  if (method === "GET" && path === "/config") {
    return jsonResponse(FIXTURE_CONFIG);
  }

  if (method === "GET" && path === "/health/deps") {
    return jsonResponse({ db: "ok", ollama: "ok", agent: "ok" });
  }

  if (method === "GET" && path === "/sessions") {
    const items: Session[] = Array.from(sessions.values()).map(({ messages: _messages, ...rest }) => rest);
    return jsonResponse({ items, total: items.length });
  }

  if (method === "POST" && path === "/sessions") {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const detail: SessionDetail = {
      id,
      title: null,
      provider: FIXTURE_CONFIG.provider,
      model: FIXTURE_CONFIG.model,
      enabled_skills: null,
      created_at: now,
      updated_at: now,
      messages: [],
    };
    sessions.set(id, detail);
    const { messages: _messages, ...session } = detail;
    return jsonResponse(session, 201);
  }

  const sessionMatch = path.match(/^\/sessions\/([^/]+)$/);
  if (sessionMatch) {
    const id = sessionMatch[1] as string;
    const detail = sessions.get(id);
    if (method === "GET") {
      return detail ? jsonResponse(detail) : notFound();
    }
    if (method === "DELETE") {
      if (!detail) return notFound();
      sessions.delete(id);
      return new Response(null, { status: 204 });
    }
  }

  const capabilitiesMatch = path.match(/^\/sessions\/([^/]+)\/capabilities$/);
  if (capabilitiesMatch && method === "PATCH") {
    const id = capabilitiesMatch[1] as string;
    const detail = sessions.get(id);
    if (!detail) return notFound();
    const body = init?.body
      ? (JSON.parse(init.body as string) as { enabled_skills: string[] | null })
      : { enabled_skills: null };
    detail.enabled_skills = body.enabled_skills;
    const { messages: _messages, ...session } = detail;
    return jsonResponse(session);
  }

  if (method === "GET" && path === "/extension-proposals") {
    return jsonResponse({ items: Array.from(extensionProposals.values()) });
  }

  if (method === "POST" && path === "/extension-proposals") {
    const body = init?.body
      ? (JSON.parse(init.body as string) as {
          title: string;
          description: string;
          tool_names: string[];
          code: string;
        })
      : { title: "", description: "", tool_names: [], code: "" };
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const proposal = {
      id,
      title: body.title,
      description: body.description,
      tool_names: body.tool_names,
      code: body.code,
      sha256: "mock-sha256-not-computed",
      status: "pending" as const,
      session_id: url.searchParams.get("session_id"),
      created_at: now,
      updated_at: now,
    };
    extensionProposals.set(id, proposal);
    return jsonResponse(proposal, 201);
  }

  const proposalMatch = path.match(/^\/extension-proposals\/([^/]+)$/);
  if (proposalMatch && method === "PATCH") {
    const id = proposalMatch[1] as string;
    const proposal = extensionProposals.get(id);
    if (!proposal) return notFound();
    const body = init?.body
      ? (JSON.parse(init.body as string) as { status: "pending" | "approved" | "rejected" })
      : { status: proposal.status };
    proposal.status = body.status;
    proposal.updated_at = new Date().toISOString();
    return jsonResponse(proposal);
  }

  const messagesMatch = path.match(/^\/sessions\/([^/]+)\/messages$/);
  if (messagesMatch && method === "POST") {
    const id = messagesMatch[1] as string;
    if (!sessions.has(id)) return notFound();
    const body = init?.body ? (JSON.parse(init.body as string) as { content: string }) : { content: "" };
    return streamingSseResponse(pickSseFixture(body.content));
  }

  const chunkMatch = path.match(/^\/chunks\/(\d+)$/);
  if (chunkMatch && method === "GET") {
    return jsonResponse(FIXTURE_CHUNK);
  }

  const artifactMatch = path.match(/^\/artifacts\/([^/]+)$/);
  if (artifactMatch && method === "GET") {
    const id = artifactMatch[1];
    if (id === FIXTURE_HTML_ARTIFACT.id) return jsonResponse(FIXTURE_HTML_ARTIFACT);
    return jsonResponse(FIXTURE_ARTIFACT);
  }

  return notFound();
}

let installed = false;

export function installMockApi(): void {
  if (installed) return;
  installed = true;
  const realFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === "string" ? input : input.toString());
    if (!url.toString().startsWith(BASE_URL)) {
      return realFetch(input, init);
    }
    return handleMockRequest(url, init);
  };

  console.info("[mocks] fetch mock installed — API responses are fixtures, not the real `api` service");
}
