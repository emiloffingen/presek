import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../lib/apiBase';

const SITE_URL = (import.meta.env.PUBLIC_SITE_URL || 'https://presek.live').replace(/\/+$/, '');
const API_URL = apiBaseUrl();

export const GET: APIRoute = async () => {
	try {
		const controller = new AbortController();
		const timer = setTimeout(() => controller.abort(), 10000);
		const res = await fetch(`${API_URL}/news?lang=sr`, { signal: controller.signal });
		clearTimeout(timer);
		const data = res.ok ? await res.json() : null;
		const count = Array.isArray(data?.clusters) ? data.clusters.length : 0;
		const subtitle = count > 0
			? `${count} aktivnih klastera sa upoređenim izvorima`
			: 'Srpska platforma za poređenje vesti i izvora';

		const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#111827"/>
  <rect x="0" y="0" width="1200" height="14" fill="#b91c1c"/>
  <text x="90" y="130" font-family="Georgia, serif" font-size="34" font-weight="700" fill="#b91c1c" letter-spacing="3">PRESEK.rs</text>
  <text x="90" y="270" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f9fafb">vesti sa više</text>
  <text x="90" y="360" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f9fafb">konteksta i poređenja</text>
  <text x="90" y="470" font-family="Arial, sans-serif" font-size="34" fill="#d1d5db">${subtitle}</text>
  <text x="1110" y="560" font-family="Georgia, serif" font-size="46" font-weight="700" fill="#f9fafb" text-anchor="end">${SITE_URL.replace(/^https?:\/\//, '')}</text>
</svg>`;

		return new Response(svg, {
			headers: {
				'Content-Type': 'image/svg+xml; charset=utf-8',
				'Cache-Control': 'public, max-age=900',
			},
		});
	} catch {
		const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#111827"/>
  <rect x="0" y="0" width="1200" height="14" fill="#b91c1c"/>
  <text x="90" y="130" font-family="Georgia, serif" font-size="34" font-weight="700" fill="#b91c1c" letter-spacing="3">PRESEK.rs</text>
  <text x="90" y="270" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f9fafb">vesti sa više</text>
  <text x="90" y="360" font-family="Georgia, serif" font-size="88" font-weight="700" fill="#f9fafb">konteksta i poređenja</text>
  <text x="90" y="470" font-family="Arial, sans-serif" font-size="34" fill="#d1d5db">Srpska platforma za poređenje vesti i izvora</text>
</svg>`;
		return new Response(svg, {
			headers: {
				'Content-Type': 'image/svg+xml; charset=utf-8',
				'Cache-Control': 'public, max-age=900',
			},
		});
	}
};
