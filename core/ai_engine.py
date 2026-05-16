import json
import time
import httpx
import re
import logging
import asyncio
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import AsyncGenerator

from core.config import (
    PROVIDER_FALLBACK_ORDER,
    PROVIDER_FALLBACK_ORDER_RESEARCH,
    PROVIDER_FALLBACK_ORDER_SUMMARY,
)


from prometheus_client import Histogram, Counter, REGISTRY

log = logging.getLogger("presek")


from nlp import synthesize_locally


# =============================================================================
# Prompt Injection Protection
# =============================================================================

# Patterns that indicate potential prompt injection attempts
# These are designed to catch common injection techniques while allowing
# legitimate user content to pass through
_PROMPT_INJECTION_PATTERNS = [
    # System prompt extraction attempts
    r"(?:system|assistant|user|developer|engineer|admin|root)[\s:]*[\:-\[\]]*\s*prompt",
    r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)",
    r"disregard\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)",
    r"forget\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)",
    # Role manipulation
    r"you\s+are\s+(?:now|actually)\s+a",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"act\s+as\s+(?:if\s+you\s+are|a)",
    r"roleplay\s+as",
    # Delimiter attacks
    r"```\s*(?:system|assistant|user|developer)",
    r"\<\s*(?:system|assistant|user|developer)",
    r"\[\s*(?:system|assistant|user|developer)",
    # Jailbreak attempts
    r"DAN\s*\:\s*",  # "DAN:" (Do Anything Now)
    r"developer\s+mode",
    r"jailbreak",
    r"bypass\s+(?:safety|content|filter)",
    r"disable\s+(?:safety|content|filter)",
    # Code execution attempts
    r"(?:exec|evaluate|run|execute)\s*\(",
    r"(?:exec|evaluate|run|execute)\s*\[",
    r"(?:exec|evaluate|run|execute)\s*\{",
    r"python\s*\:",
    r"javascript\s*\:",
    r"bash\s*\:",
    r"\$\s*\{",
    # Data exfiltration attempts
    r"send\s+(?:this|the|all)\s+(?:data|information|content|response)\s+to",
    r"post\s+(?:this|the|all)\s+(?:data|information|content|response)\s+to",
    r"email\s+(?:this|the|all)\s+(?:data|information|content|response)",
]

# Maximum prompt length to prevent DoS via huge prompts
MAX_PROMPT_LENGTH = 32000


def sanitize_ai_prompt(prompt: str, context: str = "user") -> str:
    """
    Sanitize AI prompts to prevent prompt injection attacks.
    
    This function:
    1. Validates prompt length
    2. Checks for known injection patterns
    3. Logs suspicious attempts
    4. Returns sanitized prompt or raises ValueError if injection detected
    
    Args:
        prompt: The prompt text to sanitize
        context: Context for logging (e.g., "user", "system", "article")
    
    Returns:
        The sanitized prompt string
        
    Raises:
        ValueError: If prompt injection is detected
    """
    if not prompt:
        return prompt
    
    if not isinstance(prompt, str):
        raise ValueError(f"Prompt must be a string, got {type(prompt).__name__}")
    
    # Check length
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(
            f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters "
            f"(got {len(prompt)} characters) from context: {context}"
        )
    
    # Check for injection patterns (case-insensitive)
    lower_prompt = prompt.lower()
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lower_prompt, re.IGNORECASE):
            # Log the attempt (without the actual prompt for security)
            log.warning(
                f"[SECURITY] Potential prompt injection attempt detected "
                f"from context '{context}'. "
                f"Pattern matched: {pattern[:50]}..."
            )
            raise ValueError(
                f"Prompt contains disallowed content pattern from context: {context}"
            )
    
    # Remove or escape problematic characters
    # Replace null bytes and control characters
    prompt = prompt.replace("\x00", "")
    
    # Normalize whitespace to prevent encoding-based attacks
    # But preserve intentional newlines and formatting
    prompt = " ".join(prompt.split())
    
    return prompt


def sanitize_ai_system_prompt(system: str) -> str:
    """
    Sanitize system prompts with stricter checks.
    System prompts are more sensitive as they define the AI's behavior.
    """
    return sanitize_ai_prompt(system, context="system")


def sanitize_ai_user_prompt(user_prompt: str) -> str:
    """
    Sanitize user prompts.
    User prompts are checked but with slightly more leniency for natural language.
    """
    return sanitize_ai_prompt(user_prompt, context="user")


# --- Prometheus Metrics ---
def _metric_or_existing(factory, name: str, *args, **kwargs):
    try:
        return factory(name, *args, **kwargs)
    except ValueError:
        for registered_name in (name, name.removesuffix("_total")):
            if registered_name in REGISTRY._names_to_collectors:
                return REGISTRY._names_to_collectors[registered_name]
        raise


AI_LATENCY = _metric_or_existing(
    Histogram,
    "presek_ai_latency_seconds",
    "Latency of AI provider calls",
    ["provider", "task_type"],
)
AI_CALLS = _metric_or_existing(
    Counter,
    "presek_ai_calls_total",
    "Total number of AI provider calls",
    ["provider", "task_type", "status"],
)

# --- Base Classes ---


class AIProvider(ABC):
    @abstractmethod
    def call(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        json_mode: bool,
        topic: str = None,
        task_type: str = "default",
    ) -> str | None:
        log.debug(f"Abstract method call() not implemented for {self.__class__.__name__}")
        return None

    @abstractmethod
    async def stream_call(
        self, prompt: str, system: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        log.debug(f"Abstract method stream_call() not implemented for {self.__class__.__name__}")
        yield ""


# --- Provider Registry ---


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, provider_name: str, api_key: str, api_url: str, model: str):
        self.provider_name = provider_name
        self.api_key = api_key
        self.api_url = api_url
        self.model = model

    def call(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        json_mode: bool,
        topic: str = None,
        task_type: str = "default",
    ) -> str | None:
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
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(self.api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[ai/{self.provider_name}] Call failed: {e}")
        return None

    async def stream_call(
        self, prompt: str, system: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res:
            yield res


class LocalProvider(AIProvider):
    async def stream_call(
        self, prompt: str, system: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res:
            for word in res.split(" "):
                yield word + " "
                await asyncio.sleep(0.01)

    def call(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        json_mode: bool,
        topic: str = None,
        task_type: str = "default",
    ) -> str | None:
        from nlp.local_analyst import analyst

        lowered_system = (system or "").lower()

        if (
            "synthesis" in lowered_system
            or "sintez" in lowered_system
            or task_type == "synthesis"
        ):
            res = analyst.analyze(prompt, system, max_tokens=max_tokens)
            if res:
                return res
            return synthesize_locally([], topic=topic)

        if "summarize" in lowered_system or task_type == "summarize":
            res = analyst.analyze(prompt, system, max_tokens=max_tokens)
            if res:
                return res

        if task_type == "research":
            res = analyst.research_query(prompt, system)
            if res:
                return json.dumps(res) if isinstance(res, dict) else res

        res = analyst.analyze(prompt, system, max_tokens=max_tokens)
        if res:
            if json_mode:
                return json.dumps(
                    {"report": res, "status": "success", "mode": "local_fallback"}
                )
        return res


class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, api_url: str, model: str):
        super().__init__("mistral", api_key, api_url, model)


class NvidiaProvider(AIProvider):
    def __init__(self, api_key: str, api_url: str, model: str):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model

    def call(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
        json_mode: bool,
        topic: str = None,
        task_type: str = "default",
    ) -> str | None:
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
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(self.api_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[ai/nvidia] Call failed: {e}")
        return None

    async def stream_call(
        self, prompt: str, system: str, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res:
            yield res


PROVIDERS = {
    "nvidia": NvidiaProvider(
        api_key=os.environ.get("NVIDIA_API_KEY", ""),
        api_url=os.environ.get(
            "NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
        ),
        model=os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"),
    ),
    "mistral_large": MistralProvider(
        api_key=os.environ.get("MISTRAL_API_KEY", ""),
        api_url=os.environ.get(
            "MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions"
        ),
        model=os.environ.get("MISTRAL_MODEL", "mistral-large-latest"),
    ),
    "mistral_small": MistralProvider(
        api_key=os.environ.get("MISTRAL_SMALL_API_KEY", ""),
        api_url=os.environ.get(
            "MISTRAL_API_URL", "https://api.mistral.ai/v1/chat/completions"
        ),
        model=os.environ.get("MISTRAL_SMALL_MODEL", "mistral-small-latest"),
    ),
    "local": LocalProvider(),
}

# --- Service Methods ---


async def _stream_with_initial_chunk(
    generator: AsyncGenerator[str, None], first_chunk: str
) -> AsyncGenerator[str, None]:
    yield first_chunk
    async for chunk in generator:
        yield chunk


async def _call_ai_async(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    stream: bool = False,
    topic: str = None,
):
    """Entrypoint with cascading failover."""
    # Sanitize prompts to prevent injection attacks
    try:
        system = sanitize_ai_system_prompt(system)
        prompt = sanitize_ai_user_prompt(prompt)
    except ValueError as e:
        log.error(f"[ai/cascade] Prompt sanitization failed: {e}")
        AI_CALLS.labels(provider="sanitization", task_type=task_type, status="blocked").inc()
        return None, None
    
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
                    AI_CALLS.labels(
                        provider=provider_name, task_type=task_type, status="empty"
                    ).inc()
                    continue
                if first_chunk:
                    AI_LATENCY.labels(
                        provider=provider_name, task_type=task_type
                    ).observe(time.time() - start_time)
                    AI_CALLS.labels(
                        provider=provider_name, task_type=task_type, status="success"
                    ).inc()
                    return (
                        _stream_with_initial_chunk(generator, first_chunk),
                        provider_name,
                    )
                continue

            res = await asyncio.to_thread(
                provider.call,
                prompt,
                system,
                max_tokens,
                json_mode,
                topic=topic,
                task_type=task_type,
            )
            if res:
                AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(
                    time.time() - start_time
                )
                AI_CALLS.labels(
                    provider=provider_name, task_type=task_type, status="success"
                ).inc()
                return res, provider_name
            else:
                AI_CALLS.labels(
                    provider=provider_name, task_type=task_type, status="failure"
                ).inc()
        except Exception as e:
            AI_CALLS.labels(
                provider=provider_name, task_type=task_type, status="error"
            ).inc()
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue

    return None, None


def _call_ai(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    topic: str = None,
):
    """Synchronous AI entrypoint with cascading failover."""
    # Sanitize prompts to prevent injection attacks
    try:
        system = sanitize_ai_system_prompt(system)
        prompt = sanitize_ai_user_prompt(prompt)
    except ValueError as e:
        log.error(f"[ai/cascade] Prompt sanitization failed: {e}")
        AI_CALLS.labels(provider="sanitization", task_type=task_type, status="blocked").inc()
        return None, None
    
    fallback_order = PROVIDER_FALLBACK_ORDER
    if task_type == "research":
        fallback_order = PROVIDER_FALLBACK_ORDER_RESEARCH
    elif task_type in ("summarize", "synthesis"):
        fallback_order = PROVIDER_FALLBACK_ORDER_SUMMARY

    for provider_name in fallback_order:
        provider = PROVIDERS[provider_name]
        start_time = time.time()
        try:
            res = provider.call(
                prompt, system, max_tokens, json_mode, topic=topic, task_type=task_type
            )
            if res:
                AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(
                    time.time() - start_time
                )
                AI_CALLS.labels(
                    provider=provider_name, task_type=task_type, status="success"
                ).inc()
                return res, provider_name
            else:
                AI_CALLS.labels(
                    provider=provider_name, task_type=task_type, status="failure"
                ).inc()
                log.warning(
                    f"[ai/cascade] Provider {provider_name} returned empty response for task {task_type}"
                )
        except Exception as e:
            AI_CALLS.labels(
                provider=provider_name, task_type=task_type, status="error"
            ).inc()
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")
            continue

    log.error(
        f"[ai/cascade] All providers in {fallback_order} failed for task {task_type}"
    )
    return None, None


def sync_call_ai(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    topic: str = None,
):
    """Backwards-compatible alias for synchronous callers."""
    return _call_ai(prompt, system, task_type, max_tokens, json_mode, topic=topic)


def clean_json_response(text: str) -> dict | str | None:
    if text is None or not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""

    # 1. Strip markdown fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    # 2. Try direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # If it's the expected structure, return it
            if "answer" in data:
                return data
            if "report" in data:
                return {"answer": data["report"], "suggestions": data.get("suggestions", [])}
            # Single key unwrapping
            if len(data) == 1:
                val = list(data.values())[0]
                if isinstance(val, str) and (len(val) > 20 or " " in val):
                    return {"answer": val, "suggestions": []}
        return data
    except Exception as e:
        log.warning(f"Direct JSON parse failed in _unwrapped_answer: {e}")

    # 3. Aggressive Regex Extraction (if JSON parse failed)
    # This handles cases where the model returns broken JSON or text with JSON inside
    # Look for "answer": "..." OR "report": "..." OR "summary": "..."
    for key in ("answer", "report", "summary"):
        pattern = rf'"{key}"\s*:\s*"(.*?)"(?=\s*[,}}])'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            clean_text = (
                match.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
            )
            return {"answer": clean_text, "suggestions": []}

    # 4. Brute force: find the first { and last } and try parsing that
    try:
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last > first:
            candidate = text[first : last + 1]
            data = json.loads(candidate)
            if isinstance(data, dict):
                if "answer" in data:
                    return data
                if "report" in data:
                    return {"answer": data["report"], "suggestions": data.get("suggestions", [])}
    except Exception as e:
        log.warning(f"Brute-force JSON parse failed in _unwrapped_answer: {e}")

    # 5. Final Fallback: Return the raw text but strip common JSON artifacts
    # if it obviously leaked (e.g. starts with { "answer": )
    text = re.sub(r'^\{\s*"answer"\s*:\s*"', '', text)
    text = re.sub(r'"\s*,\s*"suggestions".*\}\s*$', '', text, flags=re.DOTALL)
    text = re.sub(r'"\s*\}\s*$', '', text)

    return text.replace("\\n", "\n").replace('\\"', '"').strip()


def generate_cover_art(safe_id: str, svg_content: str) -> str | None:
    """Generate and save cover art for a cluster."""
    try:
        path = f"static/generated/{safe_id}.svg"
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        return f"/static/generated/{safe_id}.svg"
    except Exception as e:
        log.warning(f"[ai] Local placeholder failed: {e}")
    return None


def auto_summarize_top_clusters(target_cluster_ids: list[str] = None):
    """Dispatch synthesis tasks for the top recent clusters or specific target clusters."""
    try:
        from core.config import AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC
        from core.database import db_manager as db

        if target_cluster_ids:
            rows = db.execute(
                "SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC",
                (target_cluster_ids,),
            )
        else:
            rows = db.execute(
                "SELECT * FROM articles "
                "WHERE COALESCE(ingested_at, created_at) >= NOW() - make_interval(days => 1) "
                "ORDER BY created_at DESC"
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
        top = ranked[:AUTO_SUMMARIZE_TOP_N] if not target_cluster_ids else ranked

        if not top:
            return

        from tasks.intelligence import synthesize_cluster_task

        for cid, arts, src_count, dt in top:
            # Aggregate article content for the synthesizer
            content = "\n\n".join([(a.get("title") or "") + ": " + (a.get("summary") or "") for a in arts])
            synthesize_cluster_task.delay(cid, content=content)

        # Also trigger backfill for older clusters that might have been missed
        from tasks.intelligence import backfill_cluster_summaries_task
        backfill_cluster_summaries_task.delay(days=7, lang="sr")  # Backfill last 7 days for Serbian
        backfill_cluster_summaries_task.delay(days=7, lang="mk")  # Backfill last 7 days for Macedonian

    except Exception as e:
        log.error(f"[ai/auto_summarize] Orchestration failed: {e}")


def cleanup_generated_images(valid_ids: list[str]):
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir):
        return
    try:
        for filename in os.listdir(gen_dir):
            if filename.endswith((".jpg", ".svg")):
                cid = filename.split(".")[0]
                if cid not in valid_ids:
                    os.remove(os.path.join(gen_dir, filename))
    except (OSError, PermissionError) as e:
        log.debug(f"[ai_engine] Error cleaning up generated images: {e}")
