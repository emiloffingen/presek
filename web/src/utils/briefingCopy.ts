type MaybeText = string | null | undefined;

const SERBIAN_REPLACEMENTS: Array<[RegExp, string]> = [
    [/\bizgorjele\b/gi, 'izgorele'],
    [/\bsublimat\b/gi, 'pregled'],
    [/\bnarativa\b/gi, 'narativ'],
    [/\bnarative dodatno\b/gi, 'narativ dodatno'],
    [/\bPratiti da li će se narativ dodatno potvrditi\b/gi, 'Pratiti da li će tema biti potvrđena'],
    [/\bPratiti da li će se narativ potvrditi\b/gi, 'Pratiti da li će tema biti potvrđena'],
    [/\bOtvoreno je da li će detalji\b/gi, 'Ostaje otvoreno da li će detalji'],
    [/\bPotvrđen razvoj sa visokim medijskim konsenzusom od\b/gi, 'Tema je potvrđena u'],
    [/\bbriljantnom osobom i poli\./gi, 'briljantnom osobom i političarem.'],
    [/\bCelosno\b/g, 'Celo'],
    [/\bcelosno\b/g, 'celo'],
];

const MACEDONIAN_REPLACEMENTS: Array<[RegExp, string]> = [
    [/\bсублимат\b/gi, 'преглед'],
];

const BOILERPLATE_PATTERNS: Record<string, RegExp[]> = {
    mk: [
        /,?\s*со ограничено јавно значење\.?/gi,
        /,?\s*со ограничено јавно значење на спортскиот контекст\.?/gi,
        /\s*Јавното значење на овој настан е ограничено[^.]*\./gi,
        /\s*Настанот е потврден од повеќе извори и претставува значајна[^.]*\./gi,
        /\s*Прекинот е потврден од (?:два извори|повеќе извори) и претставува редовна техничка интервенција\.?/gi,
    ],
    sr: [
        /,?\s*sa ograničenim javnim značajem\.?/gi,
        /,?\s*sa ograničenim javnim značajem u sportskom kontekstu\.?/gi,
        /\s*Javni značaj ovog događaja je ograničen[^.]*\./gi,
        /\s*Događaj je potvrđen iz više izvora i predstavlja značajnu[^.]*\./gi,
    ],
};

export function scrubBriefingBoilerplate(text: MaybeText, lang = 'mk'): string {
    if (!text) return '';

    const locale = lang === 'mk' ? 'mk' : 'sr';
    let cleaned = text;
    for (const pattern of BOILERPLATE_PATTERNS[locale]) {
        cleaned = cleaned.replace(pattern, '');
    }

    return cleaned
        .replace(/([.!?])\s*([.!?])+/g, '$1')
        .replace(/\s+([,.;:!?])/g, '$1')
        .replace(/[^\S\n]{2,}/g, ' ')
        .trim();
}

export function simplifyBriefingBullet(text: MaybeText, lang = 'mk'): string {
    const cleaned = scrubBriefingBoilerplate(normalizeBriefingText(text, lang), lang);
    if (!cleaned) return '';

    if (lang === 'mk') {
        const match = cleaned.match(/^За (.+?), медиумите нагласуваат на (.+)$/i);
        if (match) return `${match[1]}: ${match[2].replace(/\.$/, '')}.`;
    } else {
        const match = cleaned.match(/^Za (.+?), mediji naglašavaju (.+)$/i);
        if (match) return `${match[1]}: ${match[2].replace(/\.$/, '')}.`;
    }

    return cleaned;
}

export function normalizeBriefingText(text: MaybeText, lang = 'mk'): string {
    if (!text) return '';

    const replacements = lang === 'mk' ? MACEDONIAN_REPLACEMENTS : SERBIAN_REPLACEMENTS;
    let normalized = text;

    for (const [pattern, replacement] of replacements) {
        normalized = normalized.replace(pattern, replacement);
    }

    return normalized
        .replace(/\s+([,.;:!?])/g, '$1')
        .replace(/[^\S\n]{2,}/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

export function normalizeBriefingMarkdown(markdown: MaybeText, lang = 'mk'): string {
    if (!markdown) return '';
    return markdown
        .replace(/https?:\/\/(?:www\.)?presek\.mk\/cluster\/([a-f0-9-]+)\/?/gi, '[[$1]]')
        .split('\n')
        .map((line) => scrubBriefingBoilerplate(normalizeBriefingText(line, lang), lang))
        .join('\n');
}

export function normalizeBriefingPayload<T>(value: T, lang = 'mk'): T {
    if (typeof value === 'string') {
        return normalizeBriefingText(value, lang) as T;
    }

    if (Array.isArray(value)) {
        return value.map((item) => normalizeBriefingPayload(item, lang)) as T;
    }

    if (value && typeof value === 'object') {
        const output: Record<string, unknown> = {};
        for (const [key, item] of Object.entries(value)) {
            if (key === 'content' && typeof item === 'string') {
                output[key] = normalizeBriefingMarkdown(item, lang);
            } else {
                output[key] = normalizeBriefingPayload(item, lang);
            }
        }
        return output as T;
    }

    return value;
}
