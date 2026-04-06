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

- Default radii are square: `0px`
- Borders are thin and structural
- Surfaces rely on subtle contrast rather than shadows
- Cards should feel editorial and restrained, not soft and app-like

## Layout

- Main content width is capped at `1280px`
- Standard page container uses `.site-layout`
- The visual rhythm relies on rules, rails, cards, and strong section dividers

## Usage Guidance

### Do

- Keep the serif/sans split intact
- Use blue for trust, navigation emphasis, and key actions
- Use red sparingly for urgency and live states
- Prefer off-white and gray surfaces over pure white / pure black extremes
- Preserve the newspaper tone with compact labels and strong headline hierarchy

### Don’t

- Introduce random additional font families
- Replace serif headlines with generic sans defaults
- Overuse bright accent colors
- Add oversized rounded corners everywhere
- Lean on heavy shadows or glossy UI effects
- Drift into generic SaaS styling

## Implementation Notes

- Global tokens live in [web/src/styles/global.css](/home/emiloffingen/presek/web/src/styles/global.css)
- The global theme is imported in [web/src/layouts/Layout.astro](/home/emiloffingen/presek/web/src/layouts/Layout.astro)
- Theme switching is controlled by toggling `.dark` on the document root

