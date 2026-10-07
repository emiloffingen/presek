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

export const GET: APIRoute = async () => {
    const SITE_URL = 'https://presek.mk';
    const API_URL = apiBaseUrl();
    
    const clusterData: {id: string, title: string, image: string | null, updated: string | null}[] = [];

    // Single lightweight query (backend-cached 1h). Never fan out /news here:
    // each /news scrape runs a 500-candidate pool + metadata/synthesis fan-out
    // and could block SSR for minutes under crawler traffic.
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 15000);
        const res = await fetch(`${API_URL}/sitemap-clusters?lang=mk&limit=1000`, { signal: controller.signal });
        clearTimeout(timer);
        if (res.ok) {
            const data = await res.json();
            if (data && Array.isArray(data.clusters)) {
                clusterData.push(...data.clusters
                    .filter((c: any) => c.cluster_id)
                    .map((c: any) => ({
                        id: c.cluster_id,
                        title: c.title || '',
                        image: c.image || null,
                        updated: c.updated || null
                    })));
            }
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
