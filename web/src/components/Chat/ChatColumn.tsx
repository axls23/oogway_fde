import type { ConfigResponse, Message } from "../../api/types";
import type { PendingTurn, TurnError } from "../../state/useChatTurn";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { ErrorBanner } from "./ErrorBanner";
import { StarterPrompts } from "../StarterPrompts/StarterPrompts";
import "./Chat.css";

interface ChatColumnProps {
  messages: Message[];
  pending: PendingTurn;
  sending: boolean;
  error: TurnError | null;
  config: ConfigResponse | null;
  onSend: (content: string) => void;
  onRetry: () => void;
}

export function ChatColumn({ messages, pending, sending, error, config, onSend, onRetry }: ChatColumnProps) {
  const isEmpty = messages.length === 0 && !pending.text && !pending.stage && !sending;

  return (
    <div className="chat-column">
      {/* Composer precedes the message list in DOM order deliberately — see
          the note in Chat.css about focus order vs. visual (grid) position. */}
      <div className="chat-column__composer-row">
        <Composer disabled={sending} onSend={onSend} />
      </div>
      <div className="chat-column__messages">
        {error && <ErrorBanner error={error} provider={config?.provider ?? null} onRetry={onRetry} />}
        {isEmpty ? <StarterPrompts onPick={onSend} /> : <MessageList messages={messages} pending={pending} />}
      </div>
    </div>
  );
}
