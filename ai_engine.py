import json
import time
import datetime
import urllib.request
import urllib.error
import urllib.parse
import re
import logging
from abc import ABC, abstractmethod
from collections import defaultdict

from config import (
    GOOGLE_API_KEY, GEMINI_URL,
    GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL,
    CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL,
    POLLINATIONS_API_KEY,
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    TRANSLATION_SYSTEM_PROMPT
)

log = logging.getLogger("presek")

from utils import redis_client

# --- Provider Circuit Breaker (Global via Redis) ---
CIRCUIT_PREFIX = "ai:circuit:"
CIRCUIT_FAIL_THRESHOLD = 3
CIRCUIT_RETRY_AFTER = 300 # 5 minutes

def _is_circuit_open(name: str) -> bool:
    try:
        fails = int(redis_client.get(f"{CIRCUIT_PREFIX}{name}:fails") or 0)
        if fails >= CIRCUIT_FAIL_THRESHOLD:
            last_fail = float(redis_client.get(f"{CIRCUIT_PREFIX}{name}:last_fail") or 0)
            if time.time() - last_fail > CIRCUIT_RETRY_AFTER:
                # Reset for a retry attempt
                redis_client.set(f"{CIRCUIT_PREFIX}{name}:fails", 0)
                return False
            return True
    except Exception as e:
        log.error(f"Circuit breaker check failed for {name}: {e}")
    return False

def _record_fail(name: str):
    try:
        redis_client.incr(f"{CIRCUIT_PREFIX}{name}:fails")
        redis_client.set(f"{CIRCUIT_PREFIX}{name}:last_fail", time.time())
    except Exception as e:
        log.error(f"Failed to record circuit breaker fail for {name}: {e}")

def _record_success(name: str):
    try:
        redis_client.set(f"{CIRCUIT_PREFIX}{name}:fails", 0)
    except Exception as e:
        log.error(f"Failed to record circuit breaker success for {name}: {e}")

# --- Base Classes ---

class AIProvider(ABC):
    @abstractmethod
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        pass

class GeminiProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        if not GOOGLE_API_KEY or not GEMINI_URL: return None
        
        url = GEMINI_URL
        combined = f"{system}\n\nInput:\n{prompt}"
        payload = {
            "contents": [{"parts": [{"text": combined}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.1 # Lower temperature for more factual summaries
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"}
            ]
        }
        if json_mode: 
            payload["generationConfig"]["responseMimeType"] = "application/json"
        
        try:
            headers = {"Content-Type": "application/json", "x-goog-api-key": GOOGLE_API_KEY}

            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                # Robust response parsing
                if not data or "candidates" not in data or not data["candidates"]:
                    if "promptFeedback" in data:
                        log.warning(f"[gemini] Prompt blocked by safety: {data['promptFeedback']}")
                    else:
                        log.warning(f"[gemini] Empty or invalid response: {data}")
                    return None
                    
                candidate = data["candidates"][0]
                if "content" not in candidate or "parts" not in candidate["content"]:
                    finish_reason = candidate.get("finishReason", "UNKNOWN")
                    # If safety blocked, the parts list will be missing
                    if finish_reason == "SAFETY":
                        log.warning(f"[gemini] Candidate blocked by safety: {candidate.get('safetyRatings')}")
                    else:
                        log.warning(f"[gemini] No content in candidate. Finish reason: {finish_reason}")
                    return None
                    
                return candidate["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"[gemini] API Error: {e}")
            
            if hasattr(e, 'read'):
                try: log.warning(f"[gemini] Error detail: {e.read().decode()}")
                except: pass
            return None

class OpenAICompatibleProvider(AIProvider):
    def __init__(self, name, key, url, model):
        self.name = name
        self.key = key
        self.url = url
        self.model = model

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        if not self.key: return None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}", "User-Agent": "Presek/4.0"}

            req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"[{self.name}] Error: {e}")
            if hasattr(e, 'read'):
                try: log.warning(f"[{self.name}] Error detail: {e.read().decode()}")
                except: pass
            return None

from local_nlp import summarize_locally

# --- Provider Registry ---

class LocalProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        # The prompt for summarization tasks usually contains the text to summarize
        # or the titles. We'll strip the system instructions if they are prepended.
        text = prompt.replace("Summarize the following:", "").strip()
        return summarize_locally(text)

PROVIDERS = {
    "gemini":     GeminiProvider(),
    "groq":       OpenAICompatibleProvider("groq", GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL),
    "cerebras":   OpenAICompatibleProvider("cerebras", CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL),
    "mistral":    OpenAICompatibleProvider("mistral", MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL),
    "openrouter": OpenAICompatibleProvider("openrouter", OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL),
    "local":      LocalProvider(),
}

TASK_ROUTING = {
    "translation":  ["groq", "mistral", "gemini"],
    "summarize":    ["groq", "mistral", "cerebras", "gemini", "openrouter", "local"],
    "synthesis":    ["groq", "mistral", "cerebras", "gemini", "openrouter", "local"],
    "default":      ["groq", "cerebras", "gemini", "local"],
}

# --- Service Methods ---

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False) -> tuple[str | None, str | None]:
    from config import AI_DAILY_LIMIT
    from utils import redis_client
    try:
        count = redis_client.incr("ai:daily_calls")
        redis_client.expire("ai:daily_calls", 86400)
        if count > AI_DAILY_LIMIT:
            log.warning(f"[ai] Daily limit reached ({count}/{AI_DAILY_LIMIT})")
            return None, "limit_reached"
    except Exception as e:
        log.warning(f"[ai] Redis limit check failed: {e}")

    chain = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

    for name in chain:
        if _is_circuit_open(name): continue
        
        provider = PROVIDERS.get(name)
        if not provider: continue
        
        result = provider.call(prompt, system, max_tokens, json_mode)
        if result:
            _record_success(name)
            return result, name
        else:
            _record_fail(name)
            
    return None, None

def clean_json_response(text: str) -> dict | str:
    """Extracts summary and other fields from a JSON response with high robustness."""
    if not text: return ""
    
    # Try to find JSON block
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        json_text = match.group(1)
        try:
            data = json.loads(json_text)
            # If it's a dict, try to extract common fields
            if isinstance(data, dict):
                # Return the whole dict if it has structured data we want
                if any(k in data for k in ('summary', 'perspectives', 'entities', 'topic', 'category')):
                    return data
                # If it's a single-key dict like {"result": "text"}, return the value
                if len(data) == 1:
                    return str(list(data.values())[0]).strip()
            return data
        except json.JSONDecodeError:
            # Fallback: if regex match failed to parse, maybe it's just raw text with braces
            pass

    # Fallback: Clean markdown and return as string
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    return text

def translate_to_macedonian(text: str) -> str | None:
    """Translate news text to Macedonian using AI."""
    if not text or not text.strip():
        return text

    res, _ = _call_ai(text, TRANSLATION_SYSTEM_PROMPT, task_type="translation")
    if not res:
        return None
    # Unwrap JSON response if AI returned {"summary": "..."} style
    parsed = clean_json_response(res)
    if isinstance(parsed, dict):
        return parsed.get("summary") or parsed.get("translation") or parsed.get("text") or res
    return str(parsed)

def auto_summarize_top_clusters():
    """Dispatches background tasks for summarization/synthesis with parallel execution."""
    from tasks import summarize_article_task, synthesize_cluster_task
    from utils import redis_client, score_cluster, rank_articles_in_cluster
    from config import AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC
    from database import db_manager as db
    
    try:
        # Get recent articles from the last 24h
        rows = db.execute("SELECT * FROM articles WHERE created_at >= NOW() - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 500")
        
        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(r)

        ranked = []
        for cid, arts in clusters_map.items():
            sorted_arts = rank_articles_in_cluster(arts)
            s = score_cluster(sorted_arts)
            ranked.append((cid, sorted_arts, s))
        
        ranked.sort(key=lambda x: x[2], reverse=True)

        for cid, arts, score in ranked[:AUTO_SUMMARIZE_TOP_N]:
            lead = arts[0]
            # 1. Individual Summarization (Single Lead Article)
            if not lead.get("summary"):
                dedup_key = f"task:summarize:{lead['id']}"
                if redis_client.set(dedup_key, 1, nx=True, ex=600):
                    summarize_article_task.delay(lead["id"], lead["title"])

            # 2. Multi-Source Synthesis
            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                if not db.get_synthesis_ids([cid]):
                    dedup_key = f"task:synthesize:{cid}"
                    if redis_client.set(dedup_key, 1, nx=True, ex=600):
                        # Construct context with better structure
                        lines = []
                        for a in arts[:12]: # Slightly more sources for synthesis
                            desc = (a.get('description') or '').strip()
                            desc = re.sub(r'<[^>]+>', '', desc)[:250]
                            line = f"- [{a['source']}]: {a['title']}"
                            if desc: line += f"\n  {desc}"
                            lines.append(line)
                        
                        synthesize_cluster_task.delay(cid, "\n".join(lines))
                    
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")

def search_google_image(query: str) -> str | None:
    """Searches Google for an image and returns the first high-res result URL."""
    import requests
    import re
    
    # We use a broad search term to find relevant editorial images
    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
            
        # Look for image patterns in Google's obfuscated HTML
        pattern = r'\["(http[^"]+)",\d+,\d+\]'
        matches = re.findall(pattern, resp.text)
        
        for m in matches:
            # Skip google-hosted thumbs and encrypted links
            if "gstatic.com" in m or "encrypted-tbn" in m:
                continue
            # Decode unicode escapes if present
            m = m.replace("\\u003d", "=").replace("\\u0026", "&")
            if m.lower().split('?')[0].endswith(('.jpg', '.jpeg', '.png', '.webp')):
                return m
    except Exception as e:
        log.warning(f"[google-img] Search failed for '{query}': {e}")
        
    return None

def generate_cover_art(cluster_id: str, title: str) -> str | None:
    """First tries to find a real image via Google Search, falls back to a locally generated SVG."""
    import os
    import requests
    from local_nlp import generate_local_placeholder
    from database import db_manager as db
    
    os.makedirs("static/generated", exist_ok=True)
    save_path_jpg = f"static/generated/{cluster_id}.jpg"
    save_path_svg = f"static/generated/{cluster_id}.svg"
    
    # 1. Try Google Search first (Real photo/illustration)
    img_url = search_google_image(title)
    
    if img_url:
        try:
            log.info(f"[cover-art] Found Google image for '{title}': {img_url}")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.google.com/"
            }
            resp = requests.get(img_url, headers=headers, timeout=15, stream=True)
            if resp.status_code == 200:
                with open(save_path_jpg, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return f"/static/generated/{cluster_id}.jpg"
        except Exception as e:
            log.warning(f"[google-img] Download failed from {img_url}: {e}")

    # 2. Local Fallback (Styled SVG)
    log.info(f"[cover-art] Generating local styled SVG for '{title}'")
    try:
        # Get category for better branding
        cat_row = db.execute_one("SELECT category FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,))
        category = cat_row['category'] if cat_row else "Вести"
        
        svg_content = generate_local_placeholder(cluster_id, title, category)
        with open(save_path_svg, "w", encoding="utf-8") as f:
            f.write(svg_content)
        return f"/static/generated/{cluster_id}.svg"
    except Exception as e:
        log.error(f"[cover-art] Local SVG generation failed: {e}")
        return None

def cleanup_cover_art():
    """Removes generated cover art for clusters that are no longer in the DB."""
    import os
    from database import db_manager as db
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir): return

    try:
        rows = db.execute("SELECT DISTINCT cluster_id FROM articles")
        valid_ids = {r["cluster_id"] for r in rows}
        
        count = 0
        for filename in os.listdir(gen_dir):
            if filename.endswith((".jpg", ".svg")):
                cid = filename.split(".")[0]
                if cid not in valid_ids:
                    os.remove(os.path.join(gen_dir, filename))
                    count += 1
        if count:
            log.info(f"[cleanup] Removed {count} orphaned cover art images.")
    except Exception as e:
        log.error(f"[cleanup] Image cleanup failed: {e}")
