# Presek Design System: Broadsheet 2.0

This document defines the visual and structural language of the Presek platform: a strict editorial front page with data-rich newsroom tooling.

## Core Principles

- **Broadsheet Authority:** Hierarchy is driven by strong typography, visible rules, and disciplined modular grids.
- **Editorial Restraint:** Clean space and thin structural rules replace decorative shadows, glow, gradients, and app-like chrome.
- **Content First:** The interface recedes to let the news and AI synthesis lead the experience.
- **Cyrillic-First Optimization:** Specific attention to Macedonian Cyrillic legibility and vertical rhythm.

## 1. Typography

### Primary Font Families
- **Headline Serif (`--font-serif`):** `Noto Serif`, falling back to `Source Serif 4`
  - Used for: Cluster titles, section headers, article headlines.
  - Style: Black (900) weight, tight tracking, compact line-height.
- **Display Serif (`--font-serif-display`):** `Noto Serif Display`, falling back to `Noto Serif`
  - Used for: Major mastheads and oversized hero treatments only.
- **Body Serif (`--font-nyt-body`):** `Source Serif 4`
  - Used for: Article summaries, briefings, long-form prose.
  - Style: Balanced line-height (1.62 - 1.75) for maximum readability.
- **Interface Sans (`--font-ui`, `--font-sans`, `--font-ui-condensed`):** `Manrope`, falling back to system Noto/DejaVu/Arial sans fonts
  - Used for: Navigation, metadata, labels, buttons.
  - Style: Medium/bold weights (600-700), wide tracking (0.1em) for kickers and metadata.

### Accessibility & WCAG Compliance
- **Contrast Ratios**: All text meets WCAG AA standards (minimum 4.5:1 contrast ratio)
- **Font Sizes**: Responsive typography with fluid scaling using `clamp()` functions
- **Line Height**: Cyrillic-specific adjustments (1.15 line-height) to prevent ascender/descender collisions
- **Readability**: Body text uses Source Serif 4 with 1.62-1.75 line-height for optimal readability

### Font Loading
- Use exact self-hosted `@fontsource` weights instead of package defaults.
- Headline weights: `Noto Serif Display` 700/900 plus 900 italic; `Noto Serif` 700/900 plus 900 italic for script fallback.
- Body weights: `Source Serif 4` 400/500/600 plus 400 italic.
- UI weights: `Manrope` 600/700/800 as the primary UI family. `IBM Plex Sans Condensed` remains available as a Latin-safe fallback, but Macedonian Cyrillic UI text uses Manrope to avoid mixed-font fallback.

### Cyrillic Optimization
- **Macedonian Vertical Rhythm:** Cyrillic headlines use an increased `line-height` (1.12 - 1.15) to prevent collision of ascenders and descenders.
- **Script Coverage:** Serbian Latin and Macedonian Cyrillic must use families with complete Latin-ext and Cyrillic coverage. Avoid condensed UI faces unless their main Cyrillic block is present.
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
- **Background:** Warm paper (`#fbfaf5`) / near-black newsroom terminal (`#08090b`) in dark mode.
- **Foreground:** Ink black (`#101010`) / warm white (`#f4f1e8`) in dark mode.
- **Borders:** Paper rule (`#d9d5c8`) / muted ink rule (`#1b1d22`) in dark mode.

### Brand Accents
- **Trust Blue (`--nyt-accent`):** `#173f7a`. Used for verified signals and interactive states.
- **Alert Red (`--nyt-red`):** `#a31621`. Reserved for "Breaking" and "Live" indicators.

### Accessibility Compliance
- **Contrast Ratios**: All color combinations meet WCAG AA standards (4.5:1 minimum)
- **Dark Mode**: Automated color inversion with WCAG-compliant contrast levels
- **Focus States**: Visible focus indicators for keyboard navigation
- **Color Blindness**: Sufficient contrast for protanopia, deuteranopia, and tritanopia

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
- **Article Blocks:** No rounded corners (`0px`). Articles sit on the page with thin top/bottom rules, not floating cards.

## 6. Motion (The "Rise" System)

- **Easing:** `cubic-bezier(0.16, 1, 0.3, 1)` (The "Editorial Glide").
- **Pattern:** Elements enter with a `18px` upward translate and opacity fade over `620ms`.

## 7. Accessibility Features

### ARIA Implementation
- **Semantic HTML**: Proper use of `<article>`, `<time>`, `<nav>` elements
- **ARIA Attributes**: `role`, `aria-label`, `aria-describedby` for interactive components
- **Screen Reader Support**: Hidden duplicates marked with `aria-hidden="true"`
- **Keyboard Navigation**: Focus management and visible focus states

### WCAG 2.1 AA Compliance
- **Text Contrast**: Minimum 4.5:1 contrast ratio for normal text
- **Large Text**: Minimum 3:1 contrast ratio for large text (18.66px+ bold or 24px+ normal)
- **Responsive Design**: Fluid typography and adaptive layouts
- **Color Independence**: Information not conveyed by color alone
- **Error Prevention**: Clear form validation and error messages

### Performance Optimizations
- **CSS Containment**: `contain: content` for performance-critical components
- **Font Loading**: `font-display: swap` with fallback strategies
- **Lazy Loading**: Images and non-critical resources
- **Reduced Motion**: Respects `prefers-reduced-motion` media query

---
*Last updated: june 2026 • Presek AI Design System • WCAG 2.1 AA Compliant*
