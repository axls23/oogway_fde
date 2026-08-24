import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CitationChip } from "./CitationChip";
import { api } from "../../api/client";
import { FIXTURE_CHUNK } from "../../test/fixtures/apiFixtures";
import type { Citation } from "../../api/types";

vi.mock("../../api/client", () => ({
  api: { getChunk: vi.fn() },
}));

const citation: Citation = {
  chunk_id: 8412,
  episode: "Product-Market Fit, Pricing, and the Truth About Growth",
  guest: "Brian Chesky",
  youtube_url: "https://youtube.com/watch?v=abc123",
  start_seconds: 842,
  rank: 1,
  score: 0.82,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("CitationChip (F2 / AC5)", () => {
  it("is a real button, collapsed by default with aria-expanded=false", () => {
    render(<CitationChip citation={citation} />);
    const button = screen.getByRole("button", { name: /Brian Chesky/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("expands to the verbatim snippet via a single GET /chunks/{id} — never a chat turn", async () => {
    vi.mocked(api.getChunk).mockResolvedValue(FIXTURE_CHUNK);
    const user = userEvent.setup();
    render(<CitationChip citation={citation} />);

    const button = screen.getByRole("button", { name: /Brian Chesky/ });
    await user.click(button);

    expect(button).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(screen.getByText(/leaky bucket/)).toBeInTheDocument());

    expect(api.getChunk).toHaveBeenCalledTimes(1);
    expect(api.getChunk).toHaveBeenCalledWith(8412);
  });

  it("collapses again on a second click without re-fetching", async () => {
    vi.mocked(api.getChunk).mockResolvedValue(FIXTURE_CHUNK);
    const user = userEvent.setup();
    render(<CitationChip citation={citation} />);
    const button = screen.getByRole("button", { name: /Brian Chesky/ });

    await user.click(button);
    await waitFor(() => expect(api.getChunk).toHaveBeenCalledTimes(1));
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    await waitFor(() => expect(api.getChunk).toHaveBeenCalledTimes(1)); // still 1 — cached
  });
});
