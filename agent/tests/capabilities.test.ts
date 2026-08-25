import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import type { ResourceLoader } from "@earendil-works/pi-coding-agent";
import {
  ExtensionManifestViolation,
  getCapabilitySnapshot,
  loadManifest,
  verifyExtensions,
  type ExtensionManifest,
} from "../src/capabilities.js";

function withTempDir<T>(fn: (dir: string) => T): T {
  const dir = mkdtempSync(path.join(tmpdir(), "capabilities-test-"));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function fakeLoader(opts: {
  extensions?: Array<{ resolvedPath: string; tools: string[] }>;
  errors?: Array<{ path: string; error: string }>;
  skills?: Array<{ name: string; description: string }>;
}): ResourceLoader {
  return {
    getExtensions: () => ({
      extensions: (opts.extensions ?? []).map((e) => ({
        path: e.resolvedPath,
        resolvedPath: e.resolvedPath,
        sourceInfo: { source: "test" },
        handlers: new Map(),
        tools: new Map(e.tools.map((t) => [t, { definition: { name: t }, sourceInfo: { source: "test" } }])),
        messageRenderers: new Map(),
        commands: new Map(),
        flags: new Map(),
        shortcuts: new Map(),
      })),
      errors: opts.errors ?? [],
      runtime: {} as never,
    }),
    getSkills: () => ({ skills: (opts.skills ?? []) as never, diagnostics: [] }),
  } as unknown as ResourceLoader;
}

test("loadManifest: returns an empty manifest when the file does not exist", () => {
  withTempDir((dir) => {
    const manifest = loadManifest(path.join(dir, "missing.json"));
    assert.deepEqual(manifest, { extensions: [] });
  });
});

test("loadManifest: throws on a malformed manifest (not { extensions: [...] })", () => {
  withTempDir((dir) => {
    const p = path.join(dir, "manifest.json");
    writeFileSync(p, JSON.stringify({ oops: true }));
    assert.throws(() => loadManifest(p), ExtensionManifestViolation);
  });
});

test("verifyExtensions: passes when every loaded extension matches path, hash, and declared tools", () => {
  withTempDir((dir) => {
    const extPath = path.join(dir, "example.ts");
    writeFileSync(extPath, "export default () => {};\n");
    const manifest: ExtensionManifest = {
      extensions: [
        {
          path: "example.ts",
          sha256: createHash("sha256").update(readFileSync(extPath)).digest("hex"),
          tools: ["my_tool"],
          approvedBy: "test",
          description: "test extension",
        },
      ],
    };
    const loader = fakeLoader({ extensions: [{ resolvedPath: extPath, tools: ["my_tool"] }] });
    assert.doesNotThrow(() => verifyExtensions(loader, manifest, dir));
  });
});

test("verifyExtensions: fail-closed on an extension not listed in the manifest", () => {
  withTempDir((dir) => {
    const extPath = path.join(dir, "rogue.ts");
    writeFileSync(extPath, "export default () => {};\n");
    const loader = fakeLoader({ extensions: [{ resolvedPath: extPath, tools: [] }] });
    assert.throws(() => verifyExtensions(loader, { extensions: [] }, dir), ExtensionManifestViolation);
  });
});

test("verifyExtensions: fail-closed when file content drifts from the approved hash", () => {
  withTempDir((dir) => {
    const extPath = path.join(dir, "example.ts");
    writeFileSync(extPath, "export default () => {};\n");
    const manifest: ExtensionManifest = {
      extensions: [{ path: "example.ts", sha256: "0".repeat(64), tools: [], approvedBy: "test", description: "" }],
    };
    const loader = fakeLoader({ extensions: [{ resolvedPath: extPath, tools: [] }] });
    assert.throws(() => verifyExtensions(loader, manifest, dir), ExtensionManifestViolation);
  });
});

test("verifyExtensions: fail-closed when an extension registers a tool beyond what was declared", () => {
  withTempDir((dir) => {
    const extPath = path.join(dir, "example.ts");
    writeFileSync(extPath, "export default () => {};\n");
    const hash = createHash("sha256").update(readFileSync(extPath)).digest("hex");
    const manifest: ExtensionManifest = {
      extensions: [{ path: "example.ts", sha256: hash, tools: ["approved_tool"], approvedBy: "test", description: "" }],
    };
    const loader = fakeLoader({ extensions: [{ resolvedPath: extPath, tools: ["approved_tool", "sneaky_tool"] }] });
    assert.throws(() => verifyExtensions(loader, manifest, dir), ExtensionManifestViolation);
  });
});

test("verifyExtensions: fail-closed on any extension load error, even if others loaded fine", () => {
  withTempDir((dir) => {
    const loader = fakeLoader({ extensions: [], errors: [{ path: "broken.ts", error: "SyntaxError" }] });
    assert.throws(() => verifyExtensions(loader, { extensions: [] }, dir), ExtensionManifestViolation);
  });
});

test("getCapabilitySnapshot: reports builtin tools, skills, and extension tools together", () => {
  withTempDir((dir) => {
    const extPath = path.join(dir, "example.ts");
    const loader = fakeLoader({
      skills: [{ name: "ship30-essay", description: "Write a Ship 30 essay" }],
      extensions: [{ resolvedPath: extPath, tools: ["extra_tool"] }],
    });
    const snapshot = getCapabilitySnapshot(loader, ["search_transcripts", "create_artifact"], true, dir);
    assert.deepEqual(snapshot.skills, [{ name: "ship30-essay", description: "Write a Ship 30 essay" }]);
    assert.deepEqual(snapshot.extensions, [{ path: "example.ts", tools: ["extra_tool"] }]);
    assert.equal(snapshot.extensionsEnabled, true);
    assert.deepEqual(new Set(snapshot.tools), new Set(["search_transcripts", "create_artifact", "extra_tool"]));
  });
});

test("getCapabilitySnapshot: extensionsEnabled false and no extensions loaded is the default, expected state", () => {
  withTempDir((dir) => {
    const loader = fakeLoader({ skills: [{ name: "artifact-html", description: "Render an artifact" }] });
    const snapshot = getCapabilitySnapshot(loader, ["search_transcripts", "create_artifact"], false, dir);
    assert.deepEqual(snapshot.extensions, []);
    assert.equal(snapshot.extensionsEnabled, false);
    assert.deepEqual(snapshot.tools, ["search_transcripts", "create_artifact"]);
  });
});
