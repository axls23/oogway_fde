import type { Message } from "../../api/types";
import { CitationList } from "../Citations/CitationList";
import { AbstentionCard } from "./AbstentionCard";
import { SanitizedMarkdown } from "../shared/SanitizedMarkdown";
import "./Chat.css";

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="message message--user">
        <div className="message__bubble message__bubble--user">{message.content}</div>
      </div>
    );
  }

  if (message.abstained) {
    return (
      <div className="message message--assistant">
        <AbstentionCard content={message.content} />
      </div>
    );
  }

  return (
    <div className="message message--assistant">
      <div className="message__bubble message__bubble--assistant">
        <SanitizedMarkdown content={message.content} />
      </div>
      <CitationList citations={message.citations ?? []} />
    </div>
  );
}
