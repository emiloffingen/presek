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

def extract_tags_locally(text, limit=5):
    """Simple frequency-based tag extraction."""
    words = re.findall(r'[а-шА-Ш\w]+', text.lower(), re.UNICODE)
    # Filter: proper-ish nouns (more than 3 chars, not stopword)
    important_words = [w for w in words if w not in STOPWORDS and len(w) > 4]
    
    counts = Counter(important_words)
    return [w.capitalize() for w, c in counts.most_common(limit)]
