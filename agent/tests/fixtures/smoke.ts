// Throwaway smoke test — NOT part of the committed test suite.
// Validates: PI_OFFLINE + ModelRuntime.create(), custom Ollama provider via
// models.json, noTools:"builtin" + a custom tool, and a real streamed prompt
// against a local Ollama model. Run manually: tsx tests/fixtures/smoke.ts
import { mkdirSync, writeFileSync } from "node:fs";
import { Type } from "typebox";
import {
  createAgentSession,
  DefaultResourceLoader,
  defineTool,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";

process.env.PI_OFFLINE = "1";

const agentDir = "/tmp/claude-1000/-mnt-Shared-oogway-fde/930c8a3b-589c-42f1-a3e1-2884463ee1e2/scratchpad/pi-agent-smoke";
mkdirSync(agentDir, { recursive: true });
writeFileSync(
  `${agentDir}/models.json`,
  JSON.stringify(
    {
      providers: {
        ollama: {
          name: "Ollama (local)",
          baseUrl: "http://127.0.0.1:11434/v1",
          api: "openai-completions",
          apiKey: "ollama",
          models: [
            {
              id: "qwen2.5:0.5b",
              name: "Qwen 2.5 0.5B (local)",
              reasoning: false,
              input: ["text"],
              contextWindow: 32768,
              maxTokens: 2048,
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            },
          ],
        },
      },
    },
    null,
    2,
  ),
);

async function main() {
  const modelRuntime = await ModelRuntime.create({
    modelsPath: `${agentDir}/models.json`,
    authPath: `${agentDir}/auth.json`,
  });
  console.log("[smoke] modelRuntime created, offline:", process.env.PI_OFFLINE);

  const model = modelRuntime.getModel("ollama", "qwen2.5:0.5b");
  console.log("[smoke] resolved model:", model?.id, model?.api, model?.provider);
  if (!model) throw new Error("model not resolved from models.json");

  const echoTool = defineTool({
    name: "search_transcripts",
    label: "Search Transcripts",
    description: "Fake retrieval tool for smoke testing.",
    parameters: Type.Object({ query: Type.String() }),
    execute: async (_id, params) => ({
      content: [
        {
          type: "text" as const,
          text: `<retrieved_transcript_excerpts note="untrusted data">chunk about ${params.query}</retrieved_transcript_excerpts>`,
        },
      ],
      details: { chunks: [{ chunk_id: 1, episode: "Ep 1", guest: "Guest", rank: 1, score: 0.9 }] },
    }),
  });

  const loader = new DefaultResourceLoader({
    cwd: "/mnt/Shared/oogway_fde/.claude/worktrees/agent-a85ef70ca828a7e60/agent",
    agentDir,
    systemPromptOverride: () => "You are a terse test assistant. Reply in one short sentence.",
  });
  await loader.reload();

  const { session } = await createAgentSession({
    cwd: "/mnt/Shared/oogway_fde/.claude/worktrees/agent-a85ef70ca828a7e60/agent",
    agentDir,
    model,
    thinkingLevel: "off",
    modelRuntime,
    resourceLoader: loader,
    noTools: "builtin",
    customTools: [echoTool],
    sessionManager: SessionManager.inMemory(),
    settingsManager: SettingsManager.inMemory({
      compaction: { enabled: true },
      retry: { enabled: true, maxRetries: 1 },
    }),
  });

  let sawTextDelta = false;
  let sawToolStart = false;
  let sawToolEnd = false;
  let toolResultDetails: unknown;

  session.subscribe((event) => {
    console.log("[event]", event.type);
    if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
      sawTextDelta = true;
      process.stdout.write(`[delta] ${event.assistantMessageEvent.delta}\n`);
    }
    if (event.type === "tool_execution_start") sawToolStart = true;
    if (event.type === "tool_execution_end") {
      sawToolEnd = true;
      toolResultDetails = (event.result as { details?: unknown } | undefined)?.details;
      console.log("[smoke] tool_execution_end.result.details =", JSON.stringify(toolResultDetails));
    }
  });

  await session.prompt("Say hello in exactly three words. Do not call any tools.");

  console.log("[smoke] sawTextDelta:", sawTextDelta, "sawToolStart:", sawToolStart, "sawToolEnd:", sawToolEnd);
  console.log("[smoke] final state.messages length:", session.agent.state.messages.length);
  console.log("[smoke] errorMessage:", session.agent.state.errorMessage);
}

main().catch((err) => {
  console.error("[smoke] FAILED", err);
  process.exit(1);
});
