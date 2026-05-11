# Presek Design System: Modern Editorial Broadsheet

This document defines the visual and structural language of the Presek platform, inspired by premium digital broadsheets (NYT, BBC, The Guardian).

## Core Principles

- **Broadsheet Authority:** Hierarchy is driven by strong typography and disciplined modular grids.
- **Editorial Restraint:** Clean space and thin structural rules replace decorative shadows and gradients.
- **Content First:** The interface recedes to let the news and AI synthesis lead the experience.
- **Cyrillic-First Optimization:** Specific attention to Macedonian Cyrillic legibility and vertical rhythm.

## 1. Typography

### Primary Font Families
- **Headline Serif (`--font-serif`):** `Noto Serif`
  - Used for: Major mastheads, cluster titles, section headers.
  - Style: Black (900) weight, tight tracking (-0.02em), compact line-height.
- **Body Serif (`--font-nyt-body`):** `Source Serif 4`
  - Used for: Article summaries, briefings, long-form prose.
  - Style: Balanced line-height (1.62 - 1.75) for maximum readability.
- **Interface Sans (`--font-sans`):** `Manrope`
  - Used for: Navigation, metadata, labels, buttons.
  - Style: Heavy weight (800-900) for labels, wide tracking (0.1em) for kickers.

### Cyrillic Optimization
- **Macedonian Vertical Rhythm:** Cyrillic headlines use an increased `line-height` (1.12 - 1.15) to prevent collision of descenders and ascenders (e.g., Dj, j, c).
- **Features:** `font-variant-ligatures: common-ligatures` and `font-kerning: normal` are enabled globally for serif text.

## 2. Grid & Structural Rules

### The Modular Grid
- **Desktop:** 12-column system. Standard layout is 8 columns for main feed (Broadsheet Main) and 4 columns for the sticky utility rail (Broadsheet Rail).
- **Dividers:** Thin `1px solid var(--border)` horizontal and vertical rules.
- **Masthead Rule:** `4px double var(--foreground)` or `4px solid var(--foreground)` reserved for the top of major pages.

### Editorial Rails
- The "Discovery Bar" uses a rail-style horizontal scroll with vertical separators between geographic and thematic groups.
- The "Right Rail" is sticky and houses high-density intelligence modules (Pulse, Briefing, Subjects).

## 3. Color Palette

### Base Tones
- **Background:** Off-white (`#fafafb`) / OLED Navy (`#111827`) in dark mode.
- **Foreground:** Deep charcoal (`#111827`) / Soft white (`#f3f4f6`) in dark mode.
- **Borders:** Subtle gray (`#e5e7eb`) / Muted slate (`#374151`).

### Brand Accents
- **Trust Blue (`--nyt-accent`):** `#1e40af`. Used for verified signals and interactive states.
- **Alert Red (`--nyt-red`):** `#b91c1c`. Reserved for "Breaking" and "Live" indicators.

## 4. Imagery

### Aspect Ratios
- **Standard Editorial Ratio:** **3:2** (e.g., 1200x800).
- Used for all hero images and standard news cards to provide strong vertical presence and newspaper-like framing.

### Captions & Credits
- **Typography:** Small (`0.62rem`), bold-italic sans-serif.
- **Style:** Muted foreground, placed directly below the image rule.

## 5. Components (Broadsheet Patterns)

- **Drop Caps:** Used in the first paragraph of Briefings and About pages.
- **Live Ticker:** High-contrast red bar for breaking headlines with a subtle pulse animation.
- **Pulse Stats Bar:** Clean, border-divided stats for pluralism and synthesis.
- **Editorial Cards:** No rounded corners (`0px`). Backgrounds are flat or use extremely subtle `color-mix` tints.

## 6. Motion (The "Rise" System)

- **Easing:** `cubic-bezier(0.16, 1, 0.3, 1)` (The "Editorial Glide").
- **Pattern:** Elements enter with a `18px` upward translate and opacity fade over `620ms`.

---
*Last updated: april 2026 • Presek AI Design System*
