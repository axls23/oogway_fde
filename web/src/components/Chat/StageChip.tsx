import type { StageName } from "../../sse/types";
import "./Chat.css";

const STAGE_LABEL: Record<StageName, string> = {
  thinking: "Thinking…",
  retrieving: "Searching Lenny's transcripts…",
  outlining: "Outlining…",
  drafting: "Drafting…",
  assembling: "Assembling…",
};

interface StageChipProps {
  stage: StageName;
  detail: string | null;
}

/** A single-line status chip that REPLACES in place — design.md §3:
 * "Drafting section 3 of 6…" updates the previous stage text, it does not
 * stack into a list. The parent's aria-live region is what makes the
 * replacement (not the addition) the thing a screen reader announces. */
export function StageChip({ stage, detail }: StageChipProps) {
  const label = STAGE_LABEL[stage];
  return (
    <div className="stage-chip">
      <span className="stage-chip__spinner" aria-hidden="true" />
      {label}
      {detail ? ` ${detail}` : ""}
    </div>
  );
}
