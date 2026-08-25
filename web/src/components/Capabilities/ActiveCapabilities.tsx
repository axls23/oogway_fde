import { useId, useState } from "react";
import type { Capabilities } from "../../api/types";
import "./ActiveCapabilities.css";

interface ActiveCapabilitiesProps {
  capabilities: Capabilities | null;
}

/**
 * Root CLAUDE.md invariant #4 / architecture.md §8.5, made visible: exactly
 * which skills and tools the model can use right now, and whether Pi's
 * .pi/extensions/ mechanism is even switched on. A real <button> with
 * aria-expanded, same disclosure pattern as CitationChip — no second fetch,
 * the data already arrived on GET /config.
 */
export function ActiveCapabilities({ capabilities }: ActiveCapabilitiesProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  if (!capabilities) return null;

  const toolCount = capabilities.tools.length;

  return (
    <div className="active-capabilities">
      <button
        type="button"
        className="active-capabilities__trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="active-capabilities__dot" aria-hidden="true" />
        {toolCount} tool{toolCount === 1 ? "" : "s"} active
      </button>

      {open && (
        <div id={panelId} className="active-capabilities__panel" role="region" aria-label="Active skills and plugins">
          {!capabilities.agent_reachable && (
            <p className="active-capabilities__notice" role="status">
              Agent unreachable — this list may be stale.
            </p>
          )}

          <section>
            <h3>Tools</h3>
            <ul className="active-capabilities__pills">
              {capabilities.tools.map((tool) => (
                <li key={tool} className="active-capabilities__pill">
                  {tool}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3>Skills</h3>
            {capabilities.skills.length === 0 ? (
              <p className="active-capabilities__empty">No skills discovered.</p>
            ) : (
              <ul className="active-capabilities__list">
                {capabilities.skills.map((skill) => (
                  <li key={skill.name}>
                    <strong>{skill.name}</strong>
                    <span>{skill.description}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3>Plugins</h3>
            {!capabilities.extensions_enabled ? (
              <p className="active-capabilities__empty">
                Disabled (AGENT_EXTENSIONS_ENABLED=false) — the model has no tools beyond the ones listed above.
              </p>
            ) : capabilities.extensions.length === 0 ? (
              <p className="active-capabilities__empty">Enabled, but none are loaded.</p>
            ) : (
              <ul className="active-capabilities__list">
                {capabilities.extensions.map((ext) => (
                  <li key={ext.path}>
                    <strong>{ext.path}</strong>
                    <span>{ext.tools.length > 0 ? ext.tools.join(", ") : "registers no tools"}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
