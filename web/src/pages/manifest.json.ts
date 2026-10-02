import type { APIRoute } from 'astro';
import { isMkHost } from '../lib/localePaths';

export const GET: APIRoute = async ({ request }) => {
  const url = new URL(request.url);
  const host = request.headers.get('host') || url.hostname;
  const isMk = isMkHost(host) || url.pathname.startsWith('/mk');
  const startUrl = '/?utm_source=pwa';
  const scope = '/';
  const shortcuts = isMk
    ? [
        { name: 'Медиумски извори', short_name: 'Извори', url: '/izvori' },
        { name: 'Архива', short_name: 'Архива', url: '/archive' },
        { name: 'Методологија', short_name: 'Методологија', url: '/methodology' },
      ]
    : [
        { name: 'Medijski izvori', short_name: 'Izvori', url: '/izvori' },
        { name: 'Arhiva', short_name: 'Arhiva', url: '/archive' },
        { name: 'Metodologija', short_name: 'Metodologija', url: '/methodology' },
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
    "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
    "launch_handler": { "client_mode": "navigate-existing" },
    "background_color": "#fdfdfa",
    "theme_color": "#0a192f",
    "prefer_related_applications": false,
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
    "screenshots": [
      {
        "src": "/img/screenshot-narrow.png",
        "sizes": "1080x1920",
        "type": "image/png",
        "form_factor": "narrow",
        "label": isMk ? "Почетна страница на Пресек" : "Presek home"
      },
      {
        "src": "/img/screenshot-wide.png",
        "sizes": "1920x1080",
        "type": "image/png",
        "form_factor": "wide",
        "label": isMk ? "Преглед на извори и кластери" : "Sources and clusters"
      }
    ],
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
