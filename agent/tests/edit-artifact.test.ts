import { test } from "node:test";
import assert from "node:assert/strict";
import { startFakeApi } from "./fixtures/fake-api.js";
import { editArtifactTool } from "../src/tools/edit-artifact.js";

const EXISTING_ID = "11111111-1111-1111-1111-111111111111";
const MISSING_ID = "00000000-0000-0000-0000-000000000404";

test("edit_artifact: happy path PATCHes /internal/artifacts/{id} and confirms the update", async () => {
  const { server, baseUrl } = await startFakeApi();
  try {
    const tool = editArtifactTool({ apiBaseUrl: baseUrl, internalToken: "t", sessionId: "sess-1", traceId: "trace-1" });
    const result = await tool.execute(
      "call-1",
      { artifact_id: EXISTING_ID, title: "Growth Memo v2", content: "# Hello\n\nRevised body." },
      undefined,
      undefined,
      {} as any,
    );

    const details = result.details as { artifact_id: string; kind: string; title: string };
    assert.equal(details.artifact_id, EXISTING_ID);
    assert.equal(details.title, "Growth Memo v2");

    const text = (result.content[0] as { text: string }).text;
    assert.match(text, /updated/);
  } finally {
    server.close();
  }
});

test("edit_artifact: unknown artifact_id throws rather than pretending to have saved", async () => {
  const { server, baseUrl } = await startFakeApi();
  try {
    const tool = editArtifactTool({ apiBaseUrl: baseUrl, internalToken: "t", sessionId: "sess-1", traceId: "trace-1" });
    await assert.rejects(() =>
      tool.execute("call-2", { artifact_id: MISSING_ID, content: "new content" }, undefined, undefined, {} as any),
    );
  } finally {
    server.close();
  }
});

test("edit_artifact: unreachable api throws rather than pretending to have saved", async () => {
  const tool = editArtifactTool({ apiBaseUrl: "http://127.0.0.1:1", internalToken: "t", sessionId: "s", traceId: "tr" });
  await assert.rejects(() => tool.execute("call-3", { artifact_id: EXISTING_ID, content: "x" }, undefined, undefined, {} as any));
});
