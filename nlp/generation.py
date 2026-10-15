"""Stub: nlp.generation removed in mk-only simplify."""


def compare_cluster_sources(*a, **kw):
    return {}


def generate_daily_brief_fallback(*a, **kw):
    return ""


# The cut-П mark from web/public/logo.svg (viewBox 11 7 82 82): ink top bar, accent legs.
_MARK_TOP = "20,15 80,15 80,42.8 62,47.12 62,33 38,33 38,52.88 20,57.2"
_MARK_LEFT = "20,57.2 38,52.88 38,85 20,85"
_MARK_RIGHT = "62,47.12 80,42.8 80,85 62,85"

_SECTION_LABELS_MK = {
    "Srbija": "СРБИЈА",
    "Makedonija": "МАКЕДОНИЈА",
    "Balkan": "БАЛКАН",
    "Evropa": "ЕВРОПА",
    "Amerika": "АМЕРИКА",
    "Svet": "СВЕТ",
    "Sport": "СПОРТ",
    "Tehnologija": "ТЕХНОЛОГИЈА",
    "Ekonomija": "ЕКОНОМИЈА",
    "Hronika": "ХРОНИКА",
    "Zabava": "КУЛТУРА",
}


def generate_local_placeholder(cid="", title="", category="", theme=None, lang="sr", *a, **kw):
    """Branded SVG placeholder for proxied/fallback images.

    The card sits next to its own headline, so it carries no text from the story:
    the Presek mark on the theme's paper (or ink, in dark mode), tinted by section.
    The mark is centred because thumbnails crop the 16:9 frame to its middle square.
    """
    import html as _html

    from nlp.placeholder_brand import (
        INK_DARK_TEXT,
        INK_LIGHT_TEXT,
        MUTED_DARK,
        MUTED_LIGHT,
        category_palette,
    )

    dark = str(theme or "").lower() == "dark"
    lang = str(lang or "sr").lower()

    key = _placeholder_palette_key(str(category or ""))
    bg, bg_end, accent = category_palette(key, light=not dark)
    ink = INK_DARK_TEXT if dark else INK_LIGHT_TEXT
    muted = MUTED_DARK if dark else MUTED_LIGHT
    if lang.startswith("mk"):
        section = _SECTION_LABELS_MK.get(key, "")
        brand = "PRESEK.MK"
    else:
        section = str(category or "").strip().upper()[:24] if key != "default" else ""
        brand = "PRESEK"

    section_node = (
        f'<text x="40" y="414" font-family="system-ui,sans-serif" font-size="12" font-weight="700" '
        f'letter-spacing="3" fill="{accent}">{_html.escape(section)}</text>'
        if section
        else ""
    )

    return f'''<svg width="800" height="450" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="{bg_end}"/>
    </linearGradient>
    <pattern id="rule" width="800" height="18" patternUnits="userSpaceOnUse">
      <rect width="800" height="1" fill="{ink}" fill-opacity="0.05"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#rule)"/>
  <g transform="translate(400 215) scale(3.1) translate(-52 -48)">
    <polygon points="{_MARK_TOP}" fill="{ink}" fill-opacity="0.82" transform="translate(4 -4)"/>
    <polygon points="{_MARK_LEFT}" fill="{accent}"/>
    <polygon points="{_MARK_RIGHT}" fill="{accent}"/>
  </g>
  <rect x="0" y="438" width="800" height="12" fill="{accent}"/>
  {section_node}
  <text x="760" y="414" text-anchor="end" font-family="system-ui,sans-serif" font-size="12" font-weight="700" letter-spacing="3" fill="{muted}">{brand}</text>
</svg>'''


def _placeholder_palette_key(category: str) -> str:
    c = str(category or "").lower()
    if any(
        k in c
        for k in (
            "sport",
            "fudbal",
            "košarka",
            "kosarka",
            "tenis",
            "liga",
            "gol",
            "спорт",
            "фудбал",
            "кошарка",
            "тенис",
            "лига",
            "гол",
        )
    ):
        return "Sport"
    if any(k in c for k in ("ekonom", "biznis", "finans", "berza", "економ", "бизнис", "финанс", "берза")):
        return "Ekonomija"
    if any(k in c for k in ("tehnolog", "nauka", "digital", "технолог", "наука", "дигитал")):
        return "Tehnologija"
    if any(k in c for k in ("kultur", "umetnost", "film", "muzik", "култур", "уметност", "филм", "музик")):
        return "Zabava"
    if any(k in c for k in ("makedon", "skopje", "скопје", "македон")):
        return "Makedonija"
    if any(k in c for k in ("srbija", "beograd", "србија", "белград")):
        return "Srbija"
    if "balkan" in c or "балкан" in c:
        return "Balkan"
    if any(k in c for k in ("evrop", "europe", "европ")):
        return "Evropa"
    if any(k in c for k in ("amerik", "sad", "америк", "сад")):
        return "Amerika"
    if any(k in c for k in ("svet", "world", "свет")):
        return "Svet"
    if "hronika" in c or "хроника" in c:
        return "Hronika"
    if "zabava" in c or "забава" in c:
        return "Zabava"
    return "default"


def summarize_article_fallback(*a, **kw):
    return ""


def summarize_locally(*a, **kw):
    return ""


def synthesize_cluster_fallback(*a, **kw):
    return ""


def _extract_sports_scores(*a, **kw):
    return []


def _extract_number_tokens(*a, **kw):
    return []
