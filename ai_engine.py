import json
import time
import datetime
import urllib.request
import urllib.error
import re
import logging
from collections import defaultdict

from config import (
    GOOGLE_API_KEY, GEMINI_URL, 
    CLOUDFLARE_API_TOKEN, CF_AI_URL,
    AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC, AUTO_SUMMARIZE_DELAY
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    ANALYSIS_SYSTEM_PROMPT, TRANSLATION_SYSTEM_PROMPT, 
    CATEGORIZATION_SYSTEM_PROMPT, TAGGING_SYSTEM_PROMPT,
    GLOBAL_ASSISTANT_SYSTEM_PROMPT, TOPIC_SYSTEM_PROMPT,
    DAILY_BRIEF_SYSTEM_PROMPT, FACTCHECK_SYSTEM_PROMPT,
    ENTITY_EXTRACTION_PROMPT
)
from database import get_db

log = logging.getLogger("presek")

def clean_json_response(text: str) -> dict | str:
    """
    Extracts summary and other fields from a JSON response.
    Returns a dict if valid JSON with known keys, otherwise returns cleaned string.
    """
    if not text:
        return ""
    
    # Strip markdown code blocks
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    
    # Try JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Check for synthesis-specific fields
            if 'summary' in data or 'perspectives' in data:
                return data
            # Check for single-field 'summary' response (common in translations)
            if 'summary' in data and len(data) == 1:
                return data['summary'].strip()
    except:
        pass

    return text.strip()


def _call_gemini(prompt_text: str, system_prompt: str, timeout: int = 25, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    """Shared Gemini caller. Retries with exponential backoff on rate-limit (429)."""
    if not GOOGLE_API_KEY:
        return None
    prompt_text = prompt_text[:10000]
    
    gen_config = {"maxOutputTokens": max_tokens}
    if json_mode:
        gen_config["responseMimeType"] = "application/json"
        
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": gen_config
    }).encode("utf-8")
    
    # Financial Safety Rail: Mandatory 1s delay between any two global API calls
    time.sleep(1)
    
    delays = [2, 4, 8]  # seconds before each retry (3 attempts total)
    for attempt, delay in enumerate([0] + delays):
        if delay:
            time.sleep(delay)
        try:
            req = urllib.request.Request(
                f"{GEMINI_URL}?key={GOOGLE_API_KEY}",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning(f"[gemini] Rate limited (429), retry {attempt+1}/3 in {delays[attempt] if attempt < len(delays) else '—'}s")
                continue
            log.warning(f"[gemini] HTTP {e.code}: {e}")
            return None
        except Exception as e:
            import traceback as _tb
            log.warning(f"[gemini] Call failed: {e}\n" + _tb.format_exc())
            return None
    log.warning("[gemini] All retries exhausted after rate limiting.")
    return None

def _call_cloudflare_ai(prompt_text: str, system_prompt: str, timeout: int = 30) -> str | None:
    """Call Cloudflare Workers AI REST API."""
    if not CLOUDFLARE_API_TOKEN:
        return None
    
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Input: {prompt_text}"}
        ]
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            CF_AI_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body)
        
        if data.get("success"):
            return data["result"]["response"].strip()
        else:
            log.warning(f"[cloudflare] API error: {data.get('errors')}")
            log.debug(f"[cloudflare] Raw response: {raw_body}")
            return None
    except Exception as e:
        log.warning(f"[cloudflare] Call failed: {e}")
        return None

def _call_ai(prompt_text: str, system_prompt: str, timeout: int = 30, max_tokens: int = 2000, json_mode: bool = False) -> tuple[str | None, str | None]:
    """Call AI provider (Gemini first, fallback to Cloudflare)."""
    # 1. Try Gemini
    gemini_result = _call_gemini(prompt_text, system_prompt, timeout=timeout, max_tokens=max_tokens, json_mode=json_mode)
    if gemini_result:
        return gemini_result, "gemini"

    # 2. Fallback to Cloudflare Workers AI
    cf_result = _call_cloudflare_ai(prompt_text, system_prompt, timeout=timeout)
    if cf_result:
        return cf_result, "cloudflare"
        
    return None, None

def translate_to_macedonian(text: str) -> str | None:
    """Translate news text to Macedonian using AI (Cloudflare preferred)."""
    if not text or not text.strip():
        return text
    
    res, _ = _call_ai(text, TRANSLATION_SYSTEM_PROMPT)
    if res:
        return clean_json_response(res)
    return None

def generate_cover_art(cluster_id: str, synthesis: str) -> str | None:
    """Generate professional news cover art using Cloudflare Stable Diffusion."""
    from config import CF_IMAGE_MODEL_URL, CLOUDFLARE_API_TOKEN
    import os
    
    if not CLOUDFLARE_API_TOKEN:
        return None
        
    # 1. Simplify synthesis into a visual prompt
    # Take first 2 bullets and clean
    lines = [l.strip('• ') for l in synthesis.split('\n') if '•' in l][:2]
    visual_context = ". ".join(lines)
    
    # English prompt for better results with SDXL
    prompt = f"Cinematic editorial photography, {visual_context}, professional news graphics, high resolution, 16:9 aspect ratio, neutral lighting."
    
    payload = json.dumps({"prompt": prompt}).encode("utf-8")
    save_path = f"static/generated/{cluster_id}.jpg"
    
    try:
        req = urllib.request.Request(
            CF_IMAGE_MODEL_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            # Cloudflare returns binary image data
            with open(save_path, "wb") as f:
                f.write(resp.read())
        
        return f"/static/generated/{cluster_id}.jpg"
    except Exception as e:
        log.warning(f"[ai-image] Failed to generate cover for {cluster_id}: {e}")
        return None

def auto_summarize_top_clusters(rank_articles_fn, score_cluster_fn):
    """
    Finds top clusters and dispatches background tasks for summarization/synthesis.
    """
    if not GOOGLE_API_KEY:
        return  # no Gemini key, skip silently

    try:
        from tasks import summarize_article_task, synthesize_cluster_task
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(days=1)
        rows = conn.execute(
            "SELECT * FROM articles WHERE created_at >= %s ORDER BY created_at DESC LIMIT 500",
            (cutoff,)
        ).fetchall()
        
        # Build clusters and rank them
        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(dict(r))

        ranked = []
        for cid, arts in clusters_map.items():
            sorted_arts = rank_articles_fn(arts)
            s = score_cluster_fn(sorted_arts)
            ranked.append((cid, sorted_arts, s))
        ranked.sort(key=lambda x: x[2], reverse=True)

        top = ranked[:AUTO_SUMMARIZE_TOP_N]

        for cid, arts, score in top:
            lead = arts[0]

            # 1. Dispatch summary task for the lead article (if not already done)
            if not lead.get("summary"):
                summarize_article_task.delay(lead["id"], lead["title"])

            # 2. Dispatch cluster synthesis task
            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                # Check DB cache first
                row = conn.execute("SELECT cluster_id FROM cluster_summaries WHERE cluster_id = %s", (cid,)).fetchone()
                if not row:
                    # Prepare content for synthesis task
                    lines = []
                    for a in arts[:10]:
                        line = f"- [{a['source']}]: {a['title']}"
                        desc = (a.get('description') or '').strip()
                        if desc:
                            desc = re.sub(r'<[^>]+>', '', desc)[:250].strip()
                            if desc: line += f"\n  Опис: {desc}"
                        lines.append(line)
                    content = "\n".join(lines)
                    synthesize_cluster_task.delay(cid, content)

    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")
    finally:
        conn.close()
