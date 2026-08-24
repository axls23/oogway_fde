# Pi Coding Agent SDK — vendored reference

**Package:** `@earendil-works/pi-coding-agent` · **Pinned version:** `0.84.3`
**Requires:** Node `>=22.19.0` · **Source:** github.com/badlogic/pi-mono,
`packages/coding-agent`. Verified against the package's own `docs/sdk.md`,
`docs/models.md`, `docs/custom-provider.md` and `README.md` on 2026-08-24 —
after this coding agent's training cutoff, which is exactly why this file
exists (architecture.md ADR-007). **Treat this file as the only authority
on the Pi SDK API. Anything not in it is treated as not existing** — do not
recall the API from general training; if a symbol you need is missing here,
say so rather than inventing a plausible one.

---

## Install

```bash
npm install --save-exact @earendil-works/pi-coding-agent@0.84.3
```

`--save-exact` because `agent/package.json` carries no range specifiers
(ADR-007). This also pulls in `@earendil-works/pi-ai`, `pi-agent-core`,
`pi-client`, `pi-protocol`, `pi-tui` as pinned transitive dependencies —
do not add them to `package.json` directly.

## Minimal working example (from upstream docs, confirmed real)

```typescript
import { createAgentSession, ModelRuntime, SessionManager } from "@earendil-works/pi-coding-agent";

const modelRuntime = await ModelRuntime.create();
const { session } = await createAgentSession({
  sessionManager: SessionManager.inMemory(),
  modelRuntime,
});

session.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await session.prompt("What files are in the current directory?");
```

## `createAgentSession(options)`

```typescript
const { session, extensionsResult, modelFallbackMessage } = await createAgentSession({
  cwd?: string,
  agentDir?: string,
  model?: Model,
  thinkingLevel?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max",
  tools?: string[],              // enabled built-ins; default ["read","bash","edit","write"]
  customTools?: ToolDefinition[],
  noTools?: "all" | "builtin",   // "builtin" disables the 4 defaults, KEEPS customTools
  excludeTools?: string[],
  resourceLoader?: ResourceLoader,
  sessionManager?: SessionManager,
  settingsManager?: SettingsManager,
  modelRuntime?: ModelRuntime,
  scopedModels?: Array<{ model: Model; thinkingLevel: string }>,
});
```

Built-in tool names: `read`, `bash`, `powershell`, `edit`, `write`, `grep`,
`find`, `ls`. **This service uses `noTools: "builtin"` and only
`customTools: [searchTranscripts, createArtifact]`** — containment control,
architecture.md §8.5.

## `defineTool(spec)`

```typescript
import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "@sinclair/typebox"; // TypeBox — re-exported, do not add as a direct dep unless tsc requires it

const myTool = defineTool({
  name: "my_tool",
  label: "Display Name",
  description: "What it does",
  parameters: Type.Object({ input: Type.String() }),
  execute: async (_toolCallId, params) => ({
    content: [{ type: "text", text: `Result: ${params.input}` }],
    details: {},
  }),
});
```

Parameters are TypeBox schemas — validated before `execute` runs, so a
malformed tool call from the model never reaches our code.

## Models — built-in providers

```typescript
import { getModel } from "@earendil-works/pi-ai";
const opus = getModel("anthropic", "claude-opus-4-5");
```

`getModel` is exported from `@earendil-works/pi-ai` (a transitive dep of
`pi-coding-agent`, already installed — import it directly, do not add it to
`package.json`), not as a method on a `ModelRuntime` instance.

Built-in provider API key env vars include `ANTHROPIC_API_KEY` (confirmed).
For this service only Anthropic (built-in) and Ollama (custom, below) are
used — `LLM_PROVIDER` selects between them.

### `ModelRuntime.create(options?)`

```typescript
const modelRuntime = await ModelRuntime.create({
  allowModelNetwork?: boolean,     // set false in the container: PI_OFFLINE handles this
  modelRefreshTimeoutMs?: number,
  authPath?: string,
  modelsPath?: string,             // point at a repo-local models.json if not using ~/.pi/agent
  signal?: AbortSignal,
});
```

Set the env var `PI_OFFLINE=1` to disable model network access entirely —
this is what makes the `agent` container boot deterministically with no
outbound connectivity (architecture.md §3, "Offline guarantee").

## Custom provider — Ollama, via `~/.pi/agent/models.json`

Confirmed schema (`docs/custom-provider.md`, `docs/models.md`):

```json
{
  "providers": {
    "ollama": {
      "name": "Ollama (local)",
      "baseUrl": "http://host.docker.internal:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "models": [
        {
          "id": "qwen2.5:7b-instruct",
          "name": "Qwen 2.5 7B Instruct (local)",
          "reasoning": false,
          "input": ["text"],
          "contextWindow": 32768,
          "maxTokens": 4096,
          "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 }
        }
      ]
    }
  }
}
```

- `api` must be one of `"openai-completions"`, `"openai-responses"`,
  `"anthropic-messages"`, `"google-generative-ai"`. Ollama serves an
  OpenAI-compatible endpoint at `/v1`, so `"openai-completions"` is correct
  — **not** a bespoke Ollama API type; none exists in this SDK.
- `apiKey` is a required field when defining models this way, but its value
  is a placeholder — "Ollama ignores it." `"ollama"` is a conventional
  non-secret placeholder, not a real credential.
- This repo writes this file at container build/start time from a template
  (`agent/models.ollama.json`) into `${agentDir}/models.json`, rather than
  requiring an evaluator to hand-edit their home directory — see
  `agent/src/session.ts`.

## `SessionManager`

```typescript
SessionManager.create(cwd: string)   // persistent JSONL sessions under cwd/.pi/sessions
SessionManager.inMemory()            // no persistence — used only in unit tests
```

This service uses `SessionManager.create("/app")` in the container, with
`/app/.pi/sessions` mounted as the `pi-sessions` volume — the audit trail
ADR-002 describes. It is written, never read back for application state.

## `SettingsManager`

```typescript
const settingsManager = SettingsManager.inMemory({
  compaction: { enabled: true },
  retry: { enabled: true, maxRetries: 2 },
});
// or SettingsManager.create(cwd?, agentDir?) to load from files
```

Call `await settingsManager.flush()` before process exit if using a
file-backed manager. This service uses `inMemory()` — settings are fixed
by our own config, not user-editable per turn.

## `DefaultResourceLoader`

```typescript
const loader = new DefaultResourceLoader({
  cwd: "/app",                                    // discovers .pi/skills, .pi/extensions under here
  agentDir: "~/.pi/agent",
  systemPromptOverride: () => LENNY_SYSTEM_PROMPT,
  additionalExtensionPaths?: string[],
  extensionFactories?: Array<(pi) => void>,
});
await loader.reload();
```

## Session events (`session.subscribe`)

| Event | Fields used here |
|---|---|
| `agent_start` | — |
| `tool_execution_start` | `event.toolName` |
| `tool_execution_end` | `event.isError` |
| `message_update` | `event.assistantMessageEvent.type === "text_delta"`, `.delta` |
| `turn_start` / `turn_end` | `event.message`, `event.toolResults` |
| `agent_end` | `event.messages` — new messages produced this turn |

Confirmed additionally present but unused here: `message_start`,
`message_end`, `queue_update`.

## Agent state

```typescript
const state = session.agent.state;
// state.messages: AgentMessage[]
// state.model, state.systemPrompt, state.tools, state.streamingMessage?
```

Rehydration for a new turn: `session.agent.state.messages = rehydrate(historyFromPostgres);`
— confirmed as a supported in-place assignment.

## What is NOT confirmed / do not use

- No confirmed "Ollama-native" API type — always route Ollama through
  `"openai-completions"` at its `/v1` endpoint, per above.
- No confirmed synchronous, non-streaming single-call helper distinct from
  `session.prompt()` — do not invent one for the query-condensation step;
  either use a short-lived session with `noTools: "all"`, or call the
  provider's HTTP endpoint directly for that one low-temperature call if
  simpler. Prefer the direct HTTP call for condensation: it is not agentic
  work and does not need a Pi session.
