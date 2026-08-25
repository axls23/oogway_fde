// Tiny stand-in for the `api` service's internal endpoints, since `api` is
// being built in parallel and isn't running in this worktree. Serves fixed
// responses for POST /internal/retrieve and POST /internal/artifacts so
// search-transcripts.ts and create-artifact.ts can be tested against a
// real HTTP server instead of only in isolation. Not a mock framework —
// plain node:http, ~40 lines.

import { createServer, type Server } from "node:http";
import { randomUUID } from "node:crypto";

export const FAKE_CHUNKS = [
  { chunk_id: 101, episode: "Building for Growth", guest: "Ada Operator", youtube_url: "https://youtu.be/abc123", start_seconds: 42, rank: 1, score: 0.81, text: "Ship small, ship often." },
  { chunk_id: 102, episode: "Building for Growth", guest: "Ada Operator", youtube_url: "https://youtu.be/abc123", start_seconds: 210, rank: 2, score: 0.74, text: "Retention beats acquisition." },
];

export function startFakeApi(): Promise<{ server: Server; port: number; baseUrl: string }> {
  const server = createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const c of req) chunks.push(c as Buffer);
    const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf-8")) : {};

    if (req.method === "POST" && req.url === "/internal/retrieve") {
      const abstain = typeof body.query === "string" && body.query.includes("__abstain__");
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ abstained: abstain, floor: 0.45, chunks: abstain ? [] : FAKE_CHUNKS }));
      return;
    }
    if (req.method === "POST" && req.url === "/internal/artifacts") {
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ id: randomUUID(), kind: body.kind, title: body.title ?? null }));
      return;
    }
    const editMatch = req.method === "PATCH" && req.url?.match(/^\/internal\/artifacts\/([0-9a-f-]{36})$/);
    if (editMatch) {
      if (editMatch[1] === "00000000-0000-0000-0000-000000000404") {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "artifact not found", trace_id: "fixture", retryable: false } }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ id: editMatch[1], kind: "markdown", title: body.title ?? null }));
      return;
    }
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "no fixture for this route", trace_id: "fixture", retryable: false } }));
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      const port = typeof addr === "object" && addr ? addr.port : 0;
      resolve({ server, port, baseUrl: `http://127.0.0.1:${port}` });
    });
  });
}
