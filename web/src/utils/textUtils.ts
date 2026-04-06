/**
 * Utility to decode common HTML entities like &#8230; (ellipsis), &amp;, etc.
 * Uses a lightweight regex-based approach suitable for Astro components.
 */
export function decodeHtmlEntities(text: string): string {
    if (!text) return '';
    
    return text
        .replace(/&quot;/g, '"')
        .replace(/&apos;/g, "'")
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&#(\d+);/g, (match, dec) => String.fromCharCode(dec))
        .replace(/&#x([0-9a-f]+);/gi, (match, hex) => String.fromCharCode(parseInt(hex, 16)))
        .replace(/&nbsp;/g, ' ')
        .replace(/&copy;/g, '©')
        .replace(/&reg;/g, '®')
        .replace(/&hellip;/g, '…')
        .replace(/&ndash;/g, '–')
        .replace(/&mdash;/g, '—')
        .replace(/&lsquo;/g, '‘')
        .replace(/&rsquo;/g, '’')
        .replace(/&ldquo;/g, '“')
        .replace(/&rdquo;/g, '”')
        .replace(/&bull;/g, '•');
}

/**
 * Combined cleaning and decoding for news text.
 */
export function cleanAndDecode(text: string): string {
    if (!text) return '';
    return decodeHtmlEntities(text)
        .replace(/^[⚪🟢🔴]\s*/u, '')
        .replace(/#[^\s#]+/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}
