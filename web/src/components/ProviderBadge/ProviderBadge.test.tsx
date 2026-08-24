import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProviderBadge } from "./ProviderBadge";
import { FIXTURE_CONFIG } from "../../test/fixtures/apiFixtures";

describe("ProviderBadge (design.md §1 point 4 — the provider is never invisible)", () => {
  it("renders '● {provider} · {model}' once config loads", () => {
    render(<ProviderBadge config={FIXTURE_CONFIG} loading={false} failed={false} />);
    expect(screen.getByText(/ollama · qwen2\.5:7b-instruct/)).toBeInTheDocument();
  });

  it("shows a loading state before /config resolves", () => {
    render(<ProviderBadge config={null} loading={true} failed={false} />);
    expect(screen.getByText(/checking provider/i)).toBeInTheDocument();
  });

  it("shows a distinct failed state without inventing a provider name", () => {
    render(<ProviderBadge config={null} loading={false} failed={true} />);
    expect(screen.getByText(/provider unknown/i)).toBeInTheDocument();
  });
});
