import { useCallback, useState } from "react";
import { useConfig } from "./state/useConfig";
import { useSessions } from "./state/useSessions";
import { useMediaQuery, BREAKPOINTS } from "./state/useMediaQuery";
import { ProviderBadge } from "./components/ProviderBadge/ProviderBadge";
import { ActiveCapabilities } from "./components/Capabilities/ActiveCapabilities";
import { CapabilitiesSettings } from "./components/CapabilitiesSettings/CapabilitiesSettings";
import { SessionList } from "./components/Sessions/SessionList";
import { SessionWorkspace } from "./components/SessionWorkspace";
import "./App.css";

export function App() {
  const { config, loading: configLoading, failed: configFailed, refetch: refetchConfig } = useConfig();
  const { sessions, loading: sessionsLoading, refresh, createSession, deleteSession } = useSessions();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "settings">("chat");
  const isDrawerBreakpoint = useMediaQuery(BREAKPOINTS.drawer);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleCreate = useCallback(async () => {
    const session = await createSession();
    setActiveId(session.id);
    setDrawerOpen(false);
  }, [createSession]);

  const handleSelect = useCallback((id: string) => {
    setActiveId(id);
    setDrawerOpen(false);
  }, []);

  const handleDelete = useCallback(
    async (id: string) => {
      await deleteSession(id);
      if (activeId === id) setActiveId(null);
    },
    [deleteSession, activeId],
  );

  // Stable identities: SessionWorkspace's effect depends on these by
  // reference (fires "any turn that reaches the network touches session
  // recency"). An inline `() => ...` here would get a new identity every
  // App render, and since calling it triggers exactly that state update,
  // it re-renders App -> new closure -> effect fires again -> infinite loop.
  const handleSessionTouched = useCallback(() => void refresh(), [refresh]);
  const handleRetryConfig = useCallback(() => void refetchConfig(), [refetchConfig]);

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-left">
          {isDrawerBreakpoint && (
            <button
              type="button"
              className="app__drawer-toggle"
              aria-expanded={drawerOpen}
              aria-controls="session-drawer"
              onClick={() => setDrawerOpen((v) => !v)}
            >
              <span aria-hidden="true">☰</span>
              <span className="sr-only">Toggle session list</span>
            </button>
          )}
          <span className="app__name">The Lenny Growth Assistant</span>
        </div>
        <div className="app__header-right">
          <button
            type="button"
            className="app__settings-toggle"
            aria-pressed={view === "settings"}
            onClick={() => setView((v) => (v === "settings" ? "chat" : "settings"))}
          >
            ⚙ Capabilities settings
          </button>
          <ActiveCapabilities capabilities={config?.capabilities ?? null} />
          <ProviderBadge config={config} loading={configLoading} failed={configFailed} />
        </div>
      </header>

      {view === "settings" ? (
        <div className="app__body">
          <CapabilitiesSettings
            sessionId={activeId}
            capabilities={config?.capabilities ?? null}
            onClose={() => setView("chat")}
          />
        </div>
      ) : (
        <div className="app__body">
          {(!isDrawerBreakpoint || drawerOpen) && (
            <>
              <aside
                id="session-drawer"
                className={isDrawerBreakpoint ? "app__sessions app__sessions--drawer" : "app__sessions"}
              >
                <SessionList
                  sessions={sessions}
                  activeId={activeId}
                  loading={sessionsLoading}
                  onSelect={handleSelect}
                  onCreate={() => void handleCreate()}
                  onDelete={(id) => void handleDelete(id)}
                />
              </aside>
              {isDrawerBreakpoint && (
                <div className="app__scrim" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
              )}
            </>
          )}

          <main className="app__main">
            {activeId ? (
              <SessionWorkspace
                key={activeId}
                sessionId={activeId}
                config={config}
                onSessionTouched={handleSessionTouched}
                onRetryConfig={handleRetryConfig}
              />
            ) : (
              <div className="app__welcome">
                <h1>Welcome to The Lenny Growth Assistant</h1>
                <p>Start a new chat to ask a grounded question, draft a Ship 30 essay, or generate an artifact.</p>
                <button type="button" className="app__welcome-cta" onClick={() => void handleCreate()}>
                  + New chat
                </button>
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
