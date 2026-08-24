import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBanner } from "./ErrorBanner";

describe("ErrorBanner (ADR-005 — no silent failover)", () => {
  it("names the provider and states it will not fail over to cloud", () => {
    render(
      <ErrorBanner
        error={{ code: "OLLAMA_UNREACHABLE", message: "ollama is unreachable", retryable: true, partial: false }}
        provider="ollama"
        onRetry={() => {}}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/ollama error/i)).toBeInTheDocument();
    expect(screen.getByText(/not falling back to cloud automatically/i)).toBeInTheDocument();
  });

  it("offers Retry only when retryable, and calls onRetry when clicked", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <ErrorBanner
        error={{ code: "MODEL_TIMEOUT", message: "timed out", retryable: true, partial: false }}
        provider="ollama"
        onRetry={onRetry}
      />,
    );
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a 'Response was cut off' notice when the error is partial", () => {
    render(
      <ErrorBanner
        error={{ code: "MODEL_TIMEOUT", message: "timed out", retryable: true, partial: true }}
        provider="ollama"
        onRetry={() => {}}
      />,
    );
    expect(screen.getByText(/response was cut off/i)).toBeInTheDocument();
  });

  it("omits the Retry button when not retryable", () => {
    render(
      <ErrorBanner
        error={{ code: "FATAL", message: "unrecoverable", retryable: false, partial: false }}
        provider="ollama"
        onRetry={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
