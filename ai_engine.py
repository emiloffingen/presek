import json
import time
import datetime
import urllib.request
import urllib.error
import urllib.parse
import re
import logging
import asyncio
import socket
import ipaddress
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import AsyncGenerator

from config import (
    GOOGLE_API_KEY, GEMINI_URL,
    GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL,
    CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL,
    MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL,
    OPENAI_API_KEY, OPENAI_API_URL, OPENAI_MODEL,
    POLLINATIONS_API_KEY,
)
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    TRANSLATION_SYSTEM_PROMPT
)

log = logging.getLogger("presek")
GEMINI_MODEL = "gemini-2.0-flash"

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
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        pass

    @abstractmethod
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        pass

class GeminiProvider(AIProvider):
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        if not GOOGLE_API_KEY: return
        
        # Use httpx for async streaming
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?key={GOOGLE_API_KEY}"
        combined = f"{system}\n\nInput:\n{prompt}"
        payload = {
            "contents": [{"parts": [{"text": combined}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, json=payload, timeout=60.0) as response:
                    async for line in response.aiter_lines():
                        if not line: continue
                        if '"text": "' in line:
                            match = re.search(r'"text":\s*"(.*?)"', line)
                            if match:
                                text = match.group(1).encode().decode('unicode_escape')
                                yield text
        except Exception as e:
            log.warning(f"[gemini-stream] Error: {e}")

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        if not GOOGLE_API_KEY: return None
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GOOGLE_API_KEY}"
        
        # Topic-aware prompt enhancement for Gemini
        if topic:
            system = f"{system}\n\nФокус на тема: {topic}"

        payload = {
            "contents": [{"parts": [{"text": f"{system}\n\nInput:\n{prompt}"}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.1 if json_mode else 0.2,
                "responseMimeType": "application/json" if json_mode else "text/plain"
            }
        }
        
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return data['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            if hasattr(e, 'read'):
                log.error(f"[gemini] API Error: {e.read().decode()}")
            else:
                log.error(f"[gemini] Error: {e}")
        return None

class OpenAICompatibleProvider(AIProvider):
    def __init__(self, name, key, url, model):
        self.name = name
        self.key = key
        self.url = url
        self.model = model

    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        if not self.key: return
        import httpx
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "stream": True
        }
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", self.url, json=payload, headers={"Authorization": f"Bearer {self.key}"}, timeout=60.0) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                content = data['choices'][0]['delta'].get('content', '')
                                if content: yield content
                            except: pass
        except Exception as e:
            log.warning(f"[{self.name}-stream] Error: {e}")

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool, topic: str = None) -> str | None:
        if not self.key: return None
        
        if topic:
            system = f"{system}\n\nФокус на тема: {topic}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1 if json_mode else 0.3
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            req = urllib.request.Request(
                self.url, 
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode())
                return data['choices'][0]['message']['content']
        except Exception as e:
            log.error(f"[{self.name}] Error: {e}")
        return None

from local_nlp import summarize_locally, summarize_article_fallback, rewrite_to_macedonian_locally, synthesize_locally

# --- Provider Registry ---

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
            # For local synthesis, we need the raw article data if available
            # If prompt is just text, we fall back to summarizing that text
            try:
                # Prompt for synthesis usually looks like: "Articles:\n- [Source]: Title\n..."
                # But if we are called from auto_summarize_top_clusters, we might have better data.
                # However, since the interface is prompt-based, we extract titles/desc from prompt if possible.
                lines = prompt.split("\n")
                fake_articles = []
                for line in lines:
                    if "]:" in line:
                        parts = line.split("]:", 1)
                        fake_articles.append({"title": parts[1].strip(), "description": "", "source": parts[0].replace("- [", "").strip()})
                
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
    "gemini":     GeminiProvider(),
    "openai":     OpenAICompatibleProvider("openai", OPENAI_API_KEY, OPENAI_API_URL, OPENAI_MODEL),
    "groq":       OpenAICompatibleProvider("groq", GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL),
    "cerebras":   OpenAICompatibleProvider("cerebras", CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL),
    "mistral":    OpenAICompatibleProvider("mistral", MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL),
    "openrouter": OpenAICompatibleProvider("openrouter", OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL),
    "local":      LocalProvider(),
}

TASK_ROUTING = {
    "translation":  ["local"],
    "summarize":    ["local"],
    "synthesis":    ["mistral", "gemini", "local"],
    "daily_brief":  ["mistral", "gemini", "local"],
    "default":      ["local"],
}

# --- Service Methods ---

async def _call_ai_async(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, stream: bool = False, topic: str = None):
    from config import AI_DAILY_LIMIT
    from utils import redis_client
    
    chain = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

    if not stream:
        try:
            if chain and chain[0] == "local":
                res = PROVIDERS["local"].call(prompt, system, max_tokens, json_mode, topic=topic)
                if res: return res, "local"

            count = redis_client.incr("ai:daily_calls")
            redis_client.expire("ai:daily_calls", 86400)
            if count > AI_DAILY_LIMIT:
                if "local" in chain:
                    res = PROVIDERS["local"].call(prompt, system, max_tokens, json_mode, topic=topic)
                    if res:
                        return res, "local"
                return None, "limit_reached"
        except Exception as e:
            log.warning(f"[ai] Redis limit check failed: {e}")

        for name in chain:
            if name == "local":
                res = PROVIDERS["local"].call(prompt, system, max_tokens, json_mode, topic=topic)
                if res: return res, "local"
                continue
            if _is_circuit_open(name): continue
            provider = PROVIDERS.get(name)
            if not provider: continue
            result = provider.call(prompt, system, max_tokens, json_mode, topic=topic)
            if result:
                _record_success(name)
                return result, name
            else:
                _record_fail(name)
        return None, None
    else:
        # Streaming path
        for name in chain:
            if name == "local":
                return PROVIDERS["local"].stream_call(prompt, system, max_tokens)
            if _is_circuit_open(name): continue
            provider = PROVIDERS.get(name)
            if not provider: continue
            return provider.stream_call(prompt, system, max_tokens)
        return None

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Synchronous AI entrypoint used by the app and tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_call_ai_async(prompt, system, task_type, max_tokens, json_mode, topic=topic))
    finally:
        loop.close()

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
                if any(k in data for k in ('summary', 'perspectives', 'entities', 'topic', 'category')):
                    return data
                if len(data) == 1:
                    return str(list(data.values())[0]).strip()
            return data
        except: pass
    text = re.sub(r'```(?:json)?\n?', '', text)
    text = text.replace('```', '').strip()
    return text

def translate_to_macedonian(text: str) -> str | None:
    if not text or not text.strip(): return text
    try:
        res, _ = sync_call_ai(text, TRANSLATION_SYSTEM_PROMPT, task_type="translation")
        if res:
            cleaned = clean_json_response(res)
            if isinstance(cleaned, dict) and 'summary' in cleaned:
                return cleaned['summary']
            return str(cleaned)
    except Exception as e:
        log.error(f"[ai] Translation failed: {e}")
    return rewrite_to_macedonian_locally(text)

def generate_cover_art(cluster_id: str, prompt: str) -> str | None:
    """Generate an AI cover image for a cluster using Pollinations.ai."""
    if not POLLINATIONS_API_KEY: return None
    
    clean_prompt = re.sub(r'[^\w\s]', '', prompt[:200])
    # Enhanced prompt for news visuals
    styled_prompt = f"Professional news illustration, cinematic lighting, minimalistic, {clean_prompt}"
    encoded_prompt = urllib.parse.quote(styled_prompt)
    
    # URL for Pollinations.ai (Free/Fast)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&nologo=true&seed={cluster_id}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()
            if len(content) < 5000: return None # Failed generation
            
            # Store locally
            os.makedirs("static/generated", exist_ok=True)
            path = f"static/generated/{cluster_id}.jpg"
            with open(path, "wb") as f:
                f.write(content)
            return f"/static/generated/{cluster_id}.jpg"
    except Exception as e:
        log.warning(f"[ai] Cover art failed: {e}")
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
