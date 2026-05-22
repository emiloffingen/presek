from __future__ import annotations

import html
import re


def clean_extracted_article_text(text: str) -> str:
    """Remove common feed/page chrome that text extractors mix into article bodies."""
    if not text:
        return ""

    text = html.unescape(str(text))
    text = re.sub(r"^\s*IZVORNI ZAPIS\s*(?:\([^)]+\))?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*.{0,500}?\bPodeli\s+vest:\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\bPodeli\s+vest:\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:(?<=\s)|^)Oglas(?=\s|$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\bPročitajte\s+još:\s+(?:(?:(?!\bPročitajte\s+još:).){0,260}?\b(?:Politika|Društvo|Hronika|Svet|Ekonomija|Sport|Kultura|Zabava|Lifestyle|Biznis)\s+0\s*){1,8}",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"\bPročitajte\s+još:\s+.*?(?=(?:[\"„][A-ZČĆŠĐŽ0-9]|[A-ZČĆŠĐŽ][a-zčćšđž]+\s+(?:je|su|će|se)\b))",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"\s+(?:[a-zčćšđž0-9-]{2,}\s+){1,12}Pratite\s+nas\s+na\s+društvenim\s+mrežama:.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"\bPratite\s+nas\s+na\s+društvenim\s+mrežama:.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\bKoje\s+je\s+tvoje\s+mišljenje\s+o\s+ovoj\s+temi\?.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\bUčestvuj\s+u\s+diskusiji\s+ili\s+pročitaj\s+komentare.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\bBudite\s+prvi\s+koji\s+će\s+ostaviti\s+komentar.*$", "", text, flags=re.IGNORECASE | re.DOTALL)

    text = re.sub(r"\s+", " ", text)
    return text.strip()
