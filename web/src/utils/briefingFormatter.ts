import { sanitizeHtml } from '../lib/sanitize.ts';
import { localePath } from '../lib/localePaths.ts';
import { normalizeBriefingMarkdown, normalizeBriefingText } from './briefingCopy.ts';
import { briefing } from '../i18n/namespaces/briefing.ts';

type BriefingLang = 'sr' | 'mk';

function briefingT(lang: BriefingLang, key: string): string {
  const dict = briefing[lang] as Record<string, string>;
  return dict[key] ?? key;
}

function stripDecorativePrefix(text: string): string {
    return text
        .replace(/^\s*(?:[\dIVXLCDM]+[.)]\s*)+/i, '')
        .replace(/^\s*(?:тема|теза|фокус|analiza|tema|teza|fokus)\s*[:\-]\s*/i, '')
        .trim();
}

export type BriefingSection = {
    id: string;
    title: string;
    index: number;
};

export function extractBriefingSections(markdown: string): BriefingSection[] {
    if (!markdown) return [];

    const sections: BriefingSection[] = [];
    let sectionIndex = 0;

    markdown.replace(/^##\s+(.+)$/gm, (_match, rawTitle) => {
        sectionIndex += 1;
        const title = normalizeBriefingText(stripDecorativePrefix(rawTitle));
        sections.push({
            id: `section-${String(sectionIndex).padStart(2, '0')}`,
            title,
            index: sectionIndex,
        });
        return '';
    });

    return sections;
}

/**
 * A specialized formatter for the Daily Briefing markdown content.
 * Converts markdown-like structures into styled HTML for the Briefing layout.
 */
export function formatBriefing(markdown: string, lang: BriefingLang = 'mk', hostname?: string | null): string {
    if (!markdown) return "";
    const locale = lang === 'mk' ? 'mk' : 'sr';
    const l = (path: string) => localePath(path, locale, hostname);
    const topicBadge = briefingT(locale, 'briefing.topic_badge');
    const clusterLinkTitle = briefingT(locale, 'briefing.cluster_link_title');

    let html = normalizeBriefingMarkdown(markdown, lang).trim();
    let sectionIndex = 0;

    // 1. Handle Headings (e.g., # Header, ## Subheader, ### Title)
    html = html.replace(/^#\s+(.+)$/gm, ''); // Main title is handled by BriefingHeader
    html = html.replace(/^##\s+(.+)$/gm, (_match, rawTitle) => {
        sectionIndex += 1;
        const title = normalizeBriefingText(stripDecorativePrefix(rawTitle), lang);
        const sectionId = `section-${String(sectionIndex).padStart(2, '0')}`;
        return `<h2 id="${sectionId}" class="briefing-section-title"><span class="briefing-section-index">${String(sectionIndex).padStart(2, '0')}</span><span class="briefing-section-heading">${title}</span></h2>`;
    });
    html = html.replace(/^###\s+(\d+\.\s+)?(.+?)(\s+\[\[(.+?)\]\])?$/gm, (match, num, title, idGroup, id) => {
        const idBadge = id ? `<a href="${l('/cluster/')}${id}" class="briefing-inline-badge">${topicBadge}</a>` : '';
        const cleanTitle = normalizeBriefingText(stripDecorativePrefix(`${num || ''}${title}`), lang);
        return `<h3 class="briefing-item-title">${cleanTitle}${idBadge}</h3>`;
    });
    html = html.replace(/^\*\*(.+?)\*\*\s*$/gm, (_match, rawContent) => {
        const clusterMatch = rawContent.match(/\s*\[\[([a-f0-9-]+)\]\]\s*$/i);
        const clusterId = clusterMatch?.[1];
        const titlePart = clusterId
            ? rawContent.replace(/\s*\[\[[a-f0-9-]+\]\]\s*$/i, '').trim()
            : rawContent.trim();
        const title = normalizeBriefingText(stripDecorativePrefix(titlePart), lang);
        const idBadge = clusterId
            ? `<a href="${l('/cluster/')}${clusterId}" class="briefing-inline-badge">${topicBadge}</a>`
            : '';
        return `<h3 class="briefing-item-title">${title}${idBadge}</h3>`;
    });

    // Ensure headings start their own paragraph blocks.
    html = html.replace(/(<\/h[23]>)\n(?!\n)/g, '$1\n\n');

    // 2. Handle Pull-quotes (Markdown blockquotes)
    html = html.replace(/^>\s+(.+)$/gm, '<blockquote class="briefing-pull-quote">$1</blockquote>');

    // 3. Handle Lists (e.g., - Item, * Item, • Item)
    html = html.replace(/^[-*\u2022]\s+(.+)$/gm, '<li class="briefing-li">$1</li>');

    // Wrap adjacent <li> tags in <ul>
    html = html.replace(/(<li class="briefing-li">.*?<\/li>\n?)+/g, (match) => {
        return `<ul class="briefing-ul">\n${match}</ul>\n`;
    });

    // 4. Handle Paragraphs
    const blocks = html.split(/\n\n+/);
    let paragraphIndex = 0;
    html = blocks.map(block => {
        const trimmed = block.trim();
        if (!trimmed) return "";
        if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<li') || trimmed.startsWith('<blockquote')) {
            return trimmed;
        }

        paragraphIndex += 1;
        if (paragraphIndex === 1 && trimmed.length > 80 && !trimmed.includes('<')) {
             return `<p class="briefing-paragraph briefing-lede drop-cap">${trimmed}</p>`;
        }
        return `<p class="briefing-paragraph">${trimmed}</p>`;
    }).join('\n');

    // 4. Handle Bold and Italics
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 5. Handle Brackets/Citations [1], [2]
    html = html.replace(/\[(\d+)\]/g, '<sup class="text-presek-mark font-black ml-0.5">$1</sup>');

    // 6. Handle Inline Cluster Links [[id]]
    html = html.replace(/\[\[([a-f0-9\-]+)\]\]/g, (match, id) => {
        return `<a href="${l('/cluster/')}${id}" class="briefing-inline-link" title="${clusterLinkTitle}">
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="inline-block"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
        </a>`;
    });

    // 7. Final sanitization
    return sanitizeHtml(html);
}
