import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Artifact } from "../../api/types";
import { HtmlFrame } from "./HtmlFrame";
import { SanitizedMarkdown } from "../shared/SanitizedMarkdown";
import "./ArtifactViewer.css";

type Tab = "preview" | "source";

interface ArtifactViewerProps {
  artifactId: string;
  onClose: () => void;
}

/**
 * design.md §3 "Artifact pane" states table: generating (staged progress,
 * shown by the caller via the same stage chip as chat), ready (preview tab
 * default, source tab read-only), copy (raw source) / download (.md or
 * .html file).
 */
export function ArtifactViewer({ artifactId, onClose }: ArtifactViewerProps) {
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [tab, setTab] = useState<Tab>("preview");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    setArtifact(null);
    setTab("preview");

    api
      .getArtifact(artifactId)
      .then((a) => {
        if (!cancelled) setArtifact(a);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [artifactId]);

  const handleCopy = async () => {
    if (!artifact) return;
    await navigator.clipboard.writeText(artifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleDownload = () => {
    if (!artifact) return;
    const ext = artifact.kind === "html" ? "html" : "md";
    const mime = artifact.kind === "html" ? "text/html" : "text/markdown";
    const blob = new Blob([artifact.content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(artifact.title ?? "artifact").replace(/[^a-z0-9-]+/gi, "-").toLowerCase()}.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="artifact-pane">
      <div className="artifact-pane__header">
        <div className="artifact-pane__heading">
          <span className="artifact-pane__title">{artifact?.title ?? "Artifact"}</span>
          <span className="artifact-pane__sandbox-note">
            Generated content — sandboxed, scripts run in an isolated context, no network access
          </span>
        </div>
        <button type="button" className="artifact-pane__close" onClick={onClose} aria-label="Close artifact pane">
          ×
        </button>
      </div>

      {loading && <p className="artifact-pane__status">Loading artifact…</p>}
      {loadError && <p className="artifact-pane__status artifact-pane__status--error">Couldn't load this artifact.</p>}

      {artifact && (
        <>
          <div className="artifact-pane__tabs" role="tablist" aria-label="Artifact view">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "preview"}
              className={`artifact-pane__tab${tab === "preview" ? " artifact-pane__tab--active" : ""}`}
              onClick={() => setTab("preview")}
            >
              Preview
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "source"}
              className={`artifact-pane__tab${tab === "source" ? " artifact-pane__tab--active" : ""}`}
              onClick={() => setTab("source")}
            >
              Source
            </button>
            <div className="artifact-pane__actions">
              <button type="button" onClick={() => void handleCopy()}>
                {copied ? "Copied" : "Copy"}
              </button>
              <button type="button" onClick={handleDownload}>
                Download
              </button>
            </div>
          </div>

          <div className="artifact-pane__body">
            {tab === "preview" ? (
              artifact.kind === "html" ? (
                <HtmlFrame content={artifact.content} title={artifact.title ?? "Untitled artifact"} />
              ) : (
                <div className="artifact-pane__markdown">
                  <SanitizedMarkdown content={artifact.content} />
                </div>
              )
            ) : (
              <pre className="artifact-pane__source" tabIndex={0}>
                <code>{artifact.content}</code>
              </pre>
            )}
          </div>
        </>
      )}
    </div>
  );
}
