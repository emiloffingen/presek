# Presek Web (Consolidated i18n)

This directory contains the unified Astro frontend for **Presek**, serving both Serbian and Macedonian audiences from a single codebase.

## i18n Architecture
We use **Astro i18n** to manage multiple languages:
- **Serbian (sr)**: Default locale, served at `/` (domain: `presek.live`).
- **Macedonian (mk)**: Prefixed locale, served at `/mk` (domain: `presek.mk`).

Nginx handles domain-to-path mapping, proxying `presek.mk/` to the `/mk/` subpath of this application.

## Commands

Run these from this directory:

```sh
npm install
npm run dev
npm run build
npm run preview
```

## Environment

The frontend reads `PUBLIC_API_URL` and `PUBLIC_SITE_URL`.

- In local development, point it at the FastAPI backend, for example `http://127.0.0.1:5001/api`.
- **Production Serbian**: https://presek.live
- **Production Macedonian**: https://presek.mk

## Key Files
- `src/i18n/`: Translation strings and routing utilities.
- `src/layouts/Layout.astro`: Shared responsive layout with dynamic meta tags.
- `src/pages/`: Serbian pages.
- `src/pages/mk/`: Macedonian pages (automatically routed via `/mk` prefix).
