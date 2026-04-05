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
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
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

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        if not GOOGLE_API_KEY: return None
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GOOGLE_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.1
            }
        }
        if json_mode: 
            payload["generationConfig"]["responseMimeType"] = "application/json"
        
        try:
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                if not data or "candidates" not in data or not data["candidates"]:
                    return None
                    
                candidate = data["candidates"][0]
                if "content" not in candidate or "parts" not in candidate["content"]:
                    return None
                    
                return candidate["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            log.warning(f"[gemini] API Error {e.code}: {body}")
            return None
        except Exception as e:
            log.warning(f"[gemini] API Error: {e}")
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
            "temperature": 0.2,
            "stream": True
        }
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", self.url, json=payload, headers=headers, timeout=60.0) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                delta = data['choices'][0]['delta'].get('content', '')
                                if delta: yield delta
                            except: continue
        except Exception as e:
            log.warning(f"[{self.name}-stream] Error: {e}")

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
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"}
            req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"[{self.name}] Error: {e}")
            return None

from local_nlp import summarize_locally

# --- Provider Registry ---

class LocalProvider(AIProvider):
    async def stream_call(self, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
        res = self.call(prompt, system, max_tokens, False)
        if res:
            for word in res.split(' '):
                yield word + ' '
                await asyncio.sleep(0.01)

    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        if "Synthesis" in system or "synthesis" in system:
            lines = prompt.split("\n")
            titles = [l.replace("- [", "").split("]:")[0] for l in lines if "]:" in l]
            main_text = "\n".join(lines)
            summary = summarize_locally(main_text, sentence_count=4)
            return f"Збирен извештај од {len(titles)} извори: {summary}"
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
    "translation":  ["mistral", "groq", "gemini"],
    "summarize":    ["mistral", "local", "groq", "gemini"],
    "synthesis":    ["mistral", "local", "groq", "gemini"],
    "daily_brief":  ["mistral", "groq", "gemini"],
    "default":      ["mistral", "local", "groq", "gemini"],
}

# --- Service Methods ---

async def _call_ai_async(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, stream: bool = False):
    from config import AI_DAILY_LIMIT
    from utils import redis_client
    
    chain = TASK_ROUTING.get(task_type, TASK_ROUTING["default"])

    if not stream:
        try:
            if chain and chain[0] == "local":
                res = PROVIDERS["local"].call(prompt, system, max_tokens, json_mode)
                if res: return res, "local"

            count = redis_client.incr("ai:daily_calls")
            redis_client.expire("ai:daily_calls", 86400)
            if count > AI_DAILY_LIMIT:
                if "local" in chain:
                    res = PROVIDERS["local"].call(prompt, system, max_tokens, json_mode)
                    if res:
                        return res, "local"
                return None, "limit_reached"
        except Exception as e:
            log.warning(f"[ai] Redis limit check failed: {e}")

        for name in chain:
            if name == "local":
                res = PROVIDERS["local"].call(prompt, system, max_tokens, json_mode)
                if res: return res, "local"
                continue
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

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False):
    """Synchronous AI entrypoint used by the app and tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_call_ai_async(prompt, system, task_type, max_tokens, json_mode))
    finally:
        loop.close()


def sync_call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False):
    """Backwards-compatible alias for synchronous callers."""
    return _call_ai(prompt, system, task_type, max_tokens, json_mode)

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
        log.warning(f"[translate] Falling back to original text after translation error: {e}")
        return text
    return res


def _is_private_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return True


def _resolve_public_ips(candidate_url: str) -> list[str]:
    parsed = urllib.parse.urlparse(candidate_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Blocked URL")
    if hostname in {"localhost", "metadata.google.internal", "metadata.internal"}:
        raise ValueError("Blocked URL")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolved_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    safe_ips = []
    for info in resolved_infos:
        ip = info[4][0]
        if not _is_private_ip(ip) and ip not in safe_ips:
            safe_ips.append(ip)
    if not safe_ips:
        raise PermissionError("Blocked URL (Private/Reserved IP)")
    return safe_ips


def _peer_ip(response):
    sock = None
    raw = getattr(response, "raw", None)
    if raw is not None:
        connection = getattr(raw, "connection", None) or getattr(raw, "_connection", None)
        if connection is not None:
            sock = getattr(connection, "sock", None)
    if sock is None:
        return None
    try:
        return sock.getpeername()[0]
    except Exception:
        return None


def _download_safe_external_image(url: str, headers: dict[str, str], timeout: int = 15):
    import requests

    session = requests.Session()
    current_url = url
    response = None

    for _ in range(4):
        safe_ips = _resolve_public_ips(current_url)
        response = session.get(
            current_url,
            headers=headers,
            timeout=timeout,
            stream=True,
            verify=True,
            allow_redirects=False,
        )
        peer_ip = _peer_ip(response)
        if not peer_ip or peer_ip not in safe_ips:
            response.close()
            raise PermissionError("Blocked upstream target")
        if 300 <= response.status_code < 400:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Invalid upstream redirect")
            current_url = urllib.parse.urljoin(current_url, location)
            if not re.match(r"^https?://", current_url):
                raise ValueError("Invalid upstream redirect")
            continue
        return response

    raise ValueError("Too many upstream redirects")

def auto_summarize_top_clusters():
    from tasks import summarize_article_task, synthesize_cluster_task
    from utils import redis_client, score_cluster_for_synthesis, rank_articles_in_cluster
    from config import AUTO_SUMMARIZE_TOP_N, AUTO_SUMMARIZE_MIN_SRC
    from database import db_manager as db
    try:
        rows = db.execute("SELECT * FROM articles WHERE created_at >= NOW() - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 500")
        clusters_map = defaultdict(list)
        for r in rows:
            clusters_map[r["cluster_id"]].append(r)
        ranked = []
        for cid, arts in clusters_map.items():
            sorted_arts = rank_articles_in_cluster(arts)
            s = score_cluster_for_synthesis(sorted_arts)
            ranked.append((cid, sorted_arts, s))
        ranked.sort(key=lambda x: x[2], reverse=True)
        for cid, arts, score in ranked[:AUTO_SUMMARIZE_TOP_N]:
            lead = arts[0]
            if not lead.get("summary"):
                dedup_key = f"task:summarize:{lead['id']}"
                if redis_client.set(dedup_key, 1, nx=True, ex=600):
                    summarize_article_task.delay(lead["id"], lead["title"])
            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                if not db.get_synthesis_ids([cid]):
                    dedup_key = f"task:synthesize:{cid}"
                    if redis_client.set(dedup_key, 1, nx=True, ex=600):
                        lines = [f"- [{a['source']}]: {a['title']}" for a in arts[:12]]
                        synthesize_cluster_task.delay(cid, "\n".join(lines))
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")

def search_google_image(query: str) -> str | None:
    import requests
    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=isch"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        pattern = r'\["(http[^"]+)",\d+,\d+\]'
        matches = re.findall(pattern, resp.text)
        for m in matches:
            if "gstatic.com" in m or "encrypted-tbn" in m: continue
            m = m.replace("\\u003d", "=").replace("\\u0026", "&")
            if m.lower().split('?')[0].endswith(('.jpg', '.jpeg', '.png', '.webp')): return m
    except: pass
    return None

def generate_cover_art(cluster_id: str, title: str) -> str | None:
    import os
    from local_nlp import generate_local_placeholder
    from database import db_manager as db
    os.makedirs("static/generated", exist_ok=True)
    save_path_jpg = f"static/generated/{cluster_id}.jpg"
    save_path_svg = f"static/generated/{cluster_id}.svg"
    img_url = search_google_image(title)
    if img_url:
        try:
            resp = _download_safe_external_image(
                img_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            if resp.status_code == 200:
                with open(save_path_jpg, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                resp.close()
                return f"/static/generated/{cluster_id}.jpg"
            resp.close()
        except Exception as e:
            log.warning(f"[cover-art] Remote image fetch failed for {cluster_id}: {e}")
    try:
        cat_row = db.execute_one("SELECT category FROM articles WHERE cluster_id = %s LIMIT 1", (cluster_id,))
        category = cat_row['category'] if cat_row else "Вести"
        svg_content = generate_local_placeholder(cluster_id, title, category)
        with open(save_path_svg, "w", encoding="utf-8") as f: f.write(svg_content)
        return f"/static/generated/{cluster_id}.svg"
    except Exception as e:
        log.warning(f"[cover-art] Local placeholder generation failed for {cluster_id}: {e}")
        return None

def cleanup_cover_art():
    import os
    from database import db_manager as db
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir): return
    try:
        rows = db.execute("SELECT DISTINCT cluster_id FROM articles")
        valid_ids = {r["cluster_id"] for r in rows}
        for filename in os.listdir(gen_dir):
            if filename.endswith((".jpg", ".svg")):
                cid = filename.split(".")[0]
                if cid not in valid_ids: os.remove(os.path.join(gen_dir, filename))
    except: pass
