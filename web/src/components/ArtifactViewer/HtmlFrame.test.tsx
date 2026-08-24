import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HtmlFrame } from "./HtmlFrame";

describe("HtmlFrame (CLAUDE.md invariant 5 / ADR-004)", () => {
  it('renders sandbox="allow-scripts" with no allow-same-origin, ever', () => {
    render(<HtmlFrame content="<script>fetch('https://example.com')</script>" title="Malicious artifact" />);
    const iframe = screen.getByTitle("Generated content: Malicious artifact");
    expect(iframe.tagName).toBe("IFRAME");
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("sandbox")).not.toMatch(/allow-same-origin/);
  });

  it("has a descriptive title attribute (design.md §4 accessibility)", () => {
    render(<HtmlFrame content="<p>hi</p>" title="Onboarding one-pager" />);
    expect(screen.getByTitle("Generated content: Onboarding one-pager")).toBeInTheDocument();
  });

  it("passes the CSP-wrapped document as srcdoc, not the raw artifact content", () => {
    const { container } = render(<HtmlFrame content="<p>payload</p>" title="t" />);
    const iframe = container.querySelector("iframe");
    const srcdoc = iframe?.getAttribute("srcdoc") ?? "";
    expect(srcdoc).toContain("Content-Security-Policy");
    expect(srcdoc).toContain("<p>payload</p>");
  });
});
