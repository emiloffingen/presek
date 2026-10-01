"""Stub: nlp.generation removed in mk-only simplify."""


def compare_cluster_sources(*a, **kw):
    return {}


def generate_daily_brief_fallback(*a, **kw):
    return ""


def generate_local_placeholder(cid="", title="", category="", theme=None, lang="sr", *a, **kw):
    """Branded SVG placeholder for proxied/fallback images.

    Restored (was a stub returning ""). Renders the story title over the
    category palette so broken images degrade to an editorial card, not void.
    """
    import html as _html

    from nlp.placeholder_brand import category_palette

    title = str(title or "vest").strip() or "vest"
    if len(title) > 90:
        title = title[:87].rstrip() + "…"
    category = str(category or "vesti").strip() or "vesti"
    dark = str(theme or "").lower() == "dark"
    lang = str(lang or "sr").lower()

    key = _placeholder_palette_key(category)
    bg, spot, accent = category_palette(key, light=not dark)
    ink = "#f5f0e8" if dark else "#141210"
    muted = "#a8a29e" if dark else "#686257"
    kicker = "ПРЕГЛЕД ВЕСТИ" if lang.startswith("mk") else "PREGLED VESTI"
    brand = "PRESEK.MK" if lang.startswith("mk") else "PRESEK"

    lines = _wrap_title(title)
    y = 200
    text_nodes = []
    for line in lines[:3]:
        text_nodes.append(
            f'<text x="80" y="{y}" font-family="Georgia,serif" font-size="30" font-weight="900" fill="{ink}">'
            f"{_html.escape(line)}</text>"
        )
        y += 44

    return f'''<svg width="800" height="450" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="{spot}"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect x="48" y="48" width="704" height="354" fill="none" stroke="{accent}" stroke-opacity="0.35"/>
  <rect x="48" y="48" width="5" height="354" fill="{accent}"/>
  <text x="80" y="96" font-family="system-ui,sans-serif" font-size="10" font-weight="800" letter-spacing="3" fill="{muted}">{kicker}</text>
  {"".join(text_nodes)}
  <text x="80" y="380" font-family="system-ui,sans-serif" font-size="11" font-weight="800" letter-spacing="2" fill="{accent}">{brand}</text>
  <text x="720" y="380" text-anchor="end" font-family="system-ui,sans-serif" font-size="11" fill="{muted}">{_html.escape(category[:24])}</text>
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


def _wrap_title(title: str, width: int = 28, max_lines: int = 3) -> list[str]:
    words, lines, current = str(title).split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines or [str(title)[:width]]


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
