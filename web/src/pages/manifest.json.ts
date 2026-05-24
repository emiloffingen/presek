import type { APIRoute } from 'astro';

export const GET: APIRoute = async ({ request }) => {
  const url = new URL(request.url);
  const host = request.headers.get('host') || url.hostname;
  const isMk = host.includes('presek.mk') || url.pathname.startsWith('/mk');
  const basePath = isMk ? '/mk' : '';
  const startUrl = `${basePath || '/' }${basePath ? '/' : ''}?utm_source=pwa`;
  const scope = basePath ? `${basePath}/` : '/';
  const shortcuts = isMk
    ? [
        { name: 'Дневен брифинг', short_name: 'Брифинг', url: '/mk/briefing' },
        { name: 'Медиумски пулс', short_name: 'Пулс', url: '/mk/pulse' },
        { name: 'Извори', short_name: 'Извори', url: '/mk/izvori' },
      ]
    : [
        { name: 'Dnevni brifing', short_name: 'Brifing', url: '/briefing' },
        { name: 'Medijski puls', short_name: 'Puls', url: '/pulse' },
        { name: 'Izvori', short_name: 'Izvori', url: '/izvori' },
      ];

  const manifest = {
    "name": isMk ? "Пресек" : "Presek",
    "short_name": isMk ? "Пресек" : "Presek",
    "description": isMk 
      ? "Македонски информативен агрегатор со подлабок контекст и напредна јазична обработка."
      : "Srpski informativni agregator sa dubljim kontekstom i naprednom jezičkom obradom.",
    "id": scope,
    "scope": scope,
    "start_url": startUrl,
    "lang": isMk ? "mk" : "sr-Latn",
    "dir": "ltr",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#0a192f",
    "orientation": "portrait",
    "icons": [
      {
        "src": "/img/icons/presek-icon-192.png",
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "any"
      },
      {
        "src": "/img/icons/presek-icon-512.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "any"
      },
      {
        "src": "/img/icons/presek-maskable-192.png",
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "maskable"
      },
      {
        "src": "/img/icons/presek-maskable-512.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "maskable"
      },
      {
        "src": "/img/presek_emblem.svg",
        "sizes": "any",
        "type": "image/svg+xml",
        "purpose": "any"
      }
    ],
    "categories": ["news", "politics"],
    "shortcuts": shortcuts.map(shortcut => ({
      ...shortcut,
      icons: [{ "src": "/img/icons/presek-icon-192.png", "sizes": "192x192", "type": "image/png" }]
    }))
  };

  return new Response(JSON.stringify(manifest), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
};
