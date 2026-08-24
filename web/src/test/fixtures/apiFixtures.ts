import type { Artifact, ChunkDetail, ConfigResponse, Session, SessionDetail } from "../../api/types";

export const FIXTURE_CONFIG: ConfigResponse = {
  provider: "ollama",
  model: "qwen2.5:7b-instruct",
  cloud_available: false,
  corpus: { episode_count: 303, chunk_count: 41822 },
};

export const FIXTURE_SESSION: Session = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Activation vs. acquisition",
  provider: "ollama",
  model: "qwen2.5:7b-instruct",
  created_at: "2026-08-20T14:03:00Z",
  updated_at: "2026-08-20T14:05:00Z",
};

export const FIXTURE_EMPTY_SESSION: SessionDetail = {
  ...FIXTURE_SESSION,
  id: "22222222-2222-4222-8222-222222222222",
  title: null,
  messages: [],
};

export const FIXTURE_SESSION_WITH_HISTORY: SessionDetail = {
  ...FIXTURE_SESSION,
  messages: [
    {
      id: "33333333-3333-4333-8333-333333333333",
      session_id: FIXTURE_SESSION.id,
      role: "user",
      content: "Our activation dropped after we added a second onboarding step, what do people say about this?",
      abstained: false,
      created_at: "2026-08-20T14:03:00Z",
    },
    {
      id: "44444444-4444-4444-8444-444444444444",
      session_id: FIXTURE_SESSION.id,
      role: "assistant",
      content:
        "Product-market fit is less a single moment and more a threshold you cross when retention curves flatten out.",
      abstained: false,
      created_at: "2026-08-20T14:03:04Z",
      citations: [
        {
          chunk_id: 8412,
          episode: "Product-Market Fit, Pricing, and the Truth About Growth",
          guest: "Brian Chesky",
          youtube_url: "https://youtube.com/watch?v=abc123",
          start_seconds: 842,
          rank: 1,
          score: 0.82,
        },
      ],
    },
  ],
};

export const FIXTURE_CHUNK: ChunkDetail = {
  id: 8412,
  text:
    "Brian Chesky: I think product-market fit isn't really a single moment. It's more like a threshold. " +
    "You cross it when your retention curve flattens out instead of decaying to zero. Before that point, " +
    "growth is basically a leaky bucket — you can pour users in the top, but they fall out the bottom just " +
    "as fast.",
  ordinal: 14,
  episode: {
    id: 512,
    guest: "Brian Chesky",
    title: "Product-Market Fit, Pricing, and the Truth About Growth",
    youtube_url: "https://youtube.com/watch?v=abc123",
    publish_date: "2024-03-11",
    source_path: "episodes/brian-chesky/transcript.md",
  },
  start_seconds: 842,
};

export const FIXTURE_ARTIFACT: Artifact = {
  id: "a1b2c3d4-e5f6-4789-a0b1-c2d3e4f5a6b7",
  session_id: FIXTURE_SESSION.id,
  message_id: "b2c3d4e5-f6a7-4890-b1c2-d3e4f5a6b7c8",
  kind: "markdown",
  title: "Why Activation Beats Acquisition",
  content:
    "# Why Activation Beats Acquisition\n\n## The hook\n\nMost teams optimize the wrong end of the funnel.\n\n" +
    "## Section 1: Define the aha moment\n\nCasey Winters argues teams should work backward from retention, " +
    "not forward from signup.\n\n## Takeaway\n\nActivation is the metric that predicts everything downstream.\n",
  sanitized: true,
  created_at: "2026-08-20T14:06:11Z",
};

export const FIXTURE_HTML_ARTIFACT: Artifact = {
  id: "c9d8e7f6-1234-4abc-9def-0123456789ab",
  session_id: FIXTURE_SESSION.id,
  message_id: null,
  kind: "html",
  title: "Onboarding one-pager",
  content:
    "<h1>Onboarding One-Pager</h1><p>Reduce the second-step tax.</p>" +
    "<script>fetch('https://example.com').catch(()=>{});</script>",
  sanitized: true,
  created_at: "2026-08-20T14:07:00Z",
};
