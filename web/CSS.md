# Presek frontend CSS map

`global.css` is the entry point. It loads fonts, Tailwind, shadcn, and the domain modules below.

## Core

| File | Purpose |
|------|---------|
| `global.css` | Design tokens (`@theme`), base layer, typography core, ticker, focus rings |
| `layout.css` | `.site-layout`, `.broadsheet-layout` primitives |
| `design-card.css` | Shared placeholder/card patterns |

## Homepage

| File | Purpose |
|------|---------|
| `home-page.css` | Homepage layout, analysis bands, consensus carousel, mobile feed order |
| `home-feed.css` | News feed grid, for-you cards, stagger animations |
| `home-live-strip.css` | Live wire `<details>` strip |
| `trending-preview.css` | Trending preview rail |
| `lead-hero.css` | Lead hero imagery and overlay |

Imported from `HomePage.astro` / band components — not via `global.css`.

## Reading & cluster

| File | Purpose |
|------|---------|
| `cluster-reading.css` | Zen focus + compare reading modes |
| `editorial-layout.css` | Editorial shell, panels, broadsheet columns |
| `editorial-imagery.css` | Card images, motion-rise animations |
| `nyt-header.css` | Masthead, ticker, utility chrome |

## Page-specific (global import)

| File | Purpose |
|------|---------|
| `page-systems.css` | Sources + entity page systems |
| `settings-surfaces.css` | Onboarding, settings, delivery, account sync |
| `ui-primitives.css` | Interactions, skeletons, bento grid, scrollbars |
| `surface-widgets.css` | Rail suggestions, cluster-follow, reader-pref |
| `mobile-layout.css` | Mobile density + overflow polish |
| `next-level.css` | Vesti/Analiza toggle, onboarding FAB |

## Route-local (imported in pages)

| File | Loaded by |
|------|-----------|
| `pulse-premium.css` | Pulse page |
| `briefing-premium.css` | Briefing pages |
| `archive-premium.css` | Archive pages |
| `settings-premium.css` | Settings pages |
| `for-you-premium.css` | For-you page |

## Conventions

- Prefer extracting new rules into a domain file over growing `global.css`.
- Homepage analiza bands lazy-mount DOM on `<details>` open — keep card CSS in `home-page.css` aligned with `AnalysisBandsLazy.astro`.
- Import order in `global.css` matters: layout → header → reading modes → feed/widgets → primitives → next-level.

## Perf checks

```bash
cd web
npm run perf:lighthouse        # advisory (local preview, SR /)
npm run perf:lighthouse:ci     # enforced budgets (CI, SR /)
npm run perf:lighthouse:ci:mk  # enforced budgets (CI, MK /mk/)
npm run perf:lighthouse:live   # production SR URL
npm run perf:lighthouse:live:mk # production MK URL
```

Budgets (see `scripts/lighthouse-homepage.mjs`): performance ≥ 72, LCP ≤ 4200 ms, CLS ≤ 0.12.
