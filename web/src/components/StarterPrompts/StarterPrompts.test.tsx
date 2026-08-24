import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StarterPrompts } from "./StarterPrompts";

describe("StarterPrompts (F6)", () => {
  it("shows three cards, each a distinct capability", () => {
    render(<StarterPrompts onPick={() => {}} />);
    expect(screen.getByRole("button", { name: /grounded question/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ship 30 essay/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /one-pager/i })).toBeInTheDocument();
  });

  it("invokes onPick with the card's concrete prompt text", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<StarterPrompts onPick={onPick} />);
    await user.click(screen.getByRole("button", { name: /ship 30 essay/i }));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0]?.[0]).toMatch(/ship 30 essay/i);
  });
});
