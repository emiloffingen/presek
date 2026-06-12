import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../../lib/apiBase';

const SITE_URL = (import.meta.env.PUBLIC_SITE_URL || 'https://presek.live').replace(/\/+$/, '');
const API_URL = apiBaseUrl();

function escapeXml(str: string): string {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&apos;');
}

function formatDate(dateString: string | undefined): string {
    if (!dateString) return new Date().toUTCString();
    const date = new Date(dateString);
    return date.toUTCString();
}

export const GET: APIRoute = async () => {
    const clusters: any[] = [];
    const now = new Date().toUTCString();

    try {
        // Fetch Macedonian news
        const res = await fetch(`${API_URL}/news?page_size=50&page=0&lang=mk`);
        if (res.ok) {
            const data = await res.json();
            if (data && Array.isArray(data.clusters)) {
                clusters.push(...data.clusters);
            }
        }
    } catch (e) {
        console.error("RSS fetch error:", e);
    }

    const siteUrl = SITE_URL.replace('presek.live', 'presek.mk');

    // One RSS item per cluster (not per source article).
    const items = clusters
        .filter(c => c.articles && c.articles.length > 0)
        .map(cluster => {
            const article = cluster.articles[0];
            const title = cluster.synthetic_headline || cluster.title || article.title || 'Untitled';
            const description = cluster.synthetic_standfirst || article.description || cluster.summary || '';
            const link = `${siteUrl}/cluster/${cluster.cluster_id}`;
            const pubDate = formatDate(
                cluster.articles.reduce((latest: string | undefined, a: any) => {
                    const ts = a.created_at || a.ingested_at;
                    if (!ts) return latest;
                    if (!latest || new Date(ts) > new Date(latest)) return ts;
                    return latest;
                }, undefined as string | undefined)
                || article.created_at
                || article.ingested_at,
            );
            const source = article.source || 'Presek';

            return `
    <item>
      <title><![CDATA[${escapeXml(title)}]]></title>
      <link>${escapeXml(link)}</link>
      <description><![CDATA[${escapeXml(description)}]]></description>
      <pubDate>${pubDate}</pubDate>
      <dc:creator>${escapeXml(source)}</dc:creator>
      <guid isPermaLink="true">${escapeXml(link)}</guid>
    </item>`;
        })
        .join('\n');

    const siteUrl = SITE_URL.replace('presek.live', 'presek.mk');
    const title = 'Пресек - Македонија';
    const description = 'Пресек: Најнови вести од Македонија и регионот. Независно, балансирано, длабоко.';
    const language = 'mk-MK';
    const rssPath = 'mk/rss.xml';

    const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title><![CDATA[${title}]]></title>
    <link>${escapeXml(siteUrl)}</link>
    <description><![CDATA[${description}]]></description>
    <language>${language}</language>
    <pubDate>${now}</pubDate>
    <lastBuildDate>${now}</lastBuildDate>
    <managingEditor>editor@presek.live</managingEditor>
    <webMaster>webmaster@presek.live</webMaster>
    <atom:link href="${escapeXml(siteUrl)}/${rssPath}" rel="self" type="application/rss+xml" />
${items}
  </channel>
</rss>`;

    return new Response(rss, {
        headers: {
            'Content-Type': 'application/xml; charset=utf-8',
            'Cache-Control': 'public, max-age=300',
        },
    });
};
