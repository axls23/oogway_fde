import { test } from "node:test";
import assert from "node:assert/strict";
import { startFakeApi } from "./fixtures/fake-api.js";
import { createArtifactTool } from "../src/tools/create-artifact.js";

test("create_artifact: happy path posts to /internal/artifacts and echoes the persisted id", async () => {
  const { server, baseUrl } = await startFakeApi();
  try {
    const tool = createArtifactTool({ apiBaseUrl: baseUrl, internalToken: "t", sessionId: "sess-1", traceId: "trace-1" });
    const result = await tool.execute("call-1", { kind: "markdown", title: "Growth Memo", content: "# Hello\n\nBody." }, undefined, undefined, {} as any);

    const details = result.details as { artifact_id: string; kind: string; title: string };
    assert.equal(details.kind, "markdown");
    assert.equal(details.title, "Growth Memo");
    assert.match(details.artifact_id, /^[0-9a-f-]{36}$/);

    const text = (result.content[0] as { text: string }).text;
    assert.match(text, /Growth Memo/);
  } finally {
    server.close();
  }
});

test("create_artifact: unreachable api throws rather than pretending to have saved", async () => {
  const tool = createArtifactTool({ apiBaseUrl: "http://127.0.0.1:1", internalToken: "t", sessionId: "s", traceId: "tr" });
  await assert.rejects(() => tool.execute("call-2", { kind: "html", title: "T", content: "<p>x</p>" }, undefined, undefined, {} as any));
});
