import { useEffect, useRef } from "react";
import type { Message } from "../../api/types";
import type { PendingTurn } from "../../state/useChatTurn";
import { MessageBubble } from "./MessageBubble";
import { PendingTurnView } from "./PendingTurnView";
import "./Chat.css";

interface MessageListProps {
  messages: Message[];
  pending: PendingTurn;
}

export function MessageList({ messages, pending }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pending.text, pending.stage]);

  return (
    <div className="message-list" role="log" aria-label="Conversation">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      <PendingTurnView pending={pending} />
      <div ref={bottomRef} />
    </div>
  );
}
