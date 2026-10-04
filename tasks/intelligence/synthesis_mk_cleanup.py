"""Macedonian script cleanup and Serbian→MK leak repair."""

from __future__ import annotations

import re

# Direct homoglyph map (lookalikes swap) for mixed words
HOMOGLYPHS = {
    "a": "а",
    "c": "ц",
    "e": "е",
    "o": "о",
    "p": "п",
    "x": "х",
    "y": "у",
    "j": "ј",
    "s": "с",
    "i": "и",
    "A": "А",
    "C": "Ц",
    "E": "Е",
    "O": "О",
    "P": "П",
    "X": "Х",
    "Y": "У",
    "J": "Ј",
    "S": "С",
    "I": "И",
    "K": "К",
    "M": "М",
    "T": "Т",
    "B": "В",
    "H": "Н",
    "R": "Р",
}

# Serbian/Bulgarian/Russian to Macedonian leak mappings (Cyrillic and Latin).
# Applied case-insensitively as whole words.
LEAKS = {
    "током": "во текот на",
    "између": "меѓу",
    "измеѓу": "меѓу",
    "такође": "исто така",
    "како би": "за да",
    "да ли": "дали",
    "нису": "не се",
    "јесте": "е",
    "председник": "претседател",
    "премијер": "премиер",
    "министар": "министер",
    "саопштење": "соопштение",
    "тужилаштво": "обвинителство",
    "оптужница": "обвинение",
    "сарадња": "соработка",
    "састанак": "состанок",
    "земља": "земја",
    "недеља": "недела",
    "понедељак": "понеделник",
    "уторак": "вторник",
    "четвртак": "четврток",
    "петак": "петок",
    "субота": "сабота",
    "јануар": "јануари",
    "фебруар": "февруари",
    "октобар": "октомври",
    "новембар": "ноември",
    "децембар": "декември",
    "догађај": "настан",
    "због": "поради",
    "учешће": "учество",
    "предузеће": "претпријатие",
    "грађани": "граѓани",
    "грађанин": "граѓанин",
    "држављанин": "државјанин",
    "држављани": "државјани",
    "унутрашњи": "внатрешен",
    "спољашњи": "надворешен",
    "избеглице": "бегалци",
    "ухапшен": "уапсен",
    "ухапшени": "уапсени",
    "помоћ": "помош",
    "савез": "сојуз",
    "захтев": "барање",
    "веза": "врска",
    "избор": "избор",
    "избори": "избори",
    "решење": "решение",
    "односи": "односи",
    "већ": "веќе",
    # Bulgarian / Russian leaks observed in generated summaries
    "обвинения": "обвинувања",
    "продължува": "продолжува",
    "продължава": "продолжува",
    "комбинацията": "комбинацијата",
    "неблагоприятни": "неповолни",
    "буђење": "будење",
    "също": "исто така",
    "който": "кој",
    "които": "кои",
    "това": "тоа",
    "този": "овој",
    "тази": "оваа",
    "тези": "овие",
    "ще": "ќе",
    "бяха": "беа",
    "български": "бугарски",
    "българия": "бугарија",
    "европейски": "европски",
    "продължи": "продолжи",
    "продължуваат": "продолжуваат",
    "противникът": "противникот",
    "изключително": "исклучително",
    "изключителна": "исклучителна",
    "изключителни": "исклучителни",
    "блъф": "блаф",
    "съюз": "сојуз",
    "беспорядок": "неред",
    "сопствения": "сопствениот",
    "новият": "новиот",
    "покойния": "покојниот",
    "помоћи": "помогне",
    "непрекъснато": "постојано",
    "достатъчно": "доволно",
    "уязвимите": "ранливите",
    "мъже": "мажи",
    "синът": "синот",
    "той": "тој",
    "няма": "нема",
    "кратък": "краток",
    "тероризъм": "тероризам",
    "участък": "дел",
    "ветерът": "ветрот",
    "прекъснувања": "прекини",
    "сърбија": "србија",
    "скъпо": "скапо",
    "оптимизъм": "оптимизам",
    "българскиот": "бугарскиот",
    "германия": "германија",
    "оръжја": "оружја",
    "материјалът": "материјалот",
    "твърди": "тврди",
    "късно": "доцна",
    "свързува": "поврзува",
    "юбилеј": "јубилеј",
    "спасявање": "спасување",
    # Latin leaks
    "tokom": "во текот на",
    "između": "меѓу",
    "takođe": "исто така",
    "kako bi": "за да",
    "da li": "дали",
    "nisu": "не се",
    "jeste": "е",
    "predsednik": "претседател",
    "premijer": "премиер",
    "ministar": "министер",
    "saopštenje": "соопштение",
    "tužilaštvo": "обвинителство",
    "optužnica": "обвинение",
    "saradnja": "соработка",
    "sastanak": "состанок",
    "zemlja": "земја",
    "nedelja": "недела",
    "ponedeljak": "понеделник",
    "utorak": "вторник",
    "četvrtak": "четврток",
    "petak": "петок",
    "subota": "сабота",
    "januar": "јануари",
    "februar": "февруари",
    "oktobar": "октомври",
    "novembar": "ноември",
    "decembar": "декември",
    "događaj": "настан",
    "zbog": "поради",
    "učešće": "учество",
    "preduzeće": "претпријатие",
    "građani": "граѓани",
    "građanin": "граѓанин",
    "državljanin": "државјанин",
    "državljani": "државјани",
    "unutrašnji": "внатрешен",
    "spoljašnji": "надворешен",
    "izbeglice": "бегалци",
    "uhapšen": "уапсен",
    "uhapšeni": "уапсени",
    "pomoć": "помош",
    "savez": "сојуз",
    "zahtev": "барање",
    "već": "веќе",
}

# Full Latin phonetic transliteration table
PHONETIC = {
    "Lj": "Љ",
    "lj": "љ",
    "Nj": "Њ",
    "nj": "њ",
    "Dž": "Џ",
    "dž": "џ",
    "Gj": "Ѓ",
    "gj": "ѓ",
    "Kj": "Ќ",
    "kj": "ќ",
    "Dz": "Ѕ",
    "dz": "ѕ",
    "A": "А",
    "a": "а",
    "B": "Б",
    "b": "б",
    "V": "В",
    "v": "в",
    "G": "Г",
    "g": "г",
    "D": "Д",
    "d": "д",
    "Đ": "Ѓ",
    "đ": "ѓ",
    "E": "Е",
    "e": "е",
    "Ž": "Ж",
    "ž": "ж",
    "Z": "З",
    "z": "з",
    "I": "И",
    "i": "и",
    "J": "Ј",
    "j": "ј",
    "K": "К",
    "k": "к",
    "L": "Л",
    "l": "л",
    "M": "М",
    "m": "м",
    "N": "Н",
    "n": "н",
    "O": "О",
    "o": "о",
    "P": "П",
    "p": "п",
    "R": "Р",
    "r": "р",
    "S": "С",
    "s": "с",
    "T": "Т",
    "t": "т",
    "Ć": "Ќ",
    "ć": "ќ",
    "U": "У",
    "u": "у",
    "F": "Ф",
    "f": "ф",
    "H": "Х",
    "h": "х",
    "C": "Ц",
    "c": "ц",
    "Č": "Ч",
    "č": "ч",
    "Š": "Ш",
    "š": "ш",
}

# Letters that do not exist in the Macedonian alphabet. Mapped to the closest
# MK letter as a best-effort fallback. Ambiguous Bulgarian "ъ"/"ю" are handled
# word-by-word in LEAKS instead (a blind map corrupts words like продължи).
FOREIGN_LETTERS = {
    "й": "ј",
    "я": "ја",
    "ы": "и",
    "э": "е",
    "ё": "е",
    "ћ": "ќ",
    "ђ": "ѓ",
    "і": "и",
    "ї": "ји",
    "є": "е",
    "ґ": "г",
}

_TOKEN_RE = re.compile(r"^[a-zA-Z\u0400-\u04FF\u0160\u0161\u0106\u0107\u010C\u010D\u0110\u0111\u017D\u017E]+$")
_SPLIT_RE = re.compile(r'(\s+|[.,!?;:()""\'\'„“»«\[\]]+)')


def _replace_word(word: str) -> str | None:
    """Return the LEAKS replacement for a word (case preserved), else None."""
    replacement = LEAKS.get(word.lower())
    if replacement is None:
        return None
    if word[0].isupper():
        replacement = replacement[0].upper() + replacement[1:]
    return replacement


def repair_foreign_leaks(text: str) -> str:
    """Targeted repair for already-published text: replace known
    Serbian/Bulgarian/Russian word leaks and map letters outside the Macedonian
    alphabet. Does NOT transliterate Latin, so brand names and URLs survive.
    """
    if not text:
        return text
    out: list[str] = []
    for token in _SPLIT_RE.split(text):
        if not token or not _TOKEN_RE.match(token):
            out.append(token)
            continue
        if token.startswith("[") and token.endswith("]"):
            out.append(token)
            continue
        fixed = _replace_word(token)
        if fixed is not None:
            out.append(fixed)
            continue
        if any(c in FOREIGN_LETTERS for c in token):
            token = "".join(FOREIGN_LETTERS.get(c, c) for c in token)
        out.append(token)
    return "".join(out)


def _clean_macedonian_spelling_and_script(text: str) -> str:
    if not text:
        return text

    def clean_word(word: str) -> str:
        if word.startswith("[") and word.endswith("]"):
            return word

        fixed = _replace_word(word)
        if fixed is not None:
            return fixed

        if any(c in FOREIGN_LETTERS for c in word):
            word = "".join(FOREIGN_LETTERS.get(c, c) for c in word)

        has_cyrillic = any("\u0400" <= char <= "\u04ff" for char in word)
        has_latin = any(("a" <= char.lower() <= "z") for char in word)

        if has_cyrillic and has_latin:
            chars = []
            for c in word:
                if c in HOMOGLYPHS:
                    chars.append(HOMOGLYPHS[c])
                else:
                    chars.append(c)
            return "".join(chars)

        if has_latin and not has_cyrillic:
            if word.isupper() and len(word) in (2, 3, 4, 5):
                return word

            res = word
            for lat, cyr in sorted(PHONETIC.items(), key=lambda x: len(x[0]), reverse=True):
                res = res.replace(lat, cyr)
            return res

        return word

    cleaned_tokens = []
    for token in _SPLIT_RE.split(text):
        if not token:
            continue
        cleaned_tokens.append(clean_word(token) if _TOKEN_RE.match(token) else token)

    return "".join(cleaned_tokens)
