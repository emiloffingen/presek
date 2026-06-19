/**
 * Shared utility for rendering synthesis HTML from markdown-like text.
 * Used by multiple cluster components to avoid code duplication.
 */

import { cleanAndDecode, stripCitationMarkers } from './textUtils.ts';
import { stripBareUrls } from './synthesisCopy.ts';
import { sanitizeHtml } from '../lib/sanitize.ts';

/**
 * Render synthesis text with markdown formatting and citation handling.
 *
 * Features:
 * - Strips AI placeholders like [PRETHODEN kontekst]
 * - Converts **text** to <strong>text</strong>
 * - Converts *text* to <em>text</em>
 * - Converts (izvor: Name) or (Name) to <span class="citation-badge">Name</span>
 * - Strips numeric citation markers like [1], [2] from prose
 *
 * @param text - The raw synthesis text
 * @returns Sanitized HTML string
 */
export function renderSynthesisHtml(text: string): string {
	if (!text) return '';
	let clean = stripBareUrls(cleanAndDecode(text));
	if (!clean) return '';

	// 1. Strip residual AI placeholders
	clean = clean.replace(/\[PRETHODEN kontekst\]/gi, '');

	// 2. Handle Markdown Bold: **text** -> <strong>text</strong>
	clean = clean.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

	// 3. Handle Markdown Italics: *text* -> <em>text</em>
	clean = clean.replace(/\*(.*?)\*/g, '<em>$1</em>');

	// 4. Handle Parenthetical Citations: (izvor: Ime) or (Ime) -> <span class="citation-badge">Ime</span>
	// We target common news source patterns (capitalised, 1-3 words)
	clean = clean.replace(/\((?:izvor:\s*)?([A-ZA-S][a-za-s0-9\s\.]{2,20})\)/g, (_match: string, name: string) => {
		return `<span class="citation-badge">${name.trim()}</span>`;
	});

	return sanitizeHtml(stripCitationMarkers(clean));
}
