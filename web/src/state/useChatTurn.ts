import { useCallback, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { consumeSseResponse } from "../sse/parser";
import type { StageName } from "../sse/types";
import type { Citation, Message } from "../api/types";

export interface TurnError {
  code: string;
  message: string;
  retryable: boolean;
  /** The already-streamed text should stay visible when this is true
   * (design.md: "Response was cut off" notice, not a discard). */
  partial: boolean;
}

export interface PendingTurn {
  stage: StageName | null;
  stageDetail: string | null;
  text: string;
  citations: Citation[];
  artifactId: string | null;
}

const EMPTY_PENDING: PendingTurn = { stage: null, stageDetail: null, text: "", citations: [], artifactId: null };

/**
 * Owns one session's message list and the lifecycle of a single in-flight
 * turn: optimistic user message -> SSE stream -> finalized assistant
 * message, or a named, retryable error with any partial text preserved.
 *
 * Citations render from the SSE `citation` frames as they arrive (never
 * parsed from model text), per architecture.md §7 and CLAUDE.md invariant 1.
 */
export function useChatTurn(sessionId: string, initialMessages: Message[]) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [pending, setPending] = useState<PendingTurn>(EMPTY_PENDING);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<TurnError | null>(null);
  const lastContentRef = useRef<string>("");
  const abortRef = useRef<AbortController | null>(null);

  const runTurn = useCallback(
    async (content: string) => {
      lastContentRef.current = content;
      setError(null);
      setSending(true);
      setPending(EMPTY_PENDING);

      const userMessage: Message = {
        id: `optimistic-${crypto.randomUUID()}`,
        session_id: sessionId,
        role: "user",
        content,
        abstained: false,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await api.postMessageStream(sessionId, { content }, controller.signal);
        let localPending = EMPTY_PENDING;

        await consumeSseResponse(
          response,
          (frame) => {
            switch (frame.event) {
              case "stage": {
                localPending = { ...localPending, stage: frame.data.stage, stageDetail: frame.data.detail };
                setPending(localPending);
                break;
              }
              case "token": {
                localPending = { ...localPending, text: localPending.text + frame.data.text };
                setPending(localPending);
                break;
              }
              case "citation": {
                const citation: Citation = {
                  chunk_id: frame.data.chunk_id,
                  episode: frame.data.episode,
                  guest: frame.data.guest,
                  rank: frame.data.rank,
                  score: frame.data.score,
                  youtube_url: null,
                  start_seconds: null,
                };
                localPending = { ...localPending, citations: [...localPending.citations, citation] };
                setPending(localPending);
                break;
              }
              case "artifact": {
                localPending = { ...localPending, artifactId: frame.data.artifact_id };
                setPending(localPending);
                break;
              }
              case "error": {
                setError({
                  code: frame.data.code,
                  message: frame.data.message,
                  retryable: frame.data.retryable,
                  partial: frame.data.partial ?? false,
                });
                if (frame.data.partial) {
                  const assistantMessage: Message = {
                    id: `partial-${crypto.randomUUID()}`,
                    session_id: sessionId,
                    role: "assistant",
                    content: localPending.text,
                    abstained: false,
                    created_at: new Date().toISOString(),
                    citations: localPending.citations,
                  };
                  setMessages((prev) => [...prev, assistantMessage]);
                }
                localPending = EMPTY_PENDING;
                setPending(EMPTY_PENDING);
                break;
              }
              case "done": {
                const assistantMessage: Message = {
                  id: frame.data.message_id,
                  session_id: sessionId,
                  role: "assistant",
                  content: localPending.text,
                  abstained: frame.data.abstained,
                  latency_ms: frame.data.latency_ms,
                  created_at: new Date().toISOString(),
                  citations: localPending.citations,
                };
                setMessages((prev) => [...prev, assistantMessage]);
                localPending = EMPTY_PENDING;
                setPending(EMPTY_PENDING);
                break;
              }
            }
          },
          controller.signal,
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        const apiErr = err instanceof ApiError ? err : null;
        setError({
          code: apiErr?.code ?? "NETWORK_ERROR",
          message: apiErr?.message ?? "Could not reach the API.",
          retryable: apiErr?.retryable ?? true,
          partial: false,
        });
        setPending(EMPTY_PENDING);
      } finally {
        setSending(false);
        abortRef.current = null;
      }
    },
    [sessionId],
  );

  const sendMessage = useCallback((content: string) => void runTurn(content), [runTurn]);

  const retry = useCallback(() => {
    if (!lastContentRef.current) return;
    // Remove the optimistic user message that preceded the failed turn so
    // retry doesn't duplicate it.
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "user" && last.content === lastContentRef.current) {
        return prev.slice(0, -1);
      }
      return prev;
    });
    void runTurn(lastContentRef.current);
  }, [runTurn]);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, pending, sending, error, sendMessage, retry, cancel };
}
