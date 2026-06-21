// Named HTML entities we actually see in scraped RS/EN news. Covers the long
// tail via numeric fall-through; anything else passes through unchanged.
import { prepareSynthesisParagraph, stripBareUrls } from './synthesisCopy.ts';
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
    [/\bskopje\b/gi, 'Skopje'],
    [/\bbitola\b/gi, 'Bitola'],
    [/\bohrid\b/gi, 'Ohrid'],
    [/\btetovo\b/gi, 'Tetovo'],
    [/\bkumanovo\b/gi, 'Kumanovo'],
    [/\bprilep\b/gi, 'Prilep'],
    [/\bveles\b/gi, 'Veles'],
    [/\bstip\b/gi, 'Stip'],
    [/\bstrumica\b/gi, 'Strumica'],
    [/\bgostivar\b/gi, 'Gostivar'],
    [/\bkavadarci\b/gi, 'Kavadarci'],
    [/\bkocani\b/gi, 'Kocani'],
    [/\bkicevo\b/gi, 'Kicevo'],
    [/\bstruga\b/gi, 'Struga'],
    [/\bgevgelija\b/gi, 'Gevgelija'],
    [/\bnovi sad\b/gi, 'Novi Sad'],
    [/\bnis\b/gi, 'Nis'],
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

// South Slavic Cyrillic → Latin (aligned with core/language.py)
export const CYR_TO_LAT: Record<string, string> = {
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Ѓ': 'Đ', 'Е': 'E', 'Ж': 'Ž', 'З': 'Z', 'Ѕ': 'Dz', 'И': 'I', 'Ј': 'J', 'К': 'K', 'Л': 'L', 'Љ': 'Lj', 'М': 'M', 'Н': 'N', 'Њ': 'Nj', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'Ќ': 'Ć', 'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'C', 'Ч': 'Č', 'Џ': 'Dž', 'Ш': 'Š',
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'ѓ': 'đ', 'е': 'e', 'ж': 'ž', 'з': 'z', 'ѕ': 'dz', 'и': 'i', 'ј': 'j', 'к': 'k', 'л': 'l', 'љ': 'lj', 'м': 'm', 'н': 'n', 'њ': 'nj', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'ќ': 'ć', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'č', 'џ': 'dž', 'ш': 'š',
    'ћ': 'ć', 'Ћ': 'Ć', 'ђ': 'đ', 'Ђ': 'Đ',
};

export function cyrToLat(text: string): string {
    if (!text) return '';
    return text.split('').map(char => CYR_TO_LAT[char] || char).join('');
}

// Alias for backward compatibility - transliterate means Cyrillic to Latin
export const transliterate = cyrToLat;
export const transliterateToLat = cyrToLat;

const LAT_TO_CYR_DIGRAPHS: Record<string, string> = {
    'sh': 'ш', 'Sh': 'Ш', 'SH': 'Ш',
    'zh': 'ж', 'Zh': 'Ж', 'ZH': 'Ж',
    'ch': 'ч', 'Ch': 'Ч', 'CH': 'Ч',
    'dj': 'ѓ', 'Dj': 'Ѓ', 'DJ': 'Ѓ',
    'dz': 'ѕ', 'Dz': 'Ѕ', 'DZ': 'Ѕ',
    'lj': 'љ', 'Lj': 'Љ', 'LJ': 'Љ',
    'nj': 'њ', 'Nj': 'Њ', 'NJ': 'Њ',
};

function normalizeLatinDiacritics(text: string): string {
    return text
        .replace(/ć/g, 'c').replace(/č/g, 'ch').replace(/š/g, 'sh').replace(/ž/g, 'zh').replace(/đ/g, 'dj')
        .replace(/Ć/g, 'C').replace(/Č/g, 'Ch').replace(/Š/g, 'Sh').replace(/Ž/g, 'Zh').replace(/Đ/g, 'Dj');
}

export function latToCyr(text: string): string {
    if (!text) return '';

    const cyrChars = [...text].filter((char) => char >= '\u0400' && char <= '\u04ff').length;
    if (cyrChars > 0) return text;

    let result = text.replace(/vecer/gi, (match) => {
        if (match === 'VECER') return 'VEČER';
        if (match === 'Vecer') return 'Večer';
        if (match[0] === 'V') return 'Večer';
        return 'večer';
    });

    const latToCyrMap: Record<string, string> = Object.fromEntries(
        Object.entries(CYR_TO_LAT).map(([cyr, lat]) => [lat, cyr])
    );
    Object.assign(latToCyrMap, LAT_TO_CYR_DIGRAPHS);

    result = normalizeLatinDiacritics(result);
    for (const key of Object.keys(latToCyrMap).sort((a, b) => b.length - a.length)) {
        result = result.replaceAll(key, latToCyrMap[key]);
    }
    return result;
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
        const scalarMatch = text.match(/"summary"\s*:\s*"((?:[^"\\]|\\.)*)"/);
        const truncatedMatch = scalarMatch ? null : text.match(/"summary"\s*:\s*"((?:[^"\\]|\\.)*)/);
        const raw = scalarMatch?.[1] || truncatedMatch?.[1];
        if (raw) {
            text = raw.replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\'/g, "'");
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

    return stripBareUrls(cleaned.trim());
}

function normalizeDisplayTitle(text: string): string {
    let value = text;
    for (const [pattern, replacement] of TITLE_PROPER_NOUNS) {
        value = value.replace(pattern, replacement);
    }
    return value;
}

export function getDisplayTitle(article: any, fallback = '', lang?: string): string {
    let title = normalizeDisplayTitle(deShout(article?.display_title || cleanAndDecode(article?.title || fallback)));
    if (lang === 'sr' && isMostlyCyrillic(title)) {
        title = transliterate(title);
    }
    return title;
}

export function getDisplaySummary(article: any, lang?: string): string {
    const raw = article?.display_summary || article?.summary || article?.description || '';
    let summary = extractCleanSummaryText(raw);
    if (lang === 'sr' && isMostlyCyrillic(summary)) {
        summary = transliterate(summary);
    }
    return summary;
}

export function smartTruncate(text: string, limit: number): string {
    if (!text || text.length <= limit) return text;
    const sliced = text.slice(0, limit);
    const lastSpace = Math.max(
        sliced.lastIndexOf(' '),
        sliced.lastIndexOf('.'),
        sliced.lastIndexOf(','),
        sliced.lastIndexOf('-'),
        sliced.lastIndexOf('–')
    );
    if (lastSpace > limit - 25 && lastSpace > 0) {
        return `${sliced.slice(0, lastSpace).trimEnd()}...`;
    }
    return `${sliced.trimEnd()}...`;
}

export function isSyntheticStandfirstBoilerplate(input: any): boolean {
    const text = extractCleanSummaryText(input);
    if (!text) return false;

    return [
        /^Уреднички\s+преглед(?:\s|:|\.|,|$)/i,
        /^Urednički\s+pregled\s+baziran\s+na\b/i,
        /^Urednicki\s+pregled\s+baziran\s+na\b/i,
        /^Editorial\s+overview\s+based\s+on\b/i,
    ].some((pattern) => pattern.test(text));
}

export function getStoryPreviewText(cluster: any, fallbackArticle?: any, lang?: string): string {
    const standfirst = extractCleanSummaryText(cluster?.synthetic_standfirst || '');
    if (standfirst && !isSyntheticStandfirstBoilerplate(standfirst)) {
        const cleaned = prepareSynthesisParagraph(standfirst, lang || 'sr');
        if (lang === 'sr' && isMostlyCyrillic(cleaned)) {
            return transliterate(cleaned);
        }
        return cleaned;
    }

    const article = fallbackArticle || cluster?.articles?.[0];
    const summary = getDisplaySummary(article, lang);
    return prepareSynthesisParagraph(summary, lang || 'sr');
}

export function getPersonalizedText(text: string, lang: string): string {
    if (!text) return '';
    let result = deShout(text);
    if (lang === 'sr' && isMostlyCyrillic(result)) {
        result = transliterate(result);
    }
    return result;
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
 * Returns a formal edition translation key based on the time of day.
 */
export function getEditionStr(dateInput: any): string {
    const date = new Date(dateInput);
    if (isNaN(date.getTime())) return '';

    const hour = Number(new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        hour12: false,
        timeZone: 'Europe/Skopje',
    }).format(date));

    if (hour >= 5 && hour < 12) return 'edition.morning';
    if (hour >= 12 && hour < 18) return 'edition.afternoon';
    return 'edition.evening';
}

/**
 * Returns context keys for designed fallback cards.
 */
export function getDesignCardContext(cluster: any) {
    const topic = (cluster.topics?.[0] || cluster.articles?.[0]?.topic || '').toLowerCase();
    const category = (cluster.articles?.[0]?.category || '').toLowerCase();

    if (topic.includes('kultura') || category.includes('kultura') || topic.includes('umetnost')) {
        return { labelKey: 'card.culture', icon: 'palette', subKey: 'card.culture_desc' };
    }
    if (topic.includes('politika') || category.includes('politika')) {
        return { labelKey: 'card.politics', icon: 'building-2', subKey: 'card.politics_desc' };
    }
    if (topic.includes('ekonomija') || category.includes('ekonomija') || topic.includes('biznis')) {
        return { labelKey: 'card.economy', icon: 'trending-up', subKey: 'card.economy_desc' };
    }
    if (topic.includes('sport') || category.includes('sport')) {
        return { labelKey: 'card.sport', icon: 'award', subKey: 'card.sport_desc' };
    }
    if (topic.includes('tehnologija') || category.includes('tehnologija') || topic.includes('nauka')) {
        return { labelKey: 'card.tech', icon: 'cpu', subKey: 'card.tech_desc' };
    }

    return { labelKey: 'card.general', icon: 'newspaper', subKey: 'card.general_desc' };
}

/**
 * Expands [1, 2, 3] style markers into [1][2][3] for downstream handling.
 */
export function normalizeCitationMarkers(text: string): string {
    if (!text) return '';
    return text.replace(/\[(\d+(?:\s*,\s*\d+)+)\]/g, (_match, digits) =>
        digits.split(',').map((d: string) => `[${d.trim()}]`).join('')
    );
}

/**
 * Removes inline numeric citation markers from synthesis prose.
 */
export function stripCitationMarkers(text: string): string {
    if (!text) return '';
    return normalizeCitationMarkers(text)
        .replace(/\[\d+\]/g, '')
        .replace(/\s+([,.;:!?])/g, '$1')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

const COMMON_TAGS_MAP: Record<string, { sr: string; mk: string }> = {
    // Countries & Regions
    'amerika': { sr: 'Amerika', mk: 'Америка' },
    'sad': { sr: 'SAD', mk: 'САД' },
    'usa': { sr: 'SAD', mk: 'САД' },
    'rusija': { sr: 'Rusija', mk: 'Русија' },
    'russia': { sr: 'Rusija', mk: 'Русија' },
    'ukrajina': { sr: 'Ukrajina', mk: 'Украина' },
    'ukraina': { sr: 'Ukrajina', mk: 'Украина' },
    'ukraine': { sr: 'Ukrajina', mk: 'Украина' },
    'kina': { sr: 'Kina', mk: 'Кина' },
    'china': { sr: 'Kina', mk: 'Кина' },
    'evropa': { sr: 'Evropa', mk: 'Европа' },
    'europe': { sr: 'Evropa', mk: 'Европа' },
    'balkan': { sr: 'Balkan', mk: 'Балкан' },
    'srbija': { sr: 'Srbija', mk: 'Србија' },
    'serbia': { sr: 'Srbija', mk: 'Србија' },
    'makedonija': { sr: 'Makedonija', mk: 'Македонија' },
    'macedonia': { sr: 'Makedonija', mk: 'Македонија' },
    'germanija': { sr: 'Nemačka', mk: 'Германија' },
    'germany': { sr: 'Nemačka', mk: 'Германија' },
    'nemacka': { sr: 'Nemačka', mk: 'Германија' },
    'francija': { sr: 'Francuska', mk: 'Франција' },
    'france': { sr: 'Francuska', mk: 'Франција' },
    'francuska': { sr: 'Francuska', mk: 'Франција' },
    'grcija': { sr: 'Grčka', mk: 'Грција' },
    'greece': { sr: 'Grčka', mk: 'Грција' },
    'grcka': { sr: 'Grčka', mk: 'Грција' },
    'bugarija': { sr: 'Bugarska', mk: 'Бугарија' },
    'bulgaria': { sr: 'Bugarska', mk: 'Бугарија' },
    'bugarska': { sr: 'Bugarska', mk: 'Бугарија' },
    'albanija': { sr: 'Albanija', mk: 'Албанија' },
    'albania': { sr: 'Albanija', mk: 'Албанија' },
    'kosovo': { sr: 'Kosovo', mk: 'Косово' },
    'izrael': { sr: 'Izrael', mk: 'Израел' },
    'israel': { sr: 'Izrael', mk: 'Израел' },
    'palestina': { sr: 'Palestina', mk: 'Палестина' },
    'palestine': { sr: 'Palestina', mk: 'Палестина' },
    'turcija': { sr: 'Turska', mk: 'Турција' },
    'turkey': { sr: 'Turska', mk: 'Турција' },
    'turska': { sr: 'Turska', mk: 'Турција' },
    'iran': { sr: 'Iran', mk: 'Иран' },
    'danska': { sr: 'Danska', mk: 'Данска' },
    'denmark': { sr: 'Danska', mk: 'Данска' },
    'ungarska': { sr: 'Mađarska', mk: 'Унгарија' },
    'madarska': { sr: 'Mađarska', mk: 'Унгарија' },
    'hungary': { sr: 'Mađarska', mk: 'Унгарија' },

    // Cities
    'skopje': { sr: 'Skoplje', mk: 'Скопје' },
    'skoplje': { sr: 'Skoplje', mk: 'Скопје' },
    'bitola': { sr: 'Bitolj', mk: 'Битола' },
    'ohrid': { sr: 'Ohrid', mk: 'Охрид' },
    'tetovo': { sr: 'Tetovo', mk: 'Тетово' },
    'kumanovo': { sr: 'Kumanovo', mk: 'Куманово' },
    'prilep': { sr: 'Prilep', mk: 'Прилеп' },
    'veles': { sr: 'Veles', mk: 'Велес' },
    'stip': { sr: 'Štip', mk: 'Штип' },
    'strumica': { sr: 'Strumica', mk: 'Струмица' },
    'gostivar': { sr: 'Gostivar', mk: 'Гостивар' },
    'kavadarci': { sr: 'Kavadarci', mk: 'Кавадарци' },
    'kocani': { sr: 'Kočani', mk: 'Кочани' },
    'kicevo': { sr: 'Kičevo', mk: 'Кичево' },
    'struga': { sr: 'Struga', mk: 'Струга' },
    'gevgelija': { sr: 'Gevgelija', mk: 'Гевгелија' },
    'novi sad': { sr: 'Novi Sad', mk: 'Нови Сад' },
    'nis': { sr: 'Niš', mk: 'Ниш' },
    'beograd': { sr: 'Beograd', mk: 'Београд' },
    'belgrade': { sr: 'Beograd', mk: 'Београд' },
    'moskva': { sr: 'Moskva', mk: 'Москва' },
    'moscow': { sr: 'Moskva', mk: 'Москва' },
    'peking': { sr: 'Peking', mk: 'Пекинг' },
    'beijing': { sr: 'Peking', mk: 'Пекинг' },
    'budimpesta': { sr: 'Budimpešta', mk: 'Будимпешта' },
    'budapest': { sr: 'Budimpešta', mk: 'Будимpeшта' },

    // Organizations & Acronyms
    'nasa': { sr: 'NASA', mk: 'НАСА' },
    'nato': { sr: 'NATO', mk: 'НАТО' },
    'eu': { sr: 'EU', mk: 'ЕУ' },
    'oob': { sr: 'UN', mk: 'ОН' },
    'un': { sr: 'UN', mk: 'ОН' },
    'szo': { sr: 'SZO', mk: 'СЗО' },
    'who': { sr: 'SZO', mk: 'СЗО' },
    'mvr': { sr: 'MVR', mk: 'МВР' },
    'sdsm': { sr: 'SDSM', mk: 'СДСМ' },
    'vmro': { sr: 'VMRO', mk: 'ВМРО' },
    'vmro-dpmne': { sr: 'VMRO-DPMNE', mk: 'ВМРО-ДПМНЕ' },
    'bdi': { sr: 'BDI', mk: 'ДУИ' },
    'dui': { sr: 'DUI', mk: 'ДУИ' },

    // Topics / Categories / General Terms
    'vesti': { sr: 'Vesti', mk: 'Вести' },
    'zivot': { sr: 'Život', mk: 'Живот' },
    'život': { sr: 'Život', mk: 'Живот' },
    'politika': { sr: 'Politika', mk: 'Политика' },
    'ekonomija': { sr: 'Ekonomija', mk: 'Економија' },
    'sport': { sr: 'Sport', mk: 'Спорт' },
    'tehnologija': { sr: 'Tehnologija', mk: 'Технологија' },
    'technology': { sr: 'Tehnologija', mk: 'Технологија' },
    'kultura': { sr: 'Kultura', mk: 'Култура' },
    'nauka': { sr: 'Nauka', mk: 'Наука' },
    'science': { sr: 'Nauka', mk: 'Наука' },
    'zdravstvo': { sr: 'Zdravstvo', mk: 'Здравство' },
    'zdravje': { sr: 'Zdravlje', mk: 'Здравје' },
    'health': { sr: 'Zdravlje', mk: 'Здравје' },
    'obrazovanje': { sr: 'Obrazovanje', mk: 'Образование' },
    'education': { sr: 'Obrazovanje', mk: 'Образование' },
    'hronika': { sr: 'Hronika', mk: 'Хроника' },
    'crna hronika': { sr: 'Crna hronika', mk: 'Црна хроника' },
    'vreme': { sr: 'Vreme', mk: 'Време' },
    'prognoza': { sr: 'Prognoza', mk: 'Прогноза' },
    'svet': { sr: 'Svet', mk: 'Свет' },
    'world': { sr: 'Svet', mk: 'Свет' },
    'regionalni vesti': { sr: 'Regionalne vesti', mk: 'Регионални вести' },
    'regionalno': { sr: 'Regionalno', mk: 'Регионално' },
    'zabava': { sr: 'Zabava', mk: 'Забава' },
    'scena': { sr: 'Scena', mk: 'Сцена' },
    'astrologija': { sr: 'Astrologija', mk: 'Астрологија' },
    'horoskop': { sr: 'Horoskop', mk: 'Хороскоп' },
    'zanimlivosti': { sr: 'Zanimljivosti', mk: 'Занимливости' },
};

export function getSourceInitials(source: string, max = 2): string {
    const cleaned = cleanAndDecode(source).trim();
    if (!cleaned) return 'P';
    const words = cleaned.split(/[\s|·\-–—/]+/).filter(Boolean);
    if (words.length >= 2) {
        return words
            .slice(0, max)
            .map((word) => word[0] || '')
            .join('')
            .toUpperCase()
            .slice(0, max);
    }
    return cleaned.slice(0, max).toUpperCase();
}

export function normalizeEntityOrTag(tag: string, lang: string): string {
    let cleaned = cleanAndDecode(tag).trim();
    if (!cleaned) return '';

    // De-shout screaming caps
    cleaned = deShout(cleaned);

    // Check the common tags map
    const lower = cleaned.toLowerCase();
    if (COMMON_TAGS_MAP[lower]) {
        return lang === 'sr' ? COMMON_TAGS_MAP[lower].sr : COMMON_TAGS_MAP[lower].mk;
    }

    // Specific acronym checks: If it is <= 4 chars and has standard acronym characters, keep all caps
    if (lower.length <= 4 && /^[a-z]+$/i.test(lower)) {
        cleaned = cleaned.toUpperCase();
    }

    // If Macedonian, and the string doesn't contain any Cyrillic but has Latin characters,
    // we transliterate to Cyrillic!
    if (lang !== 'sr' && !isMostlyCyrillic(cleaned)) {
        cleaned = latToCyr(cleaned);
    }

    // If Serbian, and the string is in Cyrillic, transliterate to Latin
    if (lang === 'sr' && isMostlyCyrillic(cleaned)) {
        cleaned = transliterate(cleaned);
    }

    return cleaned.trim();
}

// Common words that should not be treated as entities
const COMMON_NON_ENTITY_WORDS = new Set([
    // Macedonian
    'крај', 'доделување', 'доделувањето', 'почеток', 'средба', 'состанок', 'настан', 'собрание', 'сесија',
    'решение', 'одлука', 'процес', 'ситуација', 'случај', 'прашање', 'проблем', 'резултат', 'ефект',
    'део', 'дел', 'целост', 'систем', 'метод', 'начин', 'процедура', 'постапка', 'фаза', 'етапа',
    'развој', 'напредок', 'промена', 'тренд', 'динамика', 'перспектива', 'иднина', 'минато', 'сегашност',
    'цел', 'задача', 'функција', 'улога', 'одговорност', 'обврска', 'право', 'можност', 'шанса',
    'влијание', 'ефект', 'реакција', 'одговор', 'коментар', 'мислење', 'став', 'гледиште', 'перспектива',
    'информација', 'податок', 'факт', 'чиненица', 'детал', 'аспект', 'димензија', 'елемент', 'компонента',
    'прашање', 'одговор', 'решение', 'заклучок', 'препорака', 'сугестија', 'идеја', 'предлог', 'план',
    'проект', 'иницијатива', 'акција', 'дејство', 'мерка', 'чекор', 'фаза', 'период', 'рок', 'термин',
    'датум', 'време', 'ден', 'недела', 'месец', 'година', 'период', 'раздобје', 'ера', 'епоха',
    'место', 'локација', 'позиција', 'положба', 'област', 'регион', 'подрачје', 'територија', 'простор',
    'контекст', 'околност', 'ситуација', 'услови', 'фактори', 'параметри', 'критериуми', 'стандарди',
    'правила', 'прописи', 'закони', 'регулативи', 'норми', 'прописи', 'упатства', 'инструкции', 'протоколи',
    'документ', 'файл', 'извештај', 'анализа', 'студија', 'истражување', 'евалуација', 'ревизија', 'аудит',
    'преглед', 'синтеза', 'резюме', 'извод', 'заклучок', 'препорака', 'упатство', 'насока', 'линија',
    'пристап', 'методологија', 'техника', 'постапка', 'процедура', 'алгоритам', 'модел', 'шема', 'дијаграм',
    'табела', 'графикон', 'дијаграм', 'мапа', 'карта', 'план', 'схема', 'цртеж', 'илустрација', 'слика',
    'фотографија', 'видео', 'аудио', 'снимка', 'запис', 'архива', 'евиденција', 'регистар', 'база', 'датабаза',
    'информација', 'комуникација', 'интеракција', 'кооперација', 'колаборација', 'координација', 'синхронизација',
    'интеграција', 'хармонизација', 'унификација', 'стандардизација', 'оптимизација', 'автоматизација',
    'дигитализација', 'трансформација', 'модернизација', 'реформа', 'промена', 'транзиција', 'преод',
    'развој', 'напредок', 'раст', 'експанзија', 'проширување', 'зголемување', 'повеќање', 'намалување',
    'смалување', 'редукција', 'оптимизација', 'ефикасност', 'ефективност', 'продуктивност', 'перформанси',
    'резултати', 'остварувања', 'постигнувања', 'успеси', 'неуспеси', 'проблеми', 'пречки', 'изазови',
    'можности', 'шанси', 'прилики', 'предности', 'бенефити', 'користи', 'предности', 'недостатоци',
    'манки', 'ограничувања', 'бариери', 'пречки', 'тешкотии', 'компликации', 'проблеми', 'конфликти',
    'спорови', 'несогласувања', 'разлики', 'контрадикции', 'противоречности', 'неконзистентности',
    'недоследности', 'грешки', 'погрешки', 'неточности', 'непрецизности', 'нејаснотии', 'двосмислености',
    'нејаснотии', 'конфузии', 'недоумици', 'прашања', 'дилеми', 'дискусии', 'дебати', 'расправи',
    'конверзации', 'дијалози', 'комуникации', 'интеракции', 'релации', 'односи', 'врски', 'конекции',
    'мрежи', 'системи', 'структури', 'хиерархии', 'организации', 'институции', 'установи', 'агенции',
    'служби', 'оддели', 'сектори', 'одделенија', 'екипи', 'тимови', 'групи', 'колективи', 'заедници',
    'органи', 'тела', 'комисии', 'совeti', 'одбори', 'комитети', 'работни групи', 'форуми', 'платформи',
    'иницијативи', 'мрежи', 'коалиции', 'алијанси', 'партнерства', 'соработки', 'проекти', 'програми',
    'акции', 'кампањи', 'иницијативи', 'напори', 'активности', 'дејности', 'мерки', 'интервенции',
    'реформи', 'промени', 'трансформации', 'модернизации', 'иновации', 'развои', 'напори', 'настани',
    'активности', 'дејности', 'напори', 'настани', 'собранија', 'конференции', 'симпозиуми', 'семинари',
    'работни состаноци', 'дискусии', 'презентации', 'изложби', 'саеми', 'форуми', 'конгреси', 'собранија',
    'сесии', 'заседанија', 'состаноци', 'преговори', 'консултации', 'дијалози', 'разговори', 'комуникации',
    'интеракции', 'кореспонденции', 'дописувања', 'размени', 'комуникации', 'координации', 'соработки',
    'кооперации', 'партнерства', 'сојузи', 'алијанси', 'коалиции', 'федерации', 'конфедерации', 'унии',
    'асоцијации', 'организации', 'институции', 'установи', 'агенции', 'служби', 'оддели', 'сектори',
    'одделенија', 'екипи', 'тимови', 'групи', 'колективи', 'заедници', 'органи', 'тела', 'комисии',
    'совeti', 'одбори', 'комитети', 'работни групи', 'форуми', 'платформи', 'иницијативи', 'мрежи',
    'проекти', 'програми', 'акции', 'кампањи', 'напори', 'активности', 'дејности', 'мерки', 'интервенции',
    'реформи', 'промени', 'трансформации', 'модернизации', 'иновации', 'развои', 'настани', 'собранија',
    'конференции', 'симпозиуми', 'семинари', 'работни состаноци', 'дискусии', 'презентации', 'изложби',
    'саеми', 'форуми', 'конгреси', 'сесии', 'заседанија', 'состаноци', 'преговори', 'консултации',
    'дијалози', 'разговори', 'комуникации', 'интеракции', 'кореспонденции', 'дописувања', 'размени',
    'координации', 'соработки', 'кооперации', 'партнерства', 'сојузи', 'алијанси', 'коалиции', 'федерации',
    'конфедерации', 'унии', 'асоцијации',
    // Serbian
    'крај', 'додела', 'додела', 'почетак', 'састанак', 'догађај', 'сесија', 'одлука', 'процес',
    'ситуација', 'случај', 'питање', 'проблем', 'резултат', 'део', 'целина', 'систем', 'метод',
    'начин', 'процедура', 'фаза', 'развој', 'напредак', 'промена', 'тренд', 'динамика', 'перспектива',
    'будућност', 'прошлост', 'садашњост', 'циљ', 'задатак', 'функција', 'улога', 'одговорност',
    'обaveза', 'право', 'могућност', 'шанса', 'утицај', 'ефекат', 'реакција', 'одговор', 'коментар',
    'мишљење', 'став', 'гледиште', 'информација', 'податак', 'чињеница', 'детаљ', 'аспект', 'димензија',
    'елемент', 'компонента', 'питање', 'одговор', 'решење', 'закључак', 'препорука', 'сугестија', 'идеја',
    'предлог', 'план', 'пројекат', 'иницијатива', 'акција', 'дејство', 'мера', 'корак', 'фаза', 'период',
    'рок', 'термин', 'датум', 'време', 'дан', 'недеља', 'месец', 'година', 'период', 'раздобље', 'ера',
    'епоха', 'место', 'локација', 'позиција', 'положај', 'област', 'регион', 'подручје', 'територија',
    'простор', 'контекст', 'околност', 'услови', 'фактори', 'параметри', 'критеријуми', 'стандарди',
    'правила', 'прописи', 'закони', 'регулативе', 'норме', 'упутства', 'инструкције', 'протоколи',
    'документ', 'фајл', 'извештај', 'анализа', 'студија', 'истраживање', 'евалуација', 'ревизија', 'аудит',
    'преглед', 'синтеза', 'резиме', 'закључак', 'препорука', 'упутство', 'смер', 'линија', 'приступ',
    'методологија', 'техника', 'поступак', 'процедура', 'алгоритам', 'модел', 'шема', 'дијаграм', 'табела',
    'графикон', 'мапа', 'план', 'схема', 'цртеж', 'илустрација', 'слика', 'фотографија', 'видео', 'аудио',
    'снимак', 'запис', 'архива', 'евиденција', 'регистар', 'база', 'база података', 'информација',
    'комуникација', 'интеракција', 'кооперација', 'колаборација', 'координација', 'синхронизација',
    'интеграција', 'хармонизација', 'унификација', 'стандардизација', 'оптимизација', 'аутоматизација',
    'дигитализација', 'трансформација', 'модернизација', 'реформа', 'промена', 'транзиција', 'прелаз',
    'развој', 'напредак', 'раст', 'експанзија', 'проширење', 'повећање', 'смањење', 'редукција',
    'оптимизација', 'ефикасност', 'ефективност', 'продуктивност', 'перформансе', 'резултати',
    'остварења', 'постигнућа', 'успеси', 'неуспеси', 'проблеми', 'препреке', 'изазови', 'могућности',
    'шансе', 'прилике', 'предности', 'бенефити', 'користи', 'мане', 'ограничења', 'баријере',
    'препреке', 'тешкоће', 'компликације', 'конфликти', 'спорови', 'неслагања', 'разлике', 'контрадикције',
    'противоречности', 'неконзистентности', 'недоследности', 'грешке', 'нетачности', 'непрецизности',
    'нејасноће', 'двосмислености', 'конфузије', 'дилеме', 'дискусије', 'дебате', 'расправе', 'конверзације',
    'дијалози', 'комуникације', 'интеракције', 'релације', 'односи', 'везе', 'конекције', 'мреже', 'системи',
    'структуре', 'хијерархије', 'организације', 'институције', 'установе', 'агенције', 'службе', 'одсеци',
    'сектори', 'одјељења', 'тимови', 'групе', 'колективи', 'заједнице', 'органи', 'тијела', 'комисије',
    'савјети', 'одбори', 'комитети', 'радне групе', 'форуми', 'платформе', 'иницијативе', 'мреже',
    'пројекти', 'програми', 'акције', 'кампање', 'напори', 'активности', 'мјере', 'интервенције', 'реформе',
    'промјене', 'трансформације', 'модернизације', 'иновације', 'догађаји', 'конференције', 'симпозиуми',
    'семинари', 'радне састанци', 'дискусије', 'презентације', 'изложбе', 'сајмови', 'конгреси', 'сесије',
    'сједнице', 'састанци', 'преговори', 'консултације', 'дијалози', 'разговори', 'комуникације', 'интеракције',
    'кореспонденције', 'дописвања', 'размјене', 'координације', 'сарадње', 'кооперације', 'партнерства',
    'савези', 'алијансе', 'коалиције', 'федерације', 'конфедерације', 'уније', 'асоцијације'
]);

export function normalizeAndDeduplicateTags(tags: string[], lang: string): string[] {
    if (!tags || !tags.length) return [];

    // 1. Normalize all tags
    const normalized = tags
        .map(tag => normalizeEntityOrTag(tag, lang))
        .filter(Boolean);

    // 1.5. Filter out common non-entity words
    const filtered = normalized.filter(tag => {
        if (!tag) return false;
        const tagLower = tag.toLowerCase().trim();
        return !COMMON_NON_ENTITY_WORDS.has(tagLower);
    });

    // 2. Remove exact duplicates using a Set
    const uniqueTags = Array.from(new Set(filtered));

    // 3. Remove highly redundant tags (like substrings or parentheses explanations)
    // Sort by length ascending first so shorter, more concise tags are preferred and processed first
    const sorted = [...uniqueTags].sort((a, b) => a.length - b.length);
    const result: string[] = [];

    for (const tag of sorted) {
        const tagLower = tag.toLowerCase();
        const isRedundant = result.some(existing => {
            const existingLower = existing.toLowerCase();
            // If the tag is a substring of an already-added shorter tag, or vice versa
            return tagLower.includes(existingLower) || existingLower.includes(tagLower);
        });
        if (!isRedundant) {
            result.push(tag);
        }
    }

    // Return in original unique order or sorted order?
    // Let's filter the original unique array to preserve the relevance order but only keep the non-redundant ones
    return uniqueTags.filter(tag => result.includes(tag));
}
