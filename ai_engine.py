import json
import time
import datetime
import httpx
import urllib.parse
import re
import logging
import asyncio
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import AsyncGenerator

from config import (
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL,
    CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL,
    OPENAI_API_KEY, OPENAI_API_URL, OPENAI_MODEL,
    POLLINATIONS_API_KEY, TASK_ROUTING
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    TRANSLATION_SYSTEM_PROMPT
)

from prometheus_client import Histogram, Counter

log = logging.getLogger("presek")

from utils import redis_client, record_runtime_event
from database import db_manager as db
import nlp
from nlp import summarize_locally, summarize_article_fallback, rewrite_to_macedonian_locally, synthesize_locally

# --- Prometheus Metrics ---
AI_LATENCY = Histogram(
    "presek_ai_latency_seconds",
    "Latency of AI provider calls",
    ["provider", "task_type"]
)
AI_CALLS = Counter(
    "presek_ai_calls_total",
    "Total number of AI provider calls",
    ["provider", "task_type", "status"]
)

# --- Base Classes ---

class AIProvider(ABC):
    @abstractmethod
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None, task_type: str = "default") -> str | None:
        pass

    @abstractmethod
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        pass

# --- Provider Registry ---

class MistralProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None, task_type: str = "default") -> str | None:
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

        # Use Mistral API directly
        url = MISTRAL_API_URL
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[ai/mistral] Call failed (URL: {url}): {e}")
            return None
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

class OpenAICompatibleProvider(AIProvider):
    def __init__(self, provider_name: str, api_key: str, api_url: str, model: str):
        self.provider_name = provider_name
        self.api_key = api_key
        self.api_url = api_url
        self.model = model

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None, task_type: str = "default") -> str | None:
        if not self.api_key or not self.api_url:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(self.api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[ai/{self.provider_name}] Call failed: {e}")
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

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None, task_type: str = "default") -> str | None:
        from local_analyst import analyst
        lowered_system = (system or "").lower()

        # 1. Use the new Gemma 2 2B singleton for high-quality local tasks
        if "translate" in lowered_system or "превед" in lowered_system or task_type == "translation":
            # Gemma is better at literary translation than the old regex engine
            res = analyst.analyze(prompt, system, max_tokens=max_tokens)
            if res: return res
            # Fallback to deterministic rewrite
            return rewrite_to_macedonian_locally(prompt)

        if "synthesis" in lowered_system or "синтез" in lowered_system or task_type == "synthesis":
             # We use the analyst for local synthesis if mistral is offline
             res = analyst.analyze(prompt, system, max_tokens=max_tokens)
             if res: return res
             # Fallback to multi-source synthesis
             return synthesize_locally([], topic=topic) # Fallback doesn't easily take raw prompt yet

        if "summarize" in lowered_system or task_type == "summarize":
             # Native Gemma summarization
             res = analyst.analyze(prompt, system, max_tokens=max_tokens)
             if res: return res

        if task_type == "research":
             # Native research answering
             res = analyst.research_query(prompt, system) # system here acts as context in our wrapper
             if res:
                 return json.dumps(res) if isinstance(res, dict) else res

        # Fallback to the old deterministic rules if Gemma is not suitable or fails
        return summarize_locally(prompt, sentence_count=4, topic=topic).replace("Summarize:", "").strip()
PROVIDERS = {
    "mistral": MistralProvider(),
    "local": LocalProvider(),
}

# --- Service Methods ---

async def _stream_with_initial_chunk(generator: AsyncGenerator[str, None], first_chunk: str) -> AsyncGenerator[str, None]:
    yield first_chunk
    async for chunk in generator:
        yield chunk

async def _call_ai_async(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, stream: bool = False, topic: str = None):
    """Entrypoint with cascading failover."""
    route = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])
    
    for provider_name in route:
        provider = PROVIDERS[provider_name]
        start_time = time.time()
        try:
            if stream:
                generator = provider.stream_call(prompt, system, max_tokens)
                try:
                    first_chunk = await anext(generator)
                except StopAsyncIteration:
                    AI_CALLS.labels(provider=provider_name, task_type=task_type, status="empty").inc()
                    continue
                if first_chunk:
                    AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(time.time() - start_time)
                    AI_CALLS.labels(provider=provider_name, task_type=task_type, status="success").inc()
                    return _stream_with_initial_chunk(generator, first_chunk), provider_name
                continue
            
            res = await asyncio.to_thread(provider.call, prompt, system, max_tokens, json_mode, topic=topic, task_type=task_type)
            if res:
                AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(time.time() - start_time)
                AI_CALLS.labels(provider=provider_name, task_type=task_type, status="success").inc()
                return res, provider_name
            else:
                AI_CALLS.labels(provider=provider_name, task_type=task_type, status="failure").inc()
        except Exception as e:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="error").inc()
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue
            
    return None, None

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Synchronous AI entrypoint with cascading failover."""
    route = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])
    
    for provider_name in route:
        provider = PROVIDERS[provider_name]
        start_time = time.time()
        try:
            res = provider.call(prompt, system, max_tokens, json_mode, topic=topic, task_type=task_type)
            if res:
                AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(time.time() - start_time)
                AI_CALLS.labels(provider=provider_name, task_type=task_type, status="success").inc()
                return res, provider_name
            else:
                AI_CALLS.labels(provider=provider_name, task_type=task_type, status="failure").inc()
        except Exception as e:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="error").inc()
            log.warning(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue
            
    return None, None

def sync_call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Backwards-compatible alias for synchronous callers."""
    return _call_ai(prompt, system, task_type, max_tokens, json_mode, topic=topic)

def clean_json_response(text: str) -> dict | str | None:
    if text is None:
        return ""
    if not isinstance(text, str):
        return ""

    text = text.strip()
    if not text:
        return ""

    # Look for JSON structure
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        json_text = match.group(1)
        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                # Valid keys check
                if any(k in data for k in ('summary', 'perspectives', 'entities', 'topic', 'category', 'article', 'synthetic_headline')):
                    return data
                # Single-key bridge
                if len(data) == 1:
                    return str(list(data.values())[0]).strip()
            return data
        except Exception:
            pass

    # Strip optional markdown fences while keeping plain-text fallbacks usable.
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

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
            
            if existing_at is None:
                # Stage 1: Fast Draft (Immediate)
                tasks_mod.synthesize_cluster_task.apply_async(args=(cid, lines), kwargs={"fast_mode": True})
                # Stage 2: Deep Synthesis (Scheduled 2 mins later)
                tasks_mod.synthesize_cluster_task.apply_async(args=(cid, lines), kwargs={"fast_mode": False}, countdown=120)
            else:
                # Just update existing stale synthesis
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
        record_runtime_event("translation_path", source_lang=lang, mode="already_mk")
        # If it's already Cyrillic, don't use the rewrite engine which might rephrase/damage it.
        # Just do basic whitespace normalization.
        cyrillic_chars = len(re.findall(r"[А-Яа-яЀ-ӿ]", text))
        latin_chars = len(re.findall(r"[A-Za-z]", text))
        if cyrillic_chars > latin_chars:
            return re.sub(r"\s+", " ", text).strip()
        return rewrite_to_macedonian_locally(text)

    def _is_usable_macedonian_translation(candidate: str | None) -> bool:
        candidate = str(candidate or "").strip()
        if not candidate:
            return False
        if candidate.casefold() == text.strip().casefold():
            return False

        candidate_cyrillic = len(re.findall(r"[А-Яа-яЀ-ӿ]", candidate))
        candidate_latin = len(re.findall(r"[A-Za-z]", candidate))
        if candidate_cyrillic >= max(6, candidate_latin):
            return True

        rewritten = rewrite_to_macedonian_locally(candidate)
        rewritten_cyrillic = len(re.findall(r"[А-Яа-яЀ-ӿ]", rewritten))
        if rewritten and rewritten.casefold() != text.strip().casefold() and rewritten_cyrillic >= max(6, candidate_cyrillic):
            return True
        return False

    def _normalize_translation_candidate(candidate: str | None) -> str | None:
        candidate = str(candidate or "").strip()
        if not candidate:
            return None
        if _is_usable_macedonian_translation(candidate):
            normalized = rewrite_to_macedonian_locally(candidate)
            normalized = str(normalized or "").strip()
            return normalized or candidate
        return None

    # 1. Try self-hosted NLLB (free, no API cost, but heavy on RAM)
    from config import LOCAL_TRANSLATION_ENABLED
    if LOCAL_TRANSLATION_ENABLED:
        try:
            from nllb_translate import translate as nllb_translate
            result = nllb_translate(text, lang)
            translated = _normalize_translation_candidate(result)
            if translated:
                record_runtime_event("translation_path", source_lang=lang, mode="nllb")
                log.info(f"[translate] {lang}→mk via nllb: {text[:60]}...")
                return translated
        except Exception as e:
            log.warning(f"[translate] NLLB failed for {lang} text: {e}")

    # 2. Fallback to AI API
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
                translated = _normalize_translation_candidate(parsed["summary"])
                if translated:
                    record_runtime_event("translation_path", source_lang=lang, mode="ai", provider=provider or "unknown")
                    log.info(f"[translate] {lang}→mk via {provider}: {text[:60]}...")
                    return translated
            elif isinstance(parsed, str):
                translated = _normalize_translation_candidate(parsed)
                if translated:
                    record_runtime_event("translation_path", source_lang=lang, mode="ai", provider=provider or "unknown")
                    log.info(f"[translate] {lang}→mk via {provider}: {text[:60]}...")
                    return translated
    except Exception as e:
        log.warning(f"[translate] AI translation failed for {lang} text: {e}")

    # 3. Last resort: local rewrite (best-effort)
    rewritten = rewrite_to_macedonian_locally(text)
    if rewritten and str(rewritten).strip() and str(rewritten).strip().casefold() != text.strip().casefold():
        record_runtime_event("translation_path", source_lang=lang, mode="local_rewrite")
        return rewritten

    record_runtime_event("translation_path", source_lang=lang, mode="original_return")
    return text

def generate_cover_art(cluster_id: str, prompt: str) -> str | None:
    """Generate a stylized AI cover image (Pollinations) or a fallback local placeholder."""
    # Validate cluster_id early to prevent path traversal and ensure safe_id is available
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(cluster_id))
    if not safe_id:
        log.warning("[ai] Invalid cluster_id for cover art: %s", cluster_id)
        return None
    
    category = "Вести"
    try:
        row = db.execute_one("SELECT category FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,))
        if row: category = row.get("category", "Вести")
    except: pass

    cooldown_key = "ai:cover_art:pollinations:cooldown"

    # 1. Try AI Generation (Pollinations)
    if POLLINATIONS_API_KEY:
        try:
            if redis_client.get(cooldown_key):
                raise RuntimeError("pollinations_cooldown_active")
        except RuntimeError:
            pass
        except Exception:
            pass

        clean_prompt = re.sub(r'[^\w\s]', '', prompt[:300])
        if len(clean_prompt) > 100:
            styled_prompt = f"Professional editorial news illustration, high-quality journalism style, minimalistic, cinematic lighting, conceptual art about: {clean_prompt[:250]}"
        else:
            styled_prompt = f"Professional news illustration, cinematic lighting, minimalistic, {clean_prompt}"
        
        encoded_prompt = urllib.parse.quote(styled_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true&seed={cluster_id}"
        
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                content = resp.content
                if len(content) > 5000:
                    os.makedirs("static/generated", exist_ok=True)
                    path = f"static/generated/{safe_id}.jpg"
                    with open(path, "wb") as f:
                        f.write(content)
                    return f"/static/generated/{safe_id}.jpg"
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429:
                try:
                    redis_client.setex(cooldown_key, 1800, "1")
                except Exception:
                    pass
                log.info("[ai] Pollinations rate-limited; enabling 30 minute cooldown")
            else:
                log.debug(f"[ai] AI cover art failed: {e}")
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.debug(f"[ai] AI cover art failed: {e}")
        except RuntimeError as e:
            if str(e) != "pollinations_cooldown_active":
                log.debug(f"[ai] AI cover art failed: {e}")

    # 2. Fallback to Local SVG Placeholder
    try:
        svg_content = nlp.generate_local_placeholder(cluster_id, prompt, category)
        if svg_content:
            os.makedirs("static/generated", exist_ok=True)
            path = f"static/generated/{safe_id}.svg"
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg_content)
            return f"/static/generated/{safe_id}.svg"
    except Exception as e:
        log.warning(f"[ai] Local placeholder failed: {e}")

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
