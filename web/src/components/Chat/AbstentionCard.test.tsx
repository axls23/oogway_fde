import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AbstentionCard } from "./AbstentionCard";

describe("AbstentionCard (F5 — a first-class state, not an error)", () => {
  it("renders as role=status, not role=alert, and carries no error-banner classes", () => {
    render(<AbstentionCard content="Lenny's Podcast doesn't cover this directly." />);
    const card = screen.getByRole("status");
    expect(card.className).toContain("abstention-card");
    expect(card.className).not.toContain("error-banner");
  });

  it("shows the gap in the message text", () => {
    render(<AbstentionCard content="Closest topics indexed: pricing, activation." />);
    expect(screen.getByText(/Closest topics indexed/)).toBeInTheDocument();
  });
});
