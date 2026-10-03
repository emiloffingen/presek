"""Simplified summarizer using local Gemma 2B model.

This module provides basic summarization and cluster synthesis using
a single local Gemma model via llama-cpp-python.
"""

import json
import os
import re
from typing import Optional

from core.logging_config import get_logger

log = get_logger("presek.summarizer")

# Model configuration
MODEL_PATH = os.environ.get("LOCAL_MODEL_PATH", "models/gemma-2-2b-it-Q4_K_M.gguf")
MODEL_CONTEXT = int(os.environ.get("LOCAL_MODEL_CONTEXT", "2048"))
MODEL_THREADS = int(os.environ.get("MODEL_THREADS", "2"))
MAX_PROMPT_CHARS = int(os.environ.get("LOCAL_MODEL_MAX_PROMPT_CHARS", "4000"))

# Singleton model instance
_model = None


def _get_model():
    """Lazy-load the Gemma model singleton."""
    global _model
    if _model is not None:
        return _model

    try:
        from llama_cpp import Llama

        log.info(f"Loading Gemma model from {MODEL_PATH}")
        _model = Llama(
            model_path=MODEL_PATH,
            n_ctx=MODEL_CONTEXT,
            n_threads=MODEL_THREADS,
            use_mlock=True,
            verbose=False,
        )
        log.info("Gemma model loaded successfully")
        return _model
    except Exception as e:
        log.error(f"Failed to load Gemma model: {e}")
        raise


def _clean_text(text: str) -> str:
    """Clean and normalize generated text."""
    # Remove common artifacts
    text = re.sub(r"<[^>]+>", "", text)  # Remove HTML tags
    text = re.sub(r"\s+", " ", text)  # Normalize whitespace
    text = text.strip()
    return text


def _parse_json_response(response: str) -> Optional[dict]:
    """Try to parse JSON from model response."""
    try:
        # Try to find JSON in the response
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return None


def summarize_article(title: str, content: str) -> str:
    """Generate a brief summary of a single article.

    Args:
        title: Article title
        content: Article content (full text or description)

    Returns:
        Summary text (2-3 sentences)
    """
    model = _get_model()

    # Truncate content to fit context
    truncated_content = content[:MAX_PROMPT_CHARS] if content else ""

    prompt = f"""<start_of_turn>user
Ти си новинарски асистент. Напиши краток резиме (2-3 реченици) на македонски јазик за следнава вест.

Наслов: {title}

Содржина: {truncated_content}

Одговори само со резимето, без дополнителни објаснувања.<end_of_turn>
<start_of_turn>model\n"""

    try:
        response = model(
            prompt,
            max_tokens=200,
            temperature=0.3,
            stop=["<end_of_turn>"],
        )
        summary = response["choices"][0]["text"].strip()
        return _clean_text(summary)
    except Exception as e:
        log.error(f"Failed to generate summary: {e}")
        return ""


def synthesize_cluster(articles: list[dict]) -> dict:
    """Generate a synthesis for a cluster of related articles.

    Args:
        articles: List of dicts with 'title', 'description', 'source' keys

    Returns:
        Dict with 'headline', 'summary', 'key_facts' keys
    """
    model = _get_model()

    # Build article list for prompt
    articles_text = ""
    for i, article in enumerate(articles[:10], 1):  # Limit to 10 articles
        title = article.get("title", "")
        desc = article.get("description", "")[:500]  # Truncate descriptions
        source = article.get("source", "")
        articles_text += f"{i}. [{source}] {title}\n   {desc}\n\n"

    prompt = f"""<start_of_turn>user
Ти си новинарски уредник. На основу на следниве вести за истата тема, напиши синтеза на македонски јазик.

Вести:
{articles_text}

Одговори во JSON формат:
{{
  "headline": "Краток наслов на синтезата",
  "summary": "Резиме од 3-4 реченици што ги опфаќа клучните моменти",
  "key_facts": ["факт 1", "факт 2", "факт 3"]
}}<end_of_turn>
<start_of_turn>model\n"""

    try:
        response = model(
            prompt,
            max_tokens=500,
            temperature=0.3,
            stop=["<end_of_turn>"],
        )
        text = response["choices"][0]["text"].strip()

        # Try to parse as JSON
        parsed = _parse_json_response(text)
        if parsed:
            return {
                "headline": _clean_text(parsed.get("headline", "")),
                "summary": _clean_text(parsed.get("summary", "")),
                "key_facts": parsed.get("key_facts", []),
            }

        # Fallback: return raw text as summary
        return {
            "headline": "",
            "summary": _clean_text(text),
            "key_facts": [],
        }
    except Exception as e:
        log.error(f"Failed to generate cluster synthesis: {e}")
        return {
            "headline": "",
            "summary": "",
            "key_facts": [],
        }


def is_available() -> bool:
    """Check if the model is available and loaded."""
    try:
        _get_model()
        return True
    except Exception:
        return False
