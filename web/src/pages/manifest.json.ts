import type { APIRoute } from 'astro';

export const GET: APIRoute = async ({ request }) => {
  const url = new URL(request.url);
  const host = request.headers.get('host') || url.hostname;
  const isMk = host.includes('presek.mk');

  const manifest = {
    "name": isMk ? "Пресек" : "Presek",
    "short_name": isMk ? "Пресек" : "Presek",
    "description": isMk 
      ? "Македонски информативен агрегатор со подлабок контекст и напредна јазична обработка."
      : "Srpski informativni agregator sa dubljim kontekstom i naprednom jezičkom obradom.",
    "start_url": "/?utm_source=pwa",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#0a192f",
    "orientation": "portrait",
    "icons": [
      {
        "src": "/img/presek_emblem.svg",
        "sizes": "any",
        "type": "image/svg+xml",
        "purpose": "any maskable"
      },
      {
        "src": "/img/presek_emblem.png",
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "any"
      },
      {
        "src": "/img/presek_emblem.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "any"
      }
    ],
    "categories": ["news", "politics"],
    "shortcuts": [
      {
        "name": isMk ? "Дневен Брифинг" : "Dnevni Brifing",
        "short_name": isMk ? "Брифинг" : "Brifing",
        "url": "/briefing",
        "icons": [{ "src": "/img/presek_emblem.svg", "sizes": "any" }]
      },
      {
        "name": isMk ? "Медиумски Пулс" : "Medijski Puls",
        "short_name": isMk ? "Пулс" : "Puls",
        "url": "/stats",
        "icons": [{ "src": "/img/presek_emblem.svg", "sizes": "any" }]
      },
      {
        "name": isMk ? "извори" : "izvori",
        "short_name": isMk ? "изvori" : "izvori",
        "url": "/izvori",
        "icons": [{ "src": "/img/presek_emblem.svg", "sizes": "any" }]
      }
    ]
  };

  return new Response(JSON.stringify(manifest), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
};
