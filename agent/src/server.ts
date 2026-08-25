// agent/src/server.ts — the Pi sidecar's one streaming endpoint plus a
// liveness check. architecture.md §8.1: "a small Node process embedding
// the Pi SDK and exposing one streaming endpoint, POST /turn. FastAPI is
// the only caller."
//
// HTTP layer: Node's built-in `node:http` + global `fetch`, no framework.
// Justification: two routes, one of them a raw NDJSON stream where we need
// direct control over when headers get sent (see the buffering note
// below) — Express/Fastify would add a dependency to save maybe 20 lines
// and would fight the buffering behavior rather than help it.
//
// ── Wire protocol for POST /turn ───────────────────────────────────────
// Request:  { session_id: string, messages: Array<{role, content}>, trace_id: string }
//           `messages` is the FULL rehydrated history including the new
//           trailing user turn (ADR-002 — this service is stateless).
// Response: newline-delimited JSON, one object per line, Content-Type
//           application/x-ndjson. Each line is:
//             { type: "stage",    stage, detail }
//             { type: "token",    delta }
//             { type: "citation", chunks: [...] }
//             { type: "artifact", artifact_id, kind, title }
//             { type: "error",    code, message, retryable, partial }
//             { type: "done",     latency_ms }
//
// This was built against the DOCUMENTED ASSUMPTION handed to this task —
// NDJSON with fields like {type, delta, chunks, stage} — and matches it
// with two deliberate departures `api` needs to know about when
// reconciling the two sides:
//   1. `citation` batches ALL chunks from one search_transcripts call into
//      one frame (`chunks: [...]`), rather than one frame per chunk. Our
//      tool gets the whole ranked list back in a single tool_execution_end
//      event, so batching is the natural shape; `api` can fan this out
//      into one contracts/sse-frames.schema.json `citation` SSE frame per
//      chunk (that schema IS one-per-frame) when it translates our stream.
//   2. `done` carries only `latency_ms`. It does NOT carry `message_id` or
//      `abstained` — this service never writes to Postgres and doesn't
//      decide abstention (that's `api`'s retrieval-floor guard, root
//      CLAUDE.md invariant #2); `api` must fill both in itself when it
//      builds the real SSE `done` frame.
// Every line also carries `trace_id` (not in the original assumption) so
// a raw NDJSON dump greps against api's logs directly.
//
// ── Why the response is buffered before it's ever a stream ─────────────
// CLAUDE.md: "If Ollama ... is unreachable when a turn starts, fail
// cleanly with a distinguishable error the caller can turn into a 503 —
// do NOT retry into a different provider." An HTTP status code can only be
// set once, before the first byte is written. But Pi's own lifecycle
// events (agent_start, turn_start) fire before the provider round-trip
// even happens — confirmed empirically (see the task report): a turn
// against an unreachable/broken provider still emits agent_start,
// turn_start, message_start, message_end before failing, with zero
// text_delta and zero tool calls. So frames are buffered in memory until
// the FIRST real sign of provider success — a tool call starting, or the
// first text_delta — at which point we commit to 200, flush the buffer,
// and stream live from then on. If the turn instead settles with no such
// signal ever having fired, nothing has been written yet and we return a
// clean non-200 JSON error instead of a truncated stream.

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { DefaultResourceLoader } from "@earendil-works/pi-coding-agent";
import { createLennySession, ProviderUnavailableError, TurnRequestError, BUILTIN_TOOL_NAMES, type TurnRequestMessage } from "./session.js";
import { mapPiEvent } from "./events.js";
import type { WireEvent } from "./wire-types.js";
import { log } from "./logger.js";
import { ExtensionManifestViolation, getCapabilitySnapshot, loadManifest, verifyExtensions } from "./capabilities.js";

const PORT = Number(process.env.AGENT_PORT ?? "8100");
const CWD = process.cwd();

interface Env {
  llmProvider: string;
  llmModel: string;
  ollamaBaseUrl: string;
  apiBaseUrl: string;
  agentInternalToken: string;
  modelTimeoutS: number;
  extensionsEnabled: boolean;
}

function readEnv(): Env {
  return {
    llmProvider: process.env.LLM_PROVIDER ?? "ollama",
    llmModel: process.env.LLM_MODEL ?? "qwen2.5:7b-instruct",
    ollamaBaseUrl: process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434",
    apiBaseUrl: process.env.API_BASE_URL ?? "http://localhost:8000",
    agentInternalToken: process.env.AGENT_INTERNAL_TOKEN ?? "",
    modelTimeoutS: Number(process.env.MODEL_TIMEOUT_S ?? "60"),
    extensionsEnabled: process.env.AGENT_EXTENSIONS_ENABLED === "true",
  };
}

/**
 * GET /capabilities — read-only snapshot of active skills/extensions/tools
 * for api's /config to forward to the UI capabilities panel. Builds its own
 * loader rather than reusing createLennySession's (that one is per-turn and
 * requires a full turn request body); this is a cheap, side-effect-free
 * discovery pass over the same .pi/skills and .pi/extensions directories.
 */
async function handleCapabilities(res: ServerResponse): Promise<void> {
  const env = readEnv();
  const agentDir = path.join(CWD, ".pi", "agent");
  const loader = new DefaultResourceLoader({
    cwd: CWD,
    agentDir,
    noExtensions: !env.extensionsEnabled,
  });
  try {
    await loader.reload();
    if (env.extensionsEnabled) {
      verifyExtensions(loader, loadManifest(path.join(CWD, ".pi", "extensions", "manifest.json")), CWD);
    }
    const snapshot = getCapabilitySnapshot(loader, BUILTIN_TOOL_NAMES, env.extensionsEnabled, CWD);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(snapshot));
  } catch (err) {
    const isManifestViolation = err instanceof ExtensionManifestViolation;
    log.error("GET /capabilities failed", {
      error: err instanceof Error ? err.message : String(err),
      manifest_violation: isManifestViolation,
    });
    res.writeHead(isManifestViolation ? 409 : 500, { "content-type": "application/json" });
    res.end(
      JSON.stringify({
        error: {
          code: isManifestViolation ? "EXTENSION_MANIFEST_VIOLATION" : "AGENT_ERROR",
          message: err instanceof Error ? err.message : String(err),
          retryable: false,
        },
      }),
    );
  }
}

interface TurnRequestBody {
  session_id: string;
  messages: TurnRequestMessage[];
  trace_id: string;
  /** Root CLAUDE.md invariant #4: omitted -> every discovered skill active. */
  enabled_skills?: string[];
}

async function readJsonBody(req: IncomingMessage, maxBytes = 4 * 1024 * 1024): Promise<unknown> {
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of req) {
    total += (chunk as Buffer).length;
    if (total > maxBytes) throw new TurnRequestError(`request body exceeds ${maxBytes} bytes`);
    chunks.push(chunk as Buffer);
  }
  const raw = Buffer.concat(chunks).toString("utf-8");
  if (raw.length === 0) throw new TurnRequestError("empty request body");
  try {
    return JSON.parse(raw);
  } catch {
    throw new TurnRequestError("request body is not valid JSON");
  }
}

function validateTurnRequest(body: unknown): TurnRequestBody {
  if (typeof body !== "object" || body === null) throw new TurnRequestError("request body must be a JSON object");
  const b = body as Record<string, unknown>;
  if (typeof b.session_id !== "string" || b.session_id.length === 0) throw new TurnRequestError("session_id is required");
  if (typeof b.trace_id !== "string" || b.trace_id.length === 0) throw new TurnRequestError("trace_id is required");
  if (!Array.isArray(b.messages) || b.messages.length === 0) throw new TurnRequestError("messages must be a non-empty array");
  for (const m of b.messages) {
    if (
      typeof m !== "object" ||
      m === null ||
      !["user", "assistant", "system"].includes((m as Record<string, unknown>).role as string) ||
      typeof (m as Record<string, unknown>).content !== "string"
    ) {
      throw new TurnRequestError("each message must be { role: user|assistant|system, content: string }");
    }
  }
  let enabledSkills: string[] | undefined;
  if (b.enabled_skills !== undefined) {
    if (!Array.isArray(b.enabled_skills) || b.enabled_skills.some((s) => typeof s !== "string")) {
      throw new TurnRequestError("enabled_skills must be an array of strings when present");
    }
    enabledSkills = b.enabled_skills as string[];
  }
  return {
    session_id: b.session_id,
    trace_id: b.trace_id,
    messages: b.messages as TurnRequestMessage[],
    enabled_skills: enabledSkills,
  };
}

function errorEnvelope(code: string, message: string, traceId: string, retryable: boolean) {
  return { error: { code, message, trace_id: traceId, retryable } };
}

function providerErrorCode(provider: string): string {
  return `${provider.toUpperCase()}_UNREACHABLE`;
}

async function handleTurn(req: IncomingMessage, res: ServerResponse): Promise<void> {
  let traceId = "unknown";
  try {
    const body = validateTurnRequest(await readJsonBody(req));
    traceId = body.trace_id;
    const env = readEnv();

    let session: Awaited<ReturnType<typeof createLennySession>>["session"];
    let promptText: string;
    try {
      const created = await createLennySession(env, {
        cwd: CWD,
        sessionId: body.session_id,
        traceId,
        history: body.messages,
        enabledSkills: body.enabled_skills,
      });
      session = created.session;
      promptText = created.promptText;
    } catch (err) {
      if (err instanceof ProviderUnavailableError) {
        log.error("provider unavailable at session construction", { trace_id: traceId, session_id: body.session_id, provider: err.provider, error: err.message });
        res.writeHead(503, { "content-type": "application/json" });
        res.end(JSON.stringify(errorEnvelope(providerErrorCode(err.provider), err.message, traceId, true)));
        return;
      }
      if (err instanceof TurnRequestError) {
        res.writeHead(400, { "content-type": "application/json" });
        res.end(JSON.stringify(errorEnvelope("BAD_REQUEST", err.message, traceId, false)));
        return;
      }
      throw err;
    }

    await streamTurn(res, session, promptText, env, traceId);
  } catch (err) {
    log.error("unhandled error in /turn", { trace_id: traceId, error: err instanceof Error ? err.stack ?? err.message : String(err) });
    if (!res.headersSent) {
      const status = err instanceof TurnRequestError ? 400 : 500;
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(errorEnvelope(status === 400 ? "BAD_REQUEST" : "AGENT_ERROR", err instanceof Error ? err.message : String(err), traceId, status !== 400)));
    } else {
      writeLine(res, { type: "error", code: "AGENT_ERROR", message: err instanceof Error ? err.message : String(err), retryable: false, partial: true });
      res.end();
    }
  }
}

function writeLine(res: ServerResponse, event: WireEvent, traceId?: string): void {
  res.write(`${JSON.stringify(traceId ? { ...event, trace_id: traceId } : event)}\n`);
}

async function streamTurn(
  res: ServerResponse,
  session: Awaited<ReturnType<typeof createLennySession>>["session"],
  promptText: string,
  env: Env,
  traceId: string,
): Promise<void> {
  const startedAt = Date.now();
  const buffer: WireEvent[] = [];
  let streaming = false;
  let timedOut = false;

  const flip = () => {
    if (streaming) return;
    streaming = true;
    res.writeHead(200, { "content-type": "application/x-ndjson" });
    for (const evt of buffer) writeLine(res, evt, traceId);
    buffer.length = 0;
  };

  const push = (evt: WireEvent) => {
    if (streaming) writeLine(res, evt, traceId);
    else buffer.push(evt);
  };

  const unsubscribe = session.subscribe((event) => {
    const isRealProgress =
      event.type === "tool_execution_start" || (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta");
    if (isRealProgress) flip();
    for (const evt of mapPiEvent(event)) push(evt);
  });

  const timeoutMs = env.modelTimeoutS * 1000;
  const timer = setTimeout(() => {
    timedOut = true;
    session.abort().catch((err) => {
      log.error("session.abort() after MODEL_TIMEOUT_S failed", { trace_id: traceId, error: err instanceof Error ? err.message : String(err) });
    });
  }, timeoutMs);

  try {
    await session.prompt(promptText);
  } catch (err) {
    // prompt() resolving-through-failure is the documented behavior (see
    // session.ts / the task report), but we still guard the throw path —
    // a rejected promise here means something failed before Pi's own
    // event/message reporting could run.
    log.error("session.prompt() rejected", { trace_id: traceId, error: err instanceof Error ? err.message : String(err) });
    if (!streaming) {
      res.writeHead(503, { "content-type": "application/json" });
      res.end(JSON.stringify(errorEnvelope(providerErrorCode(env.llmProvider), err instanceof Error ? err.message : String(err), traceId, true)));
    } else {
      writeLine(res, { type: "error", code: "AGENT_ERROR", message: err instanceof Error ? err.message : String(err), retryable: false, partial: true }, traceId);
      res.end();
    }
    return;
  } finally {
    clearTimeout(timer);
    unsubscribe();
    session.dispose();
  }

  const latencyMs = Date.now() - startedAt;
  const errorMessage = session.agent.state.errorMessage;

  if (timedOut) {
    const evt: WireEvent = { type: "error", code: "MODEL_TIMEOUT", message: `turn exceeded MODEL_TIMEOUT_S=${env.modelTimeoutS}s and was aborted`, retryable: true, partial: streaming };
    if (!streaming) {
      res.writeHead(503, { "content-type": "application/json" });
      res.end(JSON.stringify(errorEnvelope(evt.code, evt.message, traceId, true)));
    } else {
      writeLine(res, evt, traceId);
      res.end();
    }
    return;
  }

  if (errorMessage && !streaming) {
    // Total failure, no real progress ever observed — the case CLAUDE.md's
    // "fail cleanly ... caller can turn into a 503" describes. See the
    // file header for why we can still choose the status code here: no
    // bytes have been written yet.
    log.error("turn failed with no streamed progress", { trace_id: traceId, provider: env.llmProvider, model: env.llmModel, error: errorMessage });
    res.writeHead(503, { "content-type": "application/json" });
    res.end(JSON.stringify(errorEnvelope(providerErrorCode(env.llmProvider), errorMessage, traceId, true)));
    return;
  }

  if (!streaming) flip(); // e.g. a genuinely empty successful turn — still owe a 200 + done.

  if (errorMessage) {
    writeLine(res, { type: "error", code: "AGENT_ERROR", message: errorMessage, retryable: false, partial: true }, traceId);
  } else {
    writeLine(res, { type: "done", latency_ms: latencyMs }, traceId);
  }
  res.end();
}

const server = createServer((req, res) => {
  const traceId = req.headers["x-trace-id"];
  if (req.method === "GET" && req.url === "/healthz") {
    // Liveness only — no I/O, per agent/CLAUDE.md and root architecture §5.
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }
  if (req.method === "GET" && req.url === "/capabilities") {
    handleCapabilities(res).catch((err) => {
      log.error("handleCapabilities crashed outside its own try/catch", { error: err instanceof Error ? err.stack ?? err.message : String(err) });
      if (!res.headersSent) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: { code: "AGENT_ERROR", message: "internal error", retryable: false } }));
      } else {
        res.end();
      }
    });
    return;
  }
  if (req.method === "POST" && req.url === "/turn") {
    handleTurn(req, res).catch((err) => {
      log.error("handleTurn crashed outside its own try/catch", { error: err instanceof Error ? err.stack ?? err.message : String(err) });
      if (!res.headersSent) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify(errorEnvelope("AGENT_ERROR", "internal error", "unknown", false)));
      } else {
        res.end();
      }
    });
    return;
  }
  res.writeHead(404, { "content-type": "application/json" });
  res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: `no route for ${req.method} ${req.url}`, trace_id: String(traceId ?? randomUUID()), retryable: false } }));
});

server.listen(PORT, () => {
  log.info("agent listening", { port: PORT, cwd: CWD });
});
