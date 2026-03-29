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
    CATEGORIZATION_SYSTEM_PROMPT
)
from database import get_db

log = logging.getLogger("presek")

def clean_json_response(text: str) -> str:
    """
    Robustly extract the summary text from a Gemini/AI response.
    Handles raw text, Markdown-wrapped JSON, and JSON objects.
    """
    if not text:
        return ""
    
    # 1. Strip markdown code blocks if they exist
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    
    # 2. Try to find the bounds of a JSON object if it looks like one
    start_brace = text.find('{')
    end_brace = text.rfind('}')
    
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        json_part = text[start_brace:end_brace+1]
        try:
            data = json.loads(json_part)
            if isinstance(data, dict) and 'summary' in data:
                return data['summary'].strip()
        except:
            pass # Not valid JSON, fall back to cleaned text

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
    """Call AI provider (Cloudflare first, fallback to Gemini)."""
    # 1. Try Cloudflare Workers AI
    cf_result = _call_cloudflare_ai(prompt_text, system_prompt, timeout=timeout)
    if cf_result:
        return cf_result, "cloudflare"
    
    # 2. Fallback to Gemini
    gemini_result = _call_gemini(prompt_text, system_prompt, timeout=timeout, max_tokens=max_tokens, json_mode=json_mode)
    if gemini_result:
        return gemini_result, "gemini"
        
    return None, None

def translate_to_macedonian(text: str) -> str | None:
    """Translate news text to Macedonian using AI (Cloudflare preferred)."""
    if not text or not text.strip():
        return text
    
    res, _ = _call_ai(text, TRANSLATION_SYSTEM_PROMPT)
    if res:
        return clean_json_response(res)
    return None

def auto_summarize_top_clusters(rank_articles_fn, score_cluster_fn):
    """
    Automatically summarize the top clusters after each ingest cycle.
    """
    if not GOOGLE_API_KEY:
        return  # no Gemini key, skip silently

    try:
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
        summarized_count = 0
        synthesis_count = 0

        for cid, arts, score in top:
            lead = arts[0]

            # 1. Summarize the lead article (if not already done)
            if not lead.get("summary"):
                summary, tier = _call_ai(lead["title"], SUMMARY_SYSTEM_PROMPT)
                if summary:
                    summary = clean_json_response(summary)
                    try:
                        conn.execute("UPDATE articles SET summary = %s WHERE id = %s", (summary, lead["id"]))
                        conn.commit()
                        summarized_count += 1
                    except Exception as e:
                        log.warning(f"[auto-summarize] DB write failed for article {lead['id']}: {e}")
                    time.sleep(6)

            # 2. Generate cluster synthesis
            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                # Check DB cache first
                row = conn.execute("SELECT cluster_id FROM cluster_summaries WHERE cluster_id = %s", (cid,)).fetchone()
                if not row:
                    lines = []
                    for a in arts[:10]:
                        line = f"- [{a['source']}]: {a['title']}"
                        desc = (a.get('description') or '').strip()
                        if desc:
                            desc = re.sub(r'<[^>]+>', '', desc)[:250].strip()
                            if desc: line += f"\n  Опис: {desc}"
                        lines.append(line)
                    content = "\n".join(lines)
                    
                    synthesis, tier = _call_ai(f"Статии:\n{content}", SYNTHESIS_SYSTEM_PROMPT, json_mode=True)
                    if synthesis:
                        clean_synthesis = clean_json_response(synthesis)
                        now = datetime.datetime.now()
                        conn.execute(
                            "INSERT INTO cluster_summaries (cluster_id, summary, created_at) VALUES (%s, %s, %s) ON CONFLICT (cluster_id) DO UPDATE SET summary = EXCLUDED.summary, created_at = EXCLUDED.created_at",
                            (cid, clean_synthesis, now)
                        )
                        conn.commit()
                        synthesis_count += 1
                        time.sleep(6)

        if summarized_count or synthesis_count:
            log.info(f"[auto-summarize] {summarized_count} article summaries, {synthesis_count} cluster syntheses generated.")
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")
    finally:
        conn.close()
