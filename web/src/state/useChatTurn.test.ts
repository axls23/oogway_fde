import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useChatTurn } from "./useChatTurn";
import { SSE_ABSTENTION, SSE_GROUNDED_QA, SSE_SHIP30_ESSAY } from "../test/fixtures/sseFixtures";

/** Builds a fetch Response whose body streams the given text in several
 * small chunks, split at byte offsets that don't respect SSE frame
 * boundaries — the same stress case the parser tests apply directly. */
function streamingResponse(text: string, chunkSize = 37): Response {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      const next = bytes.slice(offset, offset + chunkSize);
      offset += chunkSize;
      controller.enqueue(next);
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("useChatTurn against realistic SSE fixtures", () => {
  it("accumulates a citation-heavy grounded answer and finalizes on done", async () => {
    global.fetch = vi.fn().mockResolvedValue(streamingResponse(SSE_GROUNDED_QA));
    const { result } = renderHook(() => useChatTurn("session-1", []));

    act(() => {
      result.current.sendMessage("What do operators say about PMF?");
    });

    await waitFor(() => expect(result.current.sending).toBe(false));

    // optimistic user message + finalized assistant message
    expect(result.current.messages).toHaveLength(2);
    const assistant = result.current.messages[1];
    expect(assistant?.role).toBe("assistant");
    expect(assistant?.abstained).toBe(false);
    expect(assistant?.citations).toHaveLength(3);
    expect(assistant?.content).toContain("Product-market fit is");
    expect(result.current.pending.text).toBe(""); // pending cleared after done
    expect(result.current.error).toBeNull();
  });

  it("marks the finalized message abstained: true on the abstention fixture, with no citations", async () => {
    global.fetch = vi.fn().mockResolvedValue(streamingResponse(SSE_ABSTENTION));
    const { result } = renderHook(() => useChatTurn("session-1", []));

    act(() => {
      result.current.sendMessage("What do operators say about semiconductor supply chains?");
    });

    await waitFor(() => expect(result.current.sending).toBe(false));

    const assistant = result.current.messages[1];
    expect(assistant?.abstained).toBe(true);
    expect(assistant?.citations).toHaveLength(0);
  });

  it("surfaces staged progress and an artifact id for the Ship 30 fixture", async () => {
    global.fetch = vi.fn().mockResolvedValue(streamingResponse(SSE_SHIP30_ESSAY));
    const { result } = renderHook(() => useChatTurn("session-1", []));

    act(() => {
      result.current.sendMessage("Write a Ship 30 essay on activation.");
    });

    await waitFor(() => expect(result.current.sending).toBe(false));

    const assistant = result.current.messages[1];
    expect(assistant?.content).toContain("# Why Activation Beats Acquisition");
    expect(assistant?.citations?.length).toBeGreaterThanOrEqual(3);
  });
});
