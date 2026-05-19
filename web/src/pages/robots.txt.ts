import type { APIRoute } from 'astro';

export const GET: APIRoute = async ({ request }) => {
  const url = new URL(request.url);
  const host = request.headers.get('host') || url.hostname;
  const isMk = host.includes('presek.mk');
  const siteUrl = isMk ? 'https://presek.mk' : 'https://presek.live';

  const robots = `User-agent: *
Allow: /
Disallow: /api/
Disallow: /settings
Disallow: /status

Sitemap: ${siteUrl}/sitemap.xml
Sitemap: ${siteUrl}/rss.xml
`;

  return new Response(robots, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
};
