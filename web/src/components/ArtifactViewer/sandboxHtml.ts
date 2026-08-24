/**
 * Builds the `srcdoc` document for the HTML artifact iframe.
 *
 * This function is the entire security boundary described in
 * architecture.md ADR-004 and CLAUDE.md invariant 5, expressed as plain,
 * unit-testable string construction rather than something that requires a
 * running browser to verify:
 *
 *   1. The CSP <meta> tag is injected as the FIRST element of <head>, before
 *      anything from the artifact's own content is parsed, so no resource
 *      request the artifact issues — script, style, image, fetch, form — can
 *      escape it. `default-src 'none'` denies everything by default;
 *      `img-src data:` and inline style/script are the only carve-outs, and
 *      none of them permit network egress.
 *   2. The artifact's raw content is placed in <body> verbatim. If it
 *      happens to contain its own <html>/<head>/<body> wrapper (the
 *      artifact-html skill emits a full document), the HTML parser merges
 *      or discards the duplicate structural tags per the standard "in body"
 *      insertion-mode rules — critically, any <meta> the artifact tries to
 *      add of its own lands in body context and is inert, so it cannot
 *      weaken or replace the CSP we already established in the real <head>.
 *
 * The caller (HtmlFrame.tsx) is responsible for the other half of the
 * containment: rendering this string via `<iframe sandbox="allow-scripts"
 * srcDoc={...}>` with `allow-same-origin` never added.
 */
const ARTIFACT_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'unsafe-inline'";

export function buildSandboxedSrcDoc(rawContent: string): string {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${ARTIFACT_CSP}">
<title>Generated artifact</title>
</head>
<body>
${rawContent}
</body>
</html>
`;
}

export { ARTIFACT_CSP };
