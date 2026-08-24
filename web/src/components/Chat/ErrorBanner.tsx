import type { TurnError } from "../../state/useChatTurn";
import "./Chat.css";

interface ErrorBannerProps {
  error: TurnError;
  provider: string | null;
  onRetry: () => void;
}

/**
 * ADR-005: no silent failover. The banner names the provider and states
 * that outright, with a Retry action when the error is retryable. Red is
 * reserved for this state alone — the abstention card (F5) is deliberately
 * never styled this way.
 */
export function ErrorBanner({ error, provider, onRetry }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-banner__icon" aria-hidden="true">
        ⚠
      </span>
      <div className="error-banner__body">
        <p className="error-banner__title">
          {provider ? `${provider} error` : "Provider error"} — not falling back to cloud automatically
        </p>
        <p className="error-banner__message">{error.message}</p>
        {error.partial && <p className="error-banner__partial">Response was cut off.</p>}
      </div>
      {error.retryable && (
        <button type="button" className="error-banner__retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
