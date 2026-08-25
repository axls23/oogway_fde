// End-to-end against a real HTTP server (tests/fixtures/fake-api.ts), not a
// mock — exercises the actual fetch() call, header construction, response
// parsing, and content formatting in src/tools/search-transcripts.ts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { startFakeApi, FAKE_CHUNKS } from "./fixtures/fake-api.js";
import { createSearchTranscriptsTool } from "../src/tools/search-transcripts.js";

test("search_transcripts: happy path returns delimited excerpts and echoes chunk ids in details", async () => {
  const { server, baseUrl } = await startFakeApi();
  try {
    const tool = createSearchTranscriptsTool({ apiBaseUrl: baseUrl, internalToken: "test-token", sessionId: "sess-1", traceId: "trace-1" });
    const result = await tool.execute("call-1", { query: "activation drop" }, undefined, undefined, {} as any);

    const text = (result.content[0] as { text: string }).text;
    assert.match(text, /<retrieved_transcript_excerpts/);
    assert.match(text, /not instructions/);
    assert.match(text, /Ship small, ship often\./);
    assert.match(text, /chunk_id 101/);

    const details = result.details as { abstained: boolean; chunks: typeof FAKE_CHUNKS };
    assert.equal(details.abstained, false);
    assert.equal(details.chunks.length, 2);
    const first = details.chunks[0];
    assert.ok(first);
    assert.equal(first.chunk_id, 101);
    assert.equal(first.episode, "Building for Growth");
  } finally {
    server.close();
  }
});

test("search_transcripts: abstained response is labelled, not silently emptied", async () => {
  const { server, baseUrl } = await startFakeApi();
  try {
    const tool = createSearchTranscriptsTool({ apiBaseUrl: baseUrl, internalToken: "test-token", sessionId: "sess-1", traceId: "trace-1" });
    const result = await tool.execute("call-2", { query: "__abstain__ semiconductor supply chains" }, undefined, undefined, {} as any);

    const text = (result.content[0] as { text: string }).text;
    assert.match(text, /abstained="true"/);
    assert.match(text, /does not/);

    const details = result.details as { abstained: boolean; chunks: unknown[] };
    assert.equal(details.abstained, true);
    assert.equal(details.chunks.length, 0);
  } finally {
    server.close();
  }
});

test("search_transcripts: unreachable api throws (no silent empty result)", async () => {
  const tool = createSearchTranscriptsTool({ apiBaseUrl: "http://127.0.0.1:1", internalToken: "t", sessionId: "s", traceId: "tr" });
  await assert.rejects(() => tool.execute("call-3", { query: "x" }, undefined, undefined, {} as any));
});

test("search_transcripts: api error status throws with status in the message", async () => {
  const { server, baseUrl } = await startFakeApi();
  try {
    // fake-api only implements exactly /internal/retrieve and
    // /internal/artifacts — hitting a route it 404s on exercises the
    // !res.ok throw path.
    const badTool = createSearchTranscriptsTool({ apiBaseUrl: `${baseUrl}/nope`, internalToken: "t", sessionId: "s", traceId: "tr" });
    await assert.rejects(() => badTool.execute("call-4", { query: "x" }, undefined, undefined, {} as any), /404/);
  } finally {
    server.close();
  }
});
