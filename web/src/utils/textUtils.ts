import he from 'he';

/**
 * Utility to decode common HTML entities using the robust 'he' library.
 */
export function decodeHtmlEntities(text: any): string {
    if (!text) return '';
    if (typeof text !== 'string') text = String(text);
    return he.decode(text);
}

/**
 * Global cleaning and decoding for news text.
 * Strips scraping artifacts and standardizes whitespace.
 */
export function cleanAndDecode(text: any): string {
    if (!text) return '';
    if (typeof text !== 'string') text = String(text);
    
    let cleaned = decodeHtmlEntities(text);
    
    // 1. Strip scraping artifacts from the end or middle
    // Handles variants like: Read More », Read More, [&#8230;], Прочитај повеќе, etc.
    const artifacts = [
        /Read\s+More\s*[»\>\-]*\s*$/gi,
        /Прочитај\s+повеќе\s*$/gi,
        /Continue\s+reading\s*$/gi,
        /\[\s*&#\d+;\s*\]/g,      // Handles [&#8230;]
        /\[\s*\.\.\.\s*\]/g,      // Handles [...]
        /\s*&#8230;\s*$/g,        // Trailing ellipsis entity
        /\s*…\s*$/g               // Trailing actual ellipsis
    ];
    
    artifacts.forEach(regex => {
        cleaned = cleaned.replace(regex, '');
    });

    // 2. Formatting fixes
    return cleaned
        .replace(/^[⚪🟢🔴]\s*/u, '') // Remove lead status circles
        .replace(/#[^\s#]+/g, '')     // Remove hashtags
        .replace(/\s+/g, ' ')         // Collapse whitespace
        .trim();
}

export function isMostlyCyrillic(text: any): boolean {
    if (!text) return false;

    const value = cleanAndDecode(text);
    if (!value) return false;

    let cyrillic = 0;
    let latin = 0;

    for (const ch of value) {
        if (ch >= '\u0400' && ch <= '\u04FF') cyrillic += 1;
        else if ((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z')) latin += 1;
    }

    if (cyrillic < 6) return false;
    if (latin === 0) return true;
    return cyrillic >= latin * 1.6;
}
