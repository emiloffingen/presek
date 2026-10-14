import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../lib/apiBase';

const SITE_URL = (import.meta.env.PUBLIC_SITE_URL || 'https://presek.mk').replace(/\/+$/, '');
const API_URL = apiBaseUrl();

export const GET: APIRoute = async () => {
	try {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), 10000);
		const res = await fetch(`${API_URL}/news?lang=mk`, { signal: controller.signal });
		clearTimeout(timer);
		const data = res.ok ? await res.json() : null;
		const count = Array.isArray(data?.clusters) ? data.clusters.length : 0;
		const subtitle = count > 0
			? `${count} активни кластери со споредени извори`
			: 'Македонска платформа за споредба на вести и извори';

		const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#14201e"/>
  <rect x="0" y="0" width="1200" height="14" fill="#4fb8a5"/>
  <text x="90" y="130" font-family="Georgia, serif" font-size="34" font-weight="700" fill="#4fb8a5" letter-spacing="3">${SITE_URL.replace(/^https?:\/\//, '').replace(/\/.*$/, '').toUpperCase()}</text>
  <text x="90" y="270" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f5f3ec">вести со повеќе</text>
  <text x="90" y="360" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f5f3ec">контекст и споредба</text>
  <text x="90" y="470" font-family="Arial, sans-serif" font-size="34" fill="#c4d0cc">${subtitle}</text>
  <text x="1110" y="560" font-family="Georgia, serif" font-size="46" font-weight="700" fill="#f5f3ec" text-anchor="end">${SITE_URL.replace(/^https?:\/\//, '')}</text>
</svg>`;

		return new Response(svg, {
			headers: {
				'Content-Type': 'image/svg+xml; charset=utf-8',
				'Cache-Control': 'public, max-age=900',
			},
		});
	} catch {
		const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#14201e"/>
  <rect x="0" y="0" width="1200" height="14" fill="#4fb8a5"/>
  <text x="90" y="130" font-family="Georgia, serif" font-size="34" font-weight="700" fill="#4fb8a5" letter-spacing="3">${SITE_URL.replace(/^https?:\/\//, '').replace(/\/.*$/, '').toUpperCase()}</text>
  <text x="90" y="270" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f5f3ec">вести со повеќе</text>
  <text x="90" y="360" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f5f3ec">контекст и споредба</text>
  <text x="90" y="470" font-family="Arial, sans-serif" font-size="34" fill="#c4d0cc">Македонска платформа за споредба на вести и извори</text>
</svg>`;
		return new Response(svg, {
			headers: {
				'Content-Type': 'image/svg+xml; charset=utf-8',
				'Cache-Control': 'public, max-age=900',
			},
		});
	}
};
