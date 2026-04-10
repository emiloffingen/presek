import json
import time
import datetime
import urllib.request
import urllib.error
import urllib.parse
import re
import logging
import asyncio
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import AsyncGenerator

from config import (
    GOOGLE_API_KEY, GEMINI_URL,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    OPENCLAW_URL, OPENCLAW_TOKEN,
    CF_AI_URL, CF_AI_TOKEN,
    POLLINATIONS_API_KEY,
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    TRANSLATION_SYSTEM_PROMPT
)

log = logging.getLogger("presek")

from utils import redis_client
from database import db_manager as db
import local_nlp
from local_nlp import summarize_locally, summarize_article_fallback, rewrite_to_macedonian_locally, synthesize_locally

# --- Base Classes ---

class AIProvider(ABC):
    @abstractmethod
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        pass

    @abstractmethod
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        pass

# --- Provider Registry ---

class GeminiProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        if not GOOGLE_API_KEY: return None
        url = f"{GEMINI_URL}?key={GOOGLE_API_KEY}"
        
        # Newest valid structure for Gemini 2.0
        payload = {
            "system_instruction": {
                "parts": {"text": system}
            },
            "contents": [
                {
                    "parts": {"text": prompt}
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens, 
                "temperature": 0.1
            }
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            data_encoded = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_encoded, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            log.warning(f"[ai/gemini] Call failed: {e}")
            return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

class MistralProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        if not MISTRAL_API_KEY: return None
        payload = {
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MISTRAL_API_KEY}"
        }
        try:
            data_encoded = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(MISTRAL_API_URL, data=data_encoded, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning(f"[ai/mistral] Call failed: {e}")
            return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

class CloudflareAIProvider(AIProvider):
    """Cloudflare Workers AI Provider (Tier 3 fallback)."""
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        if not CF_AI_TOKEN: return None
        
        # Hardcoded account ID from your gateway URL
        account_id = "f368eacc80be4ddcfa1d6ff49717275b"
        model = "@cf/meta/llama-3-8b-instruct"
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"

        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CF_AI_TOKEN}"
        }
        try:
            data_encoded = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_encoded, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "result" in data and "response" in data["result"]:
                    return data["result"]["response"]
                return None
        except Exception as e:
            log.warning(f"[ai/cloudflare] Direct AI call failed: {e}")
            return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

class OpenClawProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        if not OPENCLAW_URL: return None
        
        base_url = OPENCLAW_URL
        if not base_url.endswith("/v1/chat/completions") and "/v1/" not in base_url:
            base_url = base_url.rstrip("/") + "/v1/chat/completions"

        payload = {
            "model": "llama3", 
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": False
        }
        headers = {"Content-Type": "application/json"}
        if OPENCLAW_TOKEN:
            headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"
            
        try:
            data_encoded = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(base_url, data=data_encoded, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning(f"[ai/openclaw] Local LLM failed: {e}")
            return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

class LocalProvider(AIProvider):
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res:
            for word in res.split(' '):
                yield word + ' '
                await asyncio.sleep(0.01)

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        lowered_system = (system or "").lower()
        if "translate" in lowered_system or "превед" in lowered_system:
            return rewrite_to_macedonian_locally(prompt)
        
        if "synthesis" in lowered_system or "синтез" in lowered_system:
            try:
                lines = prompt.split("\n")
                fake_articles = []
                for line in lines:
                    if "]:" in line:
                        parts = line.split("]:", 1)
                        fake_articles.append({
                            "title": parts[1].strip(), 
                            "description": "", 
                            "source": parts[0].replace("- [", "").strip()
                        })
                
                if fake_articles:
                    summary = synthesize_locally(fake_articles, sentence_count=4, topic=topic)
                    return summary
            except:
                pass
            
            summary = summarize_locally(prompt, sentence_count=4, topic=topic)
            return summary
            
        text = re.sub(r"^\s*summarize(?: the following)?\s*:\s*", "", prompt, flags=re.IGNORECASE).strip()
        return summarize_article_fallback("", text, topic=topic)

PROVIDERS = {
    "gemini": GeminiProvider(),
    "mistral": MistralProvider(),
    "cloudflare": CloudflareAIProvider(),
    "openclaw": OpenClawProvider(),
    "local": LocalProvider(),
}

TASK_ROUTING = {
    "translation":  ["gemini", "mistral", "cloudflare", "openclaw", "local"],
    "summarize":    ["gemini", "mistral", "cloudflare", "openclaw", "local"],
    "synthesis":    ["gemini", "mistral", "cloudflare", "openclaw", "local"],
    "daily_brief":  ["gemini", "mistral", "cloudflare", "openclaw", "local"],
    "chat":         ["gemini", "mistral", "cloudflare", "local"],
    "default":      ["gemini", "mistral", "cloudflare", "openclaw", "local"],
}

# --- Service Methods ---

async def _call_ai_async(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, stream: bool = False, topic: str = None):
    """Entrypoint with cascading failover."""
    route = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])
    
    for provider_name in route:
        provider = PROVIDERS[provider_name]
        try:
            if stream:
                return provider.stream_call(prompt, system, max_tokens), provider_name
            
            res = provider.call(prompt, system, max_tokens, json_mode, topic=topic)
            if res:
                return res, provider_name
        except Exception as e:
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue
            
    return None, "none"

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Synchronous AI entrypoint with cascading failover."""
    route = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])
    
    for provider_name in route:
        provider = PROVIDERS[provider_name]
        try:
            res = provider.call(prompt, system, max_tokens, json_mode, topic=topic)
            if res:
                return res, provider_name
        except Exception as e:
            log.warning(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue
            
    return None, "none"

def sync_call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Backwards-compatible alias for synchronous callers."""
    return _call_ai(prompt, system, task_type, max_tokens, json_mode, topic=topic)

def clean_json_response(text: str) -> dict | str:
    if not text: return ""
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        json_text = match.group(1)
        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                if any(k in data for k in ('summary', 'perspectives', 'entities', 'topic', 'category', 'article')):
                    return data
                if len(data) == 1:
                    return str(list(data.values())[0]).strip()
            return data
        except: pass
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    return text

def auto_summarize_top_clusters():
    """Dispatch synthesis tasks for the top recent clusters."""
    import sys
    from collections import defaultdict
    try:
        from config import AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC
        from database import db_manager as db
        from utils import redis_client

        rows = db.execute(
            "SELECT * FROM articles WHERE created_at >= NOW() - INTERVAL '1 day' "
            "ORDER BY created_at DESC LIMIT 500"
        )
        if not rows:
            return

        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(r)

        ranked = []
        for cid, arts in clusters_map.items():
            unique_sources = {a.get("source") for a in arts if a.get("source")}
            if len(unique_sources) < AUTO_SUMMARIZE_MIN_SRC:
                continue
            newest = max(a["created_at"] for a in arts)
            ranked.append((cid, arts, len(unique_sources), newest))

        ranked.sort(key=lambda x: (x[2], x[3]), reverse=True)
        top = ranked[:AUTO_SUMMARIZE_TOP_N]
        if not top:
            return

        top_cids = [r[0] for r in top]
        existing_rows = db.execute(
            "SELECT cluster_id, created_at FROM cluster_summaries WHERE cluster_id = ANY(%s)",
            (top_cids,)
        ) or []
        existing_map = {r["cluster_id"]: r["created_at"] for r in existing_rows}

        STALE_THRESHOLD = datetime.timedelta(minutes=30)

        tasks_mod = sys.modules.get("tasks")
        if tasks_mod is None:
            import tasks as tasks_mod

        for cid, arts, _src_count, newest in top:
            existing_at = existing_map.get(cid)
            if existing_at is not None and (newest - existing_at) <= STALE_THRESHOLD:
                continue

            try:
                if not redis_client.set(f"task:synthesize:{cid}", 1, nx=True, ex=600):
                    continue
            except Exception:
                pass

            lines = "\n".join(f"- [{a.get('source', 'Извор')}]: {a.get('title', '')}" for a in arts[:10])
            tasks_mod.synthesize_cluster_task.delay(cid, lines)
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")


def translate_to_macedonian(text: str) -> str | None:
    """Translate text to Macedonian.

    Priority: NLLB (free, self-hosted) → AI API fallback → local rewrite.
    """
    if not text or not text.strip():
        return text

    from language import detect_language
    lang = detect_language(text)

    # Already Macedonian — just normalize locally
    if lang == "mk":
        return rewrite_to_macedonian_locally(text)

    # 1. Try self-hosted NLLB (free, no API cost)
    try:
        from nllb_translate import translate as nllb_translate
        result = nllb_translate(text, lang)
        if result and result.strip():
            log.info(f"[translate] {lang}→mk via nllb: {text[:60]}...")
            return result
    except Exception as e:
        log.warning(f"[translate] NLLB failed for {lang} text: {e}")

    # 2. Fallback to AI API (Gemini/Mistral/etc.)
    try:
        result, provider = _call_ai(
            prompt=text,
            system=TRANSLATION_SYSTEM_PROMPT,
            task_type="translation",
            max_tokens=500,
            json_mode=True,
        )
        if result:
            parsed = clean_json_response(result)
            if isinstance(parsed, dict) and "summary" in parsed:
                translated = parsed["summary"].strip()
                if translated:
                    log.info(f"[translate] {lang}→mk via {provider}: {text[:60]}...")
                    return translated
            elif isinstance(parsed, str) and parsed.strip():
                log.info(f"[translate] {lang}→mk via {provider}: {text[:60]}...")
                return parsed.strip()
    except Exception as e:
        log.warning(f"[translate] AI translation failed for {lang} text: {e}")

    # 3. Last resort: local rewrite (best-effort)
    return rewrite_to_macedonian_locally(text)

def generate_cover_art(cluster_id: str, prompt: str) -> str | None:
    """Generate a stylized placeholder (Local) or AI cover image (Pollinations)."""
    category = "Вести"
    try:
        row = db.execute_one("SELECT category FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,))
        if row: category = row.get("category", "Вести")
    except: pass

    try:
        svg_content = local_nlp.generate_local_placeholder(cluster_id, prompt, category)
        if svg_content:
            os.makedirs("static/generated", exist_ok=True)
            path = f"static/generated/{cluster_id}.svg"
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            return f"/static/generated/{cluster_id}.svg"
    except Exception as e:
        log.warning(f"[ai] Local placeholder failed: {e}")

    if not POLLINATIONS_API_KEY: return None
    
    clean_prompt = re.sub(r'[^\w\s]', '', prompt[:300])
    if len(clean_prompt) > 100:
        styled_prompt = f"Professional editorial news illustration, high-quality journalism style, minimalistic, cinematic lighting, conceptual art about: {clean_prompt[:250]}"
    else:
        styled_prompt = f"Professional news illustration, cinematic lighting, minimalistic, {clean_prompt}"
    
    encoded_prompt = urllib.parse.quote(styled_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true&seed={cluster_id}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            if len(content) > 5000:
                path = f"static/generated/{cluster_id}.jpg"
                with open(path, "wb") as f:
                    f.write(content)
                return f"/static/generated/{cluster_id}.jpg"
    except Exception as e:
        log.debug(f"[ai] AI cover art failed: {e}")
    return None

def cleanup_cover_art(valid_ids: set[str]):
    """Remove generated images for clusters that no longer exist."""
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir): return
    try:
        for filename in os.listdir(gen_dir):
            if filename.endswith((".jpg", ".svg")):
                cid = filename.split(".")[0]
                if cid not in valid_ids: os.remove(os.path.join(gen_dir, filename))
    except: pass
