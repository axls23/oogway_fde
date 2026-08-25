import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConfigResponse, Message } from "../api/types";
import { useChatTurn } from "../state/useChatTurn";
import { useMediaQuery, BREAKPOINTS } from "../state/useMediaQuery";
import { ChatColumn } from "./Chat/ChatColumn";
import { ArtifactViewer } from "./ArtifactViewer/ArtifactViewer";
import { StageChip } from "./Chat/StageChip";

interface SessionWorkspaceProps {
  sessionId: string;
  config: ConfigResponse | null;
  onSessionTouched: () => void;
  onRetryConfig: () => void;
}

/**
 * Keyed by sessionId in App.tsx (key={sessionId}) so switching sessions
 * remounts this component and gives every hook a clean slate — simpler and
 * more obviously correct than threading a "reset" action through
 * useChatTurn for a single-user, tens-of-turns-a-day system (PRD A9).
 */
export function SessionWorkspace({ sessionId, config, onSessionTouched, onRetryConfig }: SessionWorkspaceProps) {
  const [initialMessages, setInitialMessages] = useState<Message[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getSession(sessionId)
      .then((detail) => {
        if (!cancelled) setInitialMessages(detail.messages);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loadFailed) {
    return <div className="chat-column__messages">Couldn't load this session.</div>;
  }
  if (!initialMessages) {
    return <div className="chat-column__messages">Loading conversation…</div>;
  }

  return (
    <SessionChat
      sessionId={sessionId}
      initialMessages={initialMessages}
      config={config}
      onSessionTouched={onSessionTouched}
      onRetryConfig={onRetryConfig}
    />
  );
}

function SessionChat({
  sessionId,
  initialMessages,
  config,
  onSessionTouched,
  onRetryConfig,
}: {
  sessionId: string;
  initialMessages: Message[];
  config: ConfigResponse | null;
  onSessionTouched: () => void;
  onRetryConfig: () => void;
}) {
  const { messages, pending, sending, error, sendMessage, retry } = useChatTurn(sessionId, initialMessages);
  const [lastArtifactId, setLastArtifactId] = useState<string | null>(null);
  const [artifactRefreshToken, setArtifactRefreshToken] = useState(0);
  const [paneOpen, setPaneOpen] = useState(false);
  const isSingleColumn = useMediaQuery(BREAKPOINTS.singleColumn);
  const [mobileTab, setMobileTab] = useState<"chat" | "artifact">("chat");

  useEffect(() => {
    if (pending.stage === "outlining" || pending.stage === "assembling") {
      setPaneOpen(true);
    }
  }, [pending.stage]);

  useEffect(() => {
    if (pending.artifactId) {
      // Bump unconditionally, even when pending.artifactId matches
      // lastArtifactId — edit_artifact revises the same id in place, and
      // this is ArtifactViewer's only signal to refetch in that case.
      setArtifactRefreshToken((n) => n + 1);
      setLastArtifactId(pending.artifactId);
      setPaneOpen(true);
      if (isSingleColumn) setMobileTab("artifact");
    }
    // isSingleColumn intentionally excluded: only react to a NEW artifact id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending.artifactId]);

  useEffect(() => {
    // Any turn that reaches the network touches session recency in the
    // session list (new/updated title, ordering) — a light-touch refresh.
    if (!sending) onSessionTouched();
  }, [sending, onSessionTouched]);

  const handleSend = (content: string) => sendMessage(content);

  // design.md §1 point 4: the provider badge re-checks GET /config after any
  // error-banner Retry, so a provider that came back is reflected right away.
  const handleRetry = () => {
    retry();
    onRetryConfig();
  };

  const artifactPane = paneOpen ? (
    lastArtifactId ? (
      <ArtifactViewer artifactId={lastArtifactId} refreshToken={artifactRefreshToken} onClose={() => setPaneOpen(false)} />
    ) : (
      <div className="artifact-pane">
        <div className="artifact-pane__header">
          <div className="artifact-pane__heading">
            <span className="artifact-pane__title">Generating…</span>
          </div>
        </div>
        <div className="artifact-pane__status">
          {pending.stage && <StageChip stage={pending.stage} detail={pending.stageDetail} />}
        </div>
      </div>
    )
  ) : null;

  if (isSingleColumn) {
    return (
      <div className="mobile-body">
        <div className="mobile-tabs" role="tablist" aria-label="View">
          <button
            type="button"
            role="tab"
            aria-selected={mobileTab === "chat"}
            className={`mobile-tabs__tab${mobileTab === "chat" ? " mobile-tabs__tab--active" : ""}`}
            onClick={() => setMobileTab("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mobileTab === "artifact"}
            disabled={!paneOpen}
            className={`mobile-tabs__tab${mobileTab === "artifact" ? " mobile-tabs__tab--active" : ""}`}
            onClick={() => setMobileTab("artifact")}
          >
            Artifact
          </button>
        </div>
        <div className="mobile-body__content">
          {mobileTab === "chat" ? (
            <ChatColumn
              messages={messages}
              pending={pending}
              sending={sending}
              error={error}
              config={config}
              onSend={handleSend}
              onRetry={handleRetry}
            />
          ) : (
            artifactPane
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="workspace">
      <div className="workspace__chat">
        <ChatColumn
          messages={messages}
          pending={pending}
          sending={sending}
          error={error}
          config={config}
          onSend={handleSend}
          onRetry={handleRetry}
        />
      </div>
      {paneOpen && <div className="workspace__artifact">{artifactPane}</div>}
    </div>
  );
}
