# Presek Design System

This document describes the current visual system used by the live Astro frontend.

## Principles

- Editorial, not startup.
- Serious and structured, not playful.
- Hierarchy comes from typography, spacing, and restraint more than from decoration.
- Interfaces should feel like a modern digital newspaper with disciplined UI framing.

## Fonts

The site imports three font families in [web/src/styles/global.css](/home/emiloffingen/presek/web/src/styles/global.css):

- `Noto Serif`
- `Source Serif 4`
- `Manrope`

### Role Mapping

- `--font-serif`: `Noto Serif`
- `--font-sans`: `Manrope`
- `--font-nyt-body`: `Source Serif 4`

### Usage Rules

- Use `Noto Serif` for headlines, article titles, and major editorial statements.
- Use `Source Serif 4` for body copy, summaries, explanations, and longer reading passages.
- Use `Manrope` for navigation, section labels, timestamps, chips, controls, and other UI scaffolding.

## Typography

### Base Body Style

Defined in [web/src/styles/global.css](/home/emiloffingen/presek/web/src/styles/global.css):

- Font: `Source Serif 4`
- Base size: `--text-base`
- Line height: `1.62`
- Letter spacing: `0.003em`
- Rendering: antialiased with `optimizeLegibility`

### Heading Style

- Font: `Noto Serif`
- Weight: black / very heavy
- Tight tracking
- Compact line height
- Balanced wrapping

### Label Style

Used for navigation and utility labels:

- Font: `Manrope`
- Small size
- Uppercase
- Heavy weight
- Wide tracking

### Fluid Type Scale

- `--text-xs`: `0.75rem` to `0.8rem`
- `--text-sm`: `0.875rem` to `0.95rem`
- `--text-base`: `1rem` to `1.125rem`
- `--text-lg`: `1.125rem` to `1.25rem`
- `--text-xl`: `1.25rem` to `1.5rem`
- `--text-2xl`: `1.5rem` to `2rem`
- `--text-3xl`: `1.875rem` to `2.5rem`
- `--text-4xl`: `2.25rem` to `3.5rem`

## Color System

### Light Mode

- `--background`: `#fafafb`
- `--foreground`: `#111827`
- `--card`: `#ffffff`
- `--secondary`: `#f3f4f6`
- `--secondary-foreground`: `#374151`
- `--border`: `#e5e7eb`
- `--muted`: `#f9fafb`
- `--muted-foreground`: `#6b7280`

### Brand / Editorial Accents

- `--nyt-accent`: `#1e40af`
- `--nyt-red`: `#b91c1c`
- `--nyt-black`: `#111827`

### Supporting Gray Scale

- `--nyt-gray-100`: `#f3f4f6`
- `--nyt-gray-200`: `#e5e7eb`
- `--nyt-gray-300`: `#d1d5db`
- `--nyt-gray-500`: `#9ca3af`
- `--nyt-gray-600`: `#4b5563`

### Dark Mode

- `--background`: `#111827`
- `--foreground`: `#f3f4f6`
- `--card`: `#1f2937`
- `--secondary`: `#1f2937`
- `--secondary-foreground`: `#d1d5db`
- `--border`: `#374151`
- `--muted-foreground`: `#9ca3af`
- `--nyt-accent`: `#60a5fa`
- `--nyt-red`: `#f87171`

## Surfaces and Shape

- Default radii are square: `0px`.
- Borders are thin and structural.
- Surfaces rely on subtle contrast rather than shadows.
- Cards should feel editorial and restrained, not soft and app-like.

## Grid and Layout Spacing

- **Base Grid:** Uses an 8px (`0.5rem`) increments for all padding, margins, and structural offsets.
- **Container:** Main content width is capped at `1280px` (`max-w-7xl`).
- **Standard Gutter:** `1.5rem` (24px) for desktop; `1rem` (16px) for mobile.
- **Column Logic:** 12-column grid on desktop. Rail/Sidebar typically occupies 4 columns (`col-span-4`) while the main feed occupies 8 (`col-span-8`).

## Editorial Components (Broadsheet Patterns)

- **The "Kicker":** A short label above the headline. Font: `Manrope`, uppercase, heavy weight, wide tracking. Color: `--nyt-accent` or `--nyt-red`.
- **The "Rule" (Borders):**
    - *Single (1px):* Standard structural separation.
    - *Double (4px double):* Reserved for the Masthead and major section breaks.
- **The "Rail":** Sticky sidebar for high-density utility modules (Pulse, Newsletter, Trending).
- **Pull Quotes:** `Noto Serif` italic, larger size (`text-xl`), with a subtle border-left.

## Iconography and Semantics

- **Library:** Lucide React.
- **Stroke Weight:** `1.5px` (thin and structural, matching the "Rule" aesthetic).
- **Sizing Tiers:**
    - `12px`: Micro-labels and utility signals.
    - `16px`: Standard card actions.
    - `24px`: Section headers and major landing points.
- **Semantic Mapping:**
    - `Sparkles`: AI Synthesis / Intelligence.
    - `Zap`: Breaking News / Real-time events.
    - `Quote`: Citations and direct statements.
    - `Clock`: Freshness and temporal signals.
    - `BarChart3`: Analytics and "Media Pulse" data.

## Motion and Easing (The "Rise" System)

- **The "Editorial Glide":** `cubic-bezier(0.16, 1, 0.3, 1)`. Motion should feel purposeful and expensive, not bouncy.
- **Entry Pattern (`motion-rise`):** Elements should enter with a slight upward translate (`10px`) and opacity fade.
- **Orchestration (Staggering):**
    - *Level 1 (0ms):* Lead Hero and Masthead.
    - *Level 2 (100ms):* Supporting News Grid.
    - *Level 3 (200ms):* Front Rail and Sidebar modules.
    - *Level 4 (300ms):* Secondary Feeds and Footer.

## Image Treatment

- **Aspect Ratios:**
    - *Hero:* `1.26:1` (Desktop) / `16:10` (Mobile).
    - *Card:* `3:2` or `16:9`.
- **Styling:** `object-fit: cover` with a thin `1px` border. No rounded corners.
- **Placeholders:** When an image fails, use the brand "П" emblem with a desaturated background from the gray scale.

## Accessibility and Inclusive Design

- **Contrast:** Aim for WCAG AA compliance (4.5:1) for all body text.
- **Focus States:** Use a `2px` solid `--nyt-accent` outline with `2px` offset. Do not round focus rings.
- **Aria Labels:** Mandatory for all icon-only buttons (Search, Theme Toggle, Share).

## Usage Guidance

### Do

- Keep the serif/sans split intact.
- Use blue for trust, navigation emphasis, and key actions.
- Use red sparingly for urgency and live states.
- Prefer off-white and gray surfaces over pure white / pure black extremes.
- Preserve the newspaper tone with compact labels and strong headline hierarchy.
- Use square corners for everything.

### Don’t

- Introduce random additional font families.
- Replace serif headlines with generic sans defaults.
- Overuse bright accent colors.
- Add oversized rounded corners.
- Lean on heavy shadows or glossy UI effects.
- Drift into generic SaaS styling.

## Implementation Notes

- Global tokens live in [web/src/styles/global.css](/home/emiloffingen/presek/web/src/styles/global.css)
- The global theme is imported in [web/src/layouts/Layout.astro](/home/emiloffingen/presek/web/src/layouts/Layout.astro)
- Theme switching is controlled by toggling `.dark` on the document root.
- Motion classes are defined in [web/src/styles/motion.css](/home/emiloffingen/presek/web/src/styles/motion.css) (if available).

