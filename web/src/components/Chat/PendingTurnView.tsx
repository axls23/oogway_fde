import type { PendingTurn } from "../../state/useChatTurn";
import { StageChip } from "./StageChip";
import { CitationList } from "../Citations/CitationList";
import { SanitizedMarkdown } from "../shared/SanitizedMarkdown";
import "./Chat.css";

/**
 * The in-flight turn: stage chip + streaming text + citations-as-they-arrive,
 * all inside one aria-live="polite" region (design.md §4) so a screen reader
 * announces the replacing stage text and the growing message without
 * interrupting the user, and without re-announcing the whole message on
 * every token.
 */
export function PendingTurnView({ pending }: { pending: PendingTurn }) {
  if (!pending.stage && !pending.text) return null;

  return (
    <div className="message message--assistant" aria-live="polite" aria-atomic="false">
      {pending.stage && <StageChip stage={pending.stage} detail={pending.stageDetail} />}
      {pending.text && (
        <div className="message__bubble message__bubble--assistant message__bubble--streaming">
          <SanitizedMarkdown content={pending.text} />
        </div>
      )}
      <CitationList citations={pending.citations} />
    </div>
  );
}
