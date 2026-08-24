import type { Citation } from "../../api/types";
import { CitationChip } from "./CitationChip";
import "./Citations.css";

interface CitationListProps {
  citations: Citation[];
}

/** Renders beneath a message, chips appearing as `citation` SSE frames
 * arrive — the caller controls ordering by passing the array in arrival
 * order (design.md §3: "the user sees sources accumulate"). */
export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) return null;
  return (
    <div className="citation-list" aria-label="Sources">
      {citations.map((c) => (
        <CitationChip key={c.chunk_id} citation={c} />
      ))}
    </div>
  );
}
