import type { APIRoute } from 'astro';
import { apiBaseUrl } from '../lib/apiBase';

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

export const GET: APIRoute = async ({ request }) => {
    const url = new URL(request.url);
    const host = request.headers.get('host') || url.hostname;
    const isMk = host.includes('presek.mk');
    const SITE_URL = isMk ? 'https://presek.mk' : 'https://presek.live';
    const API_URL = apiBaseUrl();
    
    const clusters: any[] = [];
    const now = new Date().toUTCString();

    const lang = isMk ? 'mk' : 'sr';

    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 10000);
        const res = await fetch(`${API_URL}/news?page_size=50&page=0&lang=${lang}`, { signal: controller.signal });
        clearTimeout(timer);
        if (res.ok) {
            const data = await res.json();
            if (data && Array.isArray(data.clusters)) {
                clusters.push(...data.clusters);
            }
        }
    } catch (e) {
        console.error("RSS fetch error:", e);
    }

    const countryFilter = isMk ? 'MK' : 'RS';
    const items = clusters
        .filter(c => c.articles && c.articles.length > 0)
        .map(cluster => {
            const articles = cluster.articles.filter((a: any) => a.country === countryFilter);
            const article = articles[0] || cluster.articles[0];
            const title = cluster.synthetic_headline || cluster.title || article.title || 'Untitled';
            const description = cluster.synthetic_standfirst || article.description || cluster.summary || '';
            const link = `${SITE_URL}/cluster/${cluster.cluster_id}`;
            const pubDate = formatDate(
                articles.reduce((latest: string | undefined, a: any) => {
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

    const title = isMk ? 'Пресек - Македонија' : 'Presek - Srbija';
    const description = isMk
        ? 'Пресек: Најнови вести од Македонија и регионот. Независно, балансирано, длабоко.'
        : 'Presek: Najnovije vesti iz Srbije i regiona. Nezavisno, balansirano, dubinsko.';
    const language = isMk ? 'mk-MK' : 'sr-RS';

    const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title><![CDATA[${title}]]></title>
    <link>${escapeXml(SITE_URL)}</link>
    <description><![CDATA[${description}]]></description>
    <language>${language}</language>
    <pubDate>${now}</pubDate>
    <lastBuildDate>${now}</lastBuildDate>
    <managingEditor>editor@presek.live</managingEditor>
    <webMaster>webmaster@presek.live</webMaster>
    <atom:link href="${escapeXml(SITE_URL)}/rss.xml" rel="self" type="application/rss+xml" />
${items}
  </channel>
</rss>`;

    return new Response(rss, {
        headers: {
            'Content-Type': 'application/xml; charset=utf-8',
            'Cache-Control': 'public, max-age=600, s-maxage=3600, stale-while-revalidate=1800',
        },
    });
};
