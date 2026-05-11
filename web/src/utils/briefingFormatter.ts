import { sanitizeHtml } from '../lib/sanitize';

/**
 * A specialized formatter for the Daily Briefing markdown content.
 * Converts markdown-like structures into styled HTML for the Briefing layout.
 */
export function formatBriefing(markdown: string): string {
    if (!markdown) return "";

    let html = markdown.trim();

    // 1. Handle Headings (e.g., # Header, ## Subheader, ### Title)
    html = html.replace(/^#\s+(.+)$/gm, ''); // Main title is handled by BriefingHeader
    html = html.replace(/^##\s+(.+)$/gm, '<h2 class="briefing-section-title">$1</h2>');
    html = html.replace(/^###\s+(\d+\.\s+)?(.+?)(\s+\[\[(.+?)\]\])?$/gm, (match, num, title, idGroup, id) => {
        const idBadge = id ? `<a href="/cluster/${id}" class="briefing-inline-badge">Otvorite klaster</a>` : '';
        return `<h3 class="briefing-item-title">${num || ''}${title}${idBadge}</h3>`;
    });

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
    let hasAppliedDropCap = false;
    html = blocks.map(block => {
        const trimmed = block.trim();
        if (!trimmed) return "";
        if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<li') || trimmed.startsWith('<blockquote')) {
            return trimmed;
        }
        
        // Apply drop-cap only to the very first regular paragraph
        if (!hasAppliedDropCap && trimmed.length > 100 && !trimmed.includes('<')) {
             hasAppliedDropCap = true;
             return `<p class="briefing-paragraph drop-cap">${trimmed}</p>`;
        }
        return `<p class="briefing-paragraph">${trimmed}</p>`;
    }).join('\n');

    // 4. Handle Bold and Italics
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 5. Handle Brackets/Citations [1], [2]
    html = html.replace(/\[(\d+)\]/g, '<sup class="text-nyt-accent font-black ml-0.5">$1</sup>');

    // 6. Handle Inline Cluster Links [[id]]
    html = html.replace(/\[\[([a-f0-9\-]+)\]\]/g, (match, id) => {
        return `<a href="/cluster/${id}" class="briefing-inline-link" title="Pogledajte ovaj klaster">
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="inline-block"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
        </a>`;
    });

    // 7. Final sanitization
    return sanitizeHtml(html);
}
