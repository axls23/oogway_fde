import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SanitizedMarkdown } from "./SanitizedMarkdown";

describe("SanitizedMarkdown (architecture.md §10 — raw-HTML path disabled)", () => {
  it("renders ordinary markdown formatting", () => {
    render(<SanitizedMarkdown content={"# Heading\n\nSome **bold** text."} />);
    expect(screen.getByRole("heading", { level: 1, name: "Heading" })).toBeInTheDocument();
    expect(screen.getByText("bold")).toBeInTheDocument();
  });

  it("never executes or injects embedded raw HTML — a script tag renders as inert text, not a live element", () => {
    const { container } = render(<SanitizedMarkdown content={"before <script>window.__pwned = true</script> after"} />);
    expect(container.querySelector("script")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it("never renders a raw <img> tag from embedded HTML (no tracking-pixel path)", () => {
    const { container } = render(
      <SanitizedMarkdown content={'<img src="https://track.example.com/pixel.gif" onerror="alert(1)">'} />,
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens markdown links in a new tab with rel=noreferrer", () => {
    render(<SanitizedMarkdown content={"[watch](https://youtube.com/watch?v=abc)"} />);
    const link = screen.getByRole("link", { name: "watch" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  });
});
