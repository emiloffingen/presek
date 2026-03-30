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
    CLOUDFLARE_API_TOKEN, CF_AI_URL, CF_AI_GATEWAY_URL,
    AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC, AUTO_SUMMARIZE_DELAY,
    GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL,
    CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL,
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

    # Routing through AI Gateway if available
    final_url = f"{GEMINI_URL}?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    if CF_AI_GATEWAY_URL:
        # https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/google-ai-studio/v1beta/models/{model}:generateContent
        gateway_base = CF_AI_GATEWAY_URL.rstrip('/')
        final_url = f"{gateway_base}/google-ai-studio/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"
        headers["cf-aig-cache"] = "true"

    delays = [2, 4, 8]
    for attempt, delay in enumerate([0] + delays):
        if delay:
            time.sleep(delay)
        try:
            t0 = time.time()
            req = urllib.request.Request(final_url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_res = resp.read().decode("utf-8")
                data = json.loads(raw_res)
            elapsed = round(time.time() - t0, 2)

            if "candidates" not in data or not data["candidates"]:
                log.info(f"[gemini] Empty response in {elapsed}s (attempt {attempt+1})")
                return None

            log.info(f"[gemini] OK in {elapsed}s (attempt {attempt+1})")
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            elapsed = round(time.time() - t0, 2)
            err_body = e.read().decode("utf-8") if e else ""
            if e.code == 429:
                log.info(f"[gemini] 429 rate-limited in {elapsed}s (attempt {attempt+1}), retrying...")
                continue
            log.warning(f"[gemini] HTTP {e.code} in {elapsed}s: {err_body}")
            break
        except Exception as e:
            log.warning(f"[gemini] Error: {e}")
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

    final_url = CF_AI_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"
    }

    if CF_AI_GATEWAY_URL:
        # https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/workers-ai/
        gateway_base = CF_AI_GATEWAY_URL.rstrip('/')
        # Extract the model from the original URL
        model_part = CF_AI_URL.split("/ai/run/")[-1]
        final_url = f"{gateway_base}/workers-ai/{model_part}"
        headers["cf-aig-cache"] = "true"

    try:
        t0 = time.time()
        req = urllib.request.Request(final_url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body)
        elapsed = round(time.time() - t0, 2)

        if data.get("success"):
            log.info(f"[cloudflare] OK in {elapsed}s")
            return data["result"]["response"].strip()
        log.info(f"[cloudflare] Non-success response in {elapsed}s")
        return None
    except Exception as e:
        log.warning(f"[cloudflare] Call failed: {e}")
        return None

def _call_openai_compatible(prompt_text: str, system_prompt: str, api_key: str, api_url: str, model: str, provider_name: str, timeout: int = 30, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    """Generic caller for OpenAI-compatible APIs (Groq, Cerebras, Mistral, OpenRouter)."""
    if not api_key:
        return None

    payload_dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text}
        ],
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload_dict["response_format"] = {"type": "json_object"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Presek/1.0",
    }
    
    final_url = api_url
    if CF_AI_GATEWAY_URL:
        gateway_base = CF_AI_GATEWAY_URL.rstrip('/')
        # Handle different provider path structures in AI Gateway
        if provider_name == "groq":
            final_url = f"{gateway_base}/groq/openai/v1/chat/completions"
        elif provider_name == "mistral":
            final_url = f"{gateway_base}/mistral/v1/chat/completions"
        # OpenRouter doesn't have a direct gateway alias, 
        # but we can still use the gateway as a generic proxy or just use it directly
        
        headers["cf-aig-cache"] = "true"

    # OpenRouter requires extra headers
    if provider_name == "openrouter":
        headers["HTTP-Referer"] = "https://presek.mk"
        headers["X-Title"] = "Presek News"

    payload = json.dumps(payload_dict).encode("utf-8")

    try:
        t0 = time.time()
        req = urllib.request.Request(final_url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body)
        elapsed = round(time.time() - t0, 2)

        choices = data.get("choices", [])
        if choices and choices[0].get("message", {}).get("content"):
            log.info(f"[{provider_name}] OK in {elapsed}s")
            return choices[0]["message"]["content"].strip()
        log.info(f"[{provider_name}] Empty response in {elapsed}s")
        return None
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        log.warning(f"[{provider_name}] HTTP {e.code}: {err_body}")
        return None
    except Exception as e:
        log.warning(f"[{provider_name}] Error: {e}")
        return None


def _call_groq(prompt_text: str, system_prompt: str, timeout: int = 25, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    return _call_openai_compatible(prompt_text, system_prompt, GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL, "groq", timeout, max_tokens, json_mode)

def _call_cerebras(prompt_text: str, system_prompt: str, timeout: int = 25, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    return _call_openai_compatible(prompt_text, system_prompt, CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL, "cerebras", timeout, max_tokens, json_mode)

def _call_mistral(prompt_text: str, system_prompt: str, timeout: int = 25, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    return _call_openai_compatible(prompt_text, system_prompt, MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL, "mistral", timeout, max_tokens, json_mode)

def _call_openrouter(prompt_text: str, system_prompt: str, timeout: int = 30, max_tokens: int = 1000, json_mode: bool = False) -> str | None:
    return _call_openai_compatible(prompt_text, system_prompt, OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL, "openrouter", timeout, max_tokens, json_mode)


# ── Provider Registry & Routing ──────────────────────────────────

def _get_provider(name: str):
    """Resolve provider caller by name at call time (supports patching in tests)."""
    return {
        "gemini":     _call_gemini,
        "groq":       _call_groq,
        "cerebras":   _call_cerebras,
        "mistral":    _call_mistral,
        "openrouter": _call_openrouter,
        "cloudflare": _call_cloudflare_ai,
    }.get(name)

# Task-type → ordered provider chain
# Gemini reserved for Macedonian-critical tasks; cheaper models for background work
TASK_ROUTING = {
    # Premium: Macedonian language quality matters
    "translation":  ["gemini", "mistral", "groq"],
    "synthesis":    ["gemini", "mistral", "groq"],
    "daily_brief":  ["gemini", "mistral", "groq"],
    "summarize":    ["gemini", "groq", "cerebras"],

    # Mid-tier: quality matters but not MK-specific
    "analysis":     ["groq", "cerebras", "gemini"],
    "factcheck":    ["groq", "cerebras", "gemini"],
    "ai_ask":       ["groq", "cerebras", "gemini"],

    # Background: speed/cost matters most
    "tagging":      ["cerebras", "groq", "openrouter"],
    "topic":        ["cerebras", "groq", "openrouter"],
    "entity":       ["groq", "mistral", "openrouter"],
    "entity_info":  ["cerebras", "groq", "openrouter"],
    "categorize":   ["cerebras", "groq", "openrouter"],

    # Default fallback chain (same as original _call_ai)
    "default":      ["gemini", "groq", "cerebras", "mistral", "openrouter", "cloudflare"],
}


def _call_ai(prompt_text: str, system_prompt: str, timeout: int = 30, max_tokens: int = 2000, json_mode: bool = False, task_type: str = "default") -> tuple[str | None, str | None]:
    """Call AI provider with tiered routing and daily usage capping.

    task_type controls which provider chain is used:
    - 'translation', 'synthesis', 'daily_brief' → Gemini first (best MK quality)
    - 'tagging', 'topic', 'entity', 'categorize' → Cheap/fast models first
    - 'default' → Full fallback chain starting with Gemini
    """
    from config import AI_DAILY_LIMIT
    from utils import redis_client

    # 0. Check Daily Usage Limit (counts ALL providers)
    try:
        today = datetime.date.today().isoformat()
        usage_key = f"ai_usage_count:{today}"
        current_usage = redis_client.incr(usage_key)
        if current_usage == 1:
            redis_client.expire(usage_key, 86400)

        if current_usage > AI_DAILY_LIMIT:
            if current_usage == AI_DAILY_LIMIT + 1:
                log.warning(f"AI Daily Limit ({AI_DAILY_LIMIT}) reached. Capping usage for today.")
            return None, "limit_reached"
    except Exception as e:
        log.warning(f"[limit-check] Redis error: {e}")

    # 1. Get provider chain for this task type
    chain = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

    # 2. Try each provider in order
    for provider_name in chain:
        caller = _get_provider(provider_name)
        if not caller:
            continue
        try:
            if provider_name == "cloudflare":
                # Cloudflare has different signature (no max_tokens/json_mode)
                result = caller(prompt_text, system_prompt, timeout=timeout)
            else:
                result = caller(prompt_text, system_prompt, timeout=timeout, max_tokens=max_tokens, json_mode=json_mode)
            if result:
                return result, provider_name
        except Exception as e:
            log.warning(f"[{provider_name}] Unexpected error in chain: {e}")
            continue

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
    
    res, _ = _call_ai(text, TRANSLATION_SYSTEM_PROMPT, task_type="translation")
    if res:
        cleaned = clean_json_response(res)
        if isinstance(cleaned, dict):
            return cleaned.get('summary', str(cleaned))
        return str(cleaned)
    return None

def generate_cover_art(cluster_id: str, synthesis: str) -> str | None:
    """Generate news cover art using Pollinations.ai (free, no API key needed)."""
    import os
    os.makedirs("static/generated", exist_ok=True)

    lines = [l.strip('• ') for l in synthesis.split('\n') if '•' in l][:2]
    visual_context = ". ".join(lines) if lines else synthesis[:120]
    prompt = f"Cinematic editorial news photography, {visual_context}, professional press photo, high resolution, 16:9, neutral lighting, no text"

    payload = json.dumps({
        "prompt": prompt,
        "width": 800,
        "height": 450,
        "model": "flux",
        "nologo": True,
    }).encode("utf-8")
    save_path = f"static/generated/{cluster_id}.jpg"

    try:
        req = urllib.request.Request(
            "https://image.pollinations.ai/",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Presek/1.0",
            }
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            img_data = resp.read()
            if len(img_data) < 1000:
                log.warning(f"[ai-image] Suspiciously small image ({len(img_data)}B) for {cluster_id}")
                return None
            with open(save_path, "wb") as f:
                f.write(img_data)
        log.info(f"[ai-image] Generated cover for {cluster_id} ({len(img_data)}B)")
        return f"/static/generated/{cluster_id}.jpg"
    except Exception as e:
        log.warning(f"[ai-image] Failed to generate cover for {cluster_id}: {e}")
        return None

def auto_summarize_top_clusters(rank_articles_fn, score_cluster_fn):
    """Dispatches background tasks for summarization/synthesis with deduplication."""
    conn = None
    try:
        from tasks import summarize_article_task, synthesize_cluster_task
        from utils import redis_client
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
                # Dedup: skip if already queued in the last 10 minutes
                dedup_key = f"task:summarize:{lead['id']}"
                try:
                    if not redis_client.set(dedup_key, 1, nx=True, ex=600):
                        continue
                except Exception:
                    pass  # Redis down, proceed anyway
                summarize_article_task.delay(lead["id"], lead["title"])

            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                row = conn.execute("SELECT cluster_id FROM cluster_summaries WHERE cluster_id = %s", (cid,)).fetchone()
                if not row:
                    # Dedup: skip if synthesis already queued recently
                    dedup_key = f"task:synthesize:{cid}"
                    try:
                        if not redis_client.set(dedup_key, 1, nx=True, ex=600):
                            continue
                    except Exception:
                        pass
                    lines = []
                    for a in arts[:10]:
                        line = f"- [{a['source']}]: {a['title']}"
                        lines.append(line)
                    content = "\n".join(lines)
                    synthesize_cluster_task.delay(cid, content)
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")
    finally:
        if conn:
            conn.close()
