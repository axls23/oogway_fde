import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActiveCapabilities } from "./ActiveCapabilities";
import { FIXTURE_CONFIG } from "../../test/fixtures/apiFixtures";
import type { Capabilities } from "../../api/types";

describe("ActiveCapabilities (root CLAUDE.md invariant #4, made visible in the UI)", () => {
  it("renders nothing before config has loaded", () => {
    const { container } = render(<ActiveCapabilities capabilities={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("is collapsed by default with aria-expanded=false, showing the active tool count", () => {
    render(<ActiveCapabilities capabilities={FIXTURE_CONFIG.capabilities} />);
    const button = screen.getByRole("button", { name: /2 tools active/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("expands to list tools, skills, and a disabled-extensions notice — no network fetch", async () => {
    const user = userEvent.setup();
    render(<ActiveCapabilities capabilities={FIXTURE_CONFIG.capabilities} />);
    await user.click(screen.getByRole("button", { name: /tools active/ }));

    expect(screen.getByText("search_transcripts")).toBeInTheDocument();
    expect(screen.getByText("create_artifact")).toBeInTheDocument();
    expect(screen.getByText("ship30-essay")).toBeInTheDocument();
    expect(screen.getByText("artifact-html")).toBeInTheDocument();
    expect(screen.getByText(/AGENT_EXTENSIONS_ENABLED=false/)).toBeInTheDocument();
  });

  it("lists loaded extensions by path and their registered tools when extensions are enabled", async () => {
    const capabilities: Capabilities = {
      ...FIXTURE_CONFIG.capabilities,
      extensions_enabled: true,
      extensions: [{ path: ".pi/extensions/example.ts", tools: ["extra_tool"] }],
      tools: [...FIXTURE_CONFIG.capabilities.tools, "extra_tool"],
    };
    const user = userEvent.setup();
    render(<ActiveCapabilities capabilities={capabilities} />);
    await user.click(screen.getByRole("button", { name: /tools active/ }));

    expect(screen.getByText(".pi/extensions/example.ts")).toBeInTheDocument();
    expect(screen.getByText("extra_tool", { selector: "span" })).toBeInTheDocument();
  });

  it("surfaces a staleness notice when the agent snapshot could not be fetched", async () => {
    const capabilities: Capabilities = { ...FIXTURE_CONFIG.capabilities, agent_reachable: false };
    const user = userEvent.setup();
    render(<ActiveCapabilities capabilities={capabilities} />);
    await user.click(screen.getByRole("button", { name: /tools active/ }));

    expect(screen.getByRole("status")).toHaveTextContent(/agent unreachable/i);
  });
});
