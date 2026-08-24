import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

/**
 * The one markdown rendering path in the app (chat messages and the
 * markdown artifact viewer both use it). Deliberately does NOT use
 * rehype-raw or dangerouslySetInnerHTML — react-markdown parses markdown to
 * a syntax tree and renders it as React elements, so raw HTML embedded in
 * the source is never interpreted, only shown as literal text. An explicit
 * `allowedElements` allowlist is a second layer on top of that default.
 *
 * architecture.md §10: "Rendered through a sanitiser with an allowlisted
 * tag and attribute set; the raw-HTML path is disabled."
 */
const ALLOWED_ELEMENTS = [
  "p",
  "a",
  "strong",
  "em",
  "del",
  "code",
  "pre",
  "blockquote",
  "ul",
  "ol",
  "li",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "br",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
];

const components: Components = {
  a: ({ href, children, ...props }) => (
    <a {...props} href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
};

export function SanitizedMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} allowedElements={ALLOWED_ELEMENTS} components={components}>
      {content}
    </ReactMarkdown>
  );
}
