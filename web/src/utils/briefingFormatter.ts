import { sanitizeHtml } from '../lib/sanitize';

/**
 * A specialized formatter for the Daily Briefing markdown content.
 * Converts markdown-like structures into styled HTML for the Briefing layout.
 */
export function formatBriefing(markdown: string): string {
    if (!markdown) return "";

    let html = markdown.trim();

    // 1. Handle Headings (e.g., # Header, ## Subheader, ### Title)
    // We convert ### into briefing-item-title and others into briefing-section-title
    html = html.replace(/^#\s+(.+)$/gm, ''); // Main title is handled by BriefingHeader
    html = html.replace(/^##\s+(.+)$/gm, '<h2 class="briefing-section-title">$1</h2>');
    html = html.replace(/^###\s+(\d+\.\s+)?(.+?)(\s+\[\[(.+?)\]\])?$/gm, (match, num, title, idGroup, id) => {
        const idBadge = id ? `<a href="/cluster/${id}" class="briefing-inline-badge">Отвори</a>` : '';
        return `<h3 class="briefing-item-title">${num || ''}${title}${idBadge}</h3>`;
    });

    // 2. Handle Lists (e.g., - Item, * Item, • Item)
    // We group them into <ul>
    html = html.replace(/^[-*•]\s+(.+)$/gm, '<li class="briefing-li">$1</li>');
    
    // Wrap adjacent <li> tags in <ul>
    // Using a more robust replacement for adjacent li's
    html = html.replace(/(<li class="briefing-li">.*?<\/li>\n?)+/g, (match) => {
        return `<ul class="briefing-ul">\n${match}</ul>\n`;
    });

    // 3. Handle Paragraphs
    // Filter out blocks that are already HTML tags we've added
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
        const trimmed = block.trim();
        if (!trimmed) return "";
        // If it starts with an HTML tag we just added, leave it
        if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<li')) {
            return trimmed;
        }
        // Apply drop-cap to the very first long paragraph or paragraphs starting with "Дневен"
        if (trimmed.length > 60 && !trimmed.startsWith('**') && !trimmed.startsWith('###')) {
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
