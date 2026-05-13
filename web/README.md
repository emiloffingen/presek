# Presek Web - SERBIAN

This directory contains the **Serbian** Astro frontend for Presek.

## Site Details
- **Language**: Serbian Latin
- **Domain**: presek.live
- **Brand**: PRESEK.live
- **DO NOT EDIT** this for Macedonian (presek.mk) - use `../web-mk/` instead

## Commands

Run these from `/home/emiloffingen/presek/web`:

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
- **Production URL**: https://presek.live

## Notes

- `src/pages/index.astro` is the editorial homepage.
- `src/pages/stats.astro` renders the analytics view from `/api/stats/full`.
- `web/dist` is generated build output and should not be committed.
- This is the **Serbian** frontend. For Macedonian, see `../web-mk/`.

## ⚠️ WARNING

**This is the SERBIAN site (presek.live)**

- Use Serbian Latin script (PRESEK, not ПРЕСЕК)
- Use Serbian language content
- Domain: presek.live (ASCII)
- Do NOT mix with Macedonian content
