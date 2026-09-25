import asyncio
import atexit
import json
import logging
import os
import re
import sys
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, AsyncGenerator

import httpx
from prometheus_client import REGISTRY, Counter, Histogram

from core.config import (
    AI_ENABLED,
    PROVIDER_FALLBACK_ORDER,
    PROVIDER_FALLBACK_ORDER_RESEARCH,
    PROVIDER_FALLBACK_ORDER_SUMMARY,
)

log = logging.getLogger("presek")

PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS = int(os.environ.get("PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS", "300"))
_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}


def _provider_cooldown_remaining(provider_name: str) -> float:
    return max(0.0, _PROVIDER_COOLDOWN_UNTIL.get(provider_name, 0.0) - time.time())


def _mark_provider_cooldown(provider_name: str, retry_after: str | None = None):
    try:
        cooldown_seconds = int(retry_after) if retry_after else PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS
    except (TypeError, ValueError):
        cooldown_seconds = PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS
    _PROVIDER_COOLDOWN_UNTIL[provider_name] = time.time() + max(1, cooldown_seconds)


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

# Classic "DAN:" jailbreak uses an uppercase role prefix at line start.
# Do not use a bare `dan:` match — it false-positives on Serbian news copy
# (e.g. "Prvi dan:", "Radni dan:").
_JAILBREAK_DAN_PATTERNS = [
    r"(?:^|\n)\s*DAN\s*:\s*",
    r"(?:^|\n)\s*dan\s*:\s*(?:you|ignore|forget|pretend|do anything)",
]

# Maximum prompt length to prevent DoS via huge prompts
MAX_PROMPT_LENGTH = 32000


def _raise_prompt_injection(pattern: str, context: str) -> None:
    log.warning(
        f"[SECURITY] Potential prompt injection attempt detected "
        f"from context '{context}'. "
        f"Pattern matched: {pattern[:50]}..."
    )
    raise ValueError(f"Prompt contains disallowed content pattern from context: {context}")


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

    lower_prompt = prompt.lower()

    for pattern in _JAILBREAK_DAN_PATTERNS[:1]:
        if re.search(pattern, prompt):
            _raise_prompt_injection(pattern, context)

    for pattern in _JAILBREAK_DAN_PATTERNS[1:]:
        if re.search(pattern, lower_prompt, re.IGNORECASE):
            _raise_prompt_injection(pattern, context)

    for pattern in _PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lower_prompt, re.IGNORECASE):
            _raise_prompt_injection(pattern, context)

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
        lang: str = "sr",
        response_schema: Any = None,
    ) -> str | None:
        log.debug(f"Abstract method call() not implemented for {self.__class__.__name__}")
        return None

    @abstractmethod
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        log.debug(f"Abstract method stream_call() not implemented for {self.__class__.__name__}")
        yield ""


_SHARED_HTTP_CLIENT = None


def _get_shared_client() -> httpx.Client:
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is None:
        _SHARED_HTTP_CLIENT = httpx.Client(timeout=30.0)
        atexit.register(_cleanup_shared_client)
    return _SHARED_HTTP_CLIENT


def _cleanup_shared_client():
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is not None:
        try:
            _SHARED_HTTP_CLIENT.close()
        except Exception:
            log.debug("AI engine cleanup failed")
        _SHARED_HTTP_CLIENT = None


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
        lang: str = "sr",
        response_schema: Any = None,
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
        if json_mode or response_schema:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            if task_type == "daily_brief":
                from core.runtime_limits import NVIDIA_DAILY_BRIEF_TIMEOUT_SECONDS

                timeout = float(NVIDIA_DAILY_BRIEF_TIMEOUT_SECONDS)
            else:
                timeout = 120.0
            if "pytest" in sys.modules:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(self.api_url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            else:
                client = _get_shared_client()
                resp = client.post(self.api_url, json=payload, headers=headers, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            log.warning(f"[ai/{self.provider_name}] Unexpected response format from {self.model}: {e}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                _mark_provider_cooldown(self.provider_name, e.response.headers.get("Retry-After"))
            log.warning(f"[ai/{self.provider_name}] Call failed for model {self.model}: {e}")
        except httpx.RequestError as e:
            log.warning(f"[ai/{self.provider_name}] Call failed for model {self.model}: {e}")
        return None

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res:
            yield res


class LocalProvider(AIProvider):
    def __init__(self):
        try:
            import os

            from nlp.local_analyst import MODEL_PATH

            self.model = os.path.basename(MODEL_PATH)
        except ImportError:
            self.model = "gemma-4-E2B-it-Q4_K_M.gguf"

    @staticmethod
    def _local_synthesis_system(lang: str) -> str:
        from core.runtime_limits import LOCAL_SYNTHESIS_SIMPLIFIED_SCHEMA

        if LOCAL_SYNTHESIS_SIMPLIFIED_SCHEMA:
            if lang == "mk":
                return (
                    "Ти си уредник на Пресек со мал локален модел. Врати САМО валиден JSON со клучеви: "
                    "synthetic_headline, synthetic_standfirst, summary, article, key_facts, perspectives, "
                    "verification_report, sentiment, tone_analysis. "
                    "article е еден string со 3 кратки пасуси разделени со \\n\\n. "
                    "summary е листа од 3 конкретни ставки. key_facts е листа од 3-5 кратки факти. "
                    "perspectives е листа од 1-2 објекти со angle и content. Не измислувај бројки или цитати."
                )
            return (
                "Ti si urednik Preseka sa malim lokalnim modelom. Vrati SAMO validan JSON sa kljucevima: "
                "synthetic_headline, synthetic_standfirst, summary, article, key_facts, perspectives, "
                "verification_report, sentiment, tone_analysis. "
                "article je jedan string sa 3 kratka pasusa razdvojena sa \\n\\n. "
                "summary je lista od 3 konkretne stavke. key_facts je lista od 3-5 kratkih cinjenica. "
                "perspectives je lista od 1-2 objekta sa angle i content. Ne izmisljaj brojke ili citate."
            )

        if lang == "mk":
            return (
                "Ти си главен уредник на Пресек и пишуваш со мал локален модел, затоа следи ја шемата прецизно. "
                "Напиши премиум уредничка синтеза на стандарден македонски јазик, со јасна хиерархија на факти. "
                "Врати САМО валиден JSON со клучеви: synthetic_headline, synthetic_standfirst, summary, article, "
                "key_facts, perspectives, verification_report, sentiment, tone_analysis. "
                "article мора да биде еден string со точно 5 пасуси разделени со \\n\\n: лид, контекст, согласност меѓу изворите, "
                "разлики/интереси, што е непроверено или непознато. Секој пасус има 2-4 реченици. "
                "Не прави листа извор по извор; синтетизирај. Не измислувај бројки, цитати, мотиви или причинско-последични врски. "
                "summary е листа од 3-4 конкретни ставки. key_facts е листа од 4-6 кратки проверливи факти. "
                "perspectives е листа од 2-3 објекти со angle и content. Пиши без AI фрази, без маркетинг тон и без повторување."
            )
        return (
            "Ti si glavni urednik Preseka i pišeš malim lokalnim modelom, zato precizno prati šemu. "
            "Napiši premium uredničku sintezu na književnom srpskom jeziku, latinica, sa jasnom hijerarhijom činjenica. "
            "Vrati SAMO validan JSON sa ključevima: synthetic_headline, synthetic_standfirst, summary, article, "
            "key_facts, perspectives, verification_report, sentiment, tone_analysis. "
            "article mora biti jedan string sa tačno 5 kratkih pasusa razdvojenih sa \\n\\n: lede, kontekst, saglasnost izvora, "
            "razlike/interesi, šta je neprovereno ili nepoznato. Svaki pasus ima 2-4 rečenice. "
            "Ne piši izvor po izvor; sintetizuj. Ne izmišljaj brojke, citate, motive ili uzročno-posledične veze. "
            "summary je lista od 3-4 konkretne stavke. key_facts je lista od 4-6 kratkih proverljivih činjenica. "
            "perspectives je lista od 2-3 objekta sa angle i content. Piši bez AI fraza, marketing tona i ponavljanja."
        )

    @staticmethod
    def _local_synthesis_prompt(prompt: str, lang: str) -> str:
        if lang == "mk":
            instruction = (
                "Од следниот контекст направи богата, уреднички полирана синтеза. "
                "Започни со најважната промена или последица, потоа објасни контекст и актери. "
                "Не препишувај извор по извор; спои ги фактите во една јасна приказна. "
                "Користи [1], [2] само кога конкретна тврдња е врзана за извор. "
                "Ако контекстот е слаб, напиши пократко, но не пополнувај со општи реченици."
            )
        else:
            instruction = (
                "Od sledećeg konteksta napravi bogatu, urednički poliranu sintezu. "
                "Počni najvažnijom promenom ili posledicom, zatim objasni kontekst i aktere. "
                "Ne prepisuj izvor po izvor; spoji činjenice u jednu jasnu priču. "
                "Koristi [1], [2] samo kada je konkretna tvrdnja vezana za izvor. "
                "Ako je kontekst slab, piši kraće, ali ne popunjavaj opštim rečenicama."
            )
        return f"{instruction}\n\nKONTEKST:\n{prompt}"

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
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
        lang: str = "sr",
        response_schema: Any = None,
    ) -> str | None:
        from nlp.local_analyst import analyst

        lowered_system = (system or "").lower()

        if "synthesis" in lowered_system or "sintez" in lowered_system or task_type == "synthesis":
            if json_mode or response_schema is not None:
                prompt = self._local_synthesis_prompt(prompt, lang)
                system = self._local_synthesis_system(lang)
            from core.runtime_limits import (
                LOCAL_LLM_SYNTHESIS_LOCK_TIMEOUT_SECONDS,
                LOCAL_SYNTHESIS_MAX_TOKENS,
                local_synthesis_enabled,
            )

            if not local_synthesis_enabled():
                return None

            local_max_tokens = min(max_tokens, LOCAL_SYNTHESIS_MAX_TOKENS)
            res = analyst.analyze(
                prompt,
                system,
                max_tokens=local_max_tokens,
                use_grammar=json_mode,
                lang=lang,
                response_schema=response_schema,
                temperature=0.18,
                force_local=True,
                lock_timeout=LOCAL_LLM_SYNTHESIS_LOCK_TIMEOUT_SECONDS,
                task_type="synthesis",
            )
            if res:
                return res
            return None

        if "summarize" in lowered_system or task_type == "summarize":
            res = analyst.analyze(
                prompt,
                system,
                max_tokens=max_tokens,
                lang=lang,
                force_local=True,
            )
            if res:
                return res

        if task_type == "research":
            res = analyst.research_query(prompt, system, lang=lang, force_local=True)
            if res:
                return json.dumps(res) if isinstance(res, dict) else res

        res = analyst.analyze(
            prompt,
            system,
            max_tokens=max_tokens,
            lang=lang,
            response_schema=response_schema,
            force_local=True,
        )
        if res:
            if json_mode or response_schema:
                try:
                    json.loads(res)
                    return res
                except ValueError:
                    return json.dumps({"report": res, "status": "success", "mode": "local_fallback"})
        return res


class NvidiaProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, api_url: str, model: str):
        super().__init__("nvidia", api_key, api_url, model)


class GeminiProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            "gemini",
            api_key,
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            model,
        )


class Gemini2Provider(OpenAICompatibleProvider):
    """Second Google account (separate key) for extra free quota."""

    def __init__(self, api_key: str, model: str):
        super().__init__(
            "gemini2",
            api_key,
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            model,
        )


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            "groq",
            api_key,
            "https://api.groq.com/openai/v1/chat/completions",
            model,
        )


class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            "mistral",
            api_key,
            "https://api.mistral.ai/v1/chat/completions",
            model,
        )


class Mistral2Provider(OpenAICompatibleProvider):
    """Second Mistral account (separate key + model) for extra free quota."""

    def __init__(self, api_key: str, model: str):
        super().__init__(
            "mistral2",
            api_key,
            "https://api.mistral.ai/v1/chat/completions",
            model,
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            "openrouter",
            api_key,
            "https://openrouter.ai/api/v1/chat/completions",
            model,
        )


class CerebrasProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str):
        super().__init__(
            "cerebras",
            api_key,
            "https://api.cerebras.ai/v1/chat/completions",
            model,
        )


PROVIDERS = {
    "openrouter": OpenRouterProvider(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model=os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
    ),
    "cerebras": CerebrasProvider(
        api_key=os.environ.get("CEREBRAS_API_KEY", ""),
        model=os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b"),
    ),
    "mistral": MistralProvider(
        api_key=os.environ.get("MISTRAL_API_KEY", ""),
        model=os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
    ),
    "mistral2": Mistral2Provider(
        api_key=os.environ.get("MISTRAL2_API_KEY", ""),
        model=os.environ.get("MISTRAL2_MODEL", "mistral-medium-latest"),
    ),
    "nvidia": NvidiaProvider(
        api_key=os.environ.get("NVIDIA_API_KEY", ""),
        api_url=os.environ.get("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        model=os.environ.get("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"),
    ),
    "gemini": GeminiProvider(
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    ),
    "gemini2": Gemini2Provider(
        api_key=os.environ.get("GEMINI2_API_KEY", ""),
        model=os.environ.get("GEMINI2_MODEL", "gemini-flash-latest"),
    ),
    "groq": GroqProvider(
        api_key=os.environ.get("GROQ_API_KEY", ""),
        model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
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


def _parsed_json_dict(res: str | None) -> dict | None:
    if not res:
        return None
    parsed = clean_json_response(res)
    if isinstance(parsed, dict) and parsed:
        return parsed
    return None


def build_provider_fallback_order(
    task_type: str = "default",
    provider_override: str | None = None,
    exclude_providers: list[str] | None = None,
) -> list[str]:
    """Build provider cascade order with optional primary override and exclusions."""
    if not AI_ENABLED:
        return []
    from core.runtime_limits import synthesis_local_only

    if synthesis_local_only() and task_type in ("synthesis", "summarize", "translation"):
        order = ["local"]
        if provider_override == "local" or not provider_override:
            excluded = set(exclude_providers or [])
            return [provider for provider in order if provider not in excluded]
        if provider_override in PROVIDERS and provider_override != "local":
            log.warning(
                "[ai/cascade] Ignoring provider_override=%s because SYNTHESIS_LOCAL_ONLY=true",
                provider_override,
            )
        excluded = set(exclude_providers or [])
        return [provider for provider in order if provider not in excluded]

    if task_type == "research":
        base_order = list(PROVIDER_FALLBACK_ORDER_RESEARCH)
    elif task_type in ("summarize", "synthesis"):
        try:
            from core.llm_router import SmartModelRouter

            base_order = SmartModelRouter.get_dynamic_fallback_order(task_type)
        except Exception as exc:
            log.debug(f"[ai/cascade] Dynamic fallback order unavailable: {exc}")
            base_order = list(PROVIDER_FALLBACK_ORDER_SUMMARY)
    else:
        base_order = list(PROVIDER_FALLBACK_ORDER)

    base_order = [provider for provider in base_order if provider in PROVIDERS]

    if provider_override and provider_override in PROVIDERS:
        order = [provider_override]
        for provider in base_order:
            if provider not in order:
                order.append(provider)
    else:
        order = list(base_order)

    from core.runtime_limits import local_synthesis_enabled

    if (
        "local" in PROVIDERS
        and "local" not in order
        and not (task_type == "synthesis" and not local_synthesis_enabled())
    ):
        order.append("local")

    if task_type == "synthesis" and not local_synthesis_enabled():
        order = [provider for provider in order if provider != "local"]

    excluded = set(exclude_providers or [])

    # Reserve certain providers for synthesis-only to protect their rate limits
    from core.config import PROVIDER_RESERVE_FOR_SYNTHESIS

    if PROVIDER_RESERVE_FOR_SYNTHESIS and task_type not in ("synthesis",):
        for reserved in PROVIDER_RESERVE_FOR_SYNTHESIS:
            if reserved in order and len(order) > 1:
                log.debug(
                    "[ai/cascade] Reserving provider %s for synthesis (task=%s)",
                    reserved,
                    task_type,
                )
                excluded.add(reserved)

    return [provider for provider in order if provider not in excluded]


def _record_provider_outcome(provider_name: str, task_type: str, success: bool, duration: float) -> None:
    try:
        from core.llm_router import SmartModelRouter

        SmartModelRouter._update_performance_metrics(provider_name, success, duration)
    except Exception as exc:
        log.debug(f"[ai/cascade] Failed to record provider metrics: {exc}")


def _invoke_provider_call(
    provider,
    provider_name: str,
    prompt: str,
    system: str,
    max_tokens: int,
    json_mode: bool,
    topic: str | None,
    task_type: str,
    lang: str,
    response_schema: Any,
) -> str | None:
    res = provider.call(
        prompt,
        system,
        max_tokens,
        json_mode,
        topic=topic,
        task_type=task_type,
        lang=lang,
        response_schema=response_schema,
    )

    if json_mode and res and not _parsed_json_dict(res):
        log.warning(f"[ai/cascade] Provider {provider_name} returned malformed JSON, retrying once...")
        res = provider.call(
            prompt + "\n\nCRITICAL: Return valid JSON only.",
            system,
            max_tokens,
            json_mode,
            topic=topic,
            task_type=task_type,
            lang=lang,
            response_schema=response_schema,
        )
        if res and not _parsed_json_dict(res):
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="malformed_json").inc()
            log.warning(
                f"[ai/cascade] Provider {provider_name} still returned malformed JSON for task {task_type}, trying next provider"
            )
            return None

    return res


async def _call_ai_async(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    stream: bool = False,
    topic: str = None,
    lang: str = "sr",
    response_schema: Any = None,
    provider_override: str | None = None,
    exclude_providers: list[str] | None = None,
):
    """Async entrypoint with cascading failover."""
    if not AI_ENABLED:
        return None, None
    try:
        system = sanitize_ai_system_prompt(system)
        prompt = sanitize_ai_user_prompt(prompt)
    except ValueError as e:
        log.error(f"[ai/cascade] Prompt sanitization failed: {e}")
        AI_CALLS.labels(provider="sanitization", task_type=task_type, status="blocked").inc()
        return None, None

    fallback_order = build_provider_fallback_order(task_type, provider_override, exclude_providers)
    if not fallback_order:
        log.error(f"[ai/cascade] No providers left in fallback order for task {task_type}")
        return None, None

    for provider_name in fallback_order:
        provider = PROVIDERS[provider_name]
        cooldown_remaining = _provider_cooldown_remaining(provider_name)
        if cooldown_remaining > 0:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="cooldown").inc()
            log.warning(
                f"[ai/cascade] Provider {provider_name} is rate-limited, skipping for {cooldown_remaining:.0f}s"
            )
            continue
        start_time = time.time()
        try:
            if stream:
                generator = provider.stream_call(prompt, system, max_tokens)
                try:
                    first_chunk = await anext(generator)
                except StopAsyncIteration:
                    AI_CALLS.labels(provider=provider_name, task_type=task_type, status="empty").inc()
                    _record_provider_outcome(provider_name, task_type, False, time.time() - start_time)
                    continue
                if first_chunk:
                    duration = time.time() - start_time
                    AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(duration)
                    AI_CALLS.labels(provider=provider_name, task_type=task_type, status="success").inc()
                    _record_provider_outcome(provider_name, task_type, True, duration)
                    return (
                        _stream_with_initial_chunk(generator, first_chunk),
                        provider_name,
                    )
                _record_provider_outcome(provider_name, task_type, False, time.time() - start_time)
                continue

            res = await asyncio.to_thread(
                _invoke_provider_call,
                provider,
                provider_name,
                prompt,
                system,
                max_tokens,
                json_mode,
                topic,
                task_type,
                lang,
                response_schema,
            )
            duration = time.time() - start_time
            if res:
                AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(duration)
                AI_CALLS.labels(provider=provider_name, task_type=task_type, status="success").inc()
                _record_provider_outcome(provider_name, task_type, True, duration)
                return res, provider_name

            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="failure").inc()
            _record_provider_outcome(provider_name, task_type, False, duration)
            log.warning(f"[ai/cascade] Provider {provider_name} returned empty response for task {task_type}")
        except Exception as e:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="error").inc()
            _record_provider_outcome(provider_name, task_type, False, time.time() - start_time)
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")

            if "429" in str(e):
                _mark_provider_cooldown(provider_name)
                log.info(f"[ai/cascade] Rate limit hit for {provider_name}, backing off...")
                await asyncio.sleep(2)

            continue

    log.error(f"[ai/cascade] All providers in {fallback_order} failed for task {task_type}")
    return None, None


def _call_ai(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    topic: str = None,
    lang: str = "sr",
    response_schema: Any = None,
    provider_override: str | None = None,
    exclude_providers: list[str] | None = None,
):
    """Synchronous AI entrypoint with cascading failover."""
    if not AI_ENABLED:
        return None, None
    try:
        system = sanitize_ai_system_prompt(system)
        prompt = sanitize_ai_user_prompt(prompt)
    except ValueError as e:
        log.error(f"[ai/cascade] Prompt sanitization failed: {e}")
        AI_CALLS.labels(provider="sanitization", task_type=task_type, status="blocked").inc()
        return None, None

    fallback_order = build_provider_fallback_order(task_type, provider_override, exclude_providers)
    if not fallback_order:
        log.error(f"[ai/cascade] No providers left in fallback order for task {task_type}")
        return None, None

    for provider_name in fallback_order:
        provider = PROVIDERS[provider_name]
        cooldown_remaining = _provider_cooldown_remaining(provider_name)
        if cooldown_remaining > 0:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="cooldown").inc()
            log.warning(
                f"[ai/cascade] Provider {provider_name} is rate-limited, skipping for {cooldown_remaining:.0f}s"
            )
            continue
        start_time = time.time()
        try:
            res = _invoke_provider_call(
                provider,
                provider_name,
                prompt,
                system,
                max_tokens,
                json_mode,
                topic,
                task_type,
                lang,
                response_schema,
            )
            duration = time.time() - start_time
            if res:
                AI_CALLS.labels(provider=provider_name, task_type=task_type, status="success").inc()
                AI_LATENCY.labels(provider=provider_name, task_type=task_type).observe(duration)
                _record_provider_outcome(provider_name, task_type, True, duration)
                return res, provider_name

            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="failure").inc()
            _record_provider_outcome(provider_name, task_type, False, duration)
            log.warning(f"[ai/cascade] Provider {provider_name} returned empty response for task {task_type}")
        except Exception as e:
            AI_CALLS.labels(provider=provider_name, task_type=task_type, status="error").inc()
            _record_provider_outcome(provider_name, task_type, False, time.time() - start_time)
            log.error(f"[ai/cascade] Provider {provider_name} failed: {e}")

            if "429" in str(e):
                _mark_provider_cooldown(provider_name)
                log.info(f"[ai/cascade] Rate limit hit for {provider_name}, backing off...")
                time.sleep(2)

            continue

    log.error(f"[ai/cascade] All providers in {fallback_order} failed for task {task_type}")
    return None, None


async def async_call_ai(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    topic: str = None,
    lang: str = "sr",
    response_schema: Any = None,
    provider_override: str | None = None,
    exclude_providers: list[str] | None = None,
):
    """Asynchronous AI provider cascade."""
    return await _call_ai_async(
        prompt,
        system,
        task_type,
        max_tokens,
        json_mode,
        topic=topic,
        lang=lang,
        response_schema=response_schema,
        provider_override=provider_override,
        exclude_providers=exclude_providers,
    )


def sync_call_ai(
    prompt: str,
    system: str,
    task_type: str = "default",
    max_tokens: int = 2000,
    json_mode: bool = False,
    topic: str = None,
    lang: str = "sr",
    response_schema: Any = None,
    provider_override: str | None = None,
    exclude_providers: list[str] | None = None,
):
    """Backwards-compatible alias for synchronous callers."""
    return _call_ai(
        prompt,
        system,
        task_type,
        max_tokens,
        json_mode,
        topic=topic,
        lang=lang,
        response_schema=response_schema,
        provider_override=provider_override,
        exclude_providers=exclude_providers,
    )


def _escape_json_string_control_chars(text: str) -> str:
    """Escape raw control characters that providers sometimes emit inside JSON strings."""
    result: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if escaped:
            result.append(char)
            escaped = False
            continue

        if char == "\\" and in_string:
            result.append(char)
            escaped = True
            continue

        if char == '"':
            in_string = not in_string
            result.append(char)
            continue

        if in_string and ord(char) < 0x20:
            if char == "\n":
                result.append("\\n")
            elif char == "\r":
                result.append("\\r")
            elif char == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(char):04x}")
            continue

        result.append(char)

    return "".join(result)


def repair_json_syntax(s: str) -> str:
    """Repair common LLM JSON syntax issues like trailing commas and raw newlines inside string literals."""
    if not isinstance(s, str):
        return s

    # Extract string literals to avoid modifying them
    strings = []

    def replace_str(match):
        strings.append(match.group(0))
        return f"__STR_PLACEHOLDER_{len(strings) - 1}__"

    # Match double quoted string literals, handling escaped quotes
    pattern = r'"(?:[^"\\]|\\.)*"'
    placeholder_s = re.sub(pattern, replace_str, s)

    # Now we can safely perform repairs on placeholder_s
    # 1. Remove trailing commas before } or ]
    placeholder_s = re.sub(r",\s*\}", "}", placeholder_s)
    placeholder_s = re.sub(r",\s*\]", "]", placeholder_s)

    # Restore the strings and escape any raw control characters inside them
    def restore_str(match):
        idx = int(match.group(1))
        val = strings[idx]
        inner = val[1:-1]
        # Escape raw control characters inside strings
        inner = inner.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{inner}"'

    restored = re.sub(r"__STR_PLACEHOLDER_(\d+)__", restore_str, placeholder_s)
    return restored


def clean_json_response(text: str) -> dict | str | None:
    if text is None or not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""

    # 1. Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    def _parse_json(candidate: str):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            try:
                repaired = _escape_json_string_control_chars(candidate)
                if repaired != candidate:
                    return json.loads(repaired)
            except Exception:
                log.debug("AI engine fallback")

            try:
                repaired = repair_json_syntax(candidate)
                return json.loads(repaired)
            except Exception:
                log.debug("AI engine fallback")
            raise

    # 2. Try direct JSON parse
    try:
        data = _parse_json(text)
        if isinstance(data, dict):
            # If it's the expected structure, return it
            if "answer" in data:
                return data
            if "report" in data:
                return {"answer": data["report"], "suggestions": data.get("suggestions", [])}
            # Single key unwrapping
            if len(data) == 1:
                key = list(data.keys())[0]
                val = list(data.values())[0]
                if key in ("answer", "summary", "report") and isinstance(val, str):
                    return {"answer": val, "suggestions": []}
                if isinstance(val, str) and (len(val) > 20 or " " in val):
                    return {"answer": val, "suggestions": []}
        return data
    except Exception as e:
        log.warning(f"Direct JSON parse failed in _unwrapped_answer: {e}")

    # 3. Brute force: find the first { or [ and last } or ] and try parsing that
    # Moved before regex extraction to parse full JSON objects wrapped in conversational text
    try:
        first_curly = text.find("{")
        last_curly = text.rfind("}")
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")

        first = -1
        last = -1
        if first_curly != -1 and last_curly > first_curly:
            if first_bracket != -1 and last_bracket > first_bracket:
                if first_curly < first_bracket:
                    first = first_curly
                    last = last_curly
                else:
                    first = first_bracket
                    last = last_bracket
            else:
                first = first_curly
                last = last_curly
        elif first_bracket != -1 and last_bracket > first_bracket:
            first = first_bracket
            last = last_bracket

        if first != -1 and last > first:
            candidate = text[first : last + 1]
            data = _parse_json(candidate)
            if isinstance(data, dict):
                if "answer" in data:
                    return data
                if "report" in data:
                    return {"answer": data["report"], "suggestions": data.get("suggestions", [])}
                # Single key unwrapping
                if len(data) == 1:
                    key = list(data.keys())[0]
                    val = list(data.values())[0]
                    if key in ("answer", "summary", "report") and isinstance(val, str):
                        return {"answer": val, "suggestions": []}
                    if isinstance(val, str) and (len(val) > 20 or " " in val):
                        return {"answer": val, "suggestions": []}
                return data
            return data
    except Exception as e:
        log.warning(f"Brute-force JSON parse failed in _unwrapped_answer: {e}")

    # 4. Aggressive Regex Extraction (if JSON parse failed)
    # This handles cases where the model returns broken JSON or text with JSON inside
    # We look for "answer" or "report" or "summary" followed by the content
    # This is more robust against multiline and unescaped content
    for key in ("answer", "report", "summary"):
        # Match "key": ... up to the next key or end of structure
        pattern = rf'"{key}"\s*:\s*["\'](.*?)["\'](?=\s*[,}}])'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            clean_text = match.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
            # Attempt to find suggestions if they exist in the text
            suggestions = []
            sugg_match = re.search(r'"suggestions"\s*:\s*\[(.*?)\]', text, re.DOTALL | re.IGNORECASE)
            if sugg_match:
                sugg_str = sugg_match.group(1)
                suggestions = [s.strip().strip('"').strip("'") for s in sugg_str.split(",")]
            return {"answer": clean_text, "suggestions": [s for s in suggestions if s]}

    # 5. Final Fallback: Return the raw text but strip common JSON artifacts
    # if it obviously leaked (e.g. starts with { "answer": )
    text = re.sub(r'^\{\s*"answer"\s*:\s*"', "", text)
    text = re.sub(r'"\s*,\s*"suggestions".*\}\s*$', "", text, flags=re.DOTALL)
    text = re.sub(r'"\s*\}\s*$', "", text)

    # 6. Additional cleanup for system prompt leakage and commands
    # Remove common system prompt patterns that might leak through

    # First, try to remove complete system prompt blocks
    system_prompt_patterns = [
        r"^PITANJE:\s*.*?\n\nKONTEKST ZA ANALIZU:\s*.*?\n\n",
        r"^PRASANjE:\s*.*?\n\nKONTEKST ZA ANALIZA:\s*.*?\n\n",
        r"^\*\*\*\s*Presek.*?\*\*\*\s*\n\n",
        r"^\*\*\*\s*Пресек.*?\*\*\*\s*\n\n",
        r"^PRASANjE:\s*.*?\n\n",  # Fallback for partial matches
        r"^PITANJE:\s*.*?\n\n",  # Fallback for partial matches
    ]

    for pattern in system_prompt_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            text = text[match.end() :].strip()
            break

    # Remove individual command patterns from the beginning (after system prompt removal)
    text = re.sub(r"^(?:PITANJE|PRASANjE|KONTEKST|ODGOVOR|ANSWER|REPORT):\s*", "", text, flags=re.IGNORECASE)

    # Remove JSON-like structures that might have leaked
    text = re.sub(r'\{\s*"[^"]+"\s*:\s*"[^"]*"\s*\}\s*', "", text)

    # Remove any remaining asterisk-delimited patterns
    text = re.sub(r"^\*\*\*\s*[^\*]+\*\*\*\s*", "", text, flags=re.DOTALL)

    # Clean up any remaining command-like patterns at the start
    text = re.sub(r"^[A-Z\s]+:\s*", "", text)

    # Also remove common answer prefixes in both languages
    text = re.sub(r"^(?:ODGOVOR|ANSWER):\s*", "", text, flags=re.IGNORECASE)

    # Final cleanup: remove empty lines and trim
    text = "\n".join(line for line in text.split("\n") if line.strip())

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
    if not AI_ENABLED:
        return
    try:
        from core.config import (
            AUTO_SUMMARIZE_DELAY,
            AUTO_SUMMARIZE_FRESH_HOURS,
            AUTO_SUMMARIZE_MIN_SRC,
            AUTO_SUMMARIZE_TOP_N,
        )
        from core.database import db_manager as db
        from tasks.utils import get_celery_queue_depth, pipeline_backpressure_active, synthesis_dispatch_deferred

        if not target_cluster_ids and (
            pipeline_backpressure_active() or synthesis_dispatch_deferred() or get_celery_queue_depth() >= 100
        ):
            log.info("[ai/auto_summarize] Skipping cycle while celery queue backlog is high.")
            return

        from core.config import HOMEPAGE_SYNTHESIS_ONLY

        if not target_cluster_ids and HOMEPAGE_SYNTHESIS_ONLY:
            log.info("[ai/auto_summarize] Skipping broad top-cluster sweep in homepage-only mode.")
            return

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

        candidate_ids = list(clusters_map.keys())
        fresh_summary_ids = set()
        if candidate_ids:
            fresh_rows = db.execute(
                """
                SELECT DISTINCT cluster_id
                FROM cluster_summaries
                WHERE cluster_id = ANY(%s)
                  AND created_at >= NOW() - make_interval(hours => %s)
                  AND COALESCE(generation_provider, '') NOT IN ('enhanced_fallback', '')
                """,
                (candidate_ids, AUTO_SUMMARIZE_FRESH_HOURS),
            )
            fresh_summary_ids = {row["cluster_id"] for row in fresh_rows}

        ranked = []
        for cid, arts in clusters_map.items():
            if cid in fresh_summary_ids:
                continue
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

        for idx, (cid, arts, _src_count, _dt) in enumerate(top):
            content = "\n\n".join([(a.get("title") or "") + ": " + (a.get("summary") or "") for a in arts])
            countdown = int(idx * AUTO_SUMMARIZE_DELAY)
            synthesize_cluster_task.apply_async(
                (cid, content),
                {"fast_mode": False},
                countdown=countdown,
                queue="synthesis",
            )

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
