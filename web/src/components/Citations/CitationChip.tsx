import { useId, useState } from "react";
import { useMediaQuery, BREAKPOINTS } from "../../state/useMediaQuery";
import { api } from "../../api/client";
import type { ChunkDetail, Citation } from "../../api/types";
import "./Citations.css";

interface CitationChipProps {
  citation: Citation;
}

/**
 * F2 — provenance check. A real <button> (design.md §4: keyboard-reachable,
 * aria-expanded), expanding inline to the verbatim retrieved snippet. The
 * Citation schema doesn't carry the snippet text itself, only chunk_id, so
 * expansion costs one plain GET /chunks/{id} — a data fetch, never a second
 * model call (design.md §1 point 2, AC5).
 *
 * Below 640px this renders as a bottom sheet instead of an inline accordion
 * (design.md §5), to avoid pushing chat content far down a small screen.
 */
export function CitationChip({ citation }: CitationChipProps) {
  const [expanded, setExpanded] = useState(false);
  const [chunk, setChunk] = useState<ChunkDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const isMobile = useMediaQuery(BREAKPOINTS.singleColumn);
  const panelId = useId();

  const handleToggle = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !chunk && !loading) {
      setLoading(true);
      setLoadError(false);
      try {
        const detail = await api.getChunk(citation.chunk_id);
        setChunk(detail);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    }
  };

  const youtubeUrl =
    chunk?.episode.youtube_url ??
    citation.youtube_url ??
    null;
  const startSeconds = chunk?.start_seconds ?? citation.start_seconds ?? null;
  const deepLink = youtubeUrl ? `${youtubeUrl}${startSeconds != null ? `&t=${startSeconds}s` : ""}` : null;

  return (
    <span className="citation">
      <button
        type="button"
        className="citation__chip"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => void handleToggle()}
      >
        <span className="citation__rank" aria-hidden="true">
          {citation.rank}
        </span>
        {citation.guest} · {citation.episode}
      </button>
      {expanded && (
        <span
          id={panelId}
          role="group"
          className={isMobile ? "citation__sheet" : "citation__panel"}
          aria-label={`Source snippet from ${citation.episode}`}
        >
          {isMobile && (
            <button type="button" className="citation__sheet-close" onClick={() => setExpanded(false)}>
              Close
              <span className="sr-only"> citation detail</span>
            </button>
          )}
          {loading && <span className="citation__status">Loading snippet…</span>}
          {loadError && <span className="citation__status citation__status--error">Couldn't load this snippet.</span>}
          {chunk && (
            <>
              <blockquote className="citation__snippet">{chunk.text}</blockquote>
              {deepLink && (
                <a href={deepLink} target="_blank" rel="noreferrer" className="citation__link">
                  Watch on YouTube
                </a>
              )}
            </>
          )}
        </span>
      )}
    </span>
  );
}
