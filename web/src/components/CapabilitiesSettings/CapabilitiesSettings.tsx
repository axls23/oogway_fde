import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { Capabilities, ExtensionProposal, ExtensionProposalStatus } from "../../api/types";
import "./CapabilitiesSettings.css";

interface CapabilitiesSettingsProps {
  sessionId: string | null;
  capabilities: Capabilities | null;
  onClose: () => void;
}

/**
 * Root CLAUDE.md invariant #4, made editable within its own boundary:
 *
 * - "Skills for this session" toggles which discovered skills (plain
 *   prompt text, no tools attached) apply to the active session. This can
 *   only narrow what the model is told it may do — never grant capability
 *   — so it's a live PATCH with no review step.
 * - "Plugins" is a review queue, not a deploy button: proposing an
 *   extension records a draft in Postgres. The agent only ever loads what's
 *   pinned by path+sha256+tool-names in agent/.pi/extensions/manifest.json
 *   (agent/src/capabilities.ts) — nothing here writes to that file, and
 *   "approved" here is bookkeeping for a human maintainer, not deployment.
 */
export function CapabilitiesSettings({ sessionId, capabilities, onClose }: CapabilitiesSettingsProps) {
  const [enabledSkills, setEnabledSkills] = useState<string[] | null>(null);
  const [loadingSession, setLoadingSession] = useState(Boolean(sessionId));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [proposals, setProposals] = useState<ExtensionProposal[]>([]);
  const [proposalsLoading, setProposalsLoading] = useState(true);
  const [proposalsError, setProposalsError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [toolNamesInput, setToolNamesInput] = useState("");
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!sessionId) {
      setLoadingSession(false);
      setEnabledSkills(null);
      return;
    }
    setLoadingSession(true);
    api
      .getSession(sessionId)
      .then((detail) => {
        if (!cancelled) setEnabledSkills(detail.enabled_skills);
      })
      .finally(() => {
        if (!cancelled) setLoadingSession(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const refreshProposals = useCallback(() => {
    setProposalsLoading(true);
    api
      .listExtensionProposals()
      .then((res) => {
        setProposals(res.items);
        setProposalsError(null);
      })
      .catch((err) => setProposalsError(err instanceof Error ? err.message : String(err)))
      .finally(() => setProposalsLoading(false));
  }, []);

  useEffect(() => {
    refreshProposals();
  }, [refreshProposals]);

  const skillNames = capabilities?.skills.map((s) => s.name) ?? [];
  const isEnabled = (name: string) => enabledSkills === null || enabledSkills.includes(name);

  const toggleSkill = (name: string) => {
    setSaved(false);
    setEnabledSkills((prev) => {
      const current = prev === null ? [...skillNames] : prev;
      return current.includes(name) ? current.filter((n) => n !== name) : [...current, name];
    });
  };

  const handleSave = async () => {
    if (!sessionId) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateSessionCapabilities(sessionId, { enabled_skills: enabledSkills });
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitProposal = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      const tool_names = toolNamesInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await api.createExtensionProposal({ title, description, tool_names, code }, sessionId ?? undefined);
      setTitle("");
      setDescription("");
      setToolNamesInput("");
      setCode("");
      refreshProposals();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusChange = async (id: string, status: ExtensionProposalStatus) => {
    await api.updateExtensionProposalStatus(id, status);
    refreshProposals();
  };

  return (
    <div className="capabilities-settings">
      <header className="capabilities-settings__header">
        <h1>Capabilities settings</h1>
        <button type="button" className="capabilities-settings__close" onClick={onClose}>
          ← Back to chat
        </button>
      </header>

      <section className="capabilities-settings__section">
        <h2>Skills for this session</h2>
        <p className="capabilities-settings__hint">
          Skills are plain prompt text with no tools attached — turning one off can only narrow what the
          model is told it may do, never grant it a new capability.
        </p>

        {!sessionId ? (
          <p className="capabilities-settings__empty">Select or create a chat first — skills are set per session.</p>
        ) : loadingSession ? (
          <p className="capabilities-settings__empty">Loading…</p>
        ) : skillNames.length === 0 ? (
          <p className="capabilities-settings__empty">No skills discovered.</p>
        ) : (
          <>
            <ul className="capabilities-settings__skill-list">
              {capabilities?.skills.map((skill) => (
                <li key={skill.name}>
                  <label>
                    <input
                      type="checkbox"
                      checked={isEnabled(skill.name)}
                      onChange={() => toggleSkill(skill.name)}
                    />
                    <span>
                      <strong>{skill.name}</strong>
                      <span className="capabilities-settings__skill-desc">{skill.description}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            <div className="capabilities-settings__actions">
              <button
                type="button"
                className="capabilities-settings__secondary"
                onClick={() => {
                  setSaved(false);
                  setEnabledSkills(null);
                }}
              >
                Reset to default (all active)
              </button>
              <button type="button" onClick={() => void handleSave()} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
            {saveError && (
              <p className="capabilities-settings__error" role="alert">
                {saveError}
              </p>
            )}
            {saved && !saveError && (
              <p className="capabilities-settings__success" role="status">
                Saved.
              </p>
            )}
          </>
        )}
      </section>

      <section className="capabilities-settings__section">
        <h2>Plugins</h2>
        <p className="capabilities-settings__hint">
          This is a review queue, not a deploy button. The agent only ever loads an extension listed by
          exact path, content hash, and declared tool names in <code>agent/.pi/extensions/manifest.json</code>
          . A proposal here — even one marked "approved" — changes nothing on its own; a maintainer still
          has to commit the code, add the manifest entry, and pass the CI check before it can run.
        </p>

        <h3>Approved &amp; loaded</h3>
        {!capabilities?.extensions_enabled ? (
          <p className="capabilities-settings__empty">Disabled (AGENT_EXTENSIONS_ENABLED=false).</p>
        ) : capabilities.extensions.length === 0 ? (
          <p className="capabilities-settings__empty">Enabled, but none are loaded.</p>
        ) : (
          <ul className="capabilities-settings__list">
            {capabilities.extensions.map((ext) => (
              <li key={ext.path}>
                <strong>{ext.path}</strong>
                <span>{ext.tools.join(", ")}</span>
              </li>
            ))}
          </ul>
        )}

        <h3>Proposals</h3>
        {proposalsLoading ? (
          <p className="capabilities-settings__empty">Loading…</p>
        ) : proposalsError ? (
          <p className="capabilities-settings__error" role="alert">
            {proposalsError}
          </p>
        ) : proposals.length === 0 ? (
          <p className="capabilities-settings__empty">No proposals yet.</p>
        ) : (
          <ul className="capabilities-settings__proposal-list">
            {proposals.map((p) => (
              <li key={p.id} className="capabilities-settings__proposal">
                <div className="capabilities-settings__proposal-head">
                  <strong>{p.title}</strong>
                  <span className={`capabilities-settings__status capabilities-settings__status--${p.status}`}>
                    {p.status}
                  </span>
                </div>
                <p>{p.description}</p>
                <p className="capabilities-settings__proposal-tools">tools: {p.tool_names.join(", ")}</p>
                <details>
                  <summary>Code</summary>
                  <pre>{p.code}</pre>
                  <p className="capabilities-settings__sha">sha256: {p.sha256}</p>
                </details>
                {p.status === "pending" && (
                  <div className="capabilities-settings__actions">
                    <button type="button" onClick={() => void handleStatusChange(p.id, "approved")}>
                      Mark reviewed / approved
                    </button>
                    <button
                      type="button"
                      className="capabilities-settings__secondary"
                      onClick={() => void handleStatusChange(p.id, "rejected")}
                    >
                      Reject
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        <h3>Propose a new extension</h3>
        <form className="capabilities-settings__form" onSubmit={(e) => void handleSubmitProposal(e)}>
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
          </label>
          <label>
            Description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              maxLength={2000}
              rows={2}
            />
          </label>
          <label>
            Tool names (comma-separated, e.g. <code>fetch_pricing_page</code>)
            <input
              value={toolNamesInput}
              onChange={(e) => setToolNamesInput(e.target.value)}
              required
              placeholder="my_tool, another_tool"
            />
          </label>
          <label>
            Code
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              rows={10}
              className="capabilities-settings__code-input"
            />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? "Submitting…" : "Submit proposal"}
          </button>
          {submitError && (
            <p className="capabilities-settings__error" role="alert">
              {submitError}
            </p>
          )}
        </form>
      </section>
    </div>
  );
}
