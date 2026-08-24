import { describe, expect, it } from "vitest";
import { SseStreamParser, parseSseText } from "./parser";
import {
  SSE_ABSTENTION,
  SSE_GROUNDED_QA,
  SSE_PROVIDER_ERROR_PARTIAL,
  SSE_SHIP30_ESSAY,
} from "../test/fixtures/sseFixtures";
import type { SseFrame } from "./types";

describe("parseSseText against realistic fixture sequences", () => {
  it("parses the citation-heavy grounded Q&A fixture", () => {
    const frames = parseSseText(SSE_GROUNDED_QA);
    const events = frames.map((f) => f.event);
    expect(events).toEqual([
      "stage",
      "citation",
      "citation",
      "stage",
      "token",
      "token",
      "token",
      "token",
      "citation",
      "token",
      "token",
      "done",
    ]);

    const citations = frames.filter((f): f is Extract<SseFrame, { event: "citation" }> => f.event === "citation");
    expect(citations).toHaveLength(3);
    expect(citations[0]?.data).toEqual({
      chunk_id: 8412,
      episode: "Product-Market Fit, Pricing, and the Truth About Growth",
      guest: "Brian Chesky",
      rank: 1,
      score: 0.82,
    });

    const done = frames.find((f) => f.event === "done");
    expect(done?.data).toMatchObject({ abstained: false });

    const fullText = frames
      .filter((f): f is Extract<SseFrame, { event: "token" }> => f.event === "token")
      .map((f) => f.data.text)
      .join("");
    expect(fullText).toContain("Product-market fit is");
    expect(fullText).toContain("Elena Verna adds");
  });

  it("parses the abstention fixture with no citation frames and abstained: true", () => {
    const frames = parseSseText(SSE_ABSTENTION);
    expect(frames.some((f) => f.event === "citation")).toBe(false);
    const done = frames.find((f) => f.event === "done");
    expect(done?.data).toMatchObject({ abstained: true });
    const text = frames
      .filter((f): f is Extract<SseFrame, { event: "token" }> => f.event === "token")
      .map((f) => f.data.text)
      .join("");
    expect(text).toContain("doesn't cover this directly");
  });

  it("parses the Ship 30 staged-progress fixture with in-place stage replacement and a trailing artifact frame", () => {
    const frames = parseSseText(SSE_SHIP30_ESSAY);
    const stageFrames = frames.filter((f): f is Extract<SseFrame, { event: "stage" }> => f.event === "stage");
    expect(stageFrames.map((f) => `${f.data.stage}:${f.data.detail ?? ""}`)).toEqual([
      "retrieving:",
      "outlining:",
      "drafting:section 1 of 6",
      "drafting:section 2 of 6",
      "drafting:section 3 of 6",
      "drafting:section 4 of 6",
      "drafting:section 5 of 6",
      "drafting:section 6 of 6",
      "assembling:",
    ]);

    const artifact = frames.find((f) => f.event === "artifact");
    expect(artifact?.data).toMatchObject({ kind: "markdown", title: "Why Activation Beats Acquisition" });

    // artifact frame must arrive before done, and after assembling
    const assemblingIdx = frames.findIndex((f) => f.event === "stage" && f.data.stage === "assembling");
    const artifactIdx = frames.findIndex((f) => f.event === "artifact");
    const doneIdx = frames.findIndex((f) => f.event === "done");
    expect(assemblingIdx).toBeLessThan(artifactIdx);
    expect(artifactIdx).toBeLessThan(doneIdx);
  });

  it("parses the partial-error fixture and preserves the already-streamed text alongside the error", () => {
    const frames = parseSseText(SSE_PROVIDER_ERROR_PARTIAL);
    const error = frames.find((f) => f.event === "error");
    expect(error?.data).toMatchObject({ code: "MODEL_TIMEOUT", retryable: true, partial: true });
    // no done frame — the stream terminated on error
    expect(frames.some((f) => f.event === "done")).toBe(false);
    const text = frames
      .filter((f): f is Extract<SseFrame, { event: "token" }> => f.event === "token")
      .map((f) => f.data.text)
      .join("");
    expect(text.length).toBeGreaterThan(0);
  });
});

describe("SseStreamParser incremental buffering", () => {
  it("reassembles frames split across arbitrary chunk boundaries", () => {
    const parser = new SseStreamParser();
    const whole = SSE_GROUNDED_QA;
    const collected: SseFrame[] = [];

    // Feed the fixture back one character at a time — the worst case for a
    // parser that assumes frames arrive intact from fetch's ReadableStream.
    for (const ch of whole) {
      collected.push(...parser.push(ch));
    }
    collected.push(...parser.flush());

    const reference = parseSseText(whole);
    expect(collected).toEqual(reference);
  });

  it("emits nothing for an incomplete trailing frame until flush()", () => {
    const parser = new SseStreamParser();
    const frames = parser.push('event: stage\ndata: {"stage":"retrieving","detail":null}\n\nevent: token\ndata: {"text":"partial');
    expect(frames).toHaveLength(1);
    expect(frames[0]?.event).toBe("stage");

    const flushed = parser.flush();
    expect(flushed).toHaveLength(0); // incomplete JSON — dropped, not thrown
  });

  it("drops frames with an unknown event name rather than throwing", () => {
    const frames = parseSseText('event: future_event\ndata: {"foo":"bar"}\n\nevent: done\ndata: {"message_id":"x","latency_ms":1,"abstained":false}\n\n');
    expect(frames).toHaveLength(1);
    expect(frames[0]?.event).toBe("done");
  });
});
