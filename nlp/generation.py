import re
import math
import logging
from collections import Counter
from core.trending import STOPWORDS

log = logging.getLogger(__name__)
from nlp.utils import (
    _articles_cache_key,
    _cache_get,
    _cache_set,
    _comparison_cache,
    _question_evidence_cache,
    _normalize_articles_for_local_use,
    cleanAndDecode,
    deShout,
)
from utils import record_runtime_event

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
        "klucen_aspekt": "Клучен аспект",
        "zosto_vazno": "Зошто е важно",
        "beleska": "Белешка",
        "sodrzina_generirana": "Содржината е генерирана преку локална системска анализа.",
        "povece_mediumi": "Развојот на настаните го следат повеќе медиуми.",
        "sistemski_pregled": "Системски преглед базиран на {count} извори.",
        "potvrda_osnovna": "{s1} и {s2} ја потврдуваат истата основна линија на настанот.",
        "denesniot_pregled": "Денешниот преглед е обележан со: {text}.",
        "denot_obeleza": "Денот го обележа {text1}, а внимание привлекува и {text2}.",
        "potencijalna_promena": "Потенцијална промена во политичката моќ и регионалните стратегии.",
        "direktno_vlijanie": "Директно влијание врз економската стабилност и стандардот на граѓаните.",
        "potvrden_razvoj": "Потврден развој со висок медиумски консензус од {count} извори.",
        "faza_razvoj": "Настанот е во фаза на развој и се очекуваат понатамошни официјални потврди.",
        "najdirektno": "Најдиректно од достапните извори: {text}",
        "sto_se_slucuva": "Што се случува",
        "sledeno_od": "Следено од",
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
        "klucen_aspekt": "Ključni aspekt",
        "zosto_vazno": "Zašto je važno",
        "beleska": "Beleška",
        "sodrzina_generirana": "Sadržaj je generisan putem lokalne sistemske analize.",
        "povece_mediumi": "Razvoj događaja prati više medija.",
        "sistemski_pregled": "Sistemski pregled baziran na {count} izvora.",
        "potvrda_osnovna": "{s1} i {s2} potvrđuju istu osnovnu liniju događaja.",
        "denesniot_pregled": "Današnji pregled je obeležen sa: {text}.",
        "denot_obeleza": "Dan je obeležio {text1}, a pažnju privlači i {text2}.",
        "potencijalna_promena": "Potencijalna promena u političkoj moći i regionalnim strategijama.",
        "direktno_vlijanie": "Direktan uticaj na ekonomsku stabilnost i standard građana.",
        "potvrden_razvoj": "Potvrđen razvoj sa visokim medijskim konsenzusom od {count} izvora.",
        "faza_razvoj": "Događaj je u fazi razvoja i očekuju se dalja službena potvrđivanja.",
        "najdirektno": "Najdirektnije iz dostupnih izvora: {text}",
        "sto_se_slucuva": "Šta se dešava",
        "sledeno_od": "Prati",
    },
}

from nlp.keywords import (
    _sentence_tokens,
    _extract_capitalized_phrases,
    extract_keyphrases_locally,
    normalize_tag_name,
    SOURCE_NOISE_WORDS,
    TAG_NOISE_WORDS,
)
from nlp.text_processing import _normalize_summary_sentence, _is_noisy_summary_sentence


def _clean_briefing_snippet(text):
    clean = str(text or "").strip()
    if not clean:
        return ""
    clean = re.sub(
        r"^[A-Za-z][^,]{0,40},\s*\d{1,2}\s+[^\d]{3,20}\s+\d{4}\s*\([^)]{2,20}\)\s*[-–—]\s*",
        "",
        clean,
    )
    clean = re.sub(
        r"^(Beograd|Bitola|Ohrid|Tetovo|Stip|Prilep|Veles|Kumanovo|Berovo|Dojran)\s*,\s*",
        "",
        clean,
    )
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _normalize_briefing_line(text):
    clean = _clean_briefing_snippet(text)
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
        return clean_title # Fallback if no description

    title_terms = set(_extract_terms(clean_title))
    description_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_description) if len(s.strip()) > 20
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
        summarize_locally(
            f"{clean_title}. {clean_description}", sentence_count=1, title=clean_title
        ).strip()
    )
    
    # Final check: if summary is still just the title, try to return first 140 chars of description
    if summary.casefold() == clean_title.casefold() and clean_description:
        return clean_description[:140]

    return summary or clean_description or clean_title


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
    if any(term in context for term in ("cena", "poskap", "inflacija", "budzet", "цена", "поскап", "инфлација", "буџет")):
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
    if source_count >= 3:
        return t["potvrden_razvoj"].format(count=source_count)

    return t["faza_razvoj"]


def _condense_briefing_update(text, *, max_chars=180):
    clean = _normalize_briefing_line(text)
    if not clean:
        return ""
    # Split by sentence but keep punctuation
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    candidate = sentences[0].strip()
    
    if len(candidate) < 30 and len(sentences) > 1:
        candidate = f"{candidate} {sentences[1].strip()}"
        
    candidate = candidate.rstrip(" .,;:")
    if len(candidate) <= max_chars:
        return candidate
    return candidate[: max_chars - 1].rstrip(" ,;:") + "…"


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
            overlap = len(update_tokens & other_tokens) / max(
                1, min(len(update_tokens), len(other_tokens))
            )
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
    if re.match(r"^[A-Za-z0-9\-]{2,}:\s", clean):
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
    return [
        term
        for term in re.findall(r"[A-Za-zA-Za-z0-9]{3,}", (text or "").lower())
        if term not in STOPWORDS
    ]


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


def summarize_locally(text, sentence_count=3, topic=None, title=None, lang="mk"):
    """Non-AI summarizer for news-like text."""
    if not text or len(text) < 100:
        return text

    sentences = [
        _normalize_summary_sentence(sentence)
        for sentence in re.split(r"(?<=[.!?])\s+", text)
    ]
    sentences = [sentence for sentence in sentences if sentence]
    if len(sentences) <= sentence_count:
        return text

    potential_title = None
    if not title:
        for s in sentences:
            if not _is_noisy_summary_sentence(s):
                potential_title = s
                break

    title_terms = (
        set(_sentence_tokens(title))
        if title
        else set(_sentence_tokens(potential_title or sentences[0]))
    )

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
            "denari", "evra", "procent", "milioni", "budzet", "plata", "ceni", "inflacija", "berza",
            "денари", "евра", "процент", "милиони", "буџет", "плата", "цени", "инфлација", "берза",
            "dinara", "evra", "procenat", "miliona", "budžet", "plata", "cene", "inflacija", "berza"
        }
    elif topic == "Politika":
        topic_boost_words = {
            "minister", "pretsedatel", "sobranie", "zakon", "partija", "lider", "vlada", "izbori",
            "министер", "претседател", "собрание", "закон", "партија", "лидер", "влада", "избори",
            "ministar", "predsednik", "skupština", "zakon", "partija", "lider", "vlada", "izbori"
        }
    elif topic == "Sport":
        topic_boost_words = {
            "natprevar", "gol", "pobeda", "prvenstvo", "klub", "liga", "fudbal", "kosarka",
            "натпревар", "гол", "победа", "првенство", "клуб", "лига", "фудбал", "кошарка",
            "utakmica", "gol", "pobeda", "prvenstvo", "klub", "liga", "fudbal", "košarka"
        }
    elif topic == "Kriminal":
        topic_boost_words = {
            "policija", "apsenje", "ubistvo", "sud", "obvinitelstvo", "zatvor", "napad",
            "полиција", "апсење", "убиство", "суд", "обвинителство", "затвор", "напад",
            "policija", "hapšenje", "ubistvo", "sud", "tužilaštvo", "zatvor", "napad"
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
        score += (
            (overlap * 0.5)
            + number_bonus
            + lead_bonus
            + density_bonus
            + proper_noun_bonus
            + topic_bonus
        )
        sentence_scores[i] = score

    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[
        :sentence_count
    ]
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
        summary = [
            sentence
            for sentence in sentences[:sentence_count]
            if not _is_noisy_summary_sentence(sentence)
        ]

    return " ".join(summary)


def summarize_article_fallback(title, description=None, topic=None, lang="mk"):
    parts = [str(title or "").strip(), str(description or "").strip()]
    text = ". ".join([part for part in parts if part])
    summary = summarize_locally(
        text, sentence_count=2, topic=topic, title=title, lang=lang
    ).strip()
    summary = re.sub(r"^[⚪🟢🔴]\s*", "", summary, flags=re.UNICODE)
    summary = re.sub(r"#[^\s#]+", "", summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary[:420] if summary else str(title or "").strip()


def _join_fragments(parts):
    clean = [
        str(part or "").strip(" .,;:")
        for part in parts
        if str(part or "").strip(" .,;:")
    ]
    return "; ".join(clean)


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
    names = [
        str(article.get("source") or "izvor").strip() for article in articles[:limit]
    ]
    return ", ".join(name for name in names if name)


def compare_cluster_sources(articles, lang="mk"):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {"common_line": "", "difference_points": [], "open_points": []}

    cache_key = _articles_cache_key(articles) + f":{lang}"
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
            "тврди", "според", "непотвр", "навод", "се очекува", "може", "би мож", "засега", "се уште", "се развива"
        )

    all_terms = Counter()
    article_term_sets, article_texts_lower, title_pairs = [], [], []
    number_map, entity_map = {}, {}
    uncertain_sources, article_fact_profiles = [], []

    for article in articles:
        combined = " ".join([article["title"], article["description"]]).strip()
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
    common_terms = [
        t
        for t, c in all_terms.most_common(8)
        if c >= threshold and t not in SOURCE_NOISE_WORDS
    ]
    pooled_text = " ".join(a["title"] + ". " + a["description"] for a in articles)
    candidate_phrases = extract_keyphrases_locally(pooled_text, top_n=12)
    common_phrases = [
        p
        for p in candidate_phrases
        if p
        and " " in p
        and sum(1 for txt in article_texts_lower if p.lower() in txt) >= threshold
    ]
    common_line = ""
    if common_phrases:
        from nlp.keywords import _format_common_line_from_phrases
        try:
            common_line = _format_common_line_from_phrases(common_phrases[:3], lang=lang)
        except Exception as e:
            log.debug(f"[nlp.generation] Error formatting common line: {e}")
            if lang == "sr":
                common_line = (
                    "Većina izvora se slaže oko "
                    + ", ".join(common_phrases[:3])
                    + " kao tema u fokusu."
                )
            else:
                common_line = (
                    "Повеќето извори се согласуваат околу "
                    + ", ".join(common_phrases[:3])
                    + " како теми во фокус."
                )
    elif common_terms:
        if lang == "sr":
            common_line = (
                "Većina izvora se slaže oko "
                + ", ".join(common_terms[:4])
                + " kao tema u fokusu."
            )
        else:
            common_line = (
                "Повеќето извори се согласуваат околу "
                + ", ".join(common_terms[:4])
                + " како теми во фокус."
            )

    difference_points, seen_titles = [], set()
    unique_titles = []
    for s, t in title_pairs:
        if t.casefold() not in seen_titles:
            seen_titles.add(t.casefold())
            unique_titles.append((s, t))
    if len(unique_titles) >= 2:
        if lang == "sr":
            difference_points.append(
                f"{unique_titles[0][0]} najdirektnije formuliše razvoj kao „{unique_titles[0][1]}“, dok {unique_titles[1][0]} više naglašava „{unique_titles[1][1]}“."
            )
        else:
            difference_points.append(
                f"{unique_titles[0][0]} најдиректно го формулира развојот како „{unique_titles[0][1]}“, додека {unique_titles[1][0]} повеќе нагласува „{unique_titles[1][1]}“."
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
    if uncertain_sources:
        if lang == "sr":
            open_points.append(
                f"Detalji oko ovog razvoja ostaju nepotvrđeni kod {', '.join(uncertain_sources[:2])}."
            )
        else:
            open_points.append(
                f"Деталите околу овој развој остануваат непотврдени кај {', '.join(uncertain_sources[:2])}."
            )

    # Extra check for numbers mismatch as open points
    from nlp.categories import detect_topic

    all_titles = " ".join([a.get("title") or "" for a in articles])
    is_sport = detect_topic(all_titles) == "Sport"

    if is_sport:
        scores = [
            set(_extract_sports_scores(a.get("title") or ""))
            | set(_extract_sports_scores(a.get("description") or ""))
            for a in articles
        ]
        all_scores = set().union(*scores)
        conflicting_scores = [
            s
            for s in all_scores
            if sum(1 for ms in scores if s in ms) < len(articles) and len(articles) > 1
        ]
        if conflicting_scores:
            if lang == "sr":
                open_points.append(
                    f"Informacije za konačan rezultat se razlikuju (na primer: {conflicting_scores[0]}), što može ukazivati na promenu u toku meča."
                )
            else:
                open_points.append(
                    f"Информациите за конечниот резултат се разликуваат (на пример: {conflicting_scores[0]}), што може да укажува на промена во текот на мечот."
                )

    # Generic numbers only if not many articles (less noise)
    if len(articles) > 1 and len(articles) <= 3:
        nums = [
            set(_extract_number_tokens(a.get("description") or "")) for a in articles
        ]
        all_nums = set().union(*nums)
        conflicting_nums = [n for n in all_nums if sum(1 for s in nums if n in s) == 1]
        if conflicting_nums and not any(
            n in "".join(open_points) for n in conflicting_nums
        ):
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
        }

    t = _T.get(lang, _T["mk"])
    lead = articles[0]
    comparison = compare_cluster_sources(articles, lang=lang)

    # 1. Smarter Context Extraction
    desc = cleanAndDecode(lead.get("description", ""))
    sentences = [
        _normalize_briefing_line(s)
        for s in re.split(r"(?<=[.!?])\s+", desc)
        if len(s.strip()) > 20
    ]
    sentences = [s for s in sentences if s and not _is_noisy_summary_sentence(s)]

    # 2. Build Summary Points
    summary_lines = []
    lead_title = deShout(cleanAndDecode(lead.get("title", ""))).strip()
    
    # Use the improved update extraction to avoid title repetition
    update_point = _extract_briefing_update({"title": lead_title, "description": desc}, lang=lang)

    if update_point and update_point.casefold() != lead_title.casefold():
        summary_lines.append(f"• {t['klucen_razvoj']}: {update_point}")
    else:
        # If no good update found, use a refined version of the title
        summary_lines.append(f"• {t['nastan']}: {lead_title}")

    if len(sentences) > 1:
        summary_lines.append(f"• {t['detali']}: {sentences[0]}")

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
        summary_lines.append(f"• {t['fokus']}: {common}")

    sources_str = _source_list(articles, limit=4)
    summary_lines.append(
        f"• {t['pokrienost']}: {t['sledeno_od']} {len(articles)} {t['izvori']} ({sources_str})."
    )
    
    if comparison.get("open_points"):
        summary_lines.append(f"• {t['otvoreno_lower']}: {comparison['open_points'][0]}")

    summary = "\n".join(summary_lines)

    # 3. Build a "Generated Article"
    article_body = []
    if update_point and update_point.casefold() != lead_title.casefold():
        article_body.append(f"{lead_title}. {update_point}.")
    else:
        article_body.append(f"{lead_title}. {t['povece_mediumi']}")

    if comparison.get("common_line"):
        article_body.append(comparison["common_line"])

    if comparison.get("difference_points"):
        article_body.append(comparison["difference_points"][0])

    generated_article = "\n\n".join(article_body)

    # 4. Perspectives
    perspectives = []
    if len(articles) > 1:
        perspectives.append(
            {
                "angle": t["konsenzus"],
                "content": t["potvrda_osnovna"].format(s1=articles[0]['source'], s2=articles[1]['source']),
            }
        )

    if comparison["difference_points"]:
        perspectives.append(
            {"angle": t["nijansi"], "content": comparison["difference_points"][0]}
        )

    if comparison.get("open_points"):
        perspectives.append(
            {"angle": t["otvoreno_lower"], "content": comparison["open_points"][0]}
        )

    record_runtime_event("local_synthesis_path", mode="enhanced_fallback")
    return {
        "summary": summary,
        "perspectives": perspectives[:3],
        "synthetic_headline": lead_title,
        "generated_article": generated_article,
        "synthetic_standfirst": t["sistemski_pregled"].format(count=len(articles)),
    }


def generate_daily_brief_fallback(clusters, lang="mk"):
    t = _T.get(lang, _T["mk"])
    if not clusters:
        return f"## {t['dneven_brifing']}\n\n{t['nema_vesti']}"
    display_clusters = sorted(
        clusters[:4],
        key=lambda item: (
            -int(bool(str(item.get("cluster_summary") or "").strip())),
            int(_is_penalized_briefing_title(item.get("title"))),
            -int(item.get("source_count") or 0),
        ),
    )
    display_clusters = _dedupe_briefing_clusters(display_clusters, limit=4, lang=lang)
    lines = [f"## {t['dinamika_den']}", ""]
    
    if len(display_clusters) >= 1:
        lead_update = _condense_briefing_update(
            _extract_briefing_update(display_clusters[0], lang=lang), max_chars=150
        )
        intro_line = t["denesniot_pregled"].format(text=lead_update)

        if len(display_clusters) >= 2:
            sec_update = _condense_briefing_update(
                _extract_briefing_update(display_clusters[1], lang=lang), max_chars=150
            )
            intro_line = t["denot_obeleza"].format(text1=lead_update, text2=sec_update)

        lines.append(intro_line)
        lines.append("")

    lines.append(f"## {t['kontekst_razliki']}")
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
        lines.append(
            f"• {short_t}: " f"{_extract_briefing_importance(fallback_cluster, lang=lang)}."
        )
    lines.append("")

    for index, cluster in enumerate(display_clusters, start=1):
        title = str(cluster.get("title") or "").strip()
        clean_title = _clean_briefing_snippet(title)
        
        # Use content-aware extraction to avoid repeating the title
        summary = _extract_briefing_update(cluster, lang=lang)
        importance = _extract_briefing_importance(cluster, lang=lang)
        
        lines.append(f"### {index}. {clean_title or title}")
        
        if summary and summary.casefold() != (clean_title or title).casefold():
            lines.append(f"- {t['klucen_aspekt']}: {summary}.")
        
        lines.append(f"- {t['zosto_vazno']}: {importance}.")
        lines.append("")
        
    lines.append(
        f"**{t['beleska']}**: {t['sodrzina_generirana']}"
    )
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


def _score_question_snippet(
    question_terms, question_entities, question_numbers, snippet, kind, article_rank
):
    text = str(snippet or "").strip()
    if not text:
        return 0.0
    snippet_terms, snippet_numbers = set(_extract_terms(text)), set(
        _extract_number_tokens(text)
    )
    snippet_entities = {e.casefold() for e in _extract_capitalized_phrases(text)}
    score = (
        len(question_terms & snippet_terms) * 2.4
        + sum(
            1 for e in question_entities if e in text.lower() or e in snippet_entities
        )
        * 2.1
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
            score = (
                _score_question_snippet(
                    q_terms, q_entities, q_numbers, snip, kind, rank
                )
                + c_score
            )
            ranked.append(
                {"article": art, "snippet": snip, "kind": kind, "score": score}
            )
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
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip())
        if s.strip()
    ]
    if not sentences:
        return True
    if len(set(re.sub(r"\s+", " ", s.casefold()) for s in sentences)) < len(sentences):
        return True
    return (
        sum(1 for s in sentences if _is_low_information_fragment(s))
        > len(sentences) / 2
    )


def _build_grounded_answer_from_evidence(evidence, comparison=None, lang="mk"):
    t = _T.get(lang, _T["mk"])
    if not evidence:
        return ""
    p = evidence[0]
    p_snip = _coerce_grounded_snippet(
        p.get("snippet") or p["article"].get("title") or ""
    )
    if _is_low_information_fragment(p_snip):
        p_snip = _coerce_grounded_snippet(
            summarize_locally(p["article"].get("description", ""), sentence_count=1)
        )
    return t["najdirektno"].format(text=p_snip)


def _build_minimum_cluster_summary(articles, comparison=None, lang="mk"):
    t = _T.get(lang, _T["mk"])
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return ""
    return f"• {t['sto_se_slucuva']}: {articles[0]['title']}\n• {t['pokrienost']}: {len(articles)} {t['izvori']}, {t['sledeno_od']} i {_source_list(articles)}."


def generate_local_placeholder(cluster_id, title, category="vesti"):
    import hashlib
    
    # 1. Deterministic seed from cluster_id
    seed = int(hashlib.md5(str(cluster_id).encode()).hexdigest(), 16)
    
    # 2. Professional Category Palettes (Primary, Deep, Accent)
    palettes = {
        "Srbija":      ["#8b1e22", "#4a0e10", "#c42a2e"], # Editorial Crimson
        "Makedonija":  ["#d62828", "#8c1c1c", "#f77f00"], # Macedonian Sun tones
        "Balkan":      ["#2d4a3e", "#1a2e25", "#4d806a"], # Deep Forest
        "Evropa":      ["#1b3a5a", "#0d1e33", "#3d6db2"], # Diplomatic Blue
        "Amerika":     ["#1a365d", "#102a43", "#2b6cb0"], # Atlantic Blue
        "Svet":        ["#4a3f5a", "#2d2638", "#7a6a96"], # Global Dusk
        "Sport":       ["#9c4221", "#5c2a12", "#e85d04"], # Clay/Dynamic
        "Tehnologija": ["#1a202c", "#0f172a", "#4a5568"], # Slate/Midnight
        "Ekonomija":   ["#2c5282", "#1a365d", "#4299e1"], # Corporate Blue
        "Hronika":     ["#2d3748", "#1a202c", "#4a5568"], # Industrial Grey
        "Zabava":      ["#702459", "#4a0e3a", "#b83280"], # Artsy Magenta
        "default":     ["#2d3748", "#1a202c", "#718096"],
    }
    
    colors = palettes.get(category, palettes["default"])
    c1, c2, c3 = colors
    
    # 3. Deterministic Geometric Shifts
    shift_x = (seed % 100)
    shift_y = (seed % 80)
    angle = (seed % 360)
    
    # 4. Text Wrapping Logic
    def wrap_text(text, max_chars=35):
        words = text.split()
        lines = []
        cur = []
        for w in words:
            if len(" ".join(cur + [w])) > max_chars:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        if cur: lines.append(" ".join(cur))
        return lines[:4] # Max 4 lines

    display_lines = wrap_text(title)
    text_y_start = 220 - (len(display_lines) - 1) * 25
    
    tspans = ""
    for i, line in enumerate(display_lines):
        y = text_y_start + i * 52
        # Clean line for XML
        line_clean = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        tspans += f'<tspan x="400" y="{y}">{line_clean}</tspan>'

    # 5. Generative SVG Construction
    svg = [
        f'<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">',
        f'<defs>',
        # Main Linear Gradient
        f'  <linearGradient id="grad_{cluster_id}" x1="0%" y1="0%" x2="100%" y2="100%" gradientTransform="rotate({angle})">',
        f'    <stop offset="0%" style="stop-color:{c1};stop-opacity:1" />',
        f'    <stop offset="100%" style="stop-color:{c2};stop-opacity:1" />',
        f'  </linearGradient>',
        # Radial Accent (The "Mesh" feel)
        f'  <radialGradient id="mesh_{cluster_id}" cx="{20 + (seed%60)}%" cy="{20 + (seed%60)}%" r="80%">',
        f'    <stop offset="0%" style="stop-color:{c3};stop-opacity:0.4" />',
        f'    <stop offset="100%" style="stop-color:{c2};stop-opacity:0" />',
        f'  </radialGradient>',
        # Filter for subtle noise/texture
        f'  <filter id="noise" x="0" y="0" width="100%" height="100%">',
        f'    <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch" />',
        f'    <feColorMatrix type="saturate" values="0" />',
        f'    <feComponentTransfer><feFuncA type="linear" slope="0.03" /></feComponentTransfer>',
        f'    <feComposite operator="in" in2="SourceGraphic" />',
        f'  </filter>',
        f'</defs>',
        # Background Layers
        f'<rect width="100%" height="100%" fill="url(#grad_{cluster_id})" />',
        f'<rect width="100%" height="100%" fill="url(#mesh_{cluster_id})" />',
        # Subtle Geometric Overlay (Dots or Lines)
        f'<rect width="100%" height="100%" fill="white" opacity="0.03" filter="url(#noise)" />',
    ]
    
    # Optional Geometric Detail based on ID
    if seed % 2 == 0:
        # Grid Pattern
        svg.append(f'<path d="M 0 {shift_y} L 800 {shift_y} M {shift_x} 0 L {shift_x} 450" stroke="white" stroke-width="0.5" opacity="0.1" />')
    else:
        # Subtle circle
        svg.append(f'<circle cx="{800-shift_x}" cy="{shift_y}" r="150" fill="white" opacity="0.05" />')

    # Typography
    svg.extend([
        f'<text font-family="serif" text-anchor="middle" font-size="38" font-weight="800" fill="white" style="text-shadow: 0 4px 12px rgba(0,0,0,0.3)">',
        f"{tspans}",
        f"</text>",
        # Branding
        f'<rect x="40" y="385" width="120" height="2" fill="white" opacity="0.3" />',
        f'<text x="40" y="415" font-family="sans-serif" font-size="16" font-weight="900" fill="white" opacity="0.6" letter-spacing="4">PRESEK</text>',
        f'<text x="760" y="415" text-anchor="end" font-family="sans-serif" font-size="12" font-weight="700" fill="white" opacity="0.4" letter-spacing="1">{category.upper()}</text>',
        f"</svg>"
    ])
    
    return "".join(svg)
