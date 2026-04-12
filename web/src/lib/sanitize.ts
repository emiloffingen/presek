import DOMPurify from "isomorphic-dompurify";

/**
 * Sanitize HTML content to prevent XSS attacks.
 * Safe for use in both SSR (Node) and client-side (browser) contexts.
 */
export function sanitizeHtml(dirty: string): string {
  if (!dirty) return "";
  return DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: [
      "b", "i", "em", "strong", "a", "p", "br", "ul", "ol", "li",
      "h1", "h2", "h3", "h4", "h5", "h6", "span", "div", "blockquote",
      "pre", "code", "sub", "sup", "mark", "small",
    ],
    ALLOWED_ATTR: ["href", "target", "rel", "class", "id"],
  });
}
