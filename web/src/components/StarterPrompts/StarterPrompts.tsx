import "./StarterPrompts.css";

interface StarterPromptsProps {
  onPick: (prompt: string) => void;
}

interface StarterPrompt {
  title: string;
  description: string;
  prompt: string;
}

/**
 * F6 cold start: three cards, each exercising a different capability. Shown
 * only on a brand-new empty session (design.md §3). Static, not
 * personalized (design.md §6) — there's no usage data to personalize from.
 */
const PROMPTS: StarterPrompt[] = [
  {
    title: "Ask a grounded question",
    description: "Get an answer with named sources you can spot-check.",
    prompt: "Our activation rate dropped after we added a second onboarding step. What do operators say about this?",
  },
  {
    title: "Draft a Ship 30 essay",
    description: "A structured, staged-progress essay grounded in real operator experience.",
    prompt: "Write a Ship 30 essay on why activation matters more than acquisition for early-stage growth.",
  },
  {
    title: "Generate a one-pager",
    description: "A sandboxed HTML artifact you can preview, copy, or download.",
    prompt: "Generate a one-page HTML brief summarizing what Lenny's guests say about pricing page redesigns.",
  },
];

export function StarterPrompts({ onPick }: StarterPromptsProps) {
  return (
    <div className="starter-prompts">
      <p className="starter-prompts__lede">Start with a capability, or just type your own question below.</p>
      <div className="starter-prompts__grid">
        {PROMPTS.map((p) => (
          <button key={p.title} type="button" className="starter-prompt" onClick={() => onPick(p.prompt)}>
            <span className="starter-prompt__title">{p.title}</span>
            <span className="starter-prompt__description">{p.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
