import { useState } from "react";
import type { Session } from "../../api/types";
import "./Sessions.css";

interface SessionListProps {
  sessions: Session[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

export function SessionList({ sessions, activeId, loading, onSelect, onCreate, onDelete }: SessionListProps) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  return (
    <nav className="session-list" aria-label="Sessions">
      <button type="button" className="session-list__new" onClick={onCreate}>
        + New chat
      </button>

      {loading && <p className="session-list__empty">Loading…</p>}
      {!loading && sessions.length === 0 && <p className="session-list__empty">No sessions yet.</p>}

      <ul className="session-list__items">
        {sessions.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className={`session-list__item${s.id === activeId ? " session-list__item--active" : ""}`}
              onClick={() => onSelect(s.id)}
              aria-current={s.id === activeId ? "true" : undefined}
            >
              <span className="session-list__title">{s.title ?? "Untitled session"}</span>
            </button>
            {pendingDelete === s.id ? (
              <span className="session-list__confirm">
                Delete?
                <button
                  type="button"
                  onClick={() => {
                    onDelete(s.id);
                    setPendingDelete(null);
                  }}
                >
                  Yes
                </button>
                <button type="button" onClick={() => setPendingDelete(null)}>
                  No
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="session-list__delete"
                aria-label={`Delete session ${s.title ?? "Untitled session"}`}
                onClick={() => setPendingDelete(s.id)}
              >
                ×
              </button>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
