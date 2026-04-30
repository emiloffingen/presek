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
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS,
    POLLINATIONS_API_KEY, PROVIDER_FALLBACK_ORDER
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT
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

        if "synthesis" in lowered_system or "синтез" in lowered_system or task_type == "synthesis":
             res = analyst.analyze(prompt, system, max_tokens=max_tokens)
             if res: return res
             return synthesize_locally([], topic=topic)

        if "summarize" in lowered_system or task_type == "summarize":
             res = analyst.analyze(prompt, system, max_tokens=max_tokens)
             if res: return res

        if task_type == "research":
             res = analyst.research_query(prompt, system)
             if res:
                 return json.dumps(res) if isinstance(res, dict) else res

        res = analyst.analyze(prompt, system, max_tokens=max_tokens)
        if res:
            if json_mode:
                return json.dumps({"report": res, "status": "success", "mode": "local_fallback"})
        return res

        return summarize_locally(prompt, sentence_count=4, topic=topic).replace("Summarize:", "").strip()

class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, api_url: str, model: str):
        super().__init__("mistral", api_key, api_url, model)
class GeminiProvider(AIProvider):
    def __init__(self):
        self.client = None
        self.daily_limit = 2000000 # 2 million tokens safety budget (~$0.20)
        self.models = []
        for model in [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]:
            if model and model not in self.models:
                self.models.append(model)
        if GEMINI_API_KEY:
            try:
                from google import genai
                self.client = genai.Client(api_key=GEMINI_API_KEY)
            except Exception as e:
                log.error(f"[ai/gemini] SDK init failed: {e}")

    def _get_usage_key(self):
        return f"ai:gemini:usage:{datetime.date.today().isoformat()}"

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None, task_type: str = "default") -> str | None:
        if not self.client:
            return None
        
        # 1. Check Circuit Breaker
        try:
            usage = int(redis_client.get(self._get_usage_key()) or 0)
            if usage > self.daily_limit:
                log.warning(f"[ai/gemini] Budget exceeded ({usage} tokens). Circuit breaker active.")
                return None
        except Exception as e:
            log.error(f"[ai/gemini] Budget check error: {e}")

        # Modern SDK syntax for 2026
        config = {
            "system_instruction": system,
            "max_output_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            config["response_mime_type"] = "application/json"

        for model in self.models:
            cooldown_key = f"ai:gemini:model_cooldown:{model}"
            try:
                if redis_client.get(cooldown_key):
                    log.info(f"[ai/gemini] Skipping {model}; temporary cooldown active.")
                    continue
            except Exception:
                pass
            for attempt in range(2):
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config
                    )
                    text = response.text

                    # 2. Track Usage
                    try:
                        metadata = getattr(response, 'usage_metadata', None)
                        tokens_used = getattr(metadata, 'total_token_count', None) or (len(prompt) + len(text)) // 2
                        redis_client.incrby(self._get_usage_key(), int(tokens_used))
                        redis_client.expire(self._get_usage_key(), 172800) # 48h expiry
                    except Exception as usage_err:
                        log.debug(f"Usage tracking failed: {usage_err}")

                    if model != GEMINI_MODEL:
                        try:
                            record_runtime_event("ai_gemini_fallback", task_type=task_type, model=model)
                        except Exception as event_err:
                            log.debug(f"Gemini fallback telemetry failed: {event_err}")
                    return text
                except Exception as e:
                    message = str(e)
                    transient = any(code in message for code in ("429", "500", "502", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))
                    log.warning(f"[ai/gemini] Call failed for {model}: {e}")
                    if transient:
                        try:
                            redis_client.set(cooldown_key, 1, ex=300)
                        except Exception:
                            pass
                    if transient and attempt == 0:
                        time.sleep(1.5)
                        continue
                    break
        return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        # For simplicity, we use non-streaming for now as Gemini SDK 
        # is often used synchronously in these legacy wrappers
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

class NvidiaProvider(AIProvider):
    def __init__(self, api_key: str, api_url: str, model: str):
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
            "top_p": 0.7,
        }
        # Note: Some NVIDIA models might not support response_format="json_object"
        # but most modern Llama/Nemotron models on NIM do.
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
            log.warning(f"[ai/nvidia] Call failed: {e}")
        return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

PROVIDERS = {
    "gemini": GeminiProvider(),
    "nvidia": NvidiaProvider(
        api_key=os.environ.get("NVIDIA_API_KEY", ""),
        api_url=os.environ.get("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        model=os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")
    ),
    "mistral": MistralProvider(
        api_key=os.environ.get("MISTRAL_API_KEY", ""),
        api_url=os.environ.get("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions"),
        model=os.environ.get("MISTRAL_MODEL", "mistral-large-latest")
    ),
    "local": LocalProvider(),
}

# --- Service Methods ---

async def _stream_with_initial_chunk(generator: AsyncGenerator[str, None], first_chunk: str) -> AsyncGenerator[str, None]:
    yield first_chunk
    async for chunk in generator:
        yield chunk

async def _call_ai_async(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, stream: bool = False, topic: str = None):
    """Entrypoint with cascading failover."""
    for provider_name in PROVIDER_FALLBACK_ORDER:
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
    for provider_name in PROVIDER_FALLBACK_ORDER:
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
                log.warning(f"[ai/cascade] Provider {provider_name} returned empty response for task {task_type}")
        except Exception as e:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="error").inc()
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue

    log.error(f"[ai/cascade] All providers in {PROVIDER_FALLBACK_ORDER} failed for task {task_type}")
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

    # 1. Try to find and parse a JSON block (greedy match for the largest {} or [])
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        json_text = match.group(1)
        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                # If it's a valid structured response, return the dict
                valid_keys = ('summary', 'perspectives', 'entities', 'topic', 'category', 'article', 'synthetic_headline', 'facts')
                if any(k in data for k in valid_keys):
                    return data
                # Single-key bridge: if the model wrapped everything in a single key, extract it
                if len(data) == 1:
                    val = list(data.values())[0]
                    if isinstance(val, (str, list, dict)):
                        return val
        return data
        except Exception:
            pass

    # 2. Strip optional markdown fences
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
        # Try parsing again after stripping fences
        try:
        return json.loads(text)
        except:
            pass

    # 3. Last resort: If the text looks like raw JSON but failed parsing, 
    # we don't want to return it as a "summary". 
    if text.startswith('{') and '":' in text:
        log.warning(f"[ai/clean] Text looks like malformed JSON, returning empty: {text[:100]}...")
        return ""

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
            "SELECT * FROM articles "
            "WHERE COALESCE(ingested_at, created_at) >= NOW() - make_interval(days => 1) "
            "ORDER BY COALESCE(ingested_at, created_at) DESC LIMIT 1200"
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
            newest = max((a.get("ingested_at") or a.get("created_at")) for a in arts)
            ranked.append((cid, arts, len(unique_sources), newest))

        ranked.sort(key=lambda x: (x[3], x[2]), reverse=True)
        top = ranked[:AUTO_SUMMARIZE_TOP_N]
        if not top:
        return

        top_cids = [r[0] for r in top]
        existing_rows = db.execute(
            """
            SELECT cluster_id, created_at, generated_article, synthetic_standfirst,
                   verification_report
            FROM cluster_summaries
            WHERE cluster_id = ANY(%s)
            """,
            (top_cids,)
        ) or []
        existing_map = {r["cluster_id"]: r for r in existing_rows}

        STALE_THRESHOLD = datetime.timedelta(minutes=30)

        tasks_mod = sys.modules.get("tasks")
        if tasks_mod is None:
            import tasks as tasks_mod

        dispatched = 0
        skipped_locked = 0
        skipped_fresh = 0
        for cid, arts, _src_count, newest in top:
            existing = existing_map.get(cid)
            existing_at = existing.get("created_at") if existing else None
            standfirst = str((existing or {}).get("synthetic_standfirst") or "")
            generated_article = str((existing or {}).get("generated_article") or "")
            verification_report = (existing or {}).get("verification_report")
            local_fallback_synthesis = bool(
                existing
                and not generated_article.strip()
                and not verification_report
                and (
                    "Локален сублимат" in standfirst
                    or "Автоматски преглед" in standfirst
                    or "AI анализа" in standfirst
                )
            )
            if existing_at is not None and not local_fallback_synthesis and (newest - existing_at) <= STALE_THRESHOLD:
                skipped_fresh += 1
                continue

            try:
                if not redis_client.set(f"task:synthesize:{cid}", 1, nx=True, ex=600):
                    skipped_locked += 1
                    continue
            except Exception:
                pass

            lines = "\n".join(f"- [{a.get('source', 'Извор')}]: {a.get('title', '')}" for a in arts[:10])
            
            if existing_at is None:
                # Stage 1: Fast Draft (Immediate)
                tasks_mod.synthesize_cluster_task.apply_async(args=(cid, lines), kwargs={"fast_mode": True})
                # Stage 2: Deep Synthesis (Scheduled 2 mins later)
                tasks_mod.synthesize_cluster_task.apply_async(args=(cid, lines), kwargs={"fast_mode": False}, countdown=120)
            elif local_fallback_synthesis:
                tasks_mod.synthesize_cluster_task.apply_async(args=(cid, lines), kwargs={"fast_mode": False})
            else:
                # Just update existing stale synthesis
                tasks_mod.synthesize_cluster_task.delay(cid, lines)
            dispatched += 1
        log.info(
            "[auto-summarize] ranked=%s top=%s dispatched=%s skipped_fresh=%s skipped_locked=%s",
            len(ranked),
            len(top),
            dispatched,
            skipped_fresh,
            skipped_locked,
        )
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")


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
