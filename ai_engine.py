import json
import time
import datetime
import httpx
import re
import logging
import asyncio
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import AsyncGenerator

from config import (
    PROVIDER_FALLBACK_ORDER, PROVIDER_FALLBACK_ORDER_RESEARCH, PROVIDER_FALLBACK_ORDER_SUMMARY,
    GEMINI_API_KEY, GEMINI_MODEL
)


from prometheus_client import Histogram, Counter, REGISTRY

log = logging.getLogger("presek")


from nlp import summarize_locally, synthesize_locally

# --- Prometheus Metrics ---
def _metric_or_existing(factory, name: str, *args, **kwargs):
    try:
        return factory(name, *args, **kwargs)
    except ValueError:
        for registered_name in (name, name.removesuffix("_total")):
            if registered_name in REGISTRY._names_to_collectors:
                return REGISTRY._names_to_collectors[registered_name]
        raise


AI_LATENCY = _metric_or_existing(Histogram,
    "presek_ai_latency_seconds",
    "Latency of AI provider calls",
    ["provider", "task_type"]
)
AI_CALLS = _metric_or_existing(Counter,
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

class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, api_url: str, model: str):
        super().__init__("mistral", api_key, api_url, model)

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

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None, task_type: str = "default") -> str | None:
        if not self.api_key:
            return None

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "system_instruction": {
                "parts": [{"text": system}]
            },
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.2,
            }
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(self.api_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            log.warning(f"[ai/gemini] Call failed: {e}")
        return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res: yield res

PROVIDERS = {
    "nvidia": NvidiaProvider(
        api_key=None,
        api_url=os.environ.get("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        model=os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")
    ),
    "gemini": GeminiProvider(
        api_key=GEMINI_API_KEY,
        model=GEMINI_MODEL
    ),
    "mistral_large": MistralProvider(
        api_key=os.environ.get("MISTRAL_API_KEY", ""),
        api_url=os.environ.get("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions"),
        model=os.environ.get("MISTRAL_MODEL", "mistral-large-latest")
    ),
    "mistral_small": MistralProvider(
        api_key=os.environ.get("MISTRAL_SMALL_API_KEY", ""),
        api_url=os.environ.get("MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions"),
        model=os.environ.get("MISTRAL_SMALL_MODEL", "mistral-small-latest")
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
    fallback_order = PROVIDER_FALLBACK_ORDER
    if task_type == "research":
        fallback_order = PROVIDER_FALLBACK_ORDER_RESEARCH
    elif task_type in ("summarize", "synthesis"):
        fallback_order = PROVIDER_FALLBACK_ORDER_SUMMARY
        
    for provider_name in fallback_order:
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
    fallback_order = PROVIDER_FALLBACK_ORDER
    if task_type == "research":
        fallback_order = PROVIDER_FALLBACK_ORDER_RESEARCH
    elif task_type in ("summarize", "synthesis"):
        fallback_order = PROVIDER_FALLBACK_ORDER_SUMMARY
        
    for provider_name in fallback_order:
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

    log.error(f"[ai/cascade] All providers in {fallback_order} failed for task {task_type}")
    return None, None

def sync_call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Backwards-compatible alias for synchronous callers."""
    return _call_ai(prompt, system, task_type, max_tokens, json_mode, topic=topic)

def clean_json_response(text: str) -> dict | str | None:
    if text is None or not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    try:
        data = json.loads(text)
        return data
    except Exception:
        return text

def auto_summarize_top_clusters(target_cluster_ids: list[str] = None):
    """Dispatch synthesis tasks for the top recent clusters or specific target clusters."""
    try:
        from config import AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC
        from database import db_manager as db
        from utils import redis_client

        if target_cluster_ids:
            rows = db.execute(
                "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
                (target_cluster_ids,)
            )
        else:
            rows = db.execute(
                "SELECT * FROM articles "
                "WHERE COALESCE(ingested_at, created_at) >= NOW() - make_interval(days => 1) "
                "ORDER BY created_at DESC"
            )
        if not rows: return

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
        top = ranked[:AUTO_SUMMARIZE_TOP_N] if not target_cluster_ids else ranked

        if not top: return

        from tasks.intelligence import synthesize_cluster_task
        for cid, arts, src_count, dt in top:
            synthesize_cluster_task.delay(cid)
            
    except Exception as e:
        log.error(f"[ai/auto_summarize] Orchestration failed: {e}")

def cleanup_generated_images(valid_ids: list[str]):
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir): return
    try:
        for filename in os.listdir(gen_dir):
            if filename.endswith((".jpg", ".svg")):
                cid = filename.split(".")[0]
                if cid not in valid_ids: os.remove(os.path.join(gen_dir, filename))
    except (OSError, PermissionError) as e:
        log.debug(f"[ai_engine] Error cleaning up generated images: {e}")
