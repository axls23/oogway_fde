import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CapabilitiesSettings } from "./CapabilitiesSettings";
import { api } from "../../api/client";
import { FIXTURE_CONFIG, FIXTURE_SESSION_WITH_HISTORY } from "../../test/fixtures/apiFixtures";
import type { ExtensionProposal } from "../../api/types";

vi.mock("../../api/client", () => ({
  api: {
    getSession: vi.fn(),
    updateSessionCapabilities: vi.fn(),
    listExtensionProposals: vi.fn(),
    createExtensionProposal: vi.fn(),
    updateExtensionProposalStatus: vi.fn(),
  },
}));

const PROPOSAL: ExtensionProposal = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  title: "Fetch pricing page",
  description: "Lets the model pull a competitor's pricing page.",
  tool_names: ["fetch_pricing_page"],
  code: "export default (pi) => {};",
  sha256: "deadbeef",
  status: "pending",
  session_id: null,
  created_at: "2026-08-20T00:00:00Z",
  updated_at: "2026-08-20T00:00:00Z",
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("CapabilitiesSettings (root CLAUDE.md invariant #4, made editable)", () => {
  it("tells the user to pick a session first when none is active, and never fetches a session", async () => {
    vi.mocked(api.listExtensionProposals).mockResolvedValue({ items: [] });
    render(<CapabilitiesSettings sessionId={null} capabilities={FIXTURE_CONFIG.capabilities} onClose={vi.fn()} />);

    expect(screen.getByText(/select or create a chat first/i)).toBeInTheDocument();
    expect(api.getSession).not.toHaveBeenCalled();
  });

  it("loads the session's current skill allowlist and reflects it as checkbox state", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      ...FIXTURE_SESSION_WITH_HISTORY,
      enabled_skills: ["ship30-essay"],
    });
    vi.mocked(api.listExtensionProposals).mockResolvedValue({ items: [] });

    render(
      <CapabilitiesSettings
        sessionId={FIXTURE_SESSION_WITH_HISTORY.id}
        capabilities={FIXTURE_CONFIG.capabilities}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(api.getSession).toHaveBeenCalledWith(FIXTURE_SESSION_WITH_HISTORY.id));
    const ship30 = (await screen.findByLabelText(/ship30-essay/)) as HTMLInputElement;
    const artifactHtml = screen.getByLabelText(/artifact-html/) as HTMLInputElement;
    expect(ship30.checked).toBe(true);
    expect(artifactHtml.checked).toBe(false);
  });

  it("toggling a skill off then Save sends the narrowed allowlist via PATCH — never a new tool", async () => {
    vi.mocked(api.getSession).mockResolvedValue({ ...FIXTURE_SESSION_WITH_HISTORY, enabled_skills: null });
    vi.mocked(api.listExtensionProposals).mockResolvedValue({ items: [] });
    vi.mocked(api.updateSessionCapabilities).mockResolvedValue(FIXTURE_SESSION_WITH_HISTORY);

    const user = userEvent.setup();
    render(
      <CapabilitiesSettings
        sessionId={FIXTURE_SESSION_WITH_HISTORY.id}
        capabilities={FIXTURE_CONFIG.capabilities}
        onClose={vi.fn()}
      />,
    );

    const artifactHtml = await screen.findByLabelText(/artifact-html/);
    await user.click(artifactHtml);
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.updateSessionCapabilities).toHaveBeenCalledWith(FIXTURE_SESSION_WITH_HISTORY.id, {
        enabled_skills: ["ship30-essay"],
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(/saved/i);
  });

  it("Reset to default clears the allowlist back to null (every skill active)", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      ...FIXTURE_SESSION_WITH_HISTORY,
      enabled_skills: ["ship30-essay"],
    });
    vi.mocked(api.listExtensionProposals).mockResolvedValue({ items: [] });
    vi.mocked(api.updateSessionCapabilities).mockResolvedValue(FIXTURE_SESSION_WITH_HISTORY);

    const user = userEvent.setup();
    render(
      <CapabilitiesSettings
        sessionId={FIXTURE_SESSION_WITH_HISTORY.id}
        capabilities={FIXTURE_CONFIG.capabilities}
        onClose={vi.fn()}
      />,
    );

    await screen.findByLabelText(/ship30-essay/);
    await user.click(screen.getByRole("button", { name: /reset to default/i }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.updateSessionCapabilities).toHaveBeenCalledWith(FIXTURE_SESSION_WITH_HISTORY.id, {
        enabled_skills: null,
      }),
    );
  });

  it("lists existing extension proposals with a status badge, and never claims they're deployed", async () => {
    vi.mocked(api.listExtensionProposals).mockResolvedValue({ items: [PROPOSAL] });

    render(<CapabilitiesSettings sessionId={null} capabilities={FIXTURE_CONFIG.capabilities} onClose={vi.fn()} />);

    expect(await screen.findByText("Fetch pricing page")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText(/review queue, not a deploy button/i)).toBeInTheDocument();
  });

  it("submitting the propose form calls createExtensionProposal with parsed tool names and refreshes the list", async () => {
    vi.mocked(api.listExtensionProposals)
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [PROPOSAL] });
    vi.mocked(api.createExtensionProposal).mockResolvedValue(PROPOSAL);

    const user = userEvent.setup();
    render(<CapabilitiesSettings sessionId={null} capabilities={FIXTURE_CONFIG.capabilities} onClose={vi.fn()} />);

    await waitFor(() => expect(api.listExtensionProposals).toHaveBeenCalledTimes(1));

    await user.type(screen.getByLabelText(/^title$/i), "Fetch pricing page");
    await user.type(screen.getByLabelText(/^description$/i), "Lets the model pull a pricing page.");
    await user.type(screen.getByLabelText(/tool names/i), "fetch_pricing_page, another_tool");
    fireEvent.change(screen.getByLabelText(/^code$/i), { target: { value: "export default (pi) => {};" } });
    await user.click(screen.getByRole("button", { name: /submit proposal/i }));

    await waitFor(() =>
      expect(api.createExtensionProposal).toHaveBeenCalledWith(
        {
          title: "Fetch pricing page",
          description: "Lets the model pull a pricing page.",
          tool_names: ["fetch_pricing_page", "another_tool"],
          code: "export default (pi) => {};",
        },
        undefined,
      ),
    );
    await waitFor(() => expect(api.listExtensionProposals).toHaveBeenCalledTimes(2));
  });

  it("Back to chat calls onClose", async () => {
    vi.mocked(api.listExtensionProposals).mockResolvedValue({ items: [] });
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<CapabilitiesSettings sessionId={null} capabilities={FIXTURE_CONFIG.capabilities} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /back to chat/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
