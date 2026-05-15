import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../../../lib/apiBase';

const API_URL = apiBaseUrl();

function escapeXml(value: string) {
	return String(value || '')
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function splitHeadline(text: string) {
	const clean = String(text || '').trim();
	if (clean.length <= 52) {
		return [clean, ''];
	}
	const words = clean.split(/\s+/);
	const lines = ['', ''];
	for (const word of words) {
		const target = lines[0].length <= lines[1].length ? 0 : 1;
		const next = `${lines[target]} ${word}`.trim();
		if (next.length <= 58 || !lines[target]) {
			lines[target] = next;
		} else if (!lines[1]) {
			lines[1] = word;
		} else {
			lines[1] = `${lines[1]} ${word}`.trim();
		}
	}
	if (lines[1].length > 66) {
		lines[1] = `${lines[1].slice(0, 63).trimEnd()}...`;
	}
	return lines;
}

export const GET: APIRoute = async ({ params }) => {
	const clusterId = String(params.id || '').trim();
	if (!clusterId) {
		return new Response('Not found', { status: 404 });
	}

	try {
		const res = await fetch(`${API_URL}/cluster/${clusterId}`);
		if (!res.ok) {
			return new Response('Not found', { status: 404 });
		}

		const data = await res.json();
		const cluster = data?.data;
		const lead = cluster?.articles?.[0];
		const title = escapeXml(lead?.title || 'Пресек анализа');
		const description = escapeXml(
			String(lead?.description || cluster?.summary || '')
				.replace(/\s+/g, ' ')
				.trim()
				.slice(0, 150)
		);
		const sourceCount = Number(cluster?.articles?.length || 0);
		const category = escapeXml(lead?.category || 'вести');
		const [line1, line2] = splitHeadline(title);

		const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#0f172a"/>
  <rect x="0" y="0" width="1200" height="16" fill="#b91c1c"/>
  <text x="84" y="112" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#fecaca" letter-spacing="3">${category}</text>
  <text x="84" y="210" font-family="Georgia, serif" font-size="58" font-weight="700" fill="#f8fafc">${escapeXml(line1)}</text>
  <text x="84" y="286" font-family="Georgia, serif" font-size="58" font-weight="700" fill="#f8fafc">${escapeXml(line2)}</text>
  <text x="84" y="400" font-family="Arial, sans-serif" font-size="30" fill="#cbd5e1">${description}</text>
  <text x="84" y="532" font-family="Arial, sans-serif" font-size="28" fill="#94a3b8">${sourceCount} ${sourceCount === 1 ? 'извор' : 'извори'} во споредба</text>

  <text x="1116" y="556" font-family="Georgia, serif" font-size="46" font-weight="700" fill="#f8fafc" text-anchor="end">PRESEK.mk</text>
</svg>`;

		return new Response(svg, {
			headers: {
				'Content-Type': 'image/svg+xml; charset=utf-8',
				'Cache-Control': 'public, max-age=900',
			},
		});
	} catch {
		return new Response('Not found', { status: 404 });
	}
};
