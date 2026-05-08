import re
import math
from collections import Counter
from trending import STOPWORDS
from nlp.utils import _articles_cache_key, _cache_get, _cache_set, _comparison_cache, _question_evidence_cache, _normalize_articles_for_local_use, cleanAndDecode, deShout
from utils import record_runtime_event

from nlp.keywords import _sentence_tokens, _extract_capitalized_phrases, extract_keyphrases_locally, normalize_tag_name, SOURCE_NOISE_WORDS, TAG_NOISE_WORDS
from nlp.text_processing import _normalize_summary_sentence, _is_noisy_summary_sentence

def _clean_briefing_snippet(text):
    clean = str(text or "").strip()
    if not clean:
        return ""
    clean = re.sub(r"^[A-ZА-ЯЀ-Я][^,]{0,40},\s*\d{1,2}\s+[^\d]{3,20}\s+\d{4}\s*\([^)]{2,20}\)\s*[-–—]\s*", "", clean)
    clean = re.sub(r"^(Скопје|Битола|Охрид|Тетово|Штип|Прилеп|Велес|Куманово|Берово|Дојран)\s*,\s*", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

def _normalize_briefing_line(text):
    clean = _clean_briefing_snippet(text)
    clean = re.sub(r"^[\-•*#\d.\)\s]+", "", clean).strip()
    clean = re.sub(r"\[\d+\]", "", clean).strip()
    clean = re.sub(
        r"^(Што е новото|Што се менува|Зошто е важно|Што се случува|Што е потврдено|Покриеност|Контекст|Разлика|Отворено)\s*:\s*",
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

def _extract_briefing_update(cluster):
    cluster = cluster or {}
    synthesis_lines = _briefing_lines_from_text(
        cluster.get("cluster_summary") or cluster.get("generated_article") or "",
        max_lines=4,
    )
    if synthesis_lines:
        return synthesis_lines[0]

    clean_title = _clean_briefing_snippet(cluster.get("title"))
    clean_description = _clean_briefing_snippet(cluster.get("description"))
    summary = _clean_briefing_snippet(
        summarize_locally(f"{clean_title}. {clean_description}", sentence_count=2).strip()
    )
    return summary or clean_description or clean_title

def _extract_briefing_importance(cluster):
    cluster = cluster or {}
    diff = _normalize_briefing_line(cluster.get("difference_point"))
    if diff:
        return diff

    open_point = _normalize_briefing_line(cluster.get("open_point"))
    if open_point:
        return open_point

    synthesis_lines = _briefing_lines_from_text(
        cluster.get("cluster_summary") or cluster.get("generated_article") or "",
        max_lines=4,
    )
    if len(synthesis_lines) >= 2:
        return synthesis_lines[1]

    clean_title = _clean_briefing_snippet(cluster.get("title"))
    clean_description = _clean_briefing_snippet(cluster.get("description"))
    context = f"{clean_title} {clean_description}".casefold()
    if any(term in context for term in ("избори", "парламентарни избори", "гласање", "гласаат")):
        return "Исходот може брзо да ја насочи следната политичка фаза и регионалните реакции"

    # 1. Fact Extraction: Find the most informative sentence in description that adds new info
    description_lines = _briefing_lines_from_text(clean_description, max_lines=4)
    title_terms = set(_extract_terms(clean_title))
    
    best_fact = ""
    for line in description_lines:
        line_terms = set(_extract_terms(line))
        if not line_terms: continue
        overlap = len(title_terms & line_terms) / len(line_terms)
        # We want a line that isn't just repeating the title (overlap < 0.6)
        # but is substantial (len > 30)
        if overlap < 0.6 and len(line) > 30:
            best_fact = _condense_briefing_update(line, max_chars=160)
            break
            
    if best_fact:
        return best_fact

    if any(term in context for term in ("балистич", "ракета", "ракети", "северна кореја", "пјонгјанг")):
        return "нови воени сигнали, предупредувања и дипломатски реакции"
    if any(term in context for term in ("мировник", "мировници", "он", "либан", "унифил", "меѓународните мисии")):
        return "безбедноста на меѓународните мисии и регионалната стабилност"

    # 2. Coverage-based fallback (last resort, better than "remains important")
    source_count = cluster.get("source_count") or 1
    source_name = cluster.get("source") or "повеќе извори"
    
    if source_count >= 3:
        return f"Темата предизвика широк интерес кај медиумите, со потврдени извештаи од {source_count} различни извори"
    
    return f"Развојот на настанот го следат медиумите, со првични детални информации објавени од {source_name}"

def _condense_briefing_update(text, *, max_chars=180):
    clean = _normalize_briefing_line(text)
    if not clean:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)[0].strip()
    candidate = first_sentence or clean
    candidate = candidate.rstrip(" .,;:")
    if len(candidate) <= max_chars:
        return candidate
    return candidate[: max_chars - 1].rstrip(" ,;:") + "…"

def _extract_briefing_focus_point(cluster):
    text = _condense_briefing_update(_extract_briefing_update(cluster), max_chars=140)
    if not text:
        text = _clean_briefing_snippet(cluster.get("title"))
    text = _normalize_briefing_line(text)
    return text[:180].rstrip(" .,;:")

def _dedupe_briefing_clusters(clusters, limit=4):
    deduped = []
    seen_titles = set()
    seen_updates = []

    for cluster in clusters:
        title = _clean_briefing_snippet(cluster.get("title"))
        title_key = title.casefold()
        if title_key and title_key in seen_titles:
            continue

        update = _extract_briefing_focus_point(cluster)
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
    if re.match(r"^[A-ZА-ЯЀ-Я0-9\-]{2,}:\s", clean):
        return True
    return any(marker in lowered for marker in {
        "во очајна потрага", "крах систем", "слави победа", "предавство",
        "скандал", "шокантно", "удри", "жестоко", "катастрофа",
    })

def _extract_terms(text):
    return [
        term for term in re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
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
                    if m == 0 and h >= 8: continue # 08:00, 20:00 etc
                    if h > 23: pass # Definitely a score (e.g. 32:28 in handball)
                    elif h >= 8 and m in (0, 15, 30, 45): continue # Likely time
                
                # Exclude common years/seasons (e.g. 2024-2025)
                if "-" in clean and h > 1900 and m > 1900: continue
                
                # If it's a very high number on one side and small on other, 
                # might be a year or something else, but in sports it could be basketball.
                # Max basketball score is around 150.
                if h > 200 or m > 200: continue
                
                scores.append(clean)
            except ValueError:
                pass
    return scores

def summarize_locally(text, sentence_count=3, topic=None, title=None):
    """Non-AI summarizer for news-like text."""
    if not text or len(text) < 100:
        return text

    sentences = [
        _normalize_summary_sentence(sentence)
        for sentence in re.split(r'(?<=[.!?])\s+', text)
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
    
    title_terms = set(_sentence_tokens(title)) if title else set(_sentence_tokens(potential_title or sentences[0]))
    
    words = _sentence_tokens(text)
    word_freq = Counter(words)
    if not word_freq:
        return ". ".join(sentences[:sentence_count])

    max_freq = max(word_freq.values())
    for word in word_freq:
        word_freq[word] = word_freq[word] / max_freq

    topic_boost_words = set()
    if topic == "Економија":
        topic_boost_words = {"денари", "евра", "процент", "милиони", "буџет", "плата", "цени", "инфлација", "берза"}
    elif topic == "Политика":
        topic_boost_words = {"министер", "претседател", "собрание", "закон", "партија", "лидер", "влада", "избори"}
    elif topic == "Спорт":
        topic_boost_words = {"натпревар", "гол", "победа", "првенство", "клуб", "лига", "фудбал", "кошарка"}
    elif topic == "Криминал":
        topic_boost_words = {"полиција", "апсење", "убиство", "суд", "обвинителство", "затвор", "напад"}

    sentence_scores = {}
    for i, sentence in enumerate(sentences):
        sentence_words = _sentence_tokens(sentence)
        if not sentence_words: continue

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

        if len(sentence) > 280: score *= 0.6
        score += (overlap * 0.5) + number_bonus + lead_bonus + density_bonus + proper_noun_bonus + topic_bonus
        sentence_scores[i] = score

    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:sentence_count]
    top_indices.sort()

    summary = []
    seen = set()
    for idx in top_indices:
        sentence = sentences[idx].strip()
        key = sentence.casefold()
        if key in seen: continue
        seen.add(key)
        summary.append(sentence)

    if not summary:
        summary = [sentence for sentence in sentences[:sentence_count] if not _is_noisy_summary_sentence(sentence)]

    return " ".join(summary)

def summarize_article_fallback(title, description=None, topic=None):
    parts = [str(title or "").strip(), str(description or "").strip()]
    text = ". ".join([part for part in parts if part])
    summary = summarize_locally(text, sentence_count=2, topic=topic, title=title).strip()
    summary = re.sub(r'^[⚪🟢🔴]\s*', '', summary, flags=re.UNICODE)
    summary = re.sub(r'#[^\s#]+', '', summary)
    summary = re.sub(r'\s+', ' ', summary).strip()
    return summary[:420] if summary else str(title or "").strip()

def _join_fragments(parts):
    clean = [str(part or "").strip(" .,;:") for part in parts if str(part or "").strip(" .,;:")]
    return "; ".join(clean)

def _extract_comparison_entities(text):
    entities = []
    for phrase in _extract_capitalized_phrases(text):
        clean = normalize_tag_name(phrase)
        if not clean: continue
        lowered = clean.casefold()
        if lowered in SOURCE_NOISE_WORDS or lowered in TAG_NOISE_WORDS:
            continue
        entities.append(clean)
    return entities

def _source_list(articles, limit=3):
    names = [str(article.get("source") or "Извор").strip() for article in articles[:limit]]
    return ", ".join(name for name in names if name)

def compare_cluster_sources(articles):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {"common_line": "", "difference_points": [], "open_points": []}

    cache_key = _articles_cache_key(articles)
    cached = _cache_get(_comparison_cache, cache_key)
    if cached is not None:
        record_runtime_event("local_compare_cache", mode="hit")
        return cached
    record_runtime_event("local_compare_cache", mode="miss")

    uncertainty_markers = ("тврди", "според", "непотвр", "навод", "се очекува", "може", "би мож", "засега", "се уште", "се развива")
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
        if article["title"]: title_pairs.append((article["source"], article["title"]))
        numbers = set(_extract_number_tokens(combined))
        for n in numbers: number_map.setdefault(n, set()).add(article["source"])
        entities = set(_extract_comparison_entities(combined))
        for e in entities: entity_map.setdefault(e, set()).add(article["source"])
        if any(m in combined.lower() for m in uncertainty_markers): uncertain_sources.append(article["source"])
        article_fact_profiles.append({"source": article["source"], "terms": terms, "numbers": numbers, "entities": entities, "uncertain": any(m in combined.lower() for m in uncertainty_markers)})

    threshold = max(2, math.ceil(len(articles) / 2))
    common_terms = [t for t, c in all_terms.most_common(8) if c >= threshold and t not in SOURCE_NOISE_WORDS]
    pooled_text = " ".join(a["title"] + ". " + a["description"] for a in articles)
    candidate_phrases = extract_keyphrases_locally(pooled_text, top_n=12)
    common_phrases = [p for p in candidate_phrases if p and " " in p and sum(1 for txt in article_texts_lower if p.lower() in txt) >= threshold]
    common_line = ""
    if common_phrases:
        from nlp.keywords import _format_common_line_from_phrases
        try: common_line = _format_common_line_from_phrases(common_phrases[:3])
        except: common_line = "Повеќето извори се согласуваат околу " + ", ".join(common_phrases[:3]) + " како теми во фокус."
    elif common_terms:
        common_line = "Повеќето извори се согласуваат околу " + ", ".join(common_terms[:4]) + " како теми во фокус."

    difference_points, seen_titles = [], set()
    unique_titles = []
    for s, t in title_pairs:
        if t.casefold() not in seen_titles:
            seen_titles.add(t.casefold())
            unique_titles.append((s, t))
    if len(unique_titles) >= 2:
        difference_points.append(f"{unique_titles[0][0]} најдиректно го формулира развојот како „{unique_titles[0][1]}“, додека {unique_titles[1][0]} повеќе нагласува „{unique_titles[1][1]}“.")

    open_points = []
    uncertain_sources = [a["source"] for a in articles if any(m in (a.get("title") or "").lower() or (a.get("description") or "").lower() for m in ["можеби", "се очекува", "наводно", "според неименувани", "непотврдено"])]
    if uncertain_sources:
        open_points.append(f"Деталите околу овој развој остануваат непотврдени кај {', '.join(uncertain_sources[:2])}.")
    
    # Extra check for numbers mismatch as open points
    from nlp.categories import detect_topic
    all_titles = " ".join([a.get("title") or "" for a in articles])
    is_sport = detect_topic(all_titles) == "Спорт"

    if is_sport:
        scores = [set(_extract_sports_scores(a.get("title") or "")) | set(_extract_sports_scores(a.get("description") or "")) for a in articles]
        all_scores = set().union(*scores)
        conflicting_scores = [s for s in all_scores if sum(1 for ms in scores if s in ms) < len(articles) and len(articles) > 1]
        if conflicting_scores:
            open_points.append(f"Информациите за конечниот резултат се разликуваат (на пример: {conflicting_scores[0]}), што може да укажува на промена во текот на мечот.")
    
    # Generic numbers only if not many articles (less noise)
    if len(articles) > 1 and len(articles) <= 3:
        nums = [set(_extract_number_tokens(a.get("description") or "")) for a in articles]
        all_nums = set().union(*nums)
        conflicting_nums = [n for n in all_nums if sum(1 for s in nums if n in s) == 1]
        if conflicting_nums and not any(n in "".join(open_points) for n in conflicting_nums):
            open_points.append(f"Постојат различни информации околу бројките (на пример: {conflicting_nums[0]}), што укажува на динамично известување.")

    result = {"common_line": common_line, "difference_points": difference_points[:3], "open_points": open_points[:2]}
    _cache_set(_comparison_cache, cache_key, result)
    return result

def synthesize_cluster_fallback(articles):
    articles = _normalize_articles_for_local_use(articles)
    if not articles: return {"summary": "", "perspectives": [], "synthetic_headline": "", "generated_article": ""}
    
    lead = articles[0]
    comparison = compare_cluster_sources(articles)
    
    # 1. Smarter Context Extraction
    desc = cleanAndDecode(lead.get("description", ""))
    sentences = [
        _normalize_briefing_line(s)
        for s in re.split(r'(?<=[.!?])\s+', desc)
        if len(s.strip()) > 20
    ]
    sentences = [s for s in sentences if s and not _is_noisy_summary_sentence(s)]
    
    # 2. Build Summary Points
    summary_lines = []
    lead_title = deShout(cleanAndDecode(lead.get("title", ""))).strip()
    if lead_title:
        summary_lines.append(f"• Што се случи: {lead_title}")
    
    if sentences:
        summary_lines.append(f"• Контекст: {sentences[0]}")
        
    common = comparison.get("common_line", "").replace("Повеќето извори се согласуваат околу ", "").replace(" како теми во фокус.", "").strip()
    if common and len(common) > 18 and "," not in common:
        summary_lines.append(f"• Потврда: {common}")
    
    sources_str = _source_list(articles, limit=4)
    summary_lines.append(f"• Извори: Развојот го следат {len(articles)} медиуми ({sources_str}).")
    if comparison.get("open_points"):
        summary_lines.append(f"• Што е следно: {comparison['open_points'][0]}")

    summary = "\n".join(summary_lines)

    # 3. Build a "Generated Article" from available snippets
    article_body = []
    if sentences:
        article_body.append(f"{lead_title}. {'. '.join(sentences[:2])}.")
    else:
        article_body.append(f"{lead_title}. Настанот е под лупа на медиумите.")
    
    if comparison.get("common_line"):
        article_body.append(comparison["common_line"])
    
    if comparison.get("difference_points"):
        article_body.append(comparison["difference_points"][0])

    generated_article = "\n\n".join(article_body)

    # 4. Perspectives
    perspectives = []
    if len(articles) > 1:
        perspectives.append({
            "angle": "Консензус", 
            "content": f"{articles[0]['source']} и {articles[1]['source']} ја потврдуваат истата основна линија на настанот."
        })
    
    if comparison["difference_points"]:
        perspectives.append({
            "angle": "Нијанси", 
            "content": comparison["difference_points"][0]
        })
        
    if comparison.get("open_points"):
        perspectives.append({
            "angle": "Отворено", 
            "content": comparison["open_points"][0]
        })

    record_runtime_event("local_synthesis_path", mode="enhanced_fallback")
    return {
        "summary": summary, 
        "perspectives": perspectives[:3],
        "synthetic_headline": lead_title,
        "generated_article": generated_article,
        "synthetic_standfirst": f"Уреднички преглед базиран на {len(articles)} извори."
    }

def generate_daily_brief_fallback(clusters):
    if not clusters: return "## Дневен Брифинг\n\nНема доволно достапни вести."
    display_clusters = sorted(
        clusters[:4],
        key=lambda item: (
            -int(bool(str(item.get("cluster_summary") or "").strip())),
            int(_is_penalized_briefing_title(item.get("title"))),
            -int(item.get("source_count") or 0),
        ),
    )
    display_clusters = _dedupe_briefing_clusters(display_clusters, limit=4)
    lines = ["## Што го движи денот", ""]
    # 1. Editorial Intro: explicitly state the lead story and second story
    if len(display_clusters) >= 1:
        lead_title = _condense_briefing_update(_extract_briefing_update(display_clusters[0]), max_chars=150)
        intro_line = f"Денешниот преглед го одбележа: {lead_title}."
        
        if len(display_clusters) >= 2:
            sec_title = _condense_briefing_update(_extract_briefing_update(display_clusters[1]), max_chars=150)
            intro_line = f"Денешниот ден го одбележа {lead_title}, додека внимание предизвика и {sec_title}."
            
        lines.append(intro_line)
        lines.append("")

    lines.append("## Каде се разликува известувањето")
    lines.append("")
    difference_added = False
    for cluster in display_clusters[:3]:
        diff = _normalize_briefing_line(cluster.get("difference_point"))
        if diff:
            short_t = _condense_briefing_update(cluster.get('title'), max_chars=80)
            lines.append(f"• {short_t}: {diff}")
            difference_added = True
    if not difference_added and display_clusters[:3]:
        fallback_cluster = display_clusters[0]
        short_t = _condense_briefing_update(fallback_cluster.get('title'), max_chars=80)
        lines.append(
            f"• {short_t}: "
            f"{_extract_briefing_importance(fallback_cluster)}."
        )
    lines.append("")

    lines.append("## Што да се следи понатаму")
    lines.append("")
    open_added = False
    for cluster in display_clusters[:3]:
        open_p = _normalize_briefing_line(cluster.get("open_point"))
        if open_p:
            short_t = _condense_briefing_update(cluster.get('title'), max_chars=80)
            lines.append(f"• {short_t}: {open_p}")
            open_added = True
    if not open_added and display_clusters[:3]:
        fallback_cluster = display_clusters[0]
        short_t = _condense_briefing_update(fallback_cluster.get('title'), max_chars=80)
        lines.append(
            f"• {short_t}: "
            f"Вреди да се следат следните потврди и официјални реакции околу развојот."
        )
    lines.append("")

    for index, cluster in enumerate(display_clusters, start=1):
        title, source = str(cluster.get("title") or "").strip(), str(cluster.get("source") or "Извор").strip()
        clean_title = _clean_briefing_snippet(title)
        summary = _condense_briefing_update(_extract_briefing_update(cluster))
        importance = _extract_briefing_importance(cluster)
        lines.append(f"### {index}. {clean_title or title}")
        lines.append(f"- Што се менува: {summary or clean_title or title}.")
        lines.append(f"- Зошто е важно: {importance}.")
        lines.append("")
    lines.append("**Белешка**: Содржината е генерирана преку локална системска анализа.")
    return "\n".join(lines).strip()

def _article_context_text(article):
    article = article or {}
    return " ".join(part.strip() for part in [str(article.get("title") or ""), str(article.get("description") or "")] if str(part or "").strip()).strip()

def _article_candidate_snippets(article):
    article = article or {}
    title, description = str(article.get("title") or "").strip(), str(article.get("description") or "").strip()
    snippets = [(title, "title")] if title else []
    raw_sentences = [_normalize_summary_sentence(s) for s in re.split(r'(?<=[.!?])\s+', description) if _normalize_summary_sentence(s)]
    for s in raw_sentences[:3]:
        if not _is_noisy_summary_sentence(s): snippets.append((s, "description"))
    return snippets[:4]

def _score_question_snippet(question_terms, question_entities, question_numbers, snippet, kind, article_rank):
    text = str(snippet or "").strip()
    if not text: return 0.0
    snippet_terms, snippet_numbers = set(_extract_terms(text)), set(_extract_number_tokens(text))
    snippet_entities = {e.casefold() for e in _extract_capitalized_phrases(text)}
    score = len(question_terms & snippet_terms) * 2.4 + sum(1 for e in question_entities if e in text.lower() or e in snippet_entities) * 2.1 + len(question_numbers & snippet_numbers) * 2.8
    score += 1.1 if kind == "title" else (0.7 if kind == "description" else 0.4)
    return score + max(0, 0.55 - (article_rank * 0.1))

def _rank_cluster_question_evidence(question, articles, synthesis=""):
    articles, question = _normalize_articles_for_local_use(articles), str(question or "").strip()
    if not question or not articles: return []
    cache_key = (question.casefold(), _articles_cache_key(articles), str(synthesis or "").strip())
    cached = _cache_get(_question_evidence_cache, cache_key)
    if cached is not None: return cached
    q_terms, q_entities, q_numbers = set(_extract_terms(question)), {e.casefold() for e in _extract_capitalized_phrases(question)}, set(_extract_number_tokens(question))
    ranked = []
    for rank, art in enumerate(articles):
        snippets = _article_candidate_snippets(art)
        context_text = _article_context_text(art)
        c_score = len(q_terms & set(_extract_terms(context_text))) * 0.9 + len(q_numbers & set(_extract_number_tokens(context_text))) * 1.2
        for snip, kind in snippets:
            score = _score_question_snippet(q_terms, q_entities, q_numbers, snip, kind, rank) + c_score
            ranked.append({"article": art, "snippet": snip, "kind": kind, "score": score})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    deduped, seen = [], set()
    for item in ranked:
        if item["snippet"].casefold() not in seen:
            seen.add(item["snippet"].casefold())
            deduped.append(item)
        if len(deduped) >= 4: break
    _cache_set(_question_evidence_cache, cache_key, deduped)
    return deduped

def _coerce_grounded_snippet(snippet):
    text = re.sub(r"\s+", " ", str(snippet or "").strip().strip("•")).strip()
    if text and not re.search(r"[.!?]$", text): text += "."
    return text

def _is_low_information_fragment(text):
    clean = str(text or "").strip().strip("•").strip()
    return len(clean) < 12 or not _extract_terms(clean)

def _is_low_quality_local_text(text, evidence=None):
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', str(text or "").strip()) if s.strip()]
    if not sentences: return True
    if len(set(re.sub(r"\s+", " ", s.casefold()) for s in sentences)) < len(sentences): return True
    return sum(1 for s in sentences if _is_low_information_fragment(s)) > len(sentences) / 2

def _build_grounded_answer_from_evidence(evidence, comparison=None):
    if not evidence: return ""
    p = evidence[0]
    p_snip = _coerce_grounded_snippet(p.get("snippet") or p["article"].get("title") or "")
    if _is_low_information_fragment(p_snip):
        p_snip = _coerce_grounded_snippet(summarize_locally(p["article"].get("description", ""), sentence_count=1))
    return f"Најдиректно од достапните извори: {p_snip}"

def _build_minimum_cluster_summary(articles, comparison=None):
    articles = _normalize_articles_for_local_use(articles)
    if not articles: return ""
    return f"• Што се случува: {articles[0]['title']}\n• Покриеност: {len(articles)} извори, вклучувајќи го и {_source_list(articles)}."

def generate_local_placeholder(cluster_id, title, category="Вести"):
    colors = {"Македонија": "#a63d40", "Балкан": "#3d6b63", "Европа": "#3f7d8a", "Америка": "#3e6282", "Свет": "#5f556f", "Спорт": "#b36b24", "Технологија": "#3e4954", "Економија": "#456a4f", "default": "#5f6470"}
    bg = colors.get(category, colors["default"])
    
    # Simple word-based wrapping for the SVG text
    words = title.split()
    lines = []
    current_line = []
    for w in words:
        current_line.append(w)
        if len(" ".join(current_line)) > 30:
            lines.append(" ".join(current_line))
            current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    
    # Limit to top 3 lines
    display_lines = lines[:3]
    text_y_start = 225 - (len(display_lines) - 1) * 25
    
    tspans = ""
    for i, line in enumerate(display_lines):
        y = text_y_start + i * 50
        tspans += f'<tspan x="400" y="{y}">{line}</tspan>'

    return (
        f'<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="100%" height="100%" fill="{bg}" />'
        f'<rect width="100%" height="100%" fill="black" opacity="0.1" />'
        f'<text font-family="serif" text-anchor="middle" font-size="40" font-weight="bold" fill="white">'
        f'{tspans}'
        f'</text>'
        f'<text x="40" y="410" font-family="sans-serif" font-size="20" font-weight="black" fill="white" opacity="0.5" letter-spacing="2">PRESEK</text>'
        f'</svg>'
    )
