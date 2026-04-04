import re
import math
from collections import Counter

# Reuse stopwords from your trending logic
from trending import STOPWORDS

# Simple Macedonian Lexicon for Sentiment (Positive / Negative)
# This is a starter list that can be expanded.
SENTIMENT_LEXICON = {
    # Positive
    "добро": 1.0, "одлично": 2.0, "супер": 2.0, "успех": 1.5, "напредок": 1.5,
    "победа": 2.0, "развој": 1.0, "раст": 1.0, "стабилност": 1.0, "безбедност": 1.0,
    "хуманост": 1.5, "правда": 1.5, "слобода": 1.5, "демократија": 1.0, "поддршка": 1.0,
    "помош": 1.0, "решение": 1.5, "просперитет": 2.0, "мир": 2.0, "радост": 1.5,
    
    # Negative
    "лошо": -1.0, "катастрофа": -2.0, "криза": -1.5, "проблем": -1.0, "скандал корупција": -2.0,
    "напад": -1.5, "војна": -2.0, "смрт": -2.0, "убиство": -2.0, "затвор": -1.5,
    "кражба": -1.5, "криминал": -2.0, "криминалци": -2.0, "корупција": -2.0, "неуспех": -1.5,
    "патека": -0.5, "порано": -0.5, "порака": -0.5, "порази": -1.5, "поразот": -1.5,
    "загуба": -1.5, "критикува": -1.0, "осудува": -1.5, "неправда": -1.5, "хаос": -1.5,
    "смртност": -2.0, "болест": -1.5, "штета": -1.5, "закана": -1.5, "бомба": -2.0,
}

def analyze_sentiment_locally(text):
    """
    Returns a score between -2.0 and 2.0 based on keyword frequency.
    """
    if not text: return 0.0
    
    words = re.findall(r'[а-шА-Ш\w]{3,}', text.lower())
    score = 0
    matches = 0
    
    for w in words:
        if w in SENTIMENT_LEXICON:
            score += SENTIMENT_LEXICON[w]
            matches += 1
            
    if matches == 0: return 0.0
    
    # Normalize by matches but cap at 2.0
    final_score = score / matches
    return max(-2.0, min(2.0, final_score))

def extract_keyphrases_locally(text, top_n=5):
    """
    Extracts high-value phrases without AI using word frequency and co-occurrence.
    """
    if not text: return []
    
    # Simple word counting excluding stopwords
    words = re.findall(r'[а-шА-Ш\w]{4,}', text.lower())
    words = [w for w in words if w not in STOPWORDS]
    
    # Multi-word candidate search (Bigrams)
    raw_sentences = re.split(r'[.!?]\s*', text.lower())
    bigrams = []
    for sent in raw_sentences:
        sent_words = re.findall(r'[а-шА-Ш\w]{3,}', sent)
        sent_words = [w for w in sent_words if w not in STOPWORDS]
        for i in range(len(sent_words) - 1):
            bigrams.append(f"{sent_words[i]} {sent_words[i+1]}")
            
    word_counts = Counter(words)
    bigram_counts = Counter(bigrams)
    
    # Combine and score (bias towards bigrams)
    candidates = {}
    for word, count in word_counts.items():
        candidates[word] = count
    for bigram, count in bigram_counts.items():
        if count > 1: # Only if it appears twice
            candidates[bigram] = count * 2.5
            
    sorted_phrases = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return [p[0] for p in sorted_phrases[:top_n]]

def summarize_locally(text, sentence_count=3):
    """
    Non-AI Summarizer: Scores sentences based on word frequency.
    Works entirely locally and is very fast.
    """
    if not text or len(text) < 100:
        return text

    # 1. Clean and split into sentences
    # Handle common abbreviations and punctuation
    sentences = re.split(r'(?<=[.!?]) +', text)
    if len(sentences) <= sentence_count:
        return text

    # 2. Tokenize words and count frequency (excluding stopwords)
    words = re.findall(r'[а-шА-Ш\w]+', text.lower(), re.UNICODE)
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    
    word_freq = Counter(words)
    if not word_freq:
        return ". ".join(sentences[:sentence_count])

    # Normalize frequency
    max_freq = max(word_freq.values())
    for word in word_freq:
        word_freq[word] = word_freq[word] / max_freq

    # 3. Score sentences based on word frequency
    sentence_scores = {}
    for i, sentence in enumerate(sentences):
        sentence_words = re.findall(r'[а-шА-Ш\w]+', sentence.lower(), re.UNICODE)
        score = 0
        for word in sentence_words:
            if word in word_freq:
                score += word_freq[word]
        
        # Position bonus: sentences at the start are usually more important in news
        position_bonus = 1.0 / (i + 1)
        sentence_scores[i] = score + position_bonus

    # 4. Pick top N sentences and sort by original order
    top_indices = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:sentence_count]
    top_indices.sort()

    summary = [sentences[i].strip() for i in top_indices]
    return " ".join(summary)


def summarize_article_fallback(title, description=None):
    parts = [str(title or "").strip(), str(description or "").strip()]
    text = ". ".join([part for part in parts if part])
    summary = summarize_locally(text, sentence_count=2).strip()
    if summary:
        return summary[:420]
    return str(title or "").strip()


def _normalize_articles_for_local_use(articles):
    normalized = []
    for article in articles or []:
        normalized.append({
            "title": str(article.get("title") or "").strip(),
            "description": str(article.get("description") or "").strip(),
            "source": str(article.get("source") or "Извор").strip(),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "category": article.get("category"),
        })
    return [article for article in normalized if article["title"]]


def _extract_terms(text):
    return [
        term for term in re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
        if term not in STOPWORDS
    ]


def synthesize_cluster_fallback(articles):
    articles = _normalize_articles_for_local_use(articles)
    if not articles:
        return {"summary": "", "perspectives": []}

    lead = articles[0]
    descriptions = [article["description"] for article in articles if article["description"]]
    combined_text = " ".join([lead["title"], *descriptions[:4]])
    context_summary = summarize_locally(combined_text, sentence_count=3).strip()

    summary_lines = [
        f"• Главен развој: {lead['title']}",
        f"• Опфат на извори: темата е покриена од {len(articles)} извори, со водечки извештаи од {', '.join(article['source'] for article in articles[:3])}.",
    ]
    if context_summary:
        summary_lines.append(f"• Контекст: {context_summary}")
    if descriptions:
        summary_lines.append(f"• Што следи: {descriptions[0][:220].rstrip(' .,;:')}." )

    perspectives = []
    if len(articles) >= 2:
        focus = [f"{article['source']} го нагласува „{article['title']}“" for article in articles[:3]]
        perspectives.append({
            "angle": "Различни акценти",
            "content": "; ".join(focus) + ".",
        })

    all_terms = Counter()
    for article in articles:
        all_terms.update(_extract_terms(" ".join([article["title"], article["description"]])))
    common_terms = [term for term, _count in all_terms.most_common(4)]
    if common_terms:
        perspectives.append({
            "angle": "Заедничка линија",
            "content": "Повеќето извори се вртат околу: " + ", ".join(common_terms) + ".",
        })

    if descriptions:
        perspectives.append({
            "angle": "Што останува отворено",
            "content": "Достапните извори најмногу објаснуваат што се случило, но оставаат отворени детали за следните чекори и пошироките последици.",
        })

    return {
        "summary": "\n".join(summary_lines[:4]),
        "perspectives": perspectives[:3],
    }


def generate_daily_brief_fallback(clusters):
    if not clusters:
        return "## Дневен Брифинг\n\nНема доволно достапни вести за автоматски локален брифинг."

    lines = ["## Дневен Брифинг", "", "**Главни линии на денот**"]
    for index, cluster in enumerate(clusters[:5], start=1):
        title = str(cluster.get("title") or "").strip()
        source = str(cluster.get("source") or "Извор").strip()
        topic = str(cluster.get("topic") or cluster.get("category") or "Вести").strip()
        description = str(cluster.get("description") or "").strip()
        summary = summarize_locally(f"{title}. {description}", sentence_count=2).strip()
        lines.append(f"### {index}. {title}")
        lines.append(f"- Тема: {topic}")
        lines.append(f"- Водечки извор: {source}")
        if summary:
            lines.append(f"- Клучно: {summary}")
        lines.append("")

    lines.append("**Напомена**")
    lines.append("Овој брифинг е составен локално од највисоко рангираните кластери кога AI брифинг не е достапен.")
    return "\n".join(lines).strip()


def answer_cluster_question_locally(question, articles, synthesis="", perspectives=None):
    articles = _normalize_articles_for_local_use(articles)
    if not question or not articles:
        return None

    lowered = question.lower()
    lead = articles[0]
    citations = articles[:2]
    related_questions = [
        "Како се разликуваат изворите во известувањето?",
        "Што сè уште не е потврдено?",
        "Кој е следниот важен чекор во оваа приказна?",
    ]

    if any(token in lowered for token in ["разлику", "извори", "перспектив"]):
        emphasis = [f"{article['source']} го истакнува „{article['title']}“" for article in articles[:3]]
        return {
            "answer": "; ".join(emphasis) + ". Разликите најчесто се во аголот и формулацијата, а не во основниот настан.",
            "citations": citations,
            "related_questions": related_questions,
            "confidence": "medium",
        }

    if any(token in lowered for token in ["нејасно", "непотврдено", "отворено", "што не се знае"]):
        answer = "Во достапните извори нема целосна слика за сите детали. Најјасно е основното случување, додека последиците, реакциите и следните чекори сè уште се развиваат."
        if synthesis:
            answer = f"{answer} Тековниот преглед укажува дека: {summarize_locally(synthesis, sentence_count=1)}"
        return {
            "answer": answer,
            "citations": citations,
            "related_questions": related_questions,
            "confidence": "medium",
        }

    if any(token in lowered for token in ["најваж", "што е ново", "што се случ", "главно", "што има"]):
        answer = f"Најважното во овој момент е: {lead['title']}."
        if lead["description"]:
            answer += f" {summarize_locally(lead['description'], sentence_count=1)}"
        answer += f" Темата во моментов е покриена од {len(articles)} извори."
        return {
            "answer": answer,
            "citations": citations,
            "related_questions": related_questions,
            "confidence": "high",
        }

    terms = set(_extract_terms(question))
    if terms:
        scored = []
        for article in articles:
            haystack_terms = set(_extract_terms(" ".join([article["title"], article["description"]])))
            scored.append((len(terms & haystack_terms), article))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = [article for score, article in scored if score > 0][:2]
        if top:
            answer = f"Според достапните извори, најрелевантно за вашето прашање е: {top[0]['title']}."
            if top[0]["description"]:
                answer += f" {summarize_locally(top[0]['description'], sentence_count=1)}"
            return {
                "answer": answer,
                "citations": top,
                "related_questions": related_questions,
                "confidence": "medium",
            }

    return None

def generate_local_placeholder(cluster_id, title, category="Вести"):
    """
    Generates a stylized SVG placeholder and returns the SVG string.
    Category-aware colors and patterns.
    """
    # Editorial, category-aware palette
    colors = {
        "Македонија": "#b23a48",
        "Балкан":     "#52796f",
        "Европа":     "#4d908e",
        "Америка":    "#577590",
        "Свет":       "#6d597a",
        "Спорт":      "#c77d36",
        "Технологија":"#495057",
        "Економија":  "#588157",
        "default":    "#6c757d"
    }

    bg_color = colors.get(category, colors["default"])
    title = re.sub(r"\s+", " ", (title or "").strip())
    title = title[:140] + "..." if len(title) > 140 else title

    def escape(text):
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def wrap_lines(text, max_chars=24, max_lines=4):
        if not text:
            return ["Преглед на веста"]
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) == max_lines - 1:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)

        remaining_words = words[len(" ".join(lines).split()):]
        if remaining_words and lines:
            lines[-1] = lines[-1][: max(0, max_chars - 1)].rstrip(" .,") + "…"
        return lines[:max_lines]

    lines = wrap_lines(title)
    title_svg = []
    y = 168
    for line in lines:
        title_svg.append(
            f'<text x="56" y="{y}" font-family="Georgia, \'Times New Roman\', serif" '
            f'font-size="52" font-weight="700" letter-spacing="-1.2" fill="#172033">{escape(line)}</text>'
        )
        y += 58

    subtitle = f"{category.upper()} / ПРЕСЕК"
    pattern_seed = len(title) % 3
    pattern_svg = [
        '<circle cx="705" cy="82" r="118" fill="#fffdf7" fill-opacity="0.2" />',
        '<path d="M560 40 L790 40 L640 220 Z" fill="#fffdf7" fill-opacity="0.18" />',
        '<rect x="560" y="28" width="200" height="170" rx="24" fill="#fffdf7" fill-opacity="0.16" />',
    ][pattern_seed]

    svg = f"""<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#fcfbf7" />
      <stop offset="100%" stop-color="{bg_color}" />
    </linearGradient>
  </defs>

  <rect width="100%" height="100%" fill="url(#bg)" />
  <rect width="100%" height="100%" fill="#f8f5ef" fill-opacity="0.28" />
  <rect x="28" y="28" width="744" height="394" fill="none" stroke="#1f2937" stroke-opacity="0.12" />
  <rect x="40" y="40" width="720" height="370" fill="#fffdf9" fill-opacity="0.34" />
  <rect x="56" y="56" width="66" height="26" fill="#1f2937" fill-opacity="0.9" />
  <text x="89" y="74" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="800" fill="#fffdf7">{escape(category.upper())}</text>
  <text x="56" y="112" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="700" letter-spacing="2.2" fill="#334155" fill-opacity="0.78">{escape(subtitle)}</text>
  <line x1="56" y1="126" x2="164" y2="126" stroke="#334155" stroke-opacity="0.55" stroke-width="3" />

  {"".join(title_svg)}

  <g>
    {pattern_svg}
  </g>

  <text x="744" y="392" text-anchor="end" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="800" letter-spacing="2.5" fill="#1f2937" fill-opacity="0.42">GENERATED COVER</text>
</svg>"""
    return svg
