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
        const idBadge = id ? `<a href="/cluster/${id}" class="briefing-inline-badge">Отвори кластер</a>` : '';
        return `<h3 class="briefing-item-title">${num || ''}${title}${idBadge}</h3>`;
    });

    // 2. Handle Pull-quotes (Markdown blockquotes)
    html = html.replace(/^>\s+(.+)$/gm, '<blockquote class="briefing-pull-quote">$1</blockquote>');

    // 3. Handle Lists (e.g., - Item, * Item, • Item)
    html = html.replace(/^[-*•]\s+(.+)$/gm, '<li class="briefing-li">$1</li>');
    
    // Wrap adjacent <li> tags in <ul>
    html = html.replace(/(<li class="briefing-li">.*?<\/li>\n?)+/g, (match) => {
        return `<ul class="briefing-ul">\n${match}</ul>\n`;
    });

    // 4. Handle Paragraphs
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
        const trimmed = block.trim();
        if (!trimmed) return "";
        if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<li') || trimmed.startsWith('<blockquote')) {
            return trimmed;
        }
        // Bold the first few words if it looks like a lead paragraph
        if (trimmed.length > 100 && !trimmed.includes('<')) {
            // Apply drop-cap to the macro overview paragraphs
             return `<p class="briefing-paragraph drop-cap">${trimmed}</p>`;
        }
        return `<p class="briefing-paragraph">${trimmed}</p>`;
    }).join('\n');

    // 4. Handle Bold and Italics
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 5. Handle Brackets/Citations [1], [2]
    html = html.replace(/\[(\d+)\]/g, '<sup class="text-nyt-accent font-black ml-0.5">$1</sup>');

    // 6. Final sanitization
    return sanitizeHtml(html);
}
