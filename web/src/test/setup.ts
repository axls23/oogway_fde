import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement matchMedia; useMediaQuery (src/state/useMediaQuery.ts)
// depends on it for the responsive breakpoint logic in design.md §5.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// jsdom's clipboard is not implemented; ArtifactViewer's Copy button calls it.
if (!navigator.clipboard) {
  Object.assign(navigator, {
    clipboard: { writeText: async () => {} },
  });
}
