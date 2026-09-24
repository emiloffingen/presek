import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../../lib/apiBase';
import { slugify } from '../../utils/textUtils';

const API_URL = apiBaseUrl();

export const GET: APIRoute = async () => {
    const SITE_URL = 'https://presek.mk';
    const clusterData: {id: string, title: string, updated: string | null}[] = [];

    try {
        let page = 0;
        let hasMore = true;
        while (hasMore && page < 10) {
            const res = await fetch(`${API_URL}/news?page_size=50&page=${page}`);
            if (res.ok) {
                const data = await res.json();
                if (data && Array.isArray(data.clusters)) {
                    const filtered = data.clusters.filter((c: any) =>
                        c.articles && c.articles.some((a: any) => a.country === 'MK')
                    );
                    clusterData.push(...filtered
                        .filter((c: any) => c.has_synthesis && (c.synthetic_headline || c.synthetic_standfirst))
                        .map((c: any) => ({
                            id: c.cluster_id,
                            title: c.synthetic_headline || c.title || '',
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
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
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
    <priority>0.6</priority>
  </url>`;
}).join('\n')}
</urlset>`;

    return new Response(sitemap, {
        headers: {
            'Content-Type': 'application/xml; charset=utf-8',
            'Cache-Control': 'public, max-age=3600',
        },
    });
};
