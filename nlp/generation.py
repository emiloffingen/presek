import logging
import math
import re
from collections import Counter

from core.trending import STOPWORDS

log = logging.getLogger(__name__)
from nlp.utils import (
    _articles_cache_key,
    _cache_get,
    _cache_set,
    _comparison_cache,
    _normalize_articles_for_local_use,
    _question_evidence_cache,
    cleanAndDecode,
    deShout,
)
from utils import record_runtime_event
from core.language import transliterate_cyr_to_lat

_T = {
    "mk": {
        "klucen_razvoj": "Клучен развој",
        "nastan": "Настан",
        "detali": "Детали",
        "fokus": "Фокус",
        "pokrienost": "Медиумска покриеност",
        "izvori": "извори",
        "otvoreno": "Отворено",
        "otvoreno_lower": "отворено",
        "konsenzus": "Консензус",
        "nijansi": "Нијанси",
        "dneven_brifing": "Дневен брифинг",
        "nema_vesti": "Нема доволно достапни вести.",
        "dinamika_den": "Динамика на денот",
        "klucni_nastani": "Клучни настани",
        "analiticki_uvid": "Аналитички увид",
        "ostanuva_otvoreno": "Останува отворено",
        "kontekst_razliki": "Контекст и разлики",
        "golemata_slika": "Големата Слика",
        "globalni_lokalni_oski": "Клучни теми",
        "mediumski_radar": "Медиумски Радар",
        "sto_da_se_sledi": "Што да се следи",
        "klucen_aspekt": "Клучен аспект",
        "zosto_vazno": "Зошто е важно",
        "beleska": "Белешка",
        "sodrzina_generirana": "Содржината е генерирана преку локална системска анализа.",
        "povece_mediumi": "Темата ја следат повеќе медиуми.",
        "sistemski_pregled": "Преглед базиран на {count} извори.",
        "potvrda_osnovna": "{s1} и {s2} ја потврдуваат истата основна линија на настанот.",
        "denesniot_pregled": "Денешниот преглед е обележан со: {text}.",
        "denot_obeleza": "Денот го обележа {text1}, а внимание привлекува и {text2}.",
        "potencijalna_promena": "Потенцијална промена во политичката моќ и регионалните стратегии.",
        "direktno_vlijanie": "Директно влијание врз економската стабилност и стандардот на граѓаните.",
        "potvrden_razvoj": "Основната линија е потврдена во {count} редакции; следниот важен податок е официјална потврда на деталите.",
        "faza_razvoj": "Настанот е во фаза на развој и се очекуваат понатамошни официјални потврди.",
        "najdirektno": "Најдиректно од достапните извори: {text}",
        "sto_se_slucuva": "Што се случува",
        "sledeno_od": "Следено од",
        "znacenje": "Значење",
        "sto_ostanuva": "Што останува отворено",
        "urednicki_pregled": "Уреднички преглед базиран на {count} извори.",
        "izvori_pratat_ista_linija": "Достапните извори ја следат истата основна линија, но не даваат еднаква тежина на сите детали.",
        "naredno_pratenje": "Следниот сигнал ќе биде дали официјалните актери ќе ги потврдат деталите што сега остануваат недоволно разјаснети.",
    },
    "sr": {
        "klucen_razvoj": "Ključni razvoj",
        "nastan": "Događaj",
        "detali": "Detalji",
        "fokus": "Fokus",
        "pokrienost": "Medijska pokrivenost",
        "izvori": "izvori",
        "otvoreno": "Otvoreno",
        "otvoreno_lower": "otvoreno",
        "konsenzus": "Konsenzus",
        "nijansi": "Nijanse",
        "dneven_brifing": "Dnevni brifing",
        "nema_vesti": "Nema dovoljno dostupnih vesti.",
        "dinamika_den": "Dinamika dana",
        "klucni_nastani": "Ključni događaji",
        "analiticki_uvid": "Analitički uvid",
        "ostanuva_otvoreno": "Ostaje otvoreno",
        "kontekst_razliki": "Kontekst i razlike",
        "golemata_slika": "Velika Slika",
        "globalni_lokalni_oski": "Ključne teme",
        "mediumski_radar": "Medijski Radar",
        "sto_da_se_sledi": "Šta pratiti",
        "klucen_aspekt": "Ključni aspekt",
        "zosto_vazno": "Zašto je važno",
        "beleska": "Beleška",
        "sodrzina_generirana": "Sadržaj je generisan putem lokalne sistemske analize.",
        "povece_mediumi": "Temu prati više medija.",
        "sistemski_pregled": "Pregled baziran na {count} izvora.",
        "potvrda_osnovna": "{s1} i {s2} potvrđuju istu osnovnu liniju događaja.",
        "denesniot_pregled": "Današnji pregled je obeležen sa: {text}.",
        "denot_obeleza": "Dan je obeležio {text1}, a pažnju privlači i {text2}.",
        "potencijalna_promena": "Potencijalna promena u političkoj moći i regionalnim strategijama.",
        "direktno_vlijanie": "Direktan uticaj na ekonomsku stabilnost i standard građana.",
        "potvrden_razvoj": "Osnovnu liniju potvrđuje {count} redakcija; sledeći važan podatak je zvanična potvrda detalja.",
        "faza_razvoj": "Događaj je u fazi razvoja i očekuju se dalja službena potvrđivanja.",
        "najdirektno": "Najdirektnije iz dostupnih izvora: {text}",
        "sto_se_slucuva": "Šta se dešava",
        "sledeno_od": "Prati",
        "znacenje": "Značaj",
        "sto_ostanuva": "Šta ostaje otvoreno",
        "urednicki_pregled": "Urednički pregled baziran na {count} izvora.",
        "izvori_pratat_ista_linija": "Dostupni izvori prate istu osnovnu liniju, ali ne daju jednaku težinu svim detaljima.",
        "naredno_pratenje": "Sledeći signal biće da li će zvanični akteri potvrditi detalje koji za sada ostaju nedovoljno razjašnjeni.",
    },
}

from nlp.keywords import (
    SOURCE_NOISE_WORDS,
    TAG_NOISE_WORDS,
    _extract_capitalized_phrases,
    _sentence_tokens,
    extract_keyphrases_locally,
    normalize_tag_name,
)
from nlp.text_processing import _is_noisy_summary_sentence, _normalize_summary_sentence, _jaccard_similarity


def _split_briefing_sentences(text):
    protected = re.sub(
        r"\b([A-Z\u0400-\u04FF]\.(?:[A-Z\u0400-\u04FF]\.)+)",
        lambda match: match.group(1).replace(".", "<<DOT>>"),
        str(text or ""),
    )
    sentences = re.split(r"(?<=[.!?])\s+", protected)
    return [sentence.replace("<<DOT>>", ".").strip() for sentence in sentences if sentence.strip()]


def _is_incomplete_briefing_fragment(text):
    clean = str(text or "").strip().rstrip(".")
    if not clean or len(clean) < 20:
        return True
    if clean.endswith("…"):
        return True
    if re.search(r"\b[A-Za-z\u0400-\u04FF]\.[A-Za-z\u0400-\u04FF]\.?$", clean):
        return True
    if re.search(r"\b[A-Za-z\u0400-\u04FF]{1,2}\.$", clean):
        return True
    if clean.endswith(",") or re.search(
        r"\b(i|a|da|koji|koja|koje|dok|zbog|za|od|na|koe|koi|и|а|што|додека|кој|која|кое|за|од|на)$",
        clean,
        re.IGNORECASE,
    ):
        return True
    return False


def _briefing_story_label(cluster, lang="mk"):
    title = _clean_briefing_snippet(cluster.get("title"))
    if title:
        return title
    return _condense_briefing_update(_extract_briefing_update(cluster, lang=lang), max_chars=120)


def _build_briefing_intro_line(clusters, lang="mk"):
    t = _T.get(lang, _T["mk"])
    if not clusters:
        return ""

    if len(clusters) >= 2:
        lead_label = _briefing_story_label(clusters[0], lang=lang)
        second_label = _briefing_story_label(clusters[1], lang=lang)
        if lead_label and second_label:
            if lang == "sr":
                return (
                    f"Danas se izdvajaju dve teme: {lead_label} i {second_label}."
                )
            return (
                f"Денес се издвојуваат две теми: {lead_label} и {second_label}."
            )

    lead_update = _condense_briefing_update(_extract_briefing_update(clusters[0], lang=lang), max_chars=220)
    if _is_incomplete_briefing_fragment(lead_update):
        lead_update = _briefing_story_label(clusters[0], lang=lang)
    if lead_update:
        return t["denesniot_pregled"].format(text=lead_update)
    return ""


def _briefing_coverage_source_count(clusters):
    return sum(int(cluster.get("source_count") or 1) for cluster in clusters)


def _extract_briefing_watch_signal(cluster, lang="mk"):
    t = _T.get(lang, _T["mk"])
    open_point = _normalize_briefing_line(cluster.get("open_point"))
    if open_point:
        return open_point

    diff = _normalize_briefing_line(cluster.get("difference_point"))
    if diff:
        return diff

    source_count = int(cluster.get("source_count") or 1)
    if source_count >= 2:
        if lang == "sr":
            return (
                f"Tražiti sledeću zvaničnu potvrdu ili novu brojku; temu trenutno potvrđuje "
                f"{source_count} redakcija."
            )
        return (
            f"Следниот сигнал е официјална потврда или нова бројка; темата моментално ја потврдуваат "
            f"{source_count} редакции."
        )

    return t["naredno_pratenje"]


def _clean_briefing_snippet(text):
    clean = str(text or "").strip()
    if not clean:
        return ""
    clean = re.sub(
        r"^[A-Za-z\u0400-\u04FF][^,]{0,40},\s*\d{1,2}\s+[^\d]{3,20}\s+\d{4}\s*\([^)]{2,20}\)\s*[-–—]\s*",
        "",
        clean,
    )
    clean = re.sub(
        r"^(Beograd|Bitola|Ohrid|Tetovo|Stip|Prilep|Veles|Kumanovo|Berovo|Dojran|Београд|Битола|Охрид|Тетово|Штип|Прилеп|Велес|Куманово|Берово|Дојран)\s*,\s*",
        "",
        clean,
    )
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _normalize_briefing_line(text):
    clean = _clean_briefing_snippet(text)
    clean = re.sub(
        r"(?:Форум\s+оф\s+)?Инцидент\s+Респонсе\s+анд\s+Сецурит[yу]\s+Теамс|Сецурит[yу]\s+Теамс",
        "тимови за одговор на безбедносни инциденти",
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"^[\-•*#\d.\)\s]+", "", clean).strip()
    clean = re.sub(r"\[\d+\]", "", clean).strip()
    clean = re.sub(
        r"^(Sto e novoto|Sto se menuva|Zosto e vazno|Sto se slucuva|Sto e potvrdeno|Pokrienost|kontekst|Razlika|otvoreno)\s*:\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\s+", " ", clean).strip(" .;:")
    return clean


def _briefing_lines_from_text(text, *, max_lines=3):
    lines = []
    for raw in str(text or "").splitlines():
        clean = _normalize_briefing_line(raw)
        if not clean or len(clean) < 12:
            continue
        if clean.casefold() in {item.casefold() for item in lines}:
            continue
        lines.append(clean)
        if len(lines) >= max_lines:
            break
    return lines


def _extract_briefing_update(cluster, lang="mk"):
    cluster = cluster or {}

    # 1. Try to use synthesis if available (it should already be diverse)
    synthesis_lines = _briefing_lines_from_text(
        cluster.get("cluster_summary") or cluster.get("generated_article") or "",
        max_lines=4,
    )
    if synthesis_lines:
        return synthesis_lines[0]

    # 2. Extract from description, explicitly avoiding title repetition
    clean_title = _clean_briefing_snippet(cluster.get("title"))
    clean_description = _clean_briefing_snippet(cluster.get("description"))

    if not clean_description or len(clean_description) < 20:
        return clean_title  # Fallback if no description

    title_terms = set(_extract_terms(clean_title))
    description_sentences = [
        s.strip() for s in _split_briefing_sentences(clean_description) if len(s.strip()) > 20
    ]

    for sentence in description_sentences:
        sent_terms = set(_extract_terms(sentence))
        if not sent_terms:
            continue
        # If the sentence is mostly different from the title, use it
        overlap = len(title_terms & sent_terms) / len(sent_terms) if sent_terms else 1.0
        if overlap < 0.7:
            return sentence

    # 3. If no unique sentence found, use localized summary but skip title-only lines
    summary = _clean_briefing_snippet(
        summarize_locally(f"{clean_title}. {clean_description}", sentence_count=1, title=clean_title).strip()
    )

    # Final check: if summary is still just the title, try to return first 140 chars of description
    if summary.casefold() == clean_title.casefold() and clean_description:
        return clean_description[:140]

    result = summary or clean_description or clean_title
    if _is_incomplete_briefing_fragment(result):
        for sentence in description_sentences:
            if len(sentence) >= 35 and not _is_incomplete_briefing_fragment(sentence):
                return sentence
        if clean_description and len(clean_description) >= 35:
            return clean_description[:180].rstrip(" ,;:")
    return result


def _extract_briefing_importance(cluster, lang="mk"):
    cluster = cluster or {}
    t = _T.get(lang, _T["mk"])
    diff = _normalize_briefing_line(cluster.get("difference_point"))
    if diff:
        return diff

    open_point = _normalize_briefing_line(cluster.get("open_point"))
    if open_point:
        return open_point

    # Use the second line of synthesis if available
    synthesis_lines = _briefing_lines_from_text(
        cluster.get("cluster_summary") or cluster.get("generated_article") or "",
        max_lines=4,
    )
    if len(synthesis_lines) >= 2:
        return synthesis_lines[1]

    clean_title = _clean_briefing_snippet(cluster.get("title"))
    clean_description = _clean_briefing_snippet(cluster.get("description"))
    context = f"{clean_title} {clean_description}".casefold()

    # Check for domain-specific impact markers
    if any(term in context for term in ("izbori", "glasanje", "parlamentar", "избори", "гласање", "парламентар")):
        return t["potencijalna_promena"]
    if any(
        term in context for term in ("cena", "poskap", "inflacija", "budzet", "цена", "поскап", "инфлација", "буџет")
    ):
        return t["direktno_vlijanie"]

    # 1. Fact Extraction: Find the most informative sentence in description that adds new info
    # We use a stricter overlap check than the 'update' to ensure importance is different
    description_lines = _briefing_lines_from_text(clean_description, max_lines=6)
    title_terms = set(_extract_terms(clean_title))
    update_text = _extract_briefing_update(cluster, lang=lang)
    update_terms = set(_extract_terms(update_text))

    for line in description_lines:
        line_terms = set(_extract_terms(line))
        if not line_terms:
            continue
        t_overlap = len(title_terms & line_terms) / len(line_terms)
        u_overlap = len(update_terms & line_terms) / len(line_terms)

        # We want a line that isn't title AND isn't the update
        if t_overlap < 0.6 and u_overlap < 0.6 and len(line) > 35:
            return _condense_briefing_update(line, max_chars=160)

    # 2. Coverage-based fallback
    source_count = cluster.get("source_count") or 1
    if source_count >= 2:
        return t["potvrden_razvoj"].format(count=source_count)

    for line in description_lines:
        if len(line) >= 35 and not _is_incomplete_briefing_fragment(line):
            line_terms = set(_extract_terms(line))
            if line_terms and len(title_terms & line_terms) / len(line_terms) < 0.75:
                return _condense_briefing_update(line, max_chars=160)

    return t["faza_razvoj"]


def _condense_briefing_update(text, *, max_chars=180):
    clean = _normalize_briefing_line(text)
    if not clean:
        return ""
    sentences = _split_briefing_sentences(clean)
    candidate = sentences[0].strip()

    if _is_incomplete_briefing_fragment(candidate) and len(sentences) > 1:
        candidate = f"{candidate} {sentences[1].strip()}"

    if len(candidate) < 30 and len(sentences) > 1:
        candidate = f"{candidate} {sentences[1].strip()}"

    candidate = candidate.rstrip(" .,;:")
    if len(candidate) <= max_chars and not _is_incomplete_briefing_fragment(candidate):
        return candidate

    if len(candidate) > max_chars:
        truncated = candidate[: max_chars - 1].rstrip(" ,;:")
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        if len(truncated) >= 40 and not _is_incomplete_briefing_fragment(truncated):
            return truncated + "…"
        first_sentence = sentences[0].strip().rstrip(" .,;:")
        if first_sentence and len(first_sentence) <= max_chars + 40:
            return first_sentence

    if _is_incomplete_briefing_fragment(candidate):
        for sentence in sentences[1:]:
            sentence = sentence.strip().rstrip(" .,;:")
            if len(sentence) >= 35 and not _is_incomplete_briefing_fragment(sentence):
                return sentence[:max_chars].rstrip(" ,;:")

    return candidate


def _extract_briefing_focus_point(cluster, lang="mk"):
    text = _condense_briefing_update(_extract_briefing_update(cluster, lang=lang), max_chars=160)
    if not text:
        text = _clean_briefing_snippet(cluster.get("title"))
    return _normalize_briefing_line(text).rstrip(" .,;:")


def _dedupe_briefing_clusters(clusters, limit=4, lang="mk"):
    deduped = []
    seen_titles = set()
    seen_updates = []

    for cluster in clusters:
        title = _clean_briefing_snippet(cluster.get("title"))
        title_key = title.casefold()
        if title_key and title_key in seen_titles:
            continue

        update = _extract_briefing_focus_point(cluster, lang=lang)
        update_tokens = set(_extract_terms(update))
        duplicate_update = False
        for other_tokens in seen_updates:
            if not update_tokens or not other_tokens:
                continue
            overlap = len(update_tokens & other_tokens) / max(1, min(len(update_tokens), len(other_tokens)))
            if overlap >= 0.8:
                duplicate_update = True
                break
        if duplicate_update:
            continue

        deduped.append(cluster)
        if title_key:
            seen_titles.add(title_key)
        if update_tokens:
            seen_updates.append(update_tokens)
        if len(deduped) >= limit:
            break

    return deduped


def _is_penalized_briefing_title(title):
    clean = str(title or "").strip()
    lowered = clean.casefold()
    if re.match(r"^[A-Za-z\u0400-\u04FF0-9\-]{2,}:\s", clean):
        return True
    return any(
        marker in lowered
        for marker in {
            "vo ocajna potraga",
            "krah sistem",
            "slavi pobeda",
            "predavstvo",
            "skandal",
            "sokantno",
            "udri",
            "zestoko",
            "katastrofa",
        }
    )


def _extract_terms(text):
    return [term for term in re.findall(r"[A-Za-z\u0400-\u04FF0-9]{3,}", (text or "").lower()) if term not in STOPWORDS]


def _extract_number_tokens(text):
    """Extracts plain numbers and percentages, avoiding clock times like 15:00."""
    tokens = re.findall(r"\b\d+(?::\d+)?(?:[%.,]\d+)?\b", str(text or ""))
    # Filter out common clock patterns (HH:MM)
    filtered = []
    for t in tokens:
        if ":" in t:
            parts = t.split(":")
            if len(parts) == 2:
                try:
                    h, m = int(parts[0]), int(parts[1])
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        # Kickoff times usually end in :00, :15, :30, :45
                        if m in (0, 15, 30, 45) and h >= 8:
                            continue
                except ValueError:
                    pass
        filtered.append(t)
    return filtered


def _extract_sports_scores(text):
    """Specifically looks for match results like 1-0, 2:1, (0-0)."""
    # Patterns: 1-0, 2:1, (0-0), 1:1 (halftime)
    tokens = re.findall(r"\(?\b\d+[:\-]\d+\b\)?", str(text or ""))
    scores = []
    for t in tokens:
        clean = t.strip("()")
        parts = re.split(r"[:\-]", clean)
        if len(parts) == 2:
            try:
                h, m = int(parts[0]), int(parts[1])

                # Exclude clock times (e.g. 15:00, 20:00)
                # Kickoff times usually end in :00, :15, :30, :45
                if ":" in clean:
                    if m == 0 and h >= 8:
                        continue  # 08:00, 20:00 etc
                    if h > 23:
                        pass  # Definitely a score (e.g. 32:28 in handball)
                    elif h >= 8 and m in (0, 15, 30, 45):
                        continue  # Likely time

                # Exclude common years/seasons (e.g. 2024-2025)
                if "-" in clean and h > 1900 and m > 1900:
                    continue

                # If it's a very high number on one side and small on other,
                # might be a year or something else, but in sports it could be basketball.
                # Max basketball score is around 150.
                if h > 200 or m > 200:
                    continue

                scores.append(clean)
            except ValueError:
                pass
    return scores


def _topic_stakes_sentence(text, lang="mk", topic="", category=""):
    lowered = str(text or "").casefold()
    topic_context = f"{topic or ''} {category or ''}".casefold()
    is_sr = lang == "sr"
    if any(term in lowered for term in ("izbor", "glasanje", "vlada", "sobranie", "skupština", "парламент", "избор", "влада", "собрание")):
        return (
            "Politički značaj je u tome što razvoj može pomeriti odnose među institucijama, partijama ili javnim očekivanjima."
            if is_sr
            else "Политичкото значење е во тоа што развојот може да ги помести односите меѓу институциите, партиите или јавните очекувања."
        )
    if any(term in lowered for term in ("cena", "inflacija", "budzet", "plata", "tržište", "ekonom", "цена", "инфлација", "буџет", "плата", "пазар")):
        return (
            "Ekonomska težina priče je u mogućem uticaju na troškove, budžete ili poslovne odluke."
            if is_sr
            else "Економската тежина на приказната е во можниот ефект врз трошоците, буџетите или деловните одлуки."
        )
    if any(term in lowered for term in ("policija", "sud", "tužila", "istraga", "uhap", "полиција", "суд", "обвинител", "истрага", "уапс")):
        return (
            "Institucionalni značaj zavisi od toga koliko će postupak biti potkrepljen proverljivim činjenicama i daljim odlukama nadležnih."
            if is_sr
            else "Институционалното значење зависи од тоа колку постапката ќе биде поткрепена со проверливи факти и понатамошни одлуки на надлежните."
        )
    if (
        any(term in topic_context for term in ("sport", "спорт"))
        and any(term in lowered for term in ("gol", "utakmica", "liga", "fudbal", "košarka", "натпревар", "гол", "лига", "фудбал", "кошарка"))
    ):
        return (
            "Sportski značaj se meri kroz posledice po rezultat, poredak i pritisak pred naredne mečeve."
            if is_sr
            else "Спортското значење се мери преку последиците врз резултатот, поредокот и притисокот пред следните натпревари."
        )
    return (
        "Za sada je najvažnije pratiti zvanične dopune i nove potvrde izvora."
        if is_sr
        else "Засега најважно е да се следат официјалните дополнувања и новите потврди од изворите."
    )


def summarize_locally(text, sentence_count=3, topic=None, title=None, lang="mk"):
    """Non-AI summarizer for news-like text."""
    if not text or len(text) < 100:
        return text

    sentences = [_normalize_summary_sentence(sentence) for sentence in re.split(r"(?<=[.!?])\s+", text)]
    sentences = [sentence for sentence in sentences if sentence]
    if len(sentences) <= sentence_count:
        return text

    potential_title = None
    if not title:
        for s in sentences:
            if not _is_noisy_summary_sentence(s):
                potential_title = s
                break

    title_terms = set(_sentence_tokens(title)) if title else set(_sentence_tokens(potential_title or sentences[0]))

    words = _sentence_tokens(text)
    word_freq = Counter(words)
    if not word_freq:
        return ". ".join(sentences[:sentence_count])

    max_freq = max(word_freq.values())
    for word in word_freq:
        word_freq[word] = word_freq[word] / max_freq

    topic_boost_words = set()
    if topic == "Ekonomija":
        topic_boost_words = {
            "denari",
            "evra",
            "procent",
            "milioni",
            "budzet",
            "plata",
            "ceni",
            "inflacija",
            "berza",
            "денари",
            "евра",
            "процент",
            "милиони",
            "буџет",
            "плата",
            "цени",
            "инфлација",
            "берза",
            "dinara",
            "evra",
            "procenat",
            "miliona",
            "budžet",
            "plata",
            "cene",
            "inflacija",
            "berza",
        }
    elif topic == "Politika":
        topic_boost_words = {
            "minister",
            "pretsedatel",
            "sobranie",
            "zakon",
            "partija",
            "lider",
            "vlada",
            "izbori",
            "министер",
            "претседател",
            "собрание",
            "закон",
            "партија",
            "лидер",
            "влада",
            "избори",
            "ministar",
            "predsednik",
            "skupština",
            "zakon",
            "partija",
            "lider",
            "vlada",
            "izbori",
        }
    elif topic == "Sport":
        topic_boost_words = {
            "natprevar",
            "gol",
            "pobeda",
            "prvenstvo",
            "klub",
            "liga",
            "fudbal",
            "kosarka",
            "натпревар",
            "гол",
            "победа",
            "првенство",
            "клуб",
            "лига",
            "фудбал",
            "кошарка",
            "utakmica",
            "gol",
            "pobeda",
            "prvenstvo",
            "klub",
            "liga",
            "fudbal",
            "košarka",
        }
    elif topic == "Kriminal":
        topic_boost_words = {
            "policija",
            "apsenje",
            "ubistvo",
            "sud",
            "obvinitelstvo",
            "zatvor",
            "napad",
            "полиција",
            "апсење",
            "убиство",
            "суд",
            "обвинителство",
            "затвор",
            "напад",
            "policija",
            "hapšenje",
            "ubistvo",
            "sud",
            "tužilaštvo",
            "zatvor",
            "napad",
        }

    sentence_scores = {}
    for i, sentence in enumerate(sentences):
        sentence_words = _sentence_tokens(sentence)
        if not sentence_words:
            continue

        if _is_noisy_summary_sentence(sentence):
            continue

        score = sum(word_freq.get(word, 0) for word in sentence_words)
        overlap = len(set(sentence_words) & title_terms)
        number_bonus = 0.5 if _extract_number_tokens(sentence) else 0.0
        lead_bonus = 1.8 / (i + 1)
        density_bonus = min(len(sentence_words), 24) / 24
        proper_noun_bonus = len(_extract_capitalized_phrases(sentence)) * 0.3

        topic_bonus = 0.0
        if topic_boost_words:
            matched_topic_words = len(set(sentence_words) & topic_boost_words)
            topic_bonus = matched_topic_words * 0.5

        if len(sentence) > 280:
            score *= 0.6
        score += (overlap * 0.5) + number_bonus + lead_bonus + density_bonus + proper_noun_bonus + topic_bonus
        sentence_scores[i] = score

    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:sentence_count]
    top_indices.sort()

    summary = []
    seen = set()
    for idx in top_indices:
        sentence = sentences[idx].strip()
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        summary.append(sentence)

    if not summary:
        summary = [sentence for sentence in sentences[:sentence_count] if not _is_noisy_summary_sentence(sentence)]

    return " ".join(summary)


def summarize_article_fallback(title, description=None, topic=None, lang="mk"):
    parts = [str(title or "").strip(), str(description or "").strip()]
    text = ". ".join([part for part in parts if part])
    summary = summarize_locally(text, sentence_count=2, topic=topic, title=title, lang=lang).strip()
    summary = re.sub(r"^[⚪🟢🔴]\s*", "", summary, flags=re.UNICODE)
    summary = re.sub(r"#[^\s#]+", "", summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary[:420] if summary else str(title or "").strip()


def _join_fragments(parts):
    clean = [str(part or "").strip(" .,;:") for part in parts if str(part or "").strip(" .,;:")]
    return "; ".join(clean)


def _sentence(text):
    clean = str(text or "").strip()
    clean = re.sub(r"\s+", " ", clean).strip(" ;:")
    clean = re.sub(r"([A-Za-z\u0400-\u04FF])\(", r"\1 (", clean)
    clean = re.sub(r"\)([A-Za-z\u0400-\u04FF])", r") \1", clean)
    clean = re.sub(r"([.!?]){2,}", r"\1", clean)
    clean = re.sub(r"\s+([,.;:!?])", r"\1", clean)
    if not clean:
        return ""
    return clean if clean.endswith((".", "!", "?", "…")) else f"{clean}."


def _fallback_sentence(text):
    clean = _normalize_briefing_line(text)
    if _is_incomplete_briefing_fragment(clean):
        return ""
    return _sentence(clean)


def _fallback_open_sentence(text, lang="mk"):
    clean = _fallback_sentence(text)
    if not clean:
        return ""
    if lang == "sr":
        return re.sub(r"^Otvoreno\s+(ostaje|je)\s+", "", clean, flags=re.IGNORECASE).strip()
    return re.sub(r"^Отворено\s+(останува|е)\s+", "", clean, flags=re.IGNORECASE).strip()


def _extract_comparison_entities(text):
    entities = []
    for phrase in _extract_capitalized_phrases(text):
        clean = normalize_tag_name(phrase)
        if not clean:
            continue
        lowered = clean.casefold()
        if lowered in SOURCE_NOISE_WORDS or lowered in TAG_NOISE_WORDS:
            continue
        entities.append(clean)
    return entities


def _source_list(articles, limit=3):
    names = [str(article.get("source") or "izvor").strip() for article in articles[:limit]]
    return ", ".join(name for name in names if name)


def _source_count_label(count: int, lang: str) -> str:
    if lang == "sr":
        return "izvor" if count == 1 else "izvora"
    return "извор" if count == 1 else "извори"


def _comparison_terms(text: str) -> set[str]:
    text_val = str(text or "")
    if any(ord(c) >= 0x0400 for c in text_val):
        try:
            text_val = transliterate_cyr_to_lat(text_val)
        except Exception:
            pass
    return {term for term in _extract_terms(text_val) if term not in SOURCE_NOISE_WORDS}


def _term_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _title_difference_is_substantive(left: str, right: str) -> bool:
    left_terms = _comparison_terms(left)
    right_terms = _comparison_terms(right)
    if not left_terms or not right_terms:
        return False
    overlap = _term_overlap(left_terms, right_terms)
    if overlap >= 0.68:
        return False
    return len(left_terms - right_terms) >= 2 or len(right_terms - left_terms) >= 2


def _clean_common_line(line: str, lang: str, exclude_text: str = "") -> str:
    clean = str(line or "").strip()
    if not clean:
        return ""
    common_prefixes = [
        "Većina izvora se slaže oko ",
        "Poveceto izvori se soglasuvaat okolu ",
        "Повеќето извори се согласуваат околу ",
    ]
    for prefix in common_prefixes:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    common_suffixes = [
        " kao tema u fokusu.",
        " kao teme u fokusu.",
        " као тема у фокусу.",
        " како тема во фокус.",
        " како теми во фокус.",
        " kako temi vo fokus.",
    ]
    for suffix in common_suffixes:
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)]
            break
    clean = re.sub(r"\s+", " ", clean).strip(" .,;:")
    if not clean:
        return ""
    chunks = [chunk.strip() for chunk in re.split(r",|\s+i\s+|\s+и\s+", clean) if chunk.strip()]
    meaningful = []
    exclude_terms = _comparison_terms(exclude_text) if exclude_text else set()
    for chunk in chunks:
        terms = _comparison_terms(chunk)
        if len(terms) < 2:
            continue
        if any(_term_overlap(terms, _comparison_terms(existing)) >= 0.55 for existing in meaningful):
            continue
        if exclude_terms and (len(terms & exclude_terms) / len(terms)) >= 0.75:
            continue
        meaningful.append(chunk)
    if not meaningful:
        return ""
    joined = ", ".join(meaningful[:2])
    if lang == "sr":
        return f"Izvori se najviše poklapaju oko: {joined}."
    return f"Изворите најмногу се поклопуваат околу: {joined}."


def compare_cluster_sources(articles, lang="mk"):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {"common_line": "", "difference_points": [], "open_points": []}

    cache_key = (_articles_cache_key(articles), lang)
    cached = _cache_get(_comparison_cache, cache_key)
    if cached is not None:
        record_runtime_event("local_compare_cache", mode="hit")
        return cached
    record_runtime_event("local_compare_cache", mode="miss")

    uncertainty_markers = (
        "tvrdi",
        "spored",
        "nepotvr",
        "navod",
        "se ocekuva",
        "moze",
        "bi moz",
        "zasega",
        "se jos",
        "se razviva",
    )
    if lang == "mk":
        uncertainty_markers = (
            "тврди",
            "според",
            "непотвр",
            "навод",
            "се очекува",
            "може",
            "би мож",
            "засега",
            "се уште",
            "се развива",
        )

    all_terms = Counter()
    article_term_sets, article_texts_lower, title_pairs = [], [], []
    number_map, entity_map = {}, {}
    uncertain_sources, article_fact_profiles = [], []

    for article in articles:
        combined = " ".join([article["title"], article["description"]]).strip()
        if lang == "sr":
            combined = transliterate_cyr_to_lat(combined)

        terms = set(_extract_terms(combined))
        article_term_sets.append(terms)
        all_terms.update(terms)
        article_texts_lower.append(combined.lower())
        if article["title"]:
            title_pairs.append((article["source"], article["title"]))
        numbers = set(_extract_number_tokens(combined))
        for n in numbers:
            number_map.setdefault(n, set()).add(article["source"])
        entities = set(_extract_comparison_entities(combined))
        for e in entities:
            entity_map.setdefault(e, set()).add(article["source"])
        if any(m in combined.lower() for m in uncertainty_markers):
            uncertain_sources.append(article["source"])
        article_fact_profiles.append(
            {
                "source": article["source"],
                "terms": terms,
                "numbers": numbers,
                "entities": entities,
                "uncertain": any(m in combined.lower() for m in uncertainty_markers),
            }
        )

    threshold = max(2, math.ceil(len(articles) / 2))
    common_terms = [t for t, c in all_terms.most_common(8) if c >= threshold and t not in SOURCE_NOISE_WORDS]
    pooled_text = " ".join(a["title"] + ". " + a["description"] for a in articles)

    if lang == "sr":
        pooled_text = transliterate_cyr_to_lat(pooled_text)

    candidate_phrases = extract_keyphrases_locally(pooled_text, top_n=12)
    common_phrases = [
        p
        for p in candidate_phrases
        if p and " " in p and sum(1 for txt in article_texts_lower if p.lower() in txt) >= threshold
    ]
    common_line = ""
    if common_phrases:
        from nlp.keywords import _format_common_line_from_phrases

        try:
            common_line = _format_common_line_from_phrases(common_phrases[:3], lang=lang)
        except Exception as e:
            log.debug(f"[nlp.generation] Error formatting common line: {e}")
            if lang == "sr":
                common_line = "Većina izvora se slaže oko " + ", ".join(common_phrases[:3]) + " kao tema u fokusu."
            else:
                common_line = (
                    "Повеќето извори се согласуваат околу " + ", ".join(common_phrases[:3]) + " како теми во фокус."
                )
    elif common_terms:
        if lang == "sr":
            terms = [transliterate_cyr_to_lat(t) for t in common_terms[:4]]
            common_line = "Većina izvora se slaže oko " + ", ".join(terms) + " kao tema u fokusu."
        else:
            common_line = "Повеќето извори се согласуваат околу " + ", ".join(common_terms[:4]) + " како теми во фокус."

    difference_points, seen_titles = [], set()
    source_count = len(articles)

    conflicting_numbers = [
        (number, sorted(sources))
        for number, sources in number_map.items()
        if len(sources) < source_count and len(sources) >= 1 and source_count > 1
    ]
    if conflicting_numbers:
        number, sources = conflicting_numbers[0]
        if lang == "sr":
            difference_points.append(
                f"Brojka „{number}“ pojavljuje se samo kod {', '.join(sources[:2])}, pa je treba čitati kao detalj koji nije jednako potvrđen u svim izvorima."
            )
        else:
            difference_points.append(
                f"Бројката „{number}“ се појавува само кај {', '.join(sources[:2])}, па треба да се чита како детал што не е еднакво потврден во сите извори."
            )

    unique_entities = [
        (entity, sorted(sources))
        for entity, sources in entity_map.items()
        if len(sources) == 1 and len(entity) >= 4
    ]
    if unique_entities:
        entity, sources = unique_entities[0]
        entity = _normalize_briefing_line(entity)
        if lang == "sr":
            difference_points.append(
                f"{sources[0]} izdvaja „{entity}“ kao poseban akcenat koji drugi izvori ne stavljaju u prvi plan."
            )
        else:
            difference_points.append(
                f"{sources[0]} го издвојува „{entity}“ како посебен акцент што другите извори не го ставаат во прв план."
            )

    unique_titles = []
    for s, t in title_pairs:
        if t.casefold() not in seen_titles:
            seen_titles.add(t.casefold())
            unique_titles.append((s, t))
    if len(unique_titles) >= 2:
        if lang == "sr":
            t1 = transliterate_cyr_to_lat(unique_titles[0][1])
            t2 = transliterate_cyr_to_lat(unique_titles[1][1])
            if _title_difference_is_substantive(t1, t2):
                difference_points.append(
                    f"{unique_titles[0][0]} stavlja akcenat na „{t1}“, dok {unique_titles[1][0]} priču okviruje kroz „{t2}“."
                )
        else:
            if _title_difference_is_substantive(unique_titles[0][1], unique_titles[1][1]):
                difference_points.append(
                    f"{unique_titles[0][0]} става акцент на „{unique_titles[0][1]}“, додека {unique_titles[1][0]} ја врамува приказната преку „{unique_titles[1][1]}“."
                )

    open_points = []
    uncertain_sources = [
        a["source"]
        for a in articles
        if any(
            m in (a.get("title") or "").lower() or (a.get("description") or "").lower()
            for m in [
                "mozebi",
                "se ocekuva",
                "navodno",
                "spored neimenuvani",
                "nepotvrdeno",
                "можеби",
                "се очекува",
                "наводно",
                "според неименувани",
                "непотврдено",
            ]
        )
    ]
    has_concrete_uncertainty = len(uncertain_sources) < len(articles) or bool(conflicting_numbers or unique_entities)
    if uncertain_sources and has_concrete_uncertainty:
        if lang == "sr":
            open_points.append(
                f"Otvoreno je da li će detalji koje navode {', '.join(uncertain_sources[:2])} biti potvrđeni i u drugim izvorima."
            )
        else:
            open_points.append(
                f"Отворено е дали деталите што ги наведуваат {', '.join(uncertain_sources[:2])} ќе бидат потврдени и во други извори."
            )

    # Extra check for numbers mismatch as open points
    from nlp.categories import detect_topic

    all_titles = " ".join([a.get("title") or "" for a in articles])
    is_sport = (detect_topic(all_titles) == "Sport") or any(_extract_sports_scores(a.get("title") or "") for a in articles)

    if is_sport:
        scores = [
            set(_extract_sports_scores(a.get("title") or "")) | set(_extract_sports_scores(a.get("description") or ""))
            for a in articles
        ]
        all_scores = set().union(*scores)
        conflicting_scores = [
            s for s in all_scores if sum(1 for ms in scores if s in ms) < len(articles) and len(articles) > 1
        ]
        if conflicting_scores:
            if lang == "sr":
                difference_points.append(
                    f"Izvori se razlikuju oko rezultata utakmice (na primer: {', '.join(conflicting_scores)})."
                )
                open_points.append(
                    f"Informacije za konačan rezultat se razlikuju (na primer: {conflicting_scores[0]}), što može ukazivati na promenu u toku meča."
                )
            else:
                difference_points.append(
                    f"Изворите се разликуваат околу конечниот резултат (на пример: {', '.join(conflicting_scores)})."
                )
                open_points.append(
                    f"Информациите за конечниот резултат се разликуваат (на пример: {conflicting_scores[0]}), што може да укажува на промена во текот на мечот."
                )

    # Generic numbers only if not many articles (less noise)
    if len(articles) > 1 and len(articles) <= 3:
        nums = [set(_extract_number_tokens(a.get("description") or "")) for a in articles]
        all_nums = set().union(*nums)
        conflicting_nums = [n for n in all_nums if sum(1 for s in nums if n in s) == 1]
        if conflicting_nums and not any(n in "".join(open_points) for n in conflicting_nums):
            if lang == "sr":
                open_points.append(
                    f"Postoje različite informacije oko brojki (na primer: {conflicting_nums[0]}), što ukazuje na dinamično izveštavanje."
                )
            else:
                open_points.append(
                    f"Постојат различни информации околу бројките (на пример: {conflicting_nums[0]}), што укажува на динамично известување."
                )

    result = {
        "common_line": common_line,
        "difference_points": difference_points[:3],
        "open_points": open_points[:2],
    }
    _cache_set(_comparison_cache, cache_key, result)
    return result


def synthesize_cluster_fallback(articles, lang="mk"):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {
            "summary": "",
            "perspectives": [],
            "synthetic_headline": "",
            "generated_article": "",
            "synthetic_standfirst": "",
        }

    t = _T.get(lang, _T["mk"])
    
    # Try to find a lead article in the target language (represented by country)
    lead = None
    target_country = "MK" if lang == "mk" else "RS"
    for art in articles:
        art_country = art.get("country")
        if art_country and str(art_country).upper() == target_country:
            lead = art
            break
    if not lead:
        lead = articles[0]
    comparison = compare_cluster_sources(articles, lang=lang)

    # 1. Setup Lead Title, Description, and Update Point
    lead_title = deShout(cleanAndDecode(lead.get("title", ""))).strip()
    desc = cleanAndDecode(lead.get("description", ""))

    if lang == "sr":
        lead_title = transliterate_cyr_to_lat(lead_title)
        desc = transliterate_cyr_to_lat(desc)

    update_point = _extract_briefing_update({"title": lead_title, "description": desc}, lang=lang)

    # 2. Multi-source Sentence Fusion
    candidate_sentences = []
    for art in articles:
        art_desc = cleanAndDecode(art.get("description", ""))
        if lang == "sr":
            art_desc = transliterate_cyr_to_lat(art_desc)

        art_country = art.get("country", "")
        is_target_country = art_country and str(art_country).upper() == target_country
        
        # Extract sentences from description
        raw_sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", art_desc) if s.strip()]
        
        for idx, s in enumerate(raw_sents):
            normalized = _normalize_briefing_line(s)
            if (
                not normalized
                or len(normalized) < 20
                or _is_noisy_summary_sentence(normalized)
                or _is_incomplete_briefing_fragment(normalized)
            ):
                continue
            
            # Sentence scoring logic
            score = len(normalized.split()) * 0.1
            if idx == 0:
                score += 1.0  # first description sentence gets a boost
            if re.search(r"\d+", normalized):
                score += 0.5  # contains numbers / statistics
            if is_target_country:
                score += 0.8  # matches target country/language
                
            candidate_sentences.append({
                "text": normalized,
                "score": score,
                "source": art.get("source"),
            })
            
    candidate_sentences.sort(key=lambda x: x["score"], reverse=True)
    
    selected_sentences = []
    for cand in candidate_sentences:
        # Avoid duplicating the key update point
        if update_point and _jaccard_similarity(cand["text"], update_point) > 0.28:
            continue
        if any(_jaccard_similarity(cand["text"], s["text"]) > 0.4 for s in selected_sentences):
            continue
        selected_sentences.append(cand)
        if len(selected_sentences) >= 3:
            break
            
    if not selected_sentences:
        fallback_sents = [_normalize_briefing_line(s) for s in re.split(r"(?<=[.!?])\s+", desc) if len(s.strip()) > 20]
        fallback_sents = [s for s in fallback_sents if s and not _is_noisy_summary_sentence(s)]
        for s in fallback_sents:
            if update_point and _jaccard_similarity(s, update_point) > 0.28:
                continue
            selected_sentences.append({"text": s, "source": lead.get("source")})
        if not selected_sentences and fallback_sents:
            selected_sentences.append({"text": fallback_sents[0], "source": lead.get("source")})

    # 3. Build direct editorial summary points. Avoid label-style bullets because
    # they read like a template once rendered on the cluster page.
    summary_lines = []
    update_sentence = _fallback_sentence(update_point)
    lead_sentence = _fallback_sentence(lead_title)
    if update_sentence and update_point.casefold() != lead_title.casefold():
        summary_lines.append(f"• {update_sentence}")
    else:
        summary_lines.append(f"• {lead_sentence or _sentence(lead_title)}")

    if selected_sentences and not (update_point and _jaccard_similarity(selected_sentences[0]["text"], update_point) > 0.28):
        detail_sentence = _fallback_sentence(selected_sentences[0]["text"])
        if detail_sentence:
            summary_lines.append(f"• {detail_sentence}")

    common = (
        comparison.get("common_line", "")
        .replace("Poveceto izvori se soglasuvaat okolu ", "")
        .replace("Повеќето извори се согласуваат околу ", "")
        .replace("Većina izvora se slaže oko ", "")
        .replace(" kako temi vo fokus.", "")
        .replace(" како теми во фокус.", "")
        .replace(" како тема во фокус.", "")
        .replace(" kao tema u fokusu.", "")
        .strip()
    )
    if common and len(common) > 18 and "," not in common:
        if lang == "sr":
            summary_lines.append(f"• Izvori se najjasnije poklapaju oko {_sentence(common).lower()}")
        else:
            summary_lines.append(f"• Изворите најјасно се поклопуваат околу {_sentence(common).lower()}")

    sources_str = _source_list(articles, limit=4)
    if lang == "sr":
        summary_lines.append(
            f"• Priču prati {len(articles)} {_source_count_label(len(articles), lang)} ({sources_str}), što daje osnov za poređenje akcenata, ali ne i za tvrdnje van objavljenih podataka."
        )
    else:
        summary_lines.append(
            f"• Приказната ја следат {len(articles)} {_source_count_label(len(articles), lang)} ({sources_str}), што дава основа за споредба на акцентите, но не и за тврдења надвор од објавените податоци."
        )

    if comparison.get("open_points"):
        open_sentence = _fallback_open_sentence(comparison["open_points"][0], lang=lang)
        if open_sentence:
            open_sentence = open_sentence.rstrip(" .;:")
            if lang == "sr":
                summary_lines.append(f"• Otvoreno ostaje {open_sentence}.")
            else:
                summary_lines.append(f"• Отворено останува {open_sentence}.")

    summary = "\n".join(summary_lines)

    # 3. Build an editorial fallback narrative, not a mechanical digest.
    article_body = []
    if update_point and update_point.casefold() != lead_title.casefold():
        intro_parts = [lead_sentence or _sentence(lead_title)]
        if _jaccard_similarity(update_point, lead_title) <= 0.28:
            if update_sentence:
                intro_parts.append(update_sentence)
        article_body.append(" ".join(part for part in intro_parts if part))
    else:
        article_body.append(f"{_sentence(lead_title)} {_sentence(t['povece_mediumi'])}")

    details = [sentence for sentence in (_fallback_sentence(s.get("text")) for s in selected_sentences) if sentence]
    if details:
        non_duplicate_details = [
            detail for detail in details
            if all(_jaccard_similarity(detail, existing) <= 0.28 for existing in article_body)
        ]
        if non_duplicate_details:
            article_body.append(" ".join(non_duplicate_details[:2]))

    context_basis = " ".join([lead_title, desc, " ".join(details)])
    article_body.append(_sentence(_topic_stakes_sentence(
        context_basis,
        lang=lang,
        topic=lead.get("topic") or "",
        category=lead.get("category") or "",
    )))

    source_paragraph_parts = []
    existing_text = " ".join(article_body)
    clean_common_line = _clean_common_line(comparison.get("common_line", ""), lang, exclude_text=existing_text)
    if clean_common_line:
        source_paragraph_parts.append(_sentence(clean_common_line))
    else:
        source_paragraph_parts.append(_sentence(t["izvori_pratat_ista_linija"]))
    if comparison.get("difference_points"):
        source_paragraph_parts.append(_sentence(comparison["difference_points"][0]))
    article_body.append(" ".join(source_paragraph_parts))

    if comparison.get("open_points"):
        open_point = _fallback_open_sentence(comparison["open_points"][0], lang=lang)
        if "Detalji oko ovog razvoja ostaju nepotvr" in open_point:
            open_point = _sentence(
                "Nije izdvojena konkretna sporna činjenica; treba pratiti sledeće dopune izvora."
                if lang == "sr"
                else "Не е издвоен конкретен спорен факт; треба да се следат следните дополнувања од изворите."
            )
        if open_point:
            article_body.append(f"{t['sto_ostanuva']}: {open_point}")
    elif len(articles) <= 1:
        article_body.append(_sentence(t["faza_razvoj"]))
    else:
        article_body.append(_sentence(t["naredno_pratenje"]))

    generated_article = "\n\n".join(article_body)

    # 4. Perspectives
    perspectives = []
    if len(articles) > 1:
        perspectives.append(
            {
                "angle": t["konsenzus"],
                "content": t["potvrda_osnovna"].format(s1=articles[0]["source"], s2=articles[1]["source"]),
            }
        )

    if comparison["difference_points"]:
        perspectives.append({"angle": t["nijansi"], "content": comparison["difference_points"][0]})

    if comparison.get("open_points"):
        perspectives.append({"angle": t["otvoreno_lower"], "content": comparison["open_points"][0]})

    record_runtime_event("local_synthesis_path", mode="enhanced_fallback")
    return {
        "summary": summary,
        "perspectives": perspectives[:3],
        "synthetic_headline": lead_title,
        "generated_article": generated_article,
        "synthetic_standfirst": t["urednicki_pregled"].format(count=len(articles)),
    }


def generate_daily_brief_fallback(clusters, lang="mk"):
    t = _T.get(lang, _T["mk"])
    if not clusters:
        return f"# {t['dneven_brifing']}\n\n## {t['golemata_slika']}\n\n{t['nema_vesti']}"
    display_clusters = sorted(
        clusters[:4],
        key=lambda item: (
            -int(bool(str(item.get("cluster_summary") or "").strip())),
            int(_is_penalized_briefing_title(item.get("title"))),
            -int(item.get("source_count") or 0),
        ),
    )
    display_clusters = _dedupe_briefing_clusters(display_clusters, limit=4, lang=lang)
    lines = [f"# {t['dneven_brifing']}", "", f"## {t['golemata_slika']}", ""]

    intro_line = _build_briefing_intro_line(display_clusters, lang=lang)
    if intro_line:
        lines.append(intro_line)
        coverage_sources = _briefing_coverage_source_count(display_clusters)
        if coverage_sources >= 2:
            lines.append(t["urednicki_pregled"].format(count=coverage_sources))
        lines.append("")

    lines.append(f"## {t['globalni_lokalni_oski']}")
    lines.append("")
    for index, cluster in enumerate(display_clusters, start=1):
        title = str(cluster.get("title") or "").strip()
        clean_title = _clean_briefing_snippet(title)
        cluster_id = str(cluster.get("cluster_id") or "").strip()

        summary = _extract_briefing_update(cluster, lang=lang)
        importance = _extract_briefing_importance(cluster, lang=lang)

        title_line = clean_title or title
        if cluster_id:
            title_line = f"{title_line} [[{cluster_id}]]"
        lines.append(f"### {index}. {title_line}")

        if summary and summary.casefold() != (clean_title or title).casefold() and not _is_incomplete_briefing_fragment(summary):
            lines.append(f"- {t['klucen_aspekt']}: {summary.rstrip('.')}.")

        lines.append(f"- {t['zosto_vazno']}: {importance.rstrip('.')}.")
        lines.append("")

    lines.append(f"## {t['mediumski_radar']}")
    lines.append("")
    difference_added = False
    for cluster in display_clusters[:3]:
        diff = _normalize_briefing_line(cluster.get("difference_point"))
        if diff:
            short_t = _condense_briefing_update(cluster.get("title"), max_chars=80)
            lines.append(f"• {short_t}: {diff}")
            difference_added = True
    if not difference_added and display_clusters[:3]:
        fallback_cluster = display_clusters[0]
        short_t = _condense_briefing_update(fallback_cluster.get("title"), max_chars=80)
        lines.append(f"• {short_t}: " f"{_extract_briefing_importance(fallback_cluster, lang=lang)}.")
    lines.append("")

    lines.append(f"## {t['sto_da_se_sledi']}")
    lines.append("")
    for cluster in display_clusters[:4]:
        signal = _extract_briefing_watch_signal(cluster, lang=lang)
        short_t = _condense_briefing_update(cluster.get("title"), max_chars=82)
        lines.append(f"- {short_t}: {signal}")
    lines.append("")
    lines.append(f"**{t['beleska']}**: {t['sodrzina_generirana']}")
    return "\n".join(lines).strip()


def _article_context_text(article):
    article = article or {}
    return " ".join(
        part.strip()
        for part in [
            str(article.get("title") or ""),
            str(article.get("description") or ""),
        ]
        if str(part or "").strip()
    ).strip()


def _article_candidate_snippets(article):
    article = article or {}
    title, description = (
        str(article.get("title") or "").strip(),
        str(article.get("description") or "").strip(),
    )
    snippets = [(title, "title")] if title else []
    raw_sentences = [
        _normalize_summary_sentence(s)
        for s in re.split(r"(?<=[.!?])\s+", description)
        if _normalize_summary_sentence(s)
    ]
    for s in raw_sentences[:3]:
        if not _is_noisy_summary_sentence(s):
            snippets.append((s, "description"))
    return snippets[:4]


def _score_question_snippet(question_terms, question_entities, question_numbers, snippet, kind, article_rank):
    text = str(snippet or "").strip()
    if not text:
        return 0.0
    snippet_terms, snippet_numbers = set(_extract_terms(text)), set(_extract_number_tokens(text))
    snippet_entities = {e.casefold() for e in _extract_capitalized_phrases(text)}
    score = (
        len(question_terms & snippet_terms) * 2.4
        + sum(1 for e in question_entities if e in text.lower() or e in snippet_entities) * 2.1
        + len(question_numbers & snippet_numbers) * 2.8
    )
    score += 1.1 if kind == "title" else (0.7 if kind == "description" else 0.4)
    return score + max(0, 0.55 - (article_rank * 0.1))


def _rank_cluster_question_evidence(question, articles, synthesis=""):
    articles, question = (
        _normalize_articles_for_local_use(articles),
        str(question or "").strip(),
    )
    if not question or not articles:
        return []
    cache_key = (
        question.casefold(),
        _articles_cache_key(articles),
        str(synthesis or "").strip(),
    )
    cached = _cache_get(_question_evidence_cache, cache_key)
    if cached is not None:
        return cached
    q_terms, q_entities, q_numbers = (
        set(_extract_terms(question)),
        {e.casefold() for e in _extract_capitalized_phrases(question)},
        set(_extract_number_tokens(question)),
    )
    ranked = []
    for rank, art in enumerate(articles):
        snippets = _article_candidate_snippets(art)
        context_text = _article_context_text(art)
        c_score = (
            len(q_terms & set(_extract_terms(context_text))) * 0.9
            + len(q_numbers & set(_extract_number_tokens(context_text))) * 1.2
        )
        for snip, kind in snippets:
            score = _score_question_snippet(q_terms, q_entities, q_numbers, snip, kind, rank) + c_score
            ranked.append({"article": art, "snippet": snip, "kind": kind, "score": score})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    deduped, seen = [], set()
    for item in ranked:
        if item["snippet"].casefold() not in seen:
            seen.add(item["snippet"].casefold())
            deduped.append(item)
        if len(deduped) >= 4:
            break
    _cache_set(_question_evidence_cache, cache_key, deduped)
    return deduped


def _coerce_grounded_snippet(snippet):
    text = re.sub(r"\s+", " ", str(snippet or "").strip().strip("•")).strip()
    if text and not re.search(r"[.!?]$", text):
        text += "."
    return text


def _is_low_information_fragment(text):
    clean = str(text or "").strip().strip("•").strip()
    return len(clean) < 12 or not _extract_terms(clean)


def _is_low_quality_local_text(text, evidence=None):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s.strip()]
    if not sentences:
        return True
    if len(set(re.sub(r"\s+", " ", s.casefold()) for s in sentences)) < len(sentences):
        return True
    return sum(1 for s in sentences if _is_low_information_fragment(s)) > len(sentences) / 2


def _build_grounded_answer_from_evidence(evidence, comparison=None, lang="mk"):
    t = _T.get(lang, _T["mk"])
    if not evidence:
        return ""
    p = evidence[0]
    p_snip = _coerce_grounded_snippet(p.get("snippet") or p["article"].get("title") or "")
    if _is_low_information_fragment(p_snip):
        p_snip = _coerce_grounded_snippet(summarize_locally(p["article"].get("description", ""), sentence_count=1))
    return t["najdirektno"].format(text=p_snip)


def _build_minimum_cluster_summary(articles, comparison=None, lang="mk"):
    t = _T.get(lang, _T["mk"])
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return ""

    lead = None
    target_country = "MK" if lang == "mk" else "RS"
    for art in articles:
        art_country = art.get("country")
        if art_country and str(art_country).upper() == target_country:
            lead = art
            break
    if not lead:
        lead = articles[0]

    return f"• {t['sto_se_slucuva']}: {lead['title']}\n• {t['pokrienost']}: {len(articles)} {t['izvori']}, {t['sledeno_od']} i {_source_list(articles)}."


def _placeholder_svg_escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _placeholder_paint_tokens(
    c_bg: str,
    c_spot: str,
    c_accent: str,
    *,
    light: bool,
) -> dict[str, str]:
    if light:
        return {
            "glass_fill": "rgba(255,255,255,0.28)",
            "glass_stroke": "rgba(196,92,38,0.12)",
            "grid_stroke": "rgba(16,16,16,0.04)",
            "text_primary": "#101010",
            "text_meta": "#686257",
            "meta_opacity": "0.85",
            "category_opacity": "0.95",
            "accent": c_accent,
            "line_light": "rgba(16,16,16,0.10)",
            "line_vlight": "rgba(16,16,16,0.05)",
            "line_vvlight": "rgba(16,16,16,0.03)",
            "dot": "#101010",
            "grain_fill": "#101010",
            "grain_opacity": "0.018",
            "bg_start": c_bg,
            "bg_end": "#ece8df",
            "mesh_start": c_spot,
            "mesh_start_opacity": "0.42",
            "mesh_end": "#ece8df",
            "glow_start": c_accent,
            "glow_start_opacity": "0.22",
            "glow_end": "#ece8df",
        }
    return {
        "glass_fill": "rgba(255,255,255,0.02)",
        "glass_stroke": "rgba(224,122,61,0.14)",
        "grid_stroke": "rgba(255,255,255,0.05)",
        "text_primary": "#fffefa",
        "text_meta": "#d8d3c6",
        "meta_opacity": "0.72",
        "category_opacity": "0.88",
        "accent": c_accent,
        "line_light": "rgba(255,255,255,0.14)",
        "line_vlight": "rgba(255,255,255,0.06)",
        "line_vvlight": "rgba(255,255,255,0.03)",
        "dot": "#fffefa",
        "grain_fill": "#fffefa",
        "grain_opacity": "0.035",
        "bg_start": c_bg,
        "bg_end": "#0a0908",
        "mesh_start": c_spot,
        "mesh_start_opacity": "0.48",
        "mesh_end": "#0a0908",
        "glow_start": c_accent,
        "glow_start_opacity": "0.32",
        "glow_end": "#0a0908",
    }


def _placeholder_paint_css(tokens: dict[str, str]) -> str:
    return f"""
            .ph-glass {{ fill: {tokens["glass_fill"]}; stroke: {tokens["glass_stroke"]}; }}
            .ph-grain {{ fill: {tokens["grain_fill"]}; opacity: {tokens["grain_opacity"]}; }}
            .ph-grid {{ stroke: {tokens["grid_stroke"]}; fill: none; }}
            .ph-headline {{ fill: {tokens["text_primary"]}; }}
            .ph-meta {{ fill: {tokens["text_meta"]}; opacity: {tokens["meta_opacity"]}; }}
            .ph-category {{ fill: {tokens["accent"]}; opacity: {tokens["category_opacity"]}; }}
            .ph-accent-fill {{ fill: {tokens["accent"]}; }}
            .ph-fill-dot {{ fill: {tokens["dot"]}; }}
            .ph-stroke-accent {{ stroke: {tokens["accent"]}; fill: none; }}
            .ph-stroke-line {{ stroke: {tokens["line_light"]}; fill: none; }}
            .ph-stroke-vline {{ stroke: {tokens["line_vlight"]}; fill: none; }}
            .ph-stroke-vvline {{ stroke: {tokens["line_vvlight"]}; fill: none; }}
            .ph-fill-vvline {{ fill: {tokens["line_vvlight"]}; }}
            .ph-fill-line {{ fill: {tokens["line_light"]}; }}
            .ph-accent-shape {{ stroke: {tokens["accent"]}; fill: {tokens["line_vvlight"]}; }}
            .bg-stop-start {{ stop-color: {tokens["bg_start"]}; }}
            .bg-stop-end {{ stop-color: {tokens["bg_end"]}; }}
            .mesh-stop-start {{ stop-color: {tokens["mesh_start"]}; stop-opacity: {tokens["mesh_start_opacity"]}; }}
            .mesh-stop-end {{ stop-color: {tokens["mesh_end"]}; stop-opacity: 0; }}
            .art-glow-start {{ stop-color: {tokens["glow_start"]}; stop-opacity: {tokens["glow_start_opacity"]}; }}
            .art-glow-end {{ stop-color: {tokens["glow_end"]}; stop-opacity: 0; }}
        """


def _placeholder_style_block(
    theme_l: str,
    c_bg_dark: str,
    c_spot_dark: str,
    c_accent_dark: str,
    c_bg_light: str,
    c_spot_light: str,
    c_accent_light: str,
) -> str:
    dark_tokens = _placeholder_paint_tokens(c_bg_dark, c_spot_dark, c_accent_dark, light=False)
    light_tokens = _placeholder_paint_tokens(c_bg_light, c_spot_light, c_accent_light, light=True)
    if theme_l == "light":
        return _placeholder_paint_css(light_tokens)
    if theme_l == "dark":
        return _placeholder_paint_css(dark_tokens)
    return (
        _placeholder_paint_css(dark_tokens)
        + """
            @media (prefers-color-scheme: light) {
        """
        + _placeholder_paint_css(light_tokens)
        + "\n            }\n"
    )


def generate_local_placeholder(cluster_id, title, category="vesti", theme=None, lang="sr"):
    import hashlib

    from nlp.placeholder_brand import category_palette_pair

    lang = "mk" if str(lang or "sr").lower().startswith("mk") else "sr"
    seed = int(hashlib.md5(str(cluster_id).encode(), usedforsecurity=False).hexdigest(), 16)
    category_raw = str(category or "vesti")
    category_l = category_raw.casefold()
    title = str(title or "Presek")

    if any(token in category_l for token in ("sport", "спорт", "fudbal", "фудбал")):
        category_key = "Sport"
    elif any(token in category_l for token in ("ekonom", "економ", "biznis", "бизнис", "finans", "финанс")):
        category_key = "Ekonomija"
    elif any(token in category_l for token in ("tehnolog", "технолог", "nauka", "наука", "digital", "дигитал")):
        category_key = "Tehnologija"
    elif any(token in category_l for token in ("kultur", "култур", "zabava", "забава", "film", "филм")):
        category_key = "Zabava"
    elif any(token in category_l for token in ("hronika", "хроника", "policija", "полиција", "sud", "суд")):
        category_key = "Hronika"
    elif any(token in category_l for token in ("makedon", "македон")):
        category_key = "Makedonija"
    elif any(token in category_l for token in ("srb", "срб")):
        category_key = "Srbija"
    elif any(token in category_l for token in ("evrop", "европ", "eu")):
        category_key = "Evropa"
    elif any(token in category_l for token in ("svet", "свет", "world", "global")):
        category_key = "Svet"
    else:
        category_key = category_raw if category_raw in {
            "Srbija", "Makedonija", "Balkan", "Evropa", "Amerika", "Svet",
            "Sport", "Tehnologija", "Ekonomija", "Hronika", "Zabava",
        } else "default"

    # Warm editorial palettes aligned with presek-identity.css (paper + mark accent).
    colors_dark, colors_light = category_palette_pair(category_key)
    c_bg_dark, c_spot_dark, c_accent_dark = colors_dark
    c_bg_light, c_spot_light, c_accent_light = colors_light

    theme_l = str(theme or "").lower()
    style_content = _placeholder_style_block(
        theme_l,
        c_bg_dark,
        c_spot_dark,
        c_accent_dark,
        c_bg_light,
        c_spot_light,
        c_accent_light,
    )

    # Deterministic geometric adjustments
    angle = seed % 360
    shift_x = seed % 40
    shift_y = seed % 30

    # Auto text wrap logic for asymmetrical editorial layout
    def wrap_text(text, max_chars=28):
        words = text.split()
        lines = []
        cur = []
        for w in words:
            if len(" ".join(cur + [w])) > max_chars:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur:
            lines.append(" ".join(cur))
        return lines[:4]  # Max 4 lines

    display_lines = wrap_text(title)
    num_lines = len(display_lines)

    # Typographical baseline vertical alignment inside the 370px glass panel
    # The vertical center of the panel is at y=225.
    line_height = 42
    if num_lines >= 4:
        font_size = 24
        line_height = 36
    elif num_lines == 3:
        font_size = 27
        line_height = 40
    else:
        font_size = 30
        line_height = 44

    y_start = 225 - ((num_lines - 1) * line_height) / 2 + (font_size / 3.5)

    tspans = ""
    for i, line in enumerate(display_lines):
        y = y_start + i * line_height
        line_clean = _placeholder_svg_escape(line)
        tspans += f'<tspan x="80" y="{y}">{line_clean}</tspan>'

    # Vector Art backgrounds centered at cx=590, cy=225
    art_templates = {
        "Sport": f"""
            <ellipse cx="590" cy="225" rx="110" ry="60" class="ph-stroke-vvline" stroke-width="1.5"/>
            <ellipse cx="590" cy="225" rx="140" ry="80" class="ph-stroke-accent" stroke-width="2" stroke-dasharray="6 4" opacity="0.25"/>
            <line x1="450" y1="280" x2="730" y2="170" class="ph-stroke-accent" stroke-width="4" stroke-linecap="round" opacity="0.3"/>
            <circle cx="680" cy="190" r="10" class="ph-accent-fill" opacity="0.7"/>
            <circle cx="680" cy="190" r="4" class="ph-fill-dot" opacity="0.9"/>
        """,
        "Ekonomija": f"""
            <path d="M 450 280 L 510 230 L 570 250 L 630 170 L 690 120" class="ph-stroke-accent" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.35"/>
            <path d="M 450 280 L 510 230 L 570 250 L 630 170 L 690 120 L 690 280 L 450 280 Z" fill="url(#art_glow_{cluster_id})" opacity="0.1" stroke="none"/>
            <line x1="440" y1="280" x2="700" y2="280" class="ph-stroke-line" stroke-width="1.5"/>
            <line x1="440" y1="230" x2="700" y2="230" class="ph-stroke-vline" stroke-width="1" stroke-dasharray="4 4"/>
            <line x1="440" y1="170" x2="700" y2="170" class="ph-stroke-vline" stroke-width="1" stroke-dasharray="4 4"/>
            <circle cx="690" cy="120" r="8" class="ph-accent-fill" opacity="0.7"/>
        """,
        "Tehnologija": f"""
            <circle cx="590" cy="225" r="70" class="ph-stroke-vvline" stroke-width="1"/>
            <rect x="520" y="155" width="140" height="140" rx="12" class="ph-stroke-accent" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.3"/>
            <circle cx="590" cy="225" r="22" class="ph-accent-fill" opacity="0.4"/>
            <circle cx="535" cy="170" r="6" class="ph-accent-fill" opacity="0.7"/>
            <circle cx="645" cy="280" r="6" class="ph-accent-fill" opacity="0.7"/>
            <circle cx="645" cy="170" r="8" class="ph-fill-line" opacity="0.5"/>
            <line x1="535" y1="170" x2="590" y2="225" class="ph-stroke-line" stroke-width="1.5"/>
            <line x1="645" y1="280" x2="590" y2="225" class="ph-stroke-line" stroke-width="1.5"/>
        """,
        "Zabava": f"""
            <path d="M 460 240 C 510 160, 550 290, 590 225 C 630 160, 670 290, 720 210" class="ph-stroke-accent" stroke-width="4" stroke-linecap="round" opacity="0.35"/>
            <circle cx="590" cy="225" r="45" class="ph-accent-fill" opacity="0.3"/>
            <circle cx="610" cy="205" r="8" class="ph-fill-dot" opacity="0.6"/>
        """,
        "Politika": f"""
            <path d="M 480 270 L 700 270" class="ph-stroke-accent" stroke-width="4" stroke-linecap="round" opacity="0.3"/>
            <path d="M 480 160 L 700 160" class="ph-stroke-accent" stroke-width="4" stroke-linecap="round" opacity="0.3"/>
            <path d="M 515 160 L 515 270 M 552 160 L 552 270 M 590 160 L 590 270 M 627 160 L 627 270 M 665 160 L 665 270" class="ph-stroke-line" stroke-width="2" opacity="0.6"/>
            <path d="M 495 160 L 590 110 L 685 160 Z" class="ph-accent-shape" stroke-width="3" opacity="0.3"/>
            <circle cx="590" cy="215" r="20" class="ph-accent-fill" opacity="0.5"/>
        """,
        "Svet": f"""
            <circle cx="590" cy="225" r="90" class="ph-stroke-accent" stroke-width="2.5" opacity="0.3"/>
            <ellipse cx="590" cy="225" rx="90" ry="32" class="ph-stroke-line" stroke-width="1.5"/>
            <ellipse cx="590" cy="225" rx="32" ry="90" class="ph-stroke-line" stroke-width="1.5"/>
            <circle cx="625" cy="180" r="7" class="ph-accent-fill" opacity="0.7"/>
        """,
        "Local": f"""
            <circle cx="590" cy="225" r="90" class="ph-stroke-vvline" stroke-width="1"/>
            <circle cx="590" cy="225" r="70" class="ph-stroke-accent" stroke-width="2" stroke-dasharray="6 4" opacity="0.35"/>
            <circle cx="590" cy="225" r="40" class="ph-stroke-line" stroke-width="1"/>
            <line x1="490" y1="225" x2="690" y2="225" class="ph-stroke-line" stroke-width="1.5"/>
            <line x1="590" y1="125" x2="590" y2="325" class="ph-stroke-line" stroke-width="1.5"/>
            <circle cx="550" cy="245" r="10" class="ph-accent-fill" opacity="0.7"/>
            <circle cx="550" cy="245" r="4" class="ph-fill-dot" opacity="0.9"/>
        """,
        "default": f"""
            <circle cx="590" cy="225" r="60" class="ph-stroke-vvline" stroke-width="1"/>
            <circle cx="590" cy="225" r="85" class="ph-stroke-accent" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.25"/>
            <circle cx="590" cy="225" r="22" class="ph-accent-fill" opacity="0.4"/>
            <circle cx="535" cy="185" r="7" class="ph-accent-fill" opacity="0.6"/>
            <circle cx="645" cy="260" r="6" class="ph-accent-fill" opacity="0.6"/>
            <line x1="535" y1="185" x2="590" y2="225" class="ph-stroke-line" stroke-width="1.5"/>
            <line x1="645" y1="260" x2="590" y2="225" class="ph-stroke-line" stroke-width="1.5"/>
        """
    }

    art_svg = art_templates.get(category_key, art_templates["default"])

    status_label = "ПРЕГЛЕД НА ВЕСТИ" if lang == "mk" else "PREGLED VESTI"
    site_label = "PRESEK.MK" if lang == "mk" else "PRESEK"
    category_labels_mk = {
        "Sport": "СПОРТ",
        "Ekonomija": "ЕКОНОМИЈА",
        "Tehnologija": "ТЕХНОЛОГИЈА",
        "Zabava": "КУЛТУРА",
        "Hronika": "ХРОНИКА",
        "Makedonija": "МАКЕДОНИЈА",
        "Srbija": "СРБИЈА",
        "Balkan": "БАЛКАН",
        "Evropa": "ЕВРОПА",
        "Amerika": "АМЕРИКА",
        "Svet": "СВЕТ",
        "default": "ВЕСТИ",
    }
    category_labels_sr = {
        "Sport": "SPORT",
        "Ekonomija": "EKONOMIJA",
        "Tehnologija": "TEHNOLOGIJA",
        "Zabava": "KULTURA",
        "Hronika": "HRONIKA",
        "Makedonija": "MAKEDONIJA",
        "Srbija": "SRBIJA",
        "Balkan": "BALKAN",
        "Evropa": "EVROPA",
        "Amerika": "AMERIKA",
        "Svet": "SVET",
        "default": "VESTI",
    }
    category_label = (category_labels_mk if lang == "mk" else category_labels_sr).get(
        category_key,
        category_key.upper(),
    )

    # Define color scheme support style for browser/image-tag content evaluation
    color_scheme_style = 'style="color-scheme: light dark;"'

    # 3. Construct premium editorial dynamic SVG
    svg = [
        f'<svg viewBox="0 0 800 450" {color_scheme_style} xmlns="http://www.w3.org/2000/svg">',
        '<defs>',
        # Embed the dynamic styling rule-sets
        f'<style>{style_content}</style>',
        # Main Linear Background Gradient using styles
        f'  <linearGradient id="bg_{cluster_id}" x1="0%" y1="0%" x2="100%" y2="100%">',
        '    <stop class="bg-stop-start" offset="0%" style="stop-opacity:1" />',
        '    <stop class="bg-stop-end" offset="100%" style="stop-opacity:1" />',
        '  </linearGradient>',
        # Soft Neon Spotlight Glowing Mesh
        f'  <radialGradient id="mesh_{cluster_id}" cx="{60 + (seed%20)}%" cy="{40 + (seed%20)}%" r="70%">',
        '    <stop class="mesh-stop-start" offset="0%" />',
        '    <stop class="mesh-stop-end" offset="100%" />',
        '  </radialGradient>',
        # Transparent Gradient for Art Fills
        f'  <linearGradient id="art_glow_{cluster_id}" x1="0%" y1="0%" x2="0%" y2="100%">',
        '    <stop class="art-glow-start" offset="0%" />',
        '    <stop class="art-glow-end" offset="100%" />',
        '  </linearGradient>',
        # High-end paper-grain/noise texture filter
        '  <filter id="grain" x="0" y="0" width="100%" height="100%">',
        '    <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="4" stitchTiles="stitch" />',
        '    <feColorMatrix type="saturate" values="0" />',
        '    <feComponentTransfer><feFuncA type="linear" slope="0.035" /></feComponentTransfer>',
        '    <feComposite operator="in" in2="SourceGraphic" />',
        '  </filter>',
        '</defs>',
        
        # 1. Base Gradient Backgrounds
        f'<rect width="100%" height="100%" fill="url(#bg_{cluster_id})" />',
        f'<rect width="100%" height="100%" fill="url(#mesh_{cluster_id})" />',
        
        # 2. Tactile Grain Overlay
        '<rect width="100%" height="100%" class="ph-grain" filter="url(#grain)" />',
        
        # 3. Editorial panel (paper card + brand cut)
        '<rect x="40" y="40" width="720" height="370" rx="2" class="ph-glass" stroke-width="1" />',
        '<rect x="40" y="40" width="5" height="370" class="ph-accent-fill" opacity="0.92" />',
        
        # 4. Editorial Layout Grid Lines
        '<g class="ph-grid" stroke-width="1" stroke-dasharray="6 8">',
        '  <line x1="120" y1="40" x2="120" y2="410" />',
        '  <line x1="460" y1="40" x2="460" y2="410" />',
        '  <line x1="40" y1="110" x2="760" y2="110" />',
        '  <line x1="40" y1="340" x2="760" y2="340" />',
        '</g>',
        
        # 5. Editorial status
        '<circle cx="80" cy="75" r="4" class="ph-accent-fill" opacity="0.72" />',
        f'<text x="96" y="79" class="ph-meta" font-family="system-ui, -apple-system, sans-serif" font-size="10" font-weight="900" letter-spacing="2">{status_label}</text>',
        
        # 6. Beautiful Category Vector Art
        f'{art_svg}',
        
        # 7. Asymmetric Headline Typography
        f'<text class="ph-headline" font-family="Georgia, \'Times New Roman\', serif" font-size="{font_size}" font-weight="900">',
        f'  {tspans}',
        '</text>',
        
        # 8. Premium Branding Metadata
        f'<text x="80" y="378" class="ph-meta" font-family="system-ui, -apple-system, sans-serif" font-size="11" font-weight="900" letter-spacing="4">{site_label}</text>',
        f'<text x="720" y="378" text-anchor="end" class="ph-category" font-family="system-ui, -apple-system, sans-serif" font-size="11" font-weight="900" letter-spacing="2">{category_label}</text>',
        
        '</svg>'
    ]

    return "".join(svg)
