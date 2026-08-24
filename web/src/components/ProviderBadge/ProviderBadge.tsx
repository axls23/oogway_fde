import type { ConfigResponse } from "../../api/types";
import "./ProviderBadge.css";

interface ProviderBadgeProps {
  config: ConfigResponse | null;
  loading: boolean;
  failed: boolean;
}

/**
 * Persistent header chrome, not settings-page trivia (design.md §1 point 4):
 * "the provider is never invisible." Renders `● {provider} · {model}`.
 * Refetched by the caller (App.tsx) on mount and after any error-banner
 * Retry, so a provider switch is visible without a page reload.
 */
export function ProviderBadge({ config, loading, failed }: ProviderBadgeProps) {
  if (loading) {
    return (
      <span className="provider-badge provider-badge--loading" aria-live="polite">
        <span className="provider-badge__dot" aria-hidden="true" />
        Checking provider…
      </span>
    );
  }

  if (failed || !config) {
    return (
      <span className="provider-badge provider-badge--failed" role="status">
        <span className="provider-badge__dot" aria-hidden="true" />
        Provider unknown
      </span>
    );
  }

  return (
    <span className="provider-badge" role="status">
      <span className="provider-badge__dot" aria-hidden="true" />
      {config.provider} · {config.model}
    </span>
  );
}
