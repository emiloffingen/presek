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
    
    # Extract JSON block if present
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        json_text = match.group(1)
        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                # Check for synthesis-specific fields
                if 'summary' in data or 'perspectives' in data or 'entities' in data:
                    return data
                # Check for single-field 'summary' response
                if 'summary' in data and len(data) == 1:
                    return data['summary'].strip()
            elif isinstance(data, list):
                return data
        except:
            pass

    # Fallback to cleaning markdown
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    return text.strip()


def _call_gemini(prompt_text: str, system_prompt: str, timeout: int = 25, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    """Shared Gemini caller. Uses contents-only approach for maximum compatibility."""
    if not GOOGLE_API_KEY:
        return None
    
    # Combined prompt for older API versions or restricted keys
    combined_prompt = f"{system_prompt}\n\nInput Text:\n{prompt_text}"
    
    payload_dict = {
        "contents": [{"parts": [{"text": combined_prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens}
    }
    
    if json_mode:
        payload_dict["generationConfig"]["responseMimeType"] = "application/json"
        
    payload = json.dumps(payload_dict).encode("utf-8")
    
    delays = [2, 4, 8]
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
                raw_res = resp.read().decode("utf-8")
                data = json.loads(raw_res)
            
            if "candidates" not in data or not data["candidates"]:
                return None
                
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e else ""
            if e.code == 429:
                continue
            log.warning(f"[gemini] HTTP {e.code}: {err_body}")
            break
        except Exception as e:
            log.warning(f"[gemini] Generic error: {e}")
            break
    return None

def _call_cloudflare_ai(prompt_text: str, system_prompt: str, timeout: int = 30) -> str | None:
    """Call Cloudflare Workers AI REST API."""
    if not CLOUDFLARE_API_TOKEN:
        return None
    
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Input: {prompt_text}"}
        ],
        "max_tokens": 1000
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
        return None
    except Exception as e:
        log.warning(f"[cloudflare] Call failed: {e}")
        return None

def _call_ai(prompt_text: str, system_prompt: str, timeout: int = 30, max_tokens: int = 2000, json_mode: bool = False) -> tuple[str | None, str | None]:
    """Call AI provider (Gemini first, fallback to Cloudflare) with daily usage capping."""
    from config import AI_DAILY_LIMIT
    from utils import redis_client
    
    # 0. Check Daily Usage Limit
    try:
        today = datetime.date.today().isoformat()
        usage_key = f"ai_usage_count:{today}"
        current_usage = redis_client.incr(usage_key)
        if current_usage == 1:
            redis_client.expire(usage_key, 86400) # Reset after 24h
            
        if current_usage > AI_DAILY_LIMIT:
            if current_usage == AI_DAILY_LIMIT + 1:
                log.warning(f"⚠️ AI Daily Limit ({AI_DAILY_LIMIT}) reached. Capping usage for today.")
            return None, "limit_reached"
    except Exception as e:
        log.warning(f"[limit-check] Redis error: {e}")

    # 1. Try Gemini first
    gemini_result = _call_gemini(prompt_text, system_prompt, timeout=timeout, max_tokens=max_tokens, json_mode=json_mode)
    if gemini_result:
        return gemini_result, "gemini"

    # 2. Fallback to Cloudflare Workers AI
    cf_result = _call_cloudflare_ai(prompt_text, system_prompt, timeout=timeout)
    if cf_result:
        return cf_result, "cloudflare"
        
    return None, None

def cleanup_cover_art():
    """Removes generated cover art for clusters that are no longer in the DB."""
    import os
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir):
        return

    conn = None
    try:
        conn = get_db()
        rows = conn.execute("SELECT DISTINCT cluster_id FROM articles").fetchall()
        valid_ids = {r["cluster_id"] for r in rows}
        rows = conn.execute("SELECT cluster_id FROM cluster_summaries").fetchall()
        valid_ids.update({r["cluster_id"] for r in rows})
    except Exception as e:
        log.error(f"[cleanup] DB query failed: {e}")
        return
    finally:
        if conn:
            conn.close()

    try:
        count = 0
        for filename in os.listdir(gen_dir):
            if filename.endswith(".jpg"):
                cid = filename.replace(".jpg", "")
                if cid not in valid_ids:
                    os.remove(os.path.join(gen_dir, filename))
                    count += 1
        if count:
            log.info(f"[cleanup] Removed {count} orphaned cover art images.")
    except Exception as e:
        log.error(f"[cleanup] Image cleanup failed: {e}")

def translate_to_macedonian(text: str) -> str | None:
    """Translate news text to Macedonian using AI."""
    if not text or not text.strip():
        return text
    
    res, _ = _call_ai(text, TRANSLATION_SYSTEM_PROMPT)
    if res:
        cleaned = clean_json_response(res)
        if isinstance(cleaned, dict):
            return cleaned.get('summary', str(cleaned))
        return str(cleaned)
    return None

def generate_cover_art(cluster_id: str, synthesis: str) -> str | None:
    """Generate professional news cover art using Cloudflare Stable Diffusion."""
    from config import CF_IMAGE_MODEL_URL, CLOUDFLARE_API_TOKEN
    if not CLOUDFLARE_API_TOKEN:
        return None
        
    lines = [l.strip('• ') for l in synthesis.split('\n') if '•' in l][:2]
    visual_context = ". ".join(lines)
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
            with open(save_path, "wb") as f:
                f.write(resp.read())
        return f"/static/generated/{cluster_id}.jpg"
    except Exception as e:
        log.warning(f"[ai-image] Failed to generate cover for {cluster_id}: {e}")
        return None

def auto_summarize_top_clusters(rank_articles_fn, score_cluster_fn):
    """Dispatches background tasks for summarization/synthesis."""
    try:
        from tasks import summarize_article_task, synthesize_cluster_task
        conn = get_db()
        cutoff = datetime.datetime.now() - datetime.timedelta(days=1)
        rows = conn.execute(
            "SELECT * FROM articles WHERE created_at >= %s ORDER BY created_at DESC LIMIT 500",
            (cutoff,)
        ).fetchall()
        
        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(dict(r))

        ranked = []
        for cid, arts in clusters_map.items():
            sorted_arts = rank_articles_fn(arts)
            s = score_cluster_fn(sorted_arts)
            ranked.append((cid, sorted_arts, s))
        ranked.sort(key=lambda x: x[2], reverse=True)

        for cid, arts, score in ranked[:AUTO_SUMMARIZE_TOP_N]:
            lead = arts[0]
            if not lead.get("summary"):
                summarize_article_task.delay(lead["id"], lead["title"])

            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                row = conn.execute("SELECT cluster_id FROM cluster_summaries WHERE cluster_id = %s", (cid,)).fetchone()
                if not row:
                    lines = []
                    for a in arts[:10]:
                        line = f"- [{a['source']}]: {a['title']}"
                        lines.append(line)
                    content = "\n".join(lines)
                    synthesize_cluster_task.delay(cid, content)
        conn.close()
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")
