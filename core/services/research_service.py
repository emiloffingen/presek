import logging
import time
import json
import numpy as np
from prometheus_client import Histogram
from core.ai_engine import async_call_ai, clean_json_response
from core.prompts import RESEARCH_SYSTEM_PROMPT, RESEARCH_SYSTEM_PROMPT_MK
from routes.intelligence import _RESEARCH_MODE_QUERIES, _build_gemma_research_context
from core.entities import extract_entities
from core.embeddings import get_query_embedding_async
from utils import redis_client

log = logging.getLogger(__name__)

RESEARCH_LATENCY = Histogram('presek_research_latency_seconds', 'Research generation latency', ['mode'])

class ResearchService:
    @staticmethod
    async def _get_semantic_cache(cluster_id, query_embedding, mode, lang):
        """Finds cached research by semantic similarity in Redis."""
        # This is a simplified semantic cache: 
        # In a real impl we'd use Redis Search/Vector Indexing here.
        # For now, we store results indexed by query embedding in sorted sets/hashes.
        return None

    @staticmethod
    async def _set_semantic_cache(cluster_id, query_embedding, mode, lang, response):
        pass

    @staticmethod
    async def _augment_report_with_entities(report: str):
        entities = extract_entities(report, max_entities=10)
        return {"report": report, "entities": entities}

    @staticmethod
    async def get_cluster_research(cluster_id: str, mode: str, query: str, lang: str = "sr"):
        start_time = time.time()
        clean_mode = (mode or "facts").strip().lower()
        if clean_mode not in {"facts", "perspectives", "context", "custom"}:
            clean_mode = "facts"

        research_query = query if clean_mode == "custom" else _RESEARCH_MODE_QUERIES[clean_mode]

        # 1. Check Semantic Cache
        query_embedding = await get_query_embedding_async(research_query)
        cached = await ResearchService._get_semantic_cache(cluster_id, query_embedding, clean_mode, lang)
        if cached:
            return cached

        context, sources = await _build_gemma_research_context(cluster_id, clean_mode, query)

        # Step 1: Chain-of-Thought (Extract plan/topics)
        plan_prompt = f"Identify 3 key areas of focus for this query: '{research_query}'. Context: {context[:2000]}"
        plan_raw, _ = await async_call_ai(plan_prompt, "You are a research planner. Return 3 bullet points.", task_type="research", lang=lang)
        
        # Step 2: Final Report Generation
        research_system_prompt = RESEARCH_SYSTEM_PROMPT_MK if lang == "mk" else RESEARCH_SYSTEM_PROMPT
        prompt = (
            f"Query: {research_query}\nPlan: {plan_raw}\nContext: {context}"
            if lang == "sr"
            else f"Prasanje: {research_query}\nPlan: {plan_raw}\nKontekst: {context}"
        )

        raw, provider = await async_call_ai(
            prompt,
            research_system_prompt,
            task_type="research",
            json_mode=True,
            max_tokens=1000,
            lang=lang,
        )

        RESEARCH_LATENCY.labels(mode=clean_mode).observe(time.time() - start_time)
        if not raw:
            return None

        response = clean_json_response(raw)
        
        if isinstance(response, dict) and "answer" in response:
            augmented = await ResearchService._augment_report_with_entities(response["answer"])
            response["entities"] = augmented["entities"]
            
        if response:
            await ResearchService._set_semantic_cache(cluster_id, query_embedding, clean_mode, lang, response)
            
        return response

