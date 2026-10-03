import type { APIRoute } from 'astro';

export const GET: APIRoute = async ({ request }) => {
  const url = new URL(request.url);
  const host = request.headers.get('host') || url.hostname;
  const isMk = host.includes('presek.mk');
  const siteUrl = 'https://presek.mk';

  const robots = `User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /debug/

Sitemap: ${siteUrl}/sitemap.xml
Sitemap: ${siteUrl}/rss.xml
`;

  return new Response(robots, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
    },
  });
};
