// Named HTML entities we actually see in scraped MK/EN news. Covers the long
// tail via numeric fall-through; anything else passes through unchanged.
const NAMED_ENTITIES: Record<string, string> = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00A0',
    hellip: '…', mdash: '—', ndash: '–',
    laquo: '«', raquo: '»', bdquo: '„', ldquo: '“', rdquo: '”', lsquo: '‘', rsquo: '’',
    copy: '©', reg: '®', trade: '™', middot: '·',
};

export function decodeHtmlEntities(text: any): string {
    if (!text) return '';
    if (typeof text !== 'string') text = String(text);
    return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (m, g) => {
        if (g[0] === '#') {
            const code = g[1] === 'x' || g[1] === 'X' ? parseInt(g.slice(2), 16) : parseInt(g.slice(1), 10);
            return Number.isFinite(code) ? String.fromCodePoint(code) : m;
        }
        return NAMED_ENTITIES[g.toLowerCase()] ?? m;
    });
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
