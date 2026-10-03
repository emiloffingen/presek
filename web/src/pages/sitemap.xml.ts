import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../lib/apiBase';
import { slugify } from '../utils/textUtils';

function escapeXml(value: string = '') {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;');
}

export const GET: APIRoute = async ({ request }) => {
    const url = new URL(request.url);
    const host = request.headers.get('host') || url.hostname;
    const isMk = host.includes('presek.mk');
            const SITE_URL = 'https://presek.mk';
    const API_URL = apiBaseUrl();
    
    const clusterData: {id: string, title: string, image: string | null, updated: string | null}[] = [];

    try {
        let page = 0;
        let hasMore = true;
        while (hasMore && page < 10) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 10000);
            const res = await fetch(`${API_URL}/news?page_size=50&page=${page}`, { signal: controller.signal });
            clearTimeout(timer);
            if (res.ok) {
                const data = await res.json();
                if (data && Array.isArray(data.clusters)) {
                    // Filter clusters by country to ensure correct sitemap content per domain
                    const country = isMk ? 'MK' : 'RS';
                    const filtered = data.clusters.filter((c: any) => 
                        c.articles && c.articles.some((a: any) => a.country === country)
                    );
                    clusterData.push(...filtered
                        .filter((c: any) => c.has_synthesis && (c.synthetic_headline || c.synthetic_standfirst))
                        .map((c: any) => ({
                            id: c.cluster_id,
                            title: c.synthetic_headline || c.title || '',
                            image: c.representative_image || null,
                            updated: c.synthesis_updated_at || c.articles?.[0]?.created_at || null
                        })));
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

    const staticPages = ['', '/about', '/archive', '/izvori', '/editorial', '/privacy', '/terms', '/methodology', '/contact', '/cookies'];
    const now = new Date().toISOString();

    const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
${staticPages.map(page => `  <url>
    <loc>${SITE_URL}${page}</loc>
    <lastmod>${now}</lastmod>
    <changefreq>${page === '' ? 'always' : 'daily'}</changefreq>
    <priority>${page === '' ? '1.0' : '0.8'}</priority>
  </url>`).join('\n')}
${clusterData.map(cluster => {
    const clusterSlug = slugify(cluster.title);
    const path = clusterSlug ? `${cluster.id}-${clusterSlug}` : cluster.id;
    return `  <url>
    <loc>${SITE_URL}/cluster/${path}</loc>
    <lastmod>${cluster.updated ? new Date(cluster.updated).toISOString() : now}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>${cluster.image ? `
    <image:image>
      <image:loc>${escapeXml(cluster.image)}</image:loc>
      <image:title>${escapeXml(cluster.title || 'Presek News')}</image:title>
    </image:image>` : ''}
  </url>`;
}).join('\n')}
</urlset>`;

    return new Response(sitemap, {
        headers: {
            'Content-Type': 'application/xml; charset=utf-8',
            'Cache-Control': 'public, max-age=3600, s-maxage=14400, stale-while-revalidate=7200',
        },
    });
};
