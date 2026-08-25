import type { Message } from "../../api/types";
import { CitationList } from "../Citations/CitationList";
import { AbstentionCard } from "./AbstentionCard";
import { SanitizedMarkdown } from "../shared/SanitizedMarkdown";
import "./Chat.css";

function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** "Assistant · ollama · qwen2.5:7b · 4.2s" — every field here is data the
 * Message schema already carries (provider/model/latency_ms); nothing here
 * is invented for display. design.md §1 point 4: the provider is never
 * invisible, applied per-turn as well as in the header badge. */
function assistantMeta(message: Message): string {
  const parts = ["Assistant"];
  if (message.provider) parts.push(message.provider);
  if (message.model) parts.push(message.model);
  const time = formatClock(message.created_at);
  const label = parts.join(" · ");
  if (message.latency_ms != null) {
    return `${label} · ${(message.latency_ms / 1000).toFixed(1)}s`;
  }
  return time ? `${label} · ${time}` : label;
}

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className="message message--user">
        <div className="message__meta">You · {formatClock(message.created_at)}</div>
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
      <div className="message__meta">{assistantMeta(message)}</div>
      <div className="message__bubble message__bubble--assistant">
        <SanitizedMarkdown content={message.content} />
      </div>
      <CitationList citations={message.citations ?? []} />
    </div>
  );
}
