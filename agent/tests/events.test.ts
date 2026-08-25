// mapPiEvent is a pure function — these are fabricated Pi session events,
// no live model or session required. Field shapes match
// node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-agent-core/dist/types.d.ts
// (the real installed package), not guesses.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mapPiEvent } from "../src/events.js";
import type { AgentSessionEvent } from "@earendil-works/pi-coding-agent";

test("agent_start maps to stage:thinking", () => {
  const evt = { type: "agent_start" } as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "stage", stage: "thinking", detail: null }]);
});

test("tool_execution_start(search_transcripts) maps to stage:retrieving", () => {
  const evt = { type: "tool_execution_start", toolCallId: "t1", toolName: "search_transcripts", args: { query: "x" } } as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "stage", stage: "retrieving", detail: null }]);
});

test("tool_execution_start(create_artifact) maps to stage:assembling", () => {
  const evt = { type: "tool_execution_start", toolCallId: "t2", toolName: "create_artifact", args: {} } as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "stage", stage: "assembling", detail: null }]);
});

test("tool_execution_start(edit_artifact) maps to stage:assembling", () => {
  const evt = { type: "tool_execution_start", toolCallId: "t2b", toolName: "edit_artifact", args: {} } as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "stage", stage: "assembling", detail: null }]);
});

test("tool_execution_start(unknown tool) maps to nothing", () => {
  const evt = { type: "tool_execution_start", toolCallId: "t3", toolName: "something_else", args: {} } as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), []);
});

test("tool_execution_end(search_transcripts, success) maps to one batched citation frame", () => {
  const chunks = [{ chunk_id: 1, episode: "Ep", guest: "G", youtube_url: null, start_seconds: null, rank: 1, score: 0.9 }];
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t1",
    toolName: "search_transcripts",
    isError: false,
    result: { content: [], details: { abstained: false, chunks } },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "citation", chunks }]);
});

test("tool_execution_end(search_transcripts, abstained) maps to nothing", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t1",
    toolName: "search_transcripts",
    isError: false,
    result: { content: [], details: { abstained: true, chunks: [] } },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), []);
});

test("tool_execution_end(search_transcripts, isError) maps to nothing", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t1",
    toolName: "search_transcripts",
    isError: true,
    result: { content: [], details: undefined },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), []);
});

test("tool_execution_end(create_artifact, success) maps to an artifact frame", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t2",
    toolName: "create_artifact",
    isError: false,
    result: { content: [], details: { artifact_id: "a1", kind: "html", title: "My Doc" } },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "artifact", artifact_id: "a1", kind: "html", title: "My Doc" }]);
});

test("tool_execution_end(edit_artifact, success) maps to an artifact frame", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t2c",
    toolName: "edit_artifact",
    isError: false,
    result: { content: [], details: { artifact_id: "a1", kind: "markdown", title: "My Doc v2" } },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "artifact", artifact_id: "a1", kind: "markdown", title: "My Doc v2" }]);
});

test("tool_execution_end(create_artifact, isError) maps to a non-fatal error frame carrying the thrown message", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t4",
    toolName: "create_artifact",
    isError: true,
    // Shape confirmed against the installed SDK's createErrorToolResult:
    // a thrown Error becomes { content: [{ type: "text", text: message }], details: {} }.
    result: { content: [{ type: "text", text: "create_artifact: api responded 422: MALFORMED_ARTIFACT" }], details: {} },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [
    {
      type: "error",
      code: "ARTIFACT_TOOL_FAILED",
      message: "create_artifact: api responded 422: MALFORMED_ARTIFACT",
      retryable: false,
      partial: true,
    },
  ]);
});

test("tool_execution_end(edit_artifact, isError) maps to a non-fatal error frame too", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t5",
    toolName: "edit_artifact",
    isError: true,
    result: { content: [{ type: "text", text: "edit_artifact: api responded 404: NOT_FOUND" }], details: {} },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [
    {
      type: "error",
      code: "ARTIFACT_TOOL_FAILED",
      message: "edit_artifact: api responded 404: NOT_FOUND",
      retryable: false,
      partial: true,
    },
  ]);
});

test("tool_execution_end(create_artifact, isError) falls back to a generic message when result has no text content", () => {
  const evt = {
    type: "tool_execution_end",
    toolCallId: "t6",
    toolName: "create_artifact",
    isError: true,
    result: { content: [], details: {} },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [
    { type: "error", code: "ARTIFACT_TOOL_FAILED", message: "create_artifact failed", retryable: false, partial: true },
  ]);
});

test("message_update text_delta maps to a token frame", () => {
  const evt = {
    type: "message_update",
    message: {},
    assistantMessageEvent: { type: "text_delta", delta: "hello" },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "token", delta: "hello" }]);
});

test("message_update thinking_delta maps to nothing (thinkingLevel is off)", () => {
  const evt = {
    type: "message_update",
    message: {},
    assistantMessageEvent: { type: "thinking_delta", delta: "hmm" },
  } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), []);
});

test("turn_end maps to stage:drafting", () => {
  const evt = { type: "turn_end", turnIndex: 0, message: {}, toolResults: [] } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(evt), [{ type: "stage", stage: "drafting", detail: null }]);
});

test("agent_end and other lifecycle events map to nothing (server.ts owns terminal frames)", () => {
  const agentEnd = { type: "agent_end", messages: [], willRetry: false } as unknown as AgentSessionEvent;
  const queueUpdate = { type: "queue_update", steering: [], followUp: [] } as unknown as AgentSessionEvent;
  assert.deepEqual(mapPiEvent(agentEnd), []);
  assert.deepEqual(mapPiEvent(queueUpdate), []);
});
