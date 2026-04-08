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
    GROQ_API_KEY, GROQ_API_URL, GROQ_MODEL,
    OPENAI_API_KEY, OPENAI_API_URL, OPENAI_MODEL,
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
                # Extract titles/desc from prompt if possible
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
    "local": LocalProvider(),
}

TASK_ROUTING = {
    "translation":  ["local"],
    "summarize":    ["local"],
    "synthesis":    ["local"],
    "daily_brief":  ["local"],
    "default":      ["local"],
}

# --- Service Methods ---

async def _call_ai_async(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, stream: bool = False, topic: str = None):
    """Strictly Local AI entrypoint."""
    provider = PROVIDERS["local"]
    if stream:
        return provider.stream_call(prompt, system, max_tokens)
    return provider.call(prompt, system, max_tokens, json_mode, topic=topic), "local"

def _call_ai(prompt: str, system: str, task_type: str = "default", max_tokens: int = 2000, json_mode: bool = False, topic: str = None):
    """Synchronous AI entrypoint used by the app and tests."""
    # Since it's all local now, we don't really need the event loop for the non-stream call,
    # but we'll keep the signature for compatibility.
    return PROVIDERS["local"].call(prompt, system, max_tokens, json_mode, topic=topic), "local"

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

def auto_summarize_top_clusters():
    """Dispatch synthesis tasks for the top recent clusters using local logic."""
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
    if not text or not text.strip(): return text
    # Translation is now 100% local rewriter
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
    
    clean_prompt = re.sub(r'[^\w\s]', '', prompt[:200])
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
