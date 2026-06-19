import { scrubBriefingBoilerplate } from './briefingCopy.ts';

export { scrubBriefingBoilerplate as scrubSynthesisBoilerplate } from './briefingCopy.ts';

const META_PARAGRAPH_PATTERNS: Record<'mk' | 'sr', RegExp[]> = {
    mk: [
        /^Повеќето (медиумски )?извори/i,
        /^Повеќето медиумски извештаи/i,
        /^СмартПорталот е единствениот/i,
        /^Останува непотврдено/i,
        /^За .+, медиумите нагласуваат/i,
    ],
    sr: [
        /^Većina (medijskih )?izvora/i,
        /^Većina medija/i,
        /^SmartPortal je jedini/i,
        /^Ostaje nepotvrđeno/i,
        /^Za .+, mediji naglašavaju/i,
    ],
};

export function isSynthesisMetaParagraph(text: string, lang = 'sr'): boolean {
    const locale: 'mk' | 'sr' = lang === 'mk' ? 'mk' : 'sr';
    const trimmed = String(text || '').trim();
    if (!trimmed) return false;
    return META_PARAGRAPH_PATTERNS[locale].some((pattern) => pattern.test(trimmed));
}

export function stripBareUrls(text: string): string {
    return String(text || '')
        .replace(/https?:\/\/(?:www\.)?presek\.(?:mk|live)\/cluster\/[a-f0-9-]+(?:-[a-z0-9-]+)?\/?/gi, '')
        .replace(/https?:\/\/(?:www\.)?presek\.(?:mk|live)\/[^\s]+/gi, '')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

export function prepareSynthesisParagraph(text: string, lang = 'sr'): string {
    return scrubBriefingBoilerplate(stripBareUrls(text), lang);
}

export function splitNarrativeParagraphs(text: string, lang = 'sr'): {
    story: string[];
    meta: string[];
} {
    const paragraphs = String(text || '')
        .split('\n')
        .map((paragraph) => paragraph.trim())
        .filter(Boolean);

    const story: string[] = [];
    const meta: string[] = [];

    for (const paragraph of paragraphs) {
        if (isSynthesisMetaParagraph(paragraph, lang)) {
            meta.push(paragraph);
        } else {
            story.push(paragraph);
        }
    }

    return { story, meta };
}
