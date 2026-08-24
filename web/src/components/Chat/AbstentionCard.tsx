import "./Chat.css";

/**
 * F5 corpus miss. design.md §1 point 3: "Refusal is a first-class state,
 * not an error" — distinct neutral styling (never red), and per §4
 * accessibility, distinguished from the error state by icon and copy, not
 * by hue alone.
 */
export function AbstentionCard({ content }: { content: string }) {
  return (
    <div className="abstention-card" role="status">
      <span className="abstention-card__icon" aria-hidden="true">
        ⊘
      </span>
      <div>
        <p className="abstention-card__title">Outside the corpus</p>
        <p className="abstention-card__body">{content}</p>
      </div>
    </div>
  );
}
