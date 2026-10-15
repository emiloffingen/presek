"""Presek editorial placeholder palette — mirrors the broadsheet theme (web/src/styles/theme-broadsheet.css)."""

from __future__ import annotations

# Site accent (--bs-accent) in light and dark.
PRESEK_MARK_LIGHT = "#0f6b5e"
PRESEK_MARK_DARK = "#4fb8a5"

# --bs-bg / --bs-photo (light) and --bs-bg / --bs-photo (dark).
PAPER_LIGHT = "#f5f3ec"
PAPER_LIGHT_END = "#e0ddd0"
INK_DARK = "#101615"
INK_DARK_END = "#243230"

# --bs-text for the mark's top bar and the labels.
INK_LIGHT_TEXT = "#14201e"
INK_DARK_TEXT = "#e8efed"
MUTED_LIGHT = "#55625f"
MUTED_DARK = "#9fb0ab"

# Legacy cold tints stored on clusters before the rebrand — treat as unset on the frontend.
LEGACY_COLD_TINTS = frozenset(
    {
        "#1e40af",
        "#132a4f",
        "#070c16",
        "#27272a",
        "#1e3a8a",
        "#0b2545",
        "#020b18",
        "#8b5cf6",
        "#6d28d9",
        "#581c87",
        "#3b82f6",
        "#1d4ed8",
    }
)

# Section tones from the broadsheet (--bs-tone-*): (light, dark).
_TONES: dict[str, tuple[str, str]] = {
    "pol": ("#7a3b5e", "#d79ac0"),
    "eco": ("#5a6b1e", "#b5c96a"),
    "spo": ("#b4540f", "#f0a060"),
    "wor": ("#2f5f8a", "#86b4e0"),
    "cul": ("#8a5a1c", "#e0b878"),
    "brand": (PRESEK_MARK_LIGHT, PRESEK_MARK_DARK),
}

_KEY_TONE: dict[str, str] = {
    "Srbija": "brand",
    "Makedonija": "brand",
    "Balkan": "wor",
    "Evropa": "wor",
    "Amerika": "wor",
    "Svet": "wor",
    "Sport": "spo",
    "Tehnologija": "pol",
    "Ekonomija": "eco",
    "Hronika": "pol",
    "Zabava": "cul",
    "default": "brand",
}


def category_palette(category_key: str, *, light: bool) -> tuple[str, str, str]:
    """Return (background, background end, section accent) for a placeholder."""
    tone_light, tone_dark = _TONES[_KEY_TONE.get(category_key, "brand")]
    if light:
        return PAPER_LIGHT, PAPER_LIGHT_END, tone_light
    return INK_DARK, INK_DARK_END, tone_dark


def minimal_fallback_svg(*, lang: str = "sr") -> str:
    """Ultra-minimal proxy fallback when the full generator fails."""
    label = "PRESEK.MK" if str(lang or "sr").lower().startswith("mk") else "PRESEK"
    return f'''<svg width="800" height="450" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{PAPER_LIGHT}"/>
      <stop offset="100%" stop-color="{PAPER_LIGHT_END}"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect x="48" y="48" width="5" height="354" fill="{PRESEK_MARK_LIGHT}"/>
  <text x="80" y="240" font-family="Georgia,serif" font-size="34" font-weight="900" fill="{INK_LIGHT_TEXT}">{label}</text>
</svg>'''
