import type { APIRoute } from 'astro';

export const GET: APIRoute = ({ params, request }) => {
  const url = new URL(request.url);
  const strippedPath = params.path ? `/${params.path}` : '/';
  const location = `${strippedPath}${url.search}`;

  return new Response(null, {
    status: 308,
    headers: {
      Location: location,
    },
  });
};
