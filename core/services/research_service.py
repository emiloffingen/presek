import asyncio
import logging
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from lxml import html
from prometheus_client import Histogram
from core.ai_engine import async_call_ai, clean_json_response
from core.prompts import RESEARCH_SYSTEM_PROMPT, RESEARCH_SYSTEM_PROMPT_MK
from routes.intelligence import _RESEARCH_MODE_QUERIES, _build_gemma_research_context
from core.entities import extract_entities
from core.embeddings import get_query_embedding_async

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
    def _get_obj_value(obj, *names):
        for name in names:
            if isinstance(obj, dict) and name in obj:
                return obj[name]
            if hasattr(obj, name):
                return getattr(obj, name)
        return None

    @staticmethod
    def _extract_grounding_sources(response):
        sources = []
        queries = []
        candidates = ResearchService._get_obj_value(response, "candidates") or []
        if not candidates:
            return sources, queries

        metadata = ResearchService._get_obj_value(candidates[0], "grounding_metadata", "groundingMetadata")
        if not metadata:
            return sources, queries

        queries = ResearchService._get_obj_value(metadata, "web_search_queries", "webSearchQueries") or []
        chunks = ResearchService._get_obj_value(metadata, "grounding_chunks", "groundingChunks") or []

        seen = set()
        for chunk in chunks:
            web = ResearchService._get_obj_value(chunk, "web")
            if not web:
                continue
            uri = ResearchService._get_obj_value(web, "uri") or ""
            title = ResearchService._get_obj_value(web, "title") or uri
            if not uri or uri in seen:
                continue
            seen.add(uri)
            sources.append({"title": title, "url": uri})

        return sources, queries

    @staticmethod
    def _derive_public_search_query(research_query: str, context: str, mode: str):
        custom = (research_query or "").strip()
        if mode == "custom" and custom:
            custom = re.sub(r"\s+", " ", custom)
            return custom[:180]

        match = re.search(r"--- izvor:[^\n]*---\n([^\n]{20,220})", context or "")
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip()
            return title[:180]

        clean_context = re.sub(r"\s+", " ", context or "").strip()
        return clean_context[:180]

    @staticmethod
    def _clean_search_url(url: str):
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            return unquote(target) if target else url
        return url

    @staticmethod
    async def _public_web_search(query: str, lang: str, limit: int = 5):
        if os.environ.get("ENABLE_PUBLIC_WEB_RESEARCH", "true").lower() != "true":
            return []

        clean_query = re.sub(r"\s+", " ", (query or "").strip())
        if len(clean_query) < 4:
            return []

        region = "mk-mk" if lang == "mk" else "rs-sr"
        headers = {
            "User-Agent": "PresekResearchBot/1.0 (+https://presek.live)",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=headers) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": clean_query, "kl": region},
                )
                response.raise_for_status()
        except Exception as e:
            log.info(f"[research/public-search] Search failed: {e}")
            return []

        try:
            doc = html.fromstring(response.text)
        except Exception as e:
            log.info(f"[research/public-search] Failed to parse results: {e}")
            return []

        results = []
        seen = set()
        for result in doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' result ')]"):
            title_nodes = result.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' result__a ')]")
            title = " ".join(title_nodes[0].xpath(".//text()")).strip() if title_nodes else ""
            url = ResearchService._clean_search_url(title_nodes[0].get("href", "")) if title_nodes else ""
            snippet = " ".join(
                result.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' result__snippet ')]//text()")
            ).strip()
            title = re.sub(r"\s+", " ", title)
            snippet = re.sub(r"\s+", " ", snippet)
            if not title or not url or url in seen:
                continue
            seen.add(url)
            results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= limit:
                break

        return results

    @staticmethod
    def _format_public_search_context(results):
        if not results:
            return ""
        lines = ["JAVNI WEB SEARCH REZULTATI (naslovi i isečci, koristiti kao dodatne signale):"]
        for idx, item in enumerate(results, 1):
            snippet = f" - {item['snippet']}" if item.get("snippet") else ""
            lines.append(f"[W{idx}] {item['title']}{snippet}\nURL: {item['url']}")
        return "\n".join(lines)

    @staticmethod
    async def _get_google_grounded_research(research_query: str, context: str, mode: str, lang: str):
        if os.environ.get("ENABLE_GOOGLE_GROUNDED_RESEARCH", "false").lower() != "true":
            return None

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return None

        def call_google():
            try:
                from google import genai
                from google.genai import types
            except ImportError:
                log.warning("[research/google] google-genai package not installed")
                return None

            client = genai.Client(api_key=api_key)
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            config = types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.2,
            )
            language_rule = (
                "Odgovori na književnom srpskom jeziku, latinica."
                if lang == "sr"
                else "Одговори на македонски јазик, кирилица."
            )
            prompt = (
                f"{language_rule}\n"
                "Generate a concise Google Search-grounded news research answer. "
                "Use current web evidence from Google Search when it is available, and do not invent unsupported claims. "
                "Return only valid JSON in this shape: "
                '{"answer":"4-7 short paragraphs or bullets with the best answer",'
                '"suggestions":["follow-up question 1","follow-up question 2","follow-up question 3"]}.\n\n'
                f"Research mode: {mode}\n"
                f"User question: {research_query}\n\n"
                "Local Presek cluster context, for disambiguation only:\n"
                f"{context[:3500]}"
            )

            try:
                response = client.models.generate_content(
                    model=os.environ.get("GEMINI_GROUNDED_MODEL", os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")),
                    contents=prompt,
                    config=config,
                )
            except Exception as e:
                log.warning(f"[research/google] Grounded Gemini call failed: {e}")
                return None

            parsed = clean_json_response(getattr(response, "text", "") or "")
            if isinstance(parsed, str):
                parsed = {"answer": parsed, "suggestions": []}
            if not isinstance(parsed, dict) or not parsed.get("answer"):
                return None

            sources, queries = ResearchService._extract_grounding_sources(response)
            parsed["provider"] = "gemini_google_search"
            parsed["sources"] = sources
            parsed["search_queries"] = queries
            return parsed

        return await asyncio.to_thread(call_google)

    @staticmethod
    async def get_cluster_research(cluster_id: str, mode: str, query: str, lang: str = "sr"):
        start_time = time.time()
        clean_mode = (mode or "facts").strip().lower()
        if clean_mode not in {"facts", "perspectives", "context", "custom"}:
            clean_mode = "facts"

        effective_lang = lang if lang in _RESEARCH_MODE_QUERIES else "sr"
        research_query = query if clean_mode == "custom" else _RESEARCH_MODE_QUERIES[effective_lang][clean_mode]

        # 1. Check Semantic Cache
        query_embedding = await get_query_embedding_async(research_query)
        cached = await ResearchService._get_semantic_cache(cluster_id, query_embedding, clean_mode, lang)
        if cached:
            return cached

        context, sources = await _build_gemma_research_context(cluster_id, clean_mode, query)

        google_response = await ResearchService._get_google_grounded_research(
            research_query,
            context,
            clean_mode,
            lang,
        )
        if google_response:
            augmented = await ResearchService._augment_report_with_entities(google_response["answer"])
            google_response["entities"] = augmented["entities"]
            if not google_response.get("sources"):
                google_response["sources"] = sources
            await ResearchService._set_semantic_cache(cluster_id, query_embedding, clean_mode, lang, google_response)
            RESEARCH_LATENCY.labels(mode=clean_mode).observe(time.time() - start_time)
            return google_response

        search_query = ResearchService._derive_public_search_query(research_query, context, clean_mode)
        public_sources = await ResearchService._public_web_search(search_query, lang)
        public_context = ResearchService._format_public_search_context(public_sources)
        if public_context:
            context = f"{context}\n\n{public_context}"

        # Step 1: Chain-of-Thought (Extract plan/topics)
        plan_system_prompt = (
            "Ti si planer istraživanja. Vrati 3 kratke teze za fokus."
            if lang == "sr"
            else "Ти си планер на истражување. Врати 3 кратки тези за фокус."
        )
        plan_prompt = (
            f"Identifikuj 3 ključne oblasti fokusa za ovaj upit: '{research_query}'. Kontekst: {context[:2000]}"
            if lang == "sr"
            else f"Идентификувај 3 клучни области на фокус за ова прашање: '{research_query}'. Контекст: {context[:2000]}"
        )
        plan_raw, _ = await async_call_ai(plan_prompt, plan_system_prompt, task_type="research", lang=lang)
        
        # Step 2: Final Report Generation
        research_system_prompt = RESEARCH_SYSTEM_PROMPT_MK if lang == "mk" else RESEARCH_SYSTEM_PROMPT
        prompt = (
            f"Pitanje: {research_query}\nPlan: {plan_raw}\nContext: {context}"
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

        # Normalize: clean_json_response can return a plain string on fallback
        if isinstance(response, str):
            response = {"answer": response, "suggestions": []}

        if isinstance(response, dict) and "answer" in response:
            augmented = await ResearchService._augment_report_with_entities(response["answer"])
            response["entities"] = augmented["entities"]
            response.setdefault("provider", f"public_web_search+{provider}" if public_sources else provider)
            response.setdefault("sources", public_sources or sources)
            response.setdefault("search_queries", [search_query] if public_sources else [])
            
        if response:
            await ResearchService._set_semantic_cache(cluster_id, query_embedding, clean_mode, lang, response)
            
        return response
