// Named HTML entities we actually see in scraped RS/EN news. Covers the long
// tail via numeric fall-through; anything else passes through unchanged.
const NAMED_ENTITIES: Record<string, string> = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00A0',
    hellip: '…', mdash: '—', ndash: '–',
    laquo: '«', raquo: '»', bdquo: '„', ldquo: '“', rdquo: '”', lsquo: '‘', rsquo: '’',
    copy: '©', reg: '®', trade: '™', middot: '·',
};

const TITLE_PROPER_NOUNS: Array<[RegExp, string]> = [
    [/\bsrbija\b/gi, 'Srbija'],
    [/\bbugarija\b/gi, 'Bugarija'],
    [/\bsrbija\b/gi, 'Srbija'],
    [/\bgrcija\b/gi, 'Grcija'],
    [/\balbanija\b/gi, 'Albanija'],
    [/\bkosovo\b/gi, 'Kosovo'],
    [/\brusija\b/gi, 'Rusija'],
    [/\bukraina\b/gi, 'Ukraina'],
    [/\bizrael\b/gi, 'Izrael'],
    [/\bpalestina\b/gi, 'Palestina'],
    [/\bgermanija\b/gi, 'Germanija'],
    [/\bfrancija\b/gi, 'Francija'],
    [/\bbritanska\b/gi, 'Britanska'],
    [/\bbritanski\b/gi, 'Britanski'],
    [/\bbritanija\b/gi, 'Britanija'],
    [/\bkina\b/gi, 'Kina'],
    [/\bpeking\b/gi, 'Peking'],
    [/\bsi dzinping\b/gi, 'Si Dzinping'],
    [/\bsad\b/gi, 'SAD'],
    [/\beu\b/gi, 'EU'],
    [/\bnato\b/gi, 'NATO'],
    [/\bmoskva\b/gi, 'Moskva'],
    [/\bdaniel hristov\b/gi, 'Daniel Hristov'],
    [/\bbudimpesta\b/gi, 'Budimpesta'],
    [/\bungarska\b/gi, 'Ungarska'],
    [/\bkriva palanka\b/gi, 'Kriva Palanka'],
    [/\bjugoslavija\b/gi, 'Jugoslavija'],
    [/\berdogan\b/gi, 'Erdogan'],
    [/\brute\b/gi, 'Rute'],
    [/\bturcija\b/gi, 'Turcija'],
    [/\brusija\b/gi, 'Rusija'],
    [/\bukraina\b/gi, 'Ukraina'],
    [/\biran\b/gi, 'Iran'],
    [/\bdanska\b/gi, 'Danska'],
    [/\bevropa\b/gi, 'Evropa'],
    [/\btito\b/gi, 'Tito'],
    [/\bsrpska opozicija\b/gi, 'Srpska opozicija'],
    [/\bzaev\b/gi, 'Zaev'],
    [/\bbasanovic\b/gi, 'Basanovic'],
    [/\bbasanovik\b/gi, 'Basanovic'],
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

export const CYR_TO_LAT: Record<string, string> = {
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Ѓ': 'Ǵ', 'Е': 'E', 'Ж': 'Ž', 'З': 'Z', 'Ѕ': 'Dz', 'И': 'I', 'Ј': 'J', 'К': 'K', 'Л': 'L', 'Љ': 'Lj', 'М': 'M', 'Н': 'N', 'Њ': 'Nj', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'Ќ': 'Ḱ', 'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'C', 'Ч': 'Č', 'Џ': 'Dž', 'Ш': 'Š',
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'ѓ': 'ǵ', 'е': 'e', 'ж': 'ž', 'з': 'z', 'ѕ': 'dz', 'и': 'i', 'ј': 'j', 'к': 'k', 'л': 'l', 'љ': 'lj', 'м': 'm', 'н': 'n', 'њ': 'nj', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'ќ': 'ḱ', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'č', 'џ': 'dž', 'ш': 'š'
};

export function cyrToLat(text: string): string {
    return text.split('').map(char => CYR_TO_LAT[char] || char).join('');
}

// Alias for backward compatibility - transliterate means Cyrillic to Latin
export const transliterate = cyrToLat;
export const transliterateToLat = cyrToLat;

export function latToCyr(text: string): string {
    const latToCyrMap: Record<string, string> = Object.fromEntries(Object.entries(CYR_TO_LAT).map(([k, v]) => [v, k]));
    // Simple reverse map; caution: some multi-char mappings like 'Dž' need special handling if used
    return text.split('').map(char => latToCyrMap[char] || char).join('');
}

export const transliterateToCyr = latToCyr;

/**
 * Generates a clean URL slug from a title.
 */
export function slugify(text: string): string {
    if (!text) return '';
    const transliterated = transliterate(text);
    return transliterated
        .toLowerCase()
        .replace(/[^\w\s-]/g, '') // Remove non-word chars
        .replace(/\s+/g, '-')     // Replace spaces with -
        .replace(/--+/g, '-')     // Replace multiple - with single -
        .trim();
}

/**
 * Converts ALL CAPS text into Sentence case, preserving acronyms.
 */
export function deShout(text: string): string {
    if (!text) return '';
    // If text doesn't have many lowercase letters, it's probably shouting
    const lowerCount = (text.match(/\p{Ll}/gu) || []).length;
    const totalAlpha = (text.match(/\p{L}/gu) || []).length;
    
    if (totalAlpha > 5 && lowerCount < totalAlpha * 0.2) {
        const lower = text.toLowerCase();
        return lower.charAt(0).toUpperCase() + lower.slice(1);
    }
    return text;
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
    // Handles variants like: Read More », Read More, [&#8230;], Procitaj povece, etc.
    const artifacts = [
        /Read\s+More\s*[»\>\-]*\s*$/gi,
        /Procitaj\s+povece\s*$/gi,
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

    // AI summary extraction with recursive protection against double-stringification
    let attempts = 0;
    while (attempts < 3) {
        let trimmed = text.trim();
        // Remove markdown JSON formatting if present
        trimmed = trimmed.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();

        if (
            trimmed.startsWith('{') ||
            trimmed.startsWith('&lt;%') ||
            trimmed.includes('&quot;summary&quot;') ||
            trimmed.includes('"summary":')
        ) {
            try {
                const decoded = (trimmed.includes('&quot;') || trimmed.includes('&lt;')) 
                    ? cleanAndDecode(trimmed) 
                    : trimmed;
                
                if (decoded.startsWith('{')) {
                    const parsed = JSON.parse(decoded);
                    if (parsed?.summary) {
                        text = parsed.summary;
                        attempts++;
                        continue;
                    } else if (parsed?.text) {
                        text = parsed.text;
                        attempts++;
                        continue;
                    }
                }
            } catch {
                // If parsing fails, fall through to regex cleanup
                break;
            }
        }
        break;
    }

    // Fallback: If it still looks like JSON after failing to parse, try to extract just the summary value
    if (text.includes('"summary":') || text.includes('&quot;summary&quot;')) {
        const match = text.match(/"summary"\s*:\s*"([^"]+)"/);
        if (match && match[1]) {
            text = match[1];
        }
    }

    // Enhanced markdown cleanup - strip common markdown syntax that shouldn't be rendered as HTML
    let cleaned = cleanAndDecode(text);
    
    // Remove markdown bold/italic syntax but preserve the content
    cleaned = cleaned.replace(/\*\*(.*?)\*\*/g, '$1'); // **bold**
    cleaned = cleaned.replace(/__(.*?)__/g, '$1');       // __bold__
    cleaned = cleaned.replace(/\*(.*?)\*/g, '$1');     // *italic*
    cleaned = cleaned.replace(/_(.*?)_/g, '$1');        // _italic_
    
    // Remove markdown links but keep the link text
    cleaned = cleaned.replace(/\\[(.*?)\\]\\(.*?\\)/g, '$1');
    
    // Remove markdown headers
    cleaned = cleaned.replace(/^#+\s+/gm, '');
    
    // Remove markdown code blocks
    cleaned = cleaned.replace(/`{1,3}(.*?)`{1,3}/g, '$1');
    
    // Remove markdown horizontal rules
    cleaned = cleaned.replace(/^[-*_]{3,}\s*$/gm, '');
    
    // Remove markdown blockquotes
    cleaned = cleaned.replace(/^>\s+/gm, '');
    
    // Remove markdown list markers
    cleaned = cleaned.replace(/^\s*[-*+]\s+/gm, '');
    cleaned = cleaned.replace(/^\s*\d+\.\s+/gm, '');
    
    return cleaned.trim();
}

function normalizeDisplayTitle(text: string): string {
    let value = text;
    for (const [pattern, replacement] of TITLE_PROPER_NOUNS) {
        value = value.replace(pattern, replacement);
    }
    return value;
}

export function getDisplayTitle(article: any, fallback = ''): string {
    return normalizeDisplayTitle(deShout(article?.display_title || cleanAndDecode(article?.title || fallback)));
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

    // Normalize ALL CAPS to Sentence Case (editorial polish)
    const normalized = deShout(text);
    
    // Pattern for N:N or N-N (with optional parentheses)
    return normalized.replace(/\(?\b(\d+[:\-]\d+)\b\)?/g, (match, score) => {
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
    
    const hour = Number(new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        hour12: false,
        timeZone: 'Europe/Skopje',
    }).format(date));
    
    if (hour >= 5 && hour < 12) return 'UTRINSKO IZDANIE';
    if (hour >= 12 && hour < 18) return 'PLADNEVNO IZDANIE';
    return 'VECERNO IZDANIE';
}

/**
 * Returns context for designed fallback cards.
 */
export function getDesignCardContext(cluster: any) {
    const topic = (cluster.topics?.[0] || cluster.articles?.[0]?.topic || '').toLowerCase();
    const category = (cluster.articles?.[0]?.category || '').toLowerCase();
    
    if (topic.includes('Kultura') || category.includes('Kultura') || topic.includes('umetnost')) {
        return { label: 'KULTURNA PREPORAKA', icon: 'palette', sub: 'Pregled na najznacajnite dela od istorijata na makedonskata umetnost.' };
    }
    if (topic.includes('Politika') || category.includes('Politika')) {
        return { label: 'POLITICKI FOKUS', icon: 'building-2', sub: 'Dlabinska analiza na klucnite politicki procesi i odluki.' };
    }
    if (topic.includes('Ekonomija') || category.includes('Ekonomija') || topic.includes('biznis')) {
        return { label: 'EKONOMSKI BRIFING', icon: 'trending-up', sub: 'Pregled na ekonomskite trendovi i finansiskite pazari.' };
    }
    if (topic.includes('Sport') || category.includes('Sport')) {
        return { label: 'SPORTSKI PULS', icon: 'award', sub: 'Najvaznite nastani i rezultati od svetot na sportot.' };
    }
    if (topic.includes('Tehnologija') || category.includes('Tehnologija') || topic.includes('nauka')) {
        return { label: 'TEHNOLOSKI PRESEK', icon: 'cpu', sub: 'Inovacii i otkritija koi me oblikuvaat nasata idnina.' };
    }
    
    return { label: 'SISTEMSKI PREGLED', icon: 'newspaper', sub: 'Algoritamska sinteza na vodeckite informacii od domasnite mediumi.' };
}

/**
 * Converts [1], [2], [1, 2] or even raw trailing numbers like "fact 46" into superscript links.
 */
export function parseFootnotes(text: string): string {
    if (!text) return '';
    
    let processed = text;

    // 1. Convert raw numbers at the end of words/sentences into brackets
    // Matches a space, then 1-3 digits, followed by a period or end of string
    // e.g. "pretsedatelot 1" -> "pretsedatelot [1]"
    processed = processed.replace(/\s(\d{1,3})(?=\.|\,|$|\s)/g, ' [$1]');

    // 2. Handle [1, 2, 3] style (comma separated inside brackets)
    // Splits them into individual [1][2][3] for the next pass
    processed = processed.replace(/\[(\d+(?:\s*,\s*\d+)+)\]/g, (match, digits) => {
        return digits.split(',').map((d: string) => `[${d.trim()}]`).join('');
    });

    // 3. Convert all [N] into superscript links
    return processed.replace(/\[(\d+)\]/g, (match, num) => {
        return `<sup class="text-nyt-accent font-black ml-0.5 cursor-help" title="izvor ${num}">${num}</sup>`;
    });
}
