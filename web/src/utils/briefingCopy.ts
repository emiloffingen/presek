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

export function normalizeBriefingText(text: MaybeText, lang = 'sr'): string {
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

export function normalizeBriefingMarkdown(markdown: MaybeText, lang = 'sr'): string {
    if (!markdown) return '';
    return markdown
        .split('\n')
        .map((line) => normalizeBriefingText(line, lang))
        .join('\n');
}

export function normalizeBriefingPayload<T>(value: T, lang = 'sr'): T {
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
