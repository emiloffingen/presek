"""Stub: nlp.local_analyst removed in mk-only simplify."""

import re


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
