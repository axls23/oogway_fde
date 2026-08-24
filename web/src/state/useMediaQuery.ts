import { useEffect, useState } from "react";

/** Tracks a CSS media query in React state, for the design.md §5 breakpoint
 * behaviors that need to change component structure (not just styling) —
 * e.g. citation expansion becoming a bottom sheet instead of an inline
 * accordion below 640px. */
export function useMediaQuery(query: string): boolean {
  const getMatch = () => (typeof window !== "undefined" ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState(getMatch);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const listener = () => setMatches(mql.matches);
    listener();
    mql.addEventListener("change", listener);
    return () => mql.removeEventListener("change", listener);
  }, [query]);

  return matches;
}

export const BREAKPOINTS = {
  drawer: "(max-width: 1023px)",
  singleColumn: "(max-width: 639px)",
} as const;
