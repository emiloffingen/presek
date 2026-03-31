import json
import time
import datetime
import urllib.request
import urllib.error
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

# --- Provider Circuit Breaker Registry ---
_CIRCUIT_STATE = {} # provider_name -> {fails: int, last_fail: float}

def _is_circuit_open(name: str) -> bool:
    state = _CIRCUIT_STATE.get(name)
    if not state: return False
    if state["fails"] >= 3:
        # Re-try after 5 minutes
        if time.time() - state["last_fail"] > 300:
            state["fails"] = 0
            return False
        return True
    return False

def _record_fail(name: str):
    state = _CIRCUIT_STATE.setdefault(name, {"fails": 0, "last_fail": 0})
    state["fails"] += 1
    state["last_fail"] = time.time()

def _record_success(name: str):
    if name in _CIRCUIT_STATE:
        _CIRCUIT_STATE[name]["fails"] = 0

# --- Base Classes ---

class AIProvider(ABC):
    @abstractmethod
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        pass

class GeminiProvider(AIProvider):
    def call(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str | None:
        if not GOOGLE_API_KEY: return None
        url = f"{GEMINI_URL}?key={GOOGLE_API_KEY}"
        combined = f"{system}\n\nInput:\n{prompt}"
        payload = {
            "contents": [{"parts": [{"text": combined}]}],
            "generationConfig": {"maxOutputTokens": max_tokens}
        }
        if json_mode: payload["generationConfig"]["responseMimeType"] = "application/json"
        
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            log.warning(f"[gemini] Error: {e}")
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
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens
        }
        if json_mode: payload["response_format"] = {"type": "json_object"}
        
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}", "User-Agent": "Presek/4.0"}
            req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"[{self.name}] Error: {e}")
            return None

# --- Provider Registry ---

PROVIDERS = {
    "gemini":     GeminiProvider(),
    "groq":       OpenAICompatibleProvider("groq", GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL),
    "cerebras":   OpenAICompatibleProvider("cerebras", CEREBRAS_API_KEY, CEREBRAS_API_URL, CEREBRAS_MODEL),
    "mistral":    OpenAICompatibleProvider("mistral", MISTRAL_API_KEY, MISTRAL_API_URL, MISTRAL_MODEL),
    "openrouter": OpenAICompatibleProvider("openrouter", OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL),
}

TASK_ROUTING = {
    "translation":  ["gemini", "mistral", "groq"],
    "synthesis":    ["gemini", "mistral", "groq"],
    "default":      ["gemini", "groq", "cerebras"],
}

# --- Service Methods ---

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False) -> tuple[str | None, str | None]:
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

def auto_summarize_top_clusters():
    """Dispatches background tasks for summarization/synthesis with deduplication."""
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
            if not lead.get("summary"):
                # Dedup: skip if already queued in the last 10 minutes
                dedup_key = f"task:summarize:{lead['id']}"
                if not redis_client.set(dedup_key, 1, nx=True, ex=600):
                    continue
                summarize_article_task.delay(lead["id"], lead["title"])

            unique_sources = {a["source"] for a in arts}
            if len(unique_sources) >= AUTO_SUMMARIZE_MIN_SRC:
                # Check if synthesis already exists
                if not db.get_synthesis_ids([cid]):
                    # Dedup: skip if synthesis already queued recently
                    dedup_key = f"task:synthesize:{cid}"
                    if not redis_client.set(dedup_key, 1, nx=True, ex=600):
                        continue
                    
                    lines = [f"- [{a['source']}]: {a['title']}" for a in arts[:10]]
                    synthesize_cluster_task.delay(cid, "\n".join(lines))
                    
    except Exception as e:
        log.error(f"[auto-summarize] Error: {e}")

def cleanup_cover_art():
    """Removes generated cover art for clusters that are no longer in the DB."""
    import os
    gen_dir = "static/generated"
    if not os.path.exists(gen_dir): return

    try:
        rows = db.execute("SELECT DISTINCT cluster_id FROM articles")
        valid_ids = {r["cluster_id"] for r in rows}
        
        count = 0
        for filename in os.listdir(gen_dir):
            if filename.endswith(".jpg"):
                cid = filename.replace(".jpg", "")
                if cid not in valid_ids:
                    os.remove(os.path.join(gen_dir, filename))
                    count += 1
        if count:
            log.info(f"[cleanup] Removed {count} orphaned cover art images.")
    except Exception as e:
        log.error(f"[cleanup] Image cleanup failed: {e}")
