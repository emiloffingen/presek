"""Stub: nlp.local_analyst removed in mk-only simplify.

Kept as a dependency-free shim because several modules (ai_engine, research
service, synthesis scheduling) still import `analyst`, `MODEL_PATH` and
`ResearchQueryResponse`.
"""

import os
import re

try:  # pydantic ships with the API stack; fall back to a plain class otherwise
    from pydantic import BaseModel as _BaseModel
except Exception:  # pragma: no cover
    class _BaseModel:  # type: ignore
        pass


MODEL_PATH = os.environ.get("LOCAL_MODEL_PATH", "models/gemma-4-E2B-it-Q4_K_M.gguf")


class ResearchQueryResponse(_BaseModel):
    answer: str = ""
    summary: str = ""
    entities: list[str] = []


class LocalAnalyst:
    def __init__(self, *a, **kw):
        pass

    async def analyze(self, *a, **kw):
        return {}

    def summarize(self, *a, **kw):
        return ""

    def get_zero_token_normalized_headline(self, text, *a, **kw):
        """Stable comparison form used by cluster-detail deduplication."""
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text or "").casefold())).strip()

    def extract_deep_metadata(self, *a, **kw) -> dict:
        return {"entities": [], "topics": [], "sentiment": None}

    def assess_pluralism(self, *a, **kw) -> dict:
        return {"score": None, "perspectives": []}


analyst = LocalAnalyst()
