// Named HTML entities we actually see in scraped MK/EN news. Covers the long
// tail via numeric fall-through; anything else passes through unchanged.
const NAMED_ENTITIES: Record<string, string> = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00A0',
    hellip: '…', mdash: '—', ndash: '–',
    laquo: '«', raquo: '»', bdquo: '„', ldquo: '“', rdquo: '”', lsquo: '‘', rsquo: '’',
    copy: '©', reg: '®', trade: '™', middot: '·',
};

const TITLE_PROPER_NOUNS: Array<[RegExp, string]> = [
    [/\bмакедонија\b/gi, 'Македонија'],
    [/\bмосква\b/gi, 'Москва'],
    [/\bданиел христов\b/gi, 'Даниел Христов'],
    [/\bбудимпешта\b/gi, 'Будимпешта'],
    [/\bунгарска\b/gi, 'Унгарска'],
    [/\bкрива паланка\b/gi, 'Крива Паланка'],
    [/\bјугославија\b/gi, 'Југославија'],
    [/\bердоган\b/gi, 'Ердоган'],
    [/\bруте\b/gi, 'Руте'],
    [/\bтурција\b/gi, 'Турција'],
    [/\bрусија\b/gi, 'Русија'],
    [/\bукраина\b/gi, 'Украина'],
    [/\bиран\b/gi, 'Иран'],
    [/\bданска\b/gi, 'Данска'],
    [/\bевропа\b/gi, 'Европа'],
    [/\bтито\b/gi, 'Тито'],
    [/\bсрпската опозиција\b/gi, 'Српската опозиција'],
    [/\bзаев\b/gi, 'Заев'],
    [/\bбашановиќ\b/gi, 'Башановиќ'],
    [/\bбашановик\b/gi, 'Башановиќ'],
];

export function decodeHtmlEntities(text: any): string {
    if (!text) return '';
    if (typeof text !== 'string') text = String(text);
    return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (m: string, g: string) => {
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

export function extractCleanSummaryText(input: any): string {
    let text = input || '';
    if (typeof text !== 'string') text = String(text);

    const trimmed = text.trim();
    if (
        trimmed.startsWith('{') ||
        trimmed.startsWith('&lt;%') ||
        trimmed.includes('&quot;summary&quot;')
    ) {
        try {
            const decoded = trimmed.includes('&quot;') ? cleanAndDecode(trimmed) : trimmed;
            if (decoded.startsWith('{')) {
                const parsed = JSON.parse(decoded);
                if (parsed?.summary) text = parsed.summary;
                else if (parsed?.text) text = parsed.text;
            }
        } catch {
            // Leave the original text in place if it's not valid JSON.
        }
    }

    return cleanAndDecode(text);
}

function normalizeDisplayTitle(text: string): string {
    let value = text;
    for (const [pattern, replacement] of TITLE_PROPER_NOUNS) {
        value = value.replace(pattern, replacement);
    }
    return value;
}

export function getDisplayTitle(article: any, fallback = ''): string {
    return normalizeDisplayTitle(article?.display_title || cleanAndDecode(article?.title || fallback));
}

export function getDisplaySummary(article: any): string {
    return article?.display_summary || extractCleanSummaryText(article?.summary || article?.description || '');
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

/**
 * Highlights football-like scores (e.g., 1-0, 2:1) in text,
 * while excluding clock times like 15:00.
 */
export function highlightScores(text: string): string {
    if (!text) return '';
    
    // Pattern for N:N or N-N (with optional parentheses)
    return text.replace(/\(?\b(\d+[:\-]\d+)\b\)?/g, (match, score) => {
        const parts = score.split(/[:\-]/);
        if (parts.length === 2) {
            const h = parseInt(parts[0], 10);
            const m = parseInt(parts[1], 10);
            
            // 1. If it's a ":" separator and looks like an hour (>12), it's probably time
            if (score.includes(':') && h > 12) return match;
            
            // 2. If it's a "-" separator and looks like a year-range (e.g. 2024-2025), it's not a score
            if (score.includes('-') && h > 1900 && m > 1900) return match;
            
            // 3. Scores like 15:00 can be basketball, but in most cases it's time
            // Let's assume scores are relatively small or if it's football/handball
            // If it's exactly 15:00, 20:00 etc it's very likely time.
            if (score.includes(':') && (h >= 10 && m === 0)) return match;
            
            return `<span class="font-bold text-red-600 dark:text-red-400">${match}</span>`;
        }
        return match;
    });
}

/**
 * Returns a formal edition label based on the time of day.
 */
export function getEditionStr(dateInput: any): string {
    const date = new Date(dateInput);
    if (isNaN(date.getTime())) return '';
    
    const now = new Date();
    const diffMins = Math.floor((now.getTime() - date.getTime()) / (1000 * 60));
    
    // If it's very fresh, it's an Extra Edition
    if (diffMins >= 0 && diffMins < 45) {
        return 'ВОНРЕДНО ИЗДАНИЕ';
    }

    const hour = Number(new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        hour12: false,
        timeZone: 'Europe/Skopje',
    }).format(date));
    
    if (hour >= 5 && hour < 12) return 'УТРИНСКО ИЗДАНИЕ';
    if (hour >= 12 && hour < 18) return 'ПЛАДНЕВНО ИЗДАНИЕ';
    return 'ВЕЧЕРНО ИЗДАНИЕ';
}

/**
 * Converts [1], [2] citations into superscript links.
 */
export function parseFootnotes(text: string): string {
    if (!text) return '';
    return text.replace(/\[(\d+)\]/g, (match, num) => {
        return `<sup class="text-nyt-accent font-black ml-0.5 cursor-help" title="Извор ${num}">${num}</sup>`;
    });
}
