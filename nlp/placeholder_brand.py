"""Presek editorial placeholder palette — warm paper/ink + brand mark accents."""

from __future__ import annotations

PRESEK_MARK_LIGHT = "#c45c26"
PRESEK_MARK_DARK = "#e07a3d"

PAPER_LIGHT = "#fbfaf5"
PAPER_LIGHT_END = "#ece8df"
INK_DARK = "#141210"
INK_DARK_END = "#0a0908"

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

# (bg, spot, accent) — all hues stay in the warm editorial range.
_PALETTES_DARK: dict[str, tuple[str, str, str]] = {
    "Srbija": (INK_DARK, "#3a2218", PRESEK_MARK_DARK),
    "Makedonija": ("#181008", "#452018", "#e07a3d"),
    "Balkan": ("#101612", "#243528", "#6b8f71"),
    "Evropa": ("#121418", "#2a3038", "#78716c"),
    "Amerika": ("#101318", "#243040", "#64748b"),
    "Svet": ("#141018", "#342a38", "#9a7d8c"),
    "Sport": ("#181008", "#4a2810", "#ea580c"),
    "Tehnologija": ("#141018", "#302040", "#a16207"),
    "Ekonomija": ("#101418", "#243040", "#57534e"),
    "Hronika": ("#121212", "#2a2a2a", "#78716c"),
    "Zabava": ("#180810", "#3a1828", "#be185d"),
    "default": (INK_DARK, "#2a2420", PRESEK_MARK_DARK),
}

_PALETTES_LIGHT: dict[str, tuple[str, str, str]] = {
    "Srbija": (PAPER_LIGHT, "#f5ddd0", PRESEK_MARK_LIGHT),
    "Makedonija": ("#fdf9f6", "#f8e4d8", "#c2410c"),
    "Balkan": ("#f7faf8", "#dceee0", "#3d6b52"),
    "Evropa": ("#f8f7f5", "#e8e4de", "#57534e"),
    "Amerika": ("#f8f7f5", "#e4e8ee", "#64748b"),
    "Svet": ("#faf8fa", "#eee4ee", "#7c5c6b"),
    "Sport": ("#fdfaf6", "#ffe8d2", "#c2410c"),
    "Tehnologija": ("#faf8fc", "#ece4f4", "#92400e"),
    "Ekonomija": ("#f8f9fa", "#e4e8ec", "#57534e"),
    "Hronika": ("#f8f8f8", "#e8e8e8", "#57534e"),
    "Zabava": ("#fdf8fa", "#f8e4ee", "#be185d"),
    "default": (PAPER_LIGHT, "#f0e8e0", PRESEK_MARK_LIGHT),
}


def category_palette(category_key: str, *, light: bool) -> tuple[str, str, str]:
    table = _PALETTES_LIGHT if light else _PALETTES_DARK
    return table.get(category_key, table["default"])


def category_palette_pair(category_key: str) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    return category_palette(category_key, light=False), category_palette(category_key, light=True)


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
  <rect x="48" y="48" width="704" height="354" fill="rgba(255,255,255,0.35)" stroke="#d9d5c8"/>
  <rect x="48" y="48" width="5" height="354" fill="{PRESEK_MARK_LIGHT}"/>
  <text x="80" y="96" font-family="system-ui,sans-serif" font-size="10" font-weight="800" letter-spacing="3" fill="#686257">PREGLED VESTI</text>
  <text x="80" y="240" font-family="Georgia,serif" font-size="34" font-weight="900" fill="#101010">{label}</text>
</svg>'''
