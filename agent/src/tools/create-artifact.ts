// create_artifact — architecture.md §8.3, F4. Persists through api's
// POST /internal/artifacts (contract addition — see the note in
// contracts/openapi.yaml and the report for this task: the original
// contract only exposed GET /artifacts/{id}, with no write path).

import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { CreateArtifactDetails } from "../wire-types.js";
import { log } from "../logger.js";

export interface ToolContext {
  apiBaseUrl: string;
  internalToken: string;
  sessionId: string;
  traceId: string;
}

interface ArtifactResponse {
  id: string;
  kind: "markdown" | "html";
  title: string | null;
}

export function createArtifactTool(ctx: ToolContext) {
  return defineTool({
    name: "create_artifact",
    label: "Create Artifact",
    description:
      "Persist a Markdown document or self-contained HTML/CSS snippet for the in-app Artifact " +
      "Viewer. Use this whenever the user asks for a document, essay, memo, one-pager, or " +
      "rendered snippet instead of pasting formatted content into the chat reply.",
    parameters: Type.Object({
      kind: Type.Union([Type.Literal("markdown"), Type.Literal("html")]),
      title: Type.String({ minLength: 1, maxLength: 200 }),
      content: Type.String({ minLength: 1, maxLength: 120000 }),
    }),
    execute: async (_toolCallId, params, signal) => {
      let res: Response;
      try {
        res = await fetch(`${ctx.apiBaseUrl}/internal/artifacts`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "X-Internal-Token": ctx.internalToken,
            "X-Trace-Id": ctx.traceId,
          },
          body: JSON.stringify({
            session_id: ctx.sessionId,
            kind: params.kind,
            title: params.title,
            content: params.content,
          }),
          signal,
        });
      } catch (err) {
        log.error("create_artifact: fetch to api failed", { trace_id: ctx.traceId, session_id: ctx.sessionId, error: String(err) });
        throw new Error(`create_artifact: could not reach api at ${ctx.apiBaseUrl}/internal/artifacts: ${err instanceof Error ? err.message : String(err)}`);
      }

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        log.error("create_artifact: api returned an error", { trace_id: ctx.traceId, session_id: ctx.sessionId, status: res.status, body: text.slice(0, 500) });
        throw new Error(`create_artifact: api responded ${res.status}: ${text.slice(0, 500)}`);
      }

      const artifact = (await res.json()) as ArtifactResponse;
      const details: CreateArtifactDetails = {
        artifact_id: artifact.id,
        kind: artifact.kind,
        title: artifact.title ?? params.title,
      };

      return {
        content: [{ type: "text" as const, text: `Artifact "${details.title}" (${details.kind}) created and saved to the artifact pane.` }],
        details,
      };
    },
  });
}
