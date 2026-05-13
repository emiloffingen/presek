# Presek Web - MACEDONIAN

This directory contains the **Macedonian** Astro frontend for Presek.

## Site Details
- **Language**: Macedonian Cyrillic
- **Domain**: пресек.мк (xn--80akdyelc.xn--p1ai in ASCII/Punycode)
- **Brand**: ПРЕСЕК.мк
- **DO NOT EDIT** this for Serbian (presek.live) - use `../web/` instead

## Commands

Run these from `/home/emiloffingen/presek/web-mk`:

```sh
npm install
npm run dev
npm run build
npm run preview
```

## Environment

The frontend reads `PUBLIC_API_URL` and `PUBLIC_SITE_URL`.

- In local development, point it at the FastAPI backend, for example `http://127.0.0.1:5001/api`.
- In production, keep it on the same origin when possible and use `/api`.
- **Production URL**: https://пресек.мк (https://xn--80akdyelc.xn--p1ai)

## Notes

- `src/pages/index.astro` is the editorial homepage.
- `src/pages/stats.astro` renders the analytics view from `/api/stats/full`.
- `web-mk/dist` is generated build output and should not be committed.
- This is the **Macedonian** frontend. For Serbian, see `../web/`.

## ⚠️ WARNING

**This is the MACEDONIAN site (пресек.мк)**

- Use Macedonian Cyrillic script (ПРЕСЕК, not PRESEK)
- Use Macedonian language content
- Domain: пресек.мк (Cyrillic TLD)
- Do NOT mix with Serbian content
