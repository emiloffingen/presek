import DOMPurify from "isomorphic-dompurify";

// DOMPurify does not add rel to target="_blank" links on its own, so AI/source
// links rendered into synthesis could reverse-tabnab. Install the hook once.
let relHookInstalled = false;
function ensureBlankTargetRelHook() {
  if (relHookInstalled) return;
  relHookInstalled = true;
  DOMPurify.addHook("afterSanitizeAttributes", (node: any) => {
    if (node?.tagName === "A" && node.getAttribute("target") === "_blank") {
      const rel = node.getAttribute("rel") || "";
      if (!rel.includes("noopener")) {
        node.setAttribute("rel", `${rel} noopener noreferrer`.trim());
      }
    }
  });
}

/**
 * Sanitize HTML content to prevent XSS attacks.
 *
 * Security: Uses DOMPurify with a strict allowlist. Only permits safe formatting tags
 * and specific attributes. All event handlers, javascript: URLs, and style attributes
 * are explicitly blocked.
 *
 * Safe for use in both SSR (Node) and client-side (browser) contexts.
 *
 * @param dirty - The potentially unsafe HTML string to sanitize
 * @returns A safe HTML string with all dangerous content removed
 *
 * @example
 * ```ts
 * const safe = sanitizeHtml('<script>alert("xss")</script><b>Hello</b>');
 * // Returns: '&lt;script&gt;alert("xss")&lt;/script&gt;<b>Hello</b>'
 * ```
 */
export function sanitizeHtml(dirty: string): string {
  if (!dirty) return "";

  // Trim to prevent edge cases with leading/trailing whitespace
  const trimmed = dirty.trim();
  if (!trimmed) return "";

  ensureBlankTargetRelHook();

  return DOMPurify.sanitize(trimmed, {
    // Only allow safe formatting and structural tags
    ALLOWED_TAGS: [
      "b", "i", "em", "strong", "a", "p", "br", "ul", "ol", "li",
      "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
      "pre", "code", "sub", "sup", "small", "span",
      "svg", "path", "polyline", "line"
    ],
    // Only allow safe attributes
    ALLOWED_ATTR: [
      "href", "target", "rel", "class", "title", "id",
      "xmlns", "viewBox", "width", "height", "fill", "stroke",
      "stroke-width", "stroke-linecap", "stroke-linejoin", "d",
      "x1", "y1", "x2", "y2", "points"
    ],
    // Explicitly block dangerous attributes
    FORBID_ATTR: [
      "style", "onclick", "onload", "onerror", "onmouseover",
      "onmouseout", "onmousedown", "onmouseup", "onkeydown",
      "onkeyup", "onfocus", "onblur", "javascript:", "data:"
    ],
    // Attributes are allowlisted above; the afterSanitizeAttributes hook adds
    // rel="noopener noreferrer" to target="_blank" links.
    ADD_ATTR: ["target"],
    // Only allow http:, https:, and mailto: URLs in href
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|#|\/)/i,
    // Return DOM clobbering-safe string (no document.write, etc.)
    RETURN_DOM: false,
    // Return the sanitized content as a string (not a DOM fragment)
    RETURN_DOM_FRAGMENT: false,
  });
}
