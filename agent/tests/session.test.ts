import { test } from "node:test";
import assert from "node:assert/strict";
import { buildOllamaModelsConfig, rehydrate, TurnRequestError } from "../src/session.js";

const TEMPLATE = {
  providers: {
    ollama: {
      name: "Ollama (local)",
      baseUrl: "http://host.docker.internal:11434/v1",
      api: "openai-completions",
      apiKey: "ollama",
      models: [
        {
          id: "qwen2.5:7b-instruct",
          name: "Qwen 2.5 7B Instruct (local)",
          reasoning: false,
          input: ["text"],
          contextWindow: 32768,
          maxTokens: 4096,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        },
      ],
    },
  },
};

test("buildOllamaModelsConfig: rewrites baseUrl to <OLLAMA_BASE_URL>/v1 and the model id, keeps other fields", () => {
  const out = buildOllamaModelsConfig(TEMPLATE, "http://127.0.0.1:11434", "qwen2.5:0.5b") as any;
  assert.equal(out.providers.ollama.baseUrl, "http://127.0.0.1:11434/v1");
  assert.equal(out.providers.ollama.models.length, 1);
  assert.equal(out.providers.ollama.models[0].id, "qwen2.5:0.5b");
  // Fields not being overridden survive the rewrite.
  assert.equal(out.providers.ollama.apiKey, "ollama");
  assert.equal(out.providers.ollama.models[0].contextWindow, 32768);
  assert.equal(out.providers.ollama.api, "openai-completions");
});

test("buildOllamaModelsConfig: trims a trailing slash on OLLAMA_BASE_URL before appending /v1", () => {
  const out = buildOllamaModelsConfig(TEMPLATE, "http://127.0.0.1:11434/", "qwen2.5:0.5b") as any;
  assert.equal(out.providers.ollama.baseUrl, "http://127.0.0.1:11434/v1");
});

test("buildOllamaModelsConfig: does not mutate the input template", () => {
  const before = JSON.stringify(TEMPLATE);
  buildOllamaModelsConfig(TEMPLATE, "http://example:1", "other-model");
  assert.equal(JSON.stringify(TEMPLATE), before);
});

test("buildOllamaModelsConfig: throws a clear error on a malformed template", () => {
  assert.throws(() => buildOllamaModelsConfig({ providers: { ollama: { models: [] } } }, "http://x", "m"), /models\[0\]/);
});

const FAKE_MODEL = { id: "qwen2.5:7b-instruct", api: "openai-completions", provider: "ollama" } as any;

test("rehydrate: splits the trailing user message into promptText and converts the rest", () => {
  const { messages, promptText } = rehydrate(
    [
      { role: "user", content: "our activation dropped after a second onboarding step" },
      { role: "assistant", content: "Several guests discuss this — want specifics on B2B or B2C?" },
      { role: "user", content: "B2B" },
    ],
    FAKE_MODEL,
    "trace-1",
  );
  assert.equal(promptText, "B2B");
  assert.equal(messages.length, 2);
  assert.equal((messages[0] as any).role, "user");
  assert.equal((messages[0] as any).content, "our activation dropped after a second onboarding step");
  assert.equal((messages[1] as any).role, "assistant");
  assert.deepEqual((messages[1] as any).content, [{ type: "text", text: "Several guests discuss this — want specifics on B2B or B2C?" }]);
  assert.equal((messages[1] as any).provider, "ollama");
  assert.equal((messages[1] as any).stopReason, "stop");
});

test("rehydrate: skips system-role history entries (no Pi Message variant for them)", () => {
  const { messages, promptText } = rehydrate(
    [
      { role: "system", content: "internal note: retrieval abstained on a prior turn" },
      { role: "user", content: "what about pricing" },
    ],
    FAKE_MODEL,
    "trace-2",
  );
  assert.equal(promptText, "what about pricing");
  assert.equal(messages.length, 0);
});

test("rehydrate: throws TurnRequestError when history does not end in a user message", () => {
  assert.throws(() => rehydrate([{ role: "assistant", content: "..." }], FAKE_MODEL, "trace-3"), TurnRequestError);
  assert.throws(() => rehydrate([], FAKE_MODEL, "trace-4"), TurnRequestError);
});
