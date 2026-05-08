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
      "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
      "pre", "code", "sub", "sup", "small", "span",
      "svg", "path", "polyline", "line"
    ],
    ALLOWED_ATTR: [
      "href", "target", "rel", "class", "title",
      "viewBox", "d", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
      "width", "height", "x1", "y1", "x2", "y2", "points"
    ],
  });
}
