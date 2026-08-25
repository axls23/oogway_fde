// edit_artifact — revises an artifact this session already created, in
// place. Same trust boundary and pattern as create-artifact.ts: no
// filesystem/shell tool exists for the model to reach for instead (root
// CLAUDE.md invariant #4), so a "make it shorter" follow-up needs its own
// narrow, server-mediated write path rather than falling back to pasting
// the revised content into the chat reply.

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { CreateArtifactDetails } from "../wire-types.js";
import { log } from "../logger.js";
import type { ToolContext } from "./create-artifact.js";

interface ArtifactResponse {
  id: string;
  kind: "markdown" | "html";
  title: string | null;
}

export function editArtifactTool(ctx: ToolContext) {
  return defineTool({
    name: "edit_artifact",
    label: "Edit Artifact",
    description:
      "Revise the content (and optionally the title) of an artifact already created in this " +
      "session with create_artifact — full replacement content, not a diff. Use this whenever " +
      "the user asks to change, shorten, extend, or otherwise edit something already in the " +
      "artifact pane, instead of pasting the revised content into the chat reply. Requires the " +
      "artifact_id noted when that artifact was created.",
    parameters: Type.Object({
      artifact_id: Type.String({ format: "uuid" }),
      title: Type.Optional(Type.String({ minLength: 1, maxLength: 200 })),
      content: Type.String({ minLength: 1, maxLength: 120000 }),
    }),
    execute: async (_toolCallId, params, signal) => {
      let res: Response;
      try {
        res = await fetch(`${ctx.apiBaseUrl}/internal/artifacts/${params.artifact_id}`, {
          method: "PATCH",
          headers: {
            "content-type": "application/json",
            "X-Internal-Token": ctx.internalToken,
            "X-Trace-Id": ctx.traceId,
          },
          body: JSON.stringify({
            session_id: ctx.sessionId,
            title: params.title ?? null,
            content: params.content,
          }),
          signal,
        });
      } catch (err) {
        log.error("edit_artifact: fetch to api failed", { trace_id: ctx.traceId, session_id: ctx.sessionId, error: String(err) });
        throw new Error(`edit_artifact: could not reach api at ${ctx.apiBaseUrl}/internal/artifacts/${params.artifact_id}: ${err instanceof Error ? err.message : String(err)}`);
      }

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        log.error("edit_artifact: api returned an error", { trace_id: ctx.traceId, session_id: ctx.sessionId, status: res.status, body: text.slice(0, 500) });
        // Deliberately not a silent fallback (root CLAUDE.md forbidden
        // patterns): a 404 here most often means the model guessed at an
        // artifact_id instead of using the one it was given, and the model
        // needs to see that failure to recover (e.g. by calling
        // create_artifact instead), not have it swallowed.
        throw new Error(`edit_artifact: api responded ${res.status}: ${text.slice(0, 500)}`);
      }

      const artifact = (await res.json()) as ArtifactResponse;
      const details: CreateArtifactDetails = {
        artifact_id: artifact.id,
        kind: artifact.kind,
        title: artifact.title ?? params.title ?? "Untitled",
      };

      return {
        content: [{ type: "text" as const, text: `Artifact "${details.title}" (${details.kind}) updated in the artifact pane.` }],
        details,
      };
    },
  });
}
