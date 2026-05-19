import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../lib/apiBase';

export const GET: APIRoute = async ({ request }) => {
    const url = new URL(request.url);
    const host = request.headers.get('host') || url.hostname;
    const isMk = host.includes('presek.mk');
    const SITE_URL = isMk ? 'https://presek.mk' : 'https://presek.live';
    const API_URL = apiBaseUrl();
    
    const clusterIds: string[] = [];

    try {
        let page = 0;
        let hasMore = true;
        while (hasMore && page < 10) {
            const res = await fetch(`${API_URL}/news?page_size=50&page=${page}`);
            if (res.ok) {
                const data = await res.json();
                if (data && Array.isArray(data.clusters)) {
                    // Filter clusters by country to ensure correct sitemap content per domain
                    const country = isMk ? 'MK' : 'RS';
                    const filtered = data.clusters.filter((c: any) => 
                        c.articles && c.articles.some((a: any) => a.country === country)
                    );
                    clusterIds.push(...filtered.map((c: any) => c.cluster_id));
                    hasMore = data.has_more;
                } else {
                    hasMore = false;
                }
            } else {
                hasMore = false;
            }
            page++;
        }
    } catch (e) {
        console.error("Sitemap fetch error:", e);
    }

    const staticPages = ['', '/about', '/archive', '/izvori', '/pulse', '/editorial', '/privacy', '/terms'];
    const now = new Date().toISOString();

    const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${staticPages.map(page => `  <url>
    <loc>${SITE_URL}${page}</loc>
    <lastmod>${now}</lastmod>
    <changefreq>${page === '' ? 'always' : 'daily'}</changefreq>
    <priority>${page === '' ? '1.0' : '0.8'}</priority>
  </url>`).join('\n')}
${clusterIds.map(id => `  <url>
    <loc>${SITE_URL}/cluster/${id}</loc>
    <lastmod>${now}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>`).join('\n')}
</urlset>`;

    return new Response(sitemap, {
        headers: {
            'Content-Type': 'application/xml; charset=utf-8',
            'Cache-Control': 'public, max-age=3600, s-maxage=14400, stale-while-revalidate=7200',
        },
    });
};
