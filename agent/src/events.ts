// Pure mapping from Pi's session events to our wire events — architecture.md
// §8.4's table, plus the two extensions documented inline below. Kept as a
// pure function (no fetch, no server, no session) specifically so it can be
// unit-tested against fabricated events without a live model or an HTTP
// server (per the task's testing requirement).
//
// Terminal frames ("done" / "error" for a fully-failed turn) are NOT
// produced here — they need a start timestamp and the final
// session.agent.state, both of which only server.ts has. This file only
// covers the in-flight portion of a turn: stage/token/citation/artifact.
//
// `event.result` on tool_execution_end is typed `any` in the SDK itself
// (confirmed in node_modules/@earendil-works/pi-coding-agent/node_modules/
// @earendil-works/pi-agent-core/dist/types.d.ts: `{ type: "tool_execution_end";
// toolCallId: string; toolName: string; result: any; isError: boolean }`).
// That `result` is the same AgentToolResult<TDetails> our tools' execute()
// returned (`{ content, details }`), so we read `result.details` directly
// instead of re-parsing the model's prose — same principle as the
// citations-from-metadata invariant in the root CLAUDE.md.

import type { AgentSessionEvent } from "@earendil-works/pi-coding-agent";
import type { CreateArtifactDetails, SearchTranscriptsDetails, WireEvent } from "./wire-types.js";

/**
 * On a thrown Error from a tool's execute(), the SDK sets
 * `result = { content: [{ type: "text", text: error.message }], details: {} }`
 * (confirmed in the installed package's dist/agent-loop.js,
 * createErrorToolResult/executePreparedToolCall) — read that text back out
 * rather than inventing a new error-detail channel our tools don't populate.
 */
function toolErrorText(result: unknown): string | undefined {
  const content = (result as { content?: Array<{ type?: string; text?: string }> } | undefined)?.content;
  const first = content?.[0];
  return first?.type === "text" ? first.text : undefined;
}

export function mapPiEvent(event: AgentSessionEvent): WireEvent[] {
  switch (event.type) {
    case "agent_start":
      return [{ type: "stage", stage: "thinking", detail: null }];

    case "tool_execution_start":
      if (event.toolName === "search_transcripts") {
        return [{ type: "stage", stage: "retrieving", detail: null }];
      }
      if (event.toolName === "create_artifact" || event.toolName === "edit_artifact") {
        return [{ type: "stage", stage: "assembling", detail: null }];
      }
      // noTools:"builtin" means no other tool should ever fire this, but
      // stay defensive rather than throw mid-stream over an unexpected name.
      return [];

    case "tool_execution_end": {
      if (event.isError) {
        // search_transcripts failing silently is deliberate — the model can
        // just retry the call. create_artifact/edit_artifact failing was
        // previously silent too (root CLAUDE.md forbidden pattern: an error
        // swallowed without surfacing to the caller): the tool call fails,
        // the browser gets no signal at all beyond whatever the model
        // happens to say in prose, and the only record is this service's
        // own log line. Surface it as a non-fatal in-band error instead —
        // `partial: true` matches turn.py's existing handling for a
        // mid-stream error frame (it does not abort the turn or the
        // persisted message, just annotates it).
        if (event.toolName === "create_artifact" || event.toolName === "edit_artifact") {
          const detail = toolErrorText(event.result);
          return [
            {
              type: "error",
              code: "ARTIFACT_TOOL_FAILED",
              message: detail ?? `${event.toolName} failed`,
              retryable: false,
              partial: true,
            },
          ];
        }
        return [];
      }
      const details = (event.result as { details?: unknown } | undefined)?.details;
      if (event.toolName === "search_transcripts") {
        const d = details as SearchTranscriptsDetails | undefined;
        if (!d || d.abstained || d.chunks.length === 0) return [];
        return [{ type: "citation", chunks: d.chunks }];
      }
      if (event.toolName === "create_artifact" || event.toolName === "edit_artifact") {
        const d = details as CreateArtifactDetails | undefined;
        if (!d) return [];
        return [{ type: "artifact", artifact_id: d.artifact_id, kind: d.kind, title: d.title }];
      }
      return [];
    }

    case "message_update":
      if (event.assistantMessageEvent.type === "text_delta") {
        return [{ type: "token", delta: event.assistantMessageEvent.delta }];
      }
      // thinking_delta and other assistant event kinds are not surfaced —
      // thinkingLevel is "off" for this service (architecture.md §8.2).
      return [];

    case "turn_end":
      // Section-progress `detail` for the Ship 30 flow (F3, e.g. "section 3
      // of 6") is populated by `api`, which orchestrates the multi-call
      // outline/section pipeline (architecture.md §8.4) — a single /turn
      // call here only ever sees its own turn, not the pipeline's position
      // within it.
      return [{ type: "stage", stage: "drafting", detail: null }];

    default:
      // turn_start, message_start, message_end, queue_update,
      // compaction_start/end, auto_retry_start/end,
      // summarization_retry_*, agent_settled, agent_end: no wire frame.
      // agent_end specifically is handled by server.ts (see file header).
      return [];
  }
}
