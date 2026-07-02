from __future__ import annotations

import html
import re


def clean_extracted_article_text(text: str) -> str:
    """Remove common feed/page chrome that text extractors mix into article bodies."""
    if not text:
        return ""

    text = html.unescape(str(text))

    # Strips "IZVORNI ZAPIS" or "ИЗВОРЕН ЗАПИС" (and Latin/Cyrillic variations for both Serbian and Macedonian)
    text = re.sub(
        r"^\s*(?:(?:IZVORNI|IZVOREN)\s+ZAPIS|(?:ИЗВОРНИ|ИЗВОРЕН)\s+ЗАПИС)\s*(?:\([^)]+\))?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # "Podeli vest" or "Сподели вест" / "Сподели ја веста" (and variations)
    text = re.sub(
        r"^\s*.{0,500}?\b(?:Podeli\s+vest|Spodeli\s+vest|Подели\s+вест|Сподели\s+вест|Сподели\s+ја\s+веста)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"\b(?:Podeli\s+vest|Spodeli\s+vest|Подели\s+вест|Сподели\s+вест|Сподели\s+ја\s+веста)\s*:\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # "Oglas" or "Оглас"
    text = re.sub(
        r"(?:(?<=\s)|^)(?:Oglas|Оглас)(?=\s|$)", " ", text, flags=re.IGNORECASE
    )

    # "Pročitajte još" and other variations / categories in both alphabets
    read_more_pattern = r"(?:Pročitajte\s+još|Прочитајте\s+још|Pročitajte\s+više|Прочитајте\s+више|Procitajte\s+povece|Прочитајте\s+повеќе|Прочитајте\s+уште)"
    categories_pattern = (
        r"(?:Politika|Društvo|Hronika|Svet|Ekonomija|Sport|Kultura|Zabava|Lifestyle|Biznis|"
        r"Политика|Друштво|Хроника|Свет|Економија|Спорт|Култура|Забава|Бизнис|Македонија)"
    )
    text = re.sub(
        rf"\b{read_more_pattern}\s*:\s*(?:(?:(?!\b{read_more_pattern}).){{0,260}}?\b{categories_pattern}\s+\d+\s*){{1,10}}",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    uppercase_chars = "A-ZČĆŠĐŽА-ЯЁЂЈЉЊЋЌЏЃЅ"
    lowercase_chars = "a-zčćšđžа-яёђјљњћќџѓѕ"
    text = re.sub(
        rf"\b{read_more_pattern}\s*:\s+.*?(?=(?:[\"„][{uppercase_chars}0-9]|[{uppercase_chars}][{lowercase_chars}]+\s+(?:je|su|će|se|е|се|се|ќе|се|се)\b))",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # "Pratite nas na društvenim mrežama" and variations
    follow_us_pattern = (
        r"(?:Pratite\s+nas\s+na\s+društvenim\s+mrežama|"
        r"Пратите\s+нас\s+на\s+друштвеним\s+мрежама|"
        r"Sledete\s+ne\s+na\s+(?:socijalnite|drustvenite)\s+mrezi|"
        r"Следете\s+н?[еѐ]\s+на\s+(?:социјалните|друштвените)\s+мрежи)"
    )
    text = re.sub(
        rf"\s+(?:[a-zčćšđžа-яёђјљњћќџѓѕ0-9-]{{2,}}\s+){{1,12}}{follow_us_pattern}:?.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        rf"\b{follow_us_pattern}:?.*$", "", text, flags=re.IGNORECASE | re.DOTALL
    )

    # "Koje je tvoje mišljenje o ovoj temi?" and variations
    opinion_pattern = (
        r"(?:Koje\s+je\s+tvoje\s+mišljenje\s+o\s+ovoj\s+temi|"
        r"Које\s+је\s+твоје\s+мишљење\s+о\s+овој\s+теми|"
        r"Koe\s+e\s+tvoeto\s+mislenje\s+(?:za|o)\s+ovaa\s+tema|"
        r"Кое\s+е\s+твоето\s+мислење\s+(?:за|о)\s+оваа\s+тема)\?"
    )
    text = re.sub(rf"\b{opinion_pattern}.*$", "", text, flags=re.IGNORECASE | re.DOTALL)

    # "Učestvuj u diskusiji ili pročitaj komentare" and variations
    discussion_pattern = (
        r"(?:Učestvuj\s+u\s+diskusiji\s+ili\s+pročitaj\s+komentare|"
        r"Учествуј\s+у\s+дискусији\s+или\s+прочитај\s+коментаре|"
        r"Ucestvuvaj\s+vo\s+diskusijata\s+ili\s+procitaj\s+(?:gi\s+)?komentarite|"
        r"Учествувај\s+во\s+дискусијата\s+или\s+прочитај\s+(?:ги\s+)?коментарите)"
    )
    text = re.sub(
        rf"\b{discussion_pattern}.*$", "", text, flags=re.IGNORECASE | re.DOTALL
    )

    # "Budite prvi koji će ostaviti komentar" and variations
    be_first_pattern = (
        r"(?:Budite\s+prvi\s+koji\s+će\s+ostaviti\s+komentar|"
        r"Будите\s+први\s+који\s+ће\s+оставити\s+коментар|"
        r"Bidete\s+prvi\s+(?:koi|sto)\s+ke\s+ostavat\s+komentar|"
        r"Бидете\s+први\s+(?:кои|што)\s+ќе\s+остават\s+коментар)"
    )
    text = re.sub(
        rf"\b{be_first_pattern}.*$", "", text, flags=re.IGNORECASE | re.DOTALL
    )

    # Tag blocks
    text = re.sub(
        r"\b(?:Tagovi|Тагови)\s*:\s*.*?(?=(?:Крадењето|Бидете|ИЗВОРЕН|ИЗВОРНИ|IZVORNI|$))",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Copyright warnings (Macedonian / Serbian)
    copyright_warning = (
        r"Крадењето\s+авторски\s+текстови\s+е\s+казниво\s+со\s+закон\.\s+"
        r"Преземањето\s+на\s+авторски\s+содржини\s+\(текстови\)\s+од\s+оваа\s+страница\s+е\s+дозволено\s+само\s+делумно\s+и\s+со\s+ставање\s+хиперлинк\s+до\s+содржината\s+што\s+се\s+цитира\."
    )
    text = re.sub(copyright_warning, " ", text, flags=re.IGNORECASE)

    # "Бидете информирани следете не на Facebook" or similar
    be_informed = r"Бидете\s+информирани\s*(?:следете\s+не\s+на\s+Facebook)?"
    text = re.sub(be_informed, " ", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text)
    return text.strip()
