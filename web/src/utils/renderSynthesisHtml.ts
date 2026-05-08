/**
 * Shared utility for rendering synthesis HTML from markdown-like text.
 * Used by multiple cluster components to avoid code duplication.
 */

import { cleanAndDecode, parseFootnotes } from './textUtils';
import { sanitizeHtml } from '../lib/sanitize';

/**
 * Render synthesis text with markdown formatting and citation handling.
 * 
 * Features:
 * - Strips AI placeholders like [ПРЕТХОДЕН КОНТЕКСТ]
 * - Converts **text** to <strong>text</strong>
 * - Converts *text* to <em>text</em>
 * - Converts (Извор: Name) or (Name) to <span class="citation-badge">Name</span>
 * - Handles footnotes if hasCitationSources is true
 * - Removes [1], [2] etc. citation markers if !hasCitationSources
 * 
 * @param text - The raw synthesis text
 * @param hasCitationSources - Whether to parse footnotes
 * @returns Sanitized HTML string
 */
export function renderSynthesisHtml(text: string, hasCitationSources: boolean = false): string {
	if (!text) return '';
	let clean = cleanAndDecode(text);
	if (!clean) return '';

	// 1. Strip residual AI placeholders
	clean = clean.replace(/\[ПРЕТХОДЕН КОНТЕКСТ\]/gi, '');

	// 2. Handle Markdown Bold: **text** -> <strong>text</strong>
	clean = clean.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

	// 3. Handle Markdown Italics: *text* -> <em>text</em>
	clean = clean.replace(/\*(.*?)\*/g, '<em>$1</em>');

	// 4. Handle Parenthetical Citations: (Извор: Име) or (Име) -> <span class="citation-badge">Име</span>
	// We target common news source patterns (capitalised, 1-3 words)
	clean = clean.replace(/\((?:Извор:\s*)?([A-ZА-Ш][a-zа-ш0-9\s\.]{2,20})\)/g, (match: string, name: string) => {
		return `<span class="citation-badge">${name.trim()}</span>`;
	});

	if (hasCitationSources) return sanitizeHtml(parseFootnotes(clean));
	return sanitizeHtml(clean.replace(/\[(\d+)\]/g, '').replace(/\s{2,}/g, ' ').trim());
}
