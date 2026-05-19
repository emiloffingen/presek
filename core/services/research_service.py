import logging
import hashlib
import re
from core.ai_engine import sync_call_ai, clean_json_response
from core.prompts import RESEARCH_SYSTEM_PROMPT, RESEARCH_SYSTEM_PROMPT_MK
from routes.intelligence import _RESEARCH_MODE_QUERIES, _build_gemma_research_context

log = logging.getLogger(__name__)

class ResearchService:
    @staticmethod
    async def get_cluster_research(cluster_id: str, mode: str, query: str, lang: str = "sr"):
        clean_mode = (mode or "facts").strip().lower()
        if clean_mode not in {"facts", "perspectives", "context", "custom"}:
            clean_mode = "facts"
            
        research_query = query if clean_mode == "custom" else _RESEARCH_MODE_QUERIES[clean_mode]
        
        context, sources = await _build_gemma_research_context(cluster_id, clean_mode, query)

        research_system_prompt = RESEARCH_SYSTEM_PROMPT_MK if lang == "mk" else RESEARCH_SYSTEM_PROMPT
        prompt = (
            f"PITANJE: {research_query}\n\nKONTEKST ZA ANALIZU:\n{context}"
            if lang == "sr"
            else f"PRASANjE: {research_query}\n\nKONTEKST ZA ANALIZA:\n{context}"
        )
# Use cascading AI engine
raw, provider = await async_call_ai(
    prompt,
    research_system_prompt,
    task_type="research",
    json_mode=True,
    max_tokens=800,
    lang=lang,
)

        if not raw:
            return None

        response = clean_json_response(raw)
        return response
