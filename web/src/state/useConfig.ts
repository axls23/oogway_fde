import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ConfigResponse } from "../api/types";

/**
 * Fetches GET /config on mount and exposes a refetch(), so callers (the
 * provider badge, and any error-banner Retry action) can re-pull it after a
 * retry per design.md §1 point 4 ("provider is never invisible").
 */
export function useConfig() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const cfg = await api.getConfig();
      setConfig(cfg);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { config, loading, failed, refetch };
}
