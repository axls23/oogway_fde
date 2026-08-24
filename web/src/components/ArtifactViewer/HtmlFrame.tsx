import { buildSandboxedSrcDoc } from "./sandboxHtml";
import "./ArtifactViewer.css";

interface HtmlFrameProps {
  content: string;
  title: string;
}

/**
 * NON-NEGOTIABLE (architecture.md ADR-004, CLAUDE.md invariant 5,
 * web/CLAUDE.md): sandbox is "allow-scripts" ONLY. Do not add
 * allow-same-origin under any refactor — that single attribute is what
 * keeps the frame's origin opaque, with no access to parent cookies,
 * storage, or DOM. See sandboxHtml.ts for the CSP that backs this up at
 * the network layer, and README/manual test notes for how AC8 is verified.
 */
export function HtmlFrame({ content, title }: HtmlFrameProps) {
  return (
    <iframe
      className="artifact-frame"
      sandbox="allow-scripts"
      srcDoc={buildSandboxedSrcDoc(content)}
      title={`Generated content: ${title}`}
    />
  );
}
