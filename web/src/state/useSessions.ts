import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Session } from "../api/types";

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listSessions();
      setSessions(res.items);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createSession = useCallback(async () => {
    const session = await api.createSession({});
    setSessions((prev) => [session, ...prev]);
    return session;
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    await api.deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  }, []);

  return { sessions, loading, refresh, createSession, deleteSession };
}
