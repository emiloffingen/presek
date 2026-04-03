import re
import math
from collections import Counter

# Reuse stopwords from your trending logic
from trending import STOPWORDS

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

def generate_local_placeholder(cluster_id, title, category="Вести"):
    """
    Generates a stylized SVG placeholder and returns the SVG string.
    Category-aware colors and patterns.
    """
    # Modern, news-inspired color palette
    colors = {
        "Македонија": "#E63946", # Red
        "Балкан":     "#457B9D", # Blue
        "Европа":     "#2A9D8F", # Teal
        "Америка":    "#264653", # Dark Slate
        "Свет":       "#8E44AD", # Purple
        "Спорт":      "#F4A261", # Orange
        "Технологија":"#2B2D42", # Navy
        "Економија":  "#1D3557", # Deep Blue
        "default":    "#6C757D"  # Grey
    }
    
    bg_color = colors.get(category, colors["default"])
    
    # Generate a subtle geometric pattern based on title length/hash
    pattern_seed = len(title) % 4
    patterns = [
        '<circle cx="0" cy="0" r="100" fill="white" fill-opacity="0.05" />',
        '<rect x="-100" y="-100" width="200" height="200" fill="white" fill-opacity="0.05" transform="rotate(45)" />',
        '<path d="M-200,0 L200,0 M0,-200 L0,200" stroke="white" stroke-opacity="0.05" stroke-width="40" />',
        '<circle cx="0" cy="0" r="150" fill="none" stroke="white" stroke-opacity="0.05" stroke-width="20" />'
    ]
    pattern_svg = patterns[pattern_seed]

    # Clean title for display (max 60 chars)
    display_title = title[:80] + "..." if len(title) > 80 else title
    
    svg = f"""<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="{bg_color}" />
  <g transform="translate(400, 225)">
    {pattern_svg}
  </g>
  <rect width="100%" height="100%" fill="black" fill-opacity="0.2" />
  
  <!-- Content -->
  <g transform="translate(60, 320)">
    <text x="0" y="0" font-family="system-ui, -apple-system, sans-serif" font-size="28" font-weight="800" fill="white" opacity="0.9">
        {category.upper()}
    </text>
    <rect y="15" width="40" height="4" fill="white" opacity="0.8" />
  </g>
  
  <!-- Logo/Brand -->
  <text x="740" y="50" text-anchor="end" font-family="serif" font-size="22" font-weight="bold" fill="white" opacity="0.3">ПРЕСЕК</text>
</svg>"""
    return svg
