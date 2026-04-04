# Presek Web

This directory contains the Astro frontend for Presek.

## Commands

Run these from `/home/emiloffingen/presek/web`:

```sh
npm install
npm run dev
npm run build
npm run preview
```

## Environment

The frontend reads `PUBLIC_API_URL`.

- In local development, point it at the Flask API, for example `http://127.0.0.1:5001/api`.
- In production, keep it on the same origin when possible and use `/api`.

## Notes

- `src/pages/index.astro` is the editorial homepage.
- `src/pages/stats.astro` renders the analytics view from `/api/stats/full`.
- `../web-legacy` is an older build output/codepath and should not be treated as the active frontend.
- `web/dist` is generated build output and should not be committed.
