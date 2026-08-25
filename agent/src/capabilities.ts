// Extension allowlist + capability reporting — root CLAUDE.md invariant #4
// ("Only search_transcripts and create_artifact are available to the
// model... never relax this") and architecture.md §8.5.
//
// Pi extensions (.pi/extensions/*.ts, discovered by DefaultResourceLoader)
// are arbitrary in-process TypeScript that can call registerTool() to grant
// the model any new tool, with no sandbox of their own — confirmed against
// the installed package's dist/core/extensions/types.d.ts. That makes the
// extensions directory equivalent in power to editing session.ts's
// customTools array directly, except nothing else in this repo's CI or
// runtime path reviews it the same way. This module closes that gap:
//
//   - Extension loading is off by default (AGENT_EXTENSIONS_ENABLED=false
//     -> noTools/noExtensions in session.ts) so the invariant holds by
//     configuration, not just by the directory happening to be empty.
//   - When explicitly enabled, every loaded extension must be pinned in
//     agent/.pi/extensions/manifest.json by relative path, content sha256,
//     and the exact tool names it is approved to register. Any extension
//     not listed, any content drift from its approved hash, or any tool
//     name it registers beyond what was declared is a fail-closed startup
//     error — this never degrades to "load what we can."
//   - tools/check_extension_manifest.py re-checks the same manifest at CI
//     time, so drift is caught before a container ever runs it, not just
//     at boot.

import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { ResourceLoader } from "@earendil-works/pi-coding-agent";

export interface ExtensionManifestEntry {
  path: string;
  sha256: string;
  tools: string[];
  approvedBy: string;
  description: string;
}

export interface ExtensionManifest {
  extensions: ExtensionManifestEntry[];
}

export class ExtensionManifestViolation extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExtensionManifestViolation";
  }
}

export function loadManifest(manifestPath: string): ExtensionManifest {
  if (!existsSync(manifestPath)) {
    return { extensions: [] };
  }
  const raw: unknown = JSON.parse(readFileSync(manifestPath, "utf-8"));
  if (typeof raw !== "object" || raw === null || !Array.isArray((raw as ExtensionManifest).extensions)) {
    throw new ExtensionManifestViolation(`${manifestPath} is malformed: expected { "extensions": [...] }`);
  }
  return raw as ExtensionManifest;
}

function sha256File(filePath: string): string {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

/**
 * Fail-closed allowlist check. Throws ExtensionManifestViolation on any
 * mismatch — callers must not catch this and continue; the whole point is
 * that a session never becomes promptable with an unreviewed tool attached.
 */
export function verifyExtensions(loader: ResourceLoader, manifest: ExtensionManifest, repoRoot: string): void {
  const { extensions, errors } = loader.getExtensions();

  if (errors.length > 0) {
    throw new ExtensionManifestViolation(
      `Pi reported ${errors.length} extension load error(s): ${errors.map((e) => `${e.path}: ${e.error}`).join("; ")}`,
    );
  }

  const byPath = new Map(manifest.extensions.map((e) => [e.path, e]));
  for (const ext of extensions) {
    const relPath = path.relative(repoRoot, ext.resolvedPath);
    const entry = byPath.get(relPath);
    if (!entry) {
      throw new ExtensionManifestViolation(
        `extension at ${relPath} is not listed in agent/.pi/extensions/manifest.json — refusing to start. ` +
          `Add an entry (path, sha256, approved tool names) before enabling it.`,
      );
    }
    const actualHash = sha256File(ext.resolvedPath);
    if (actualHash !== entry.sha256) {
      throw new ExtensionManifestViolation(
        `extension at ${relPath} does not match its approved hash (manifest has ${entry.sha256}, file hashes to ${actualHash}) ` +
          `— content changed since review. Re-review and update the manifest entry.`,
      );
    }
    const registeredTools = [...ext.tools.keys()];
    const undeclared = registeredTools.filter((t) => !entry.tools.includes(t));
    if (undeclared.length > 0) {
      throw new ExtensionManifestViolation(
        `extension at ${relPath} registered tool(s) not declared in its manifest entry: ${undeclared.join(", ")}`,
      );
    }
  }
}

export interface SkillSummary {
  name: string;
  description: string;
}

export interface ExtensionSummary {
  path: string;
  tools: string[];
}

export interface CapabilitySnapshot {
  skills: SkillSummary[];
  extensions: ExtensionSummary[];
  extensionsEnabled: boolean;
  tools: string[];
}

/** Read-only view of what's actually active, for /config -> the UI capabilities panel. */
export function getCapabilitySnapshot(
  loader: ResourceLoader,
  builtinToolNames: string[],
  extensionsEnabled: boolean,
  repoRoot: string,
): CapabilitySnapshot {
  const { skills } = loader.getSkills();
  const { extensions } = loader.getExtensions();
  const extensionSummaries: ExtensionSummary[] = extensions.map((ext) => ({
    path: path.relative(repoRoot, ext.resolvedPath),
    tools: [...ext.tools.keys()],
  }));
  const extensionToolNames = extensionSummaries.flatMap((e) => e.tools);
  return {
    skills: skills.map((s) => ({ name: s.name, description: s.description })),
    extensions: extensionSummaries,
    extensionsEnabled,
    tools: [...new Set([...builtinToolNames, ...extensionToolNames])],
  };
}
