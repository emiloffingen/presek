import re
from typing import Set


def extract_title_entities_regex(title: str) -> Set[str]:
    """Fallback regex-based entity extraction using Latin and Cyrillic characters."""
    # Support both Latin and Macedonian/Serbian Cyrillic
    uc = "A-Z\u0400-\u042F"
    lc = "a-z0-9\u0430-\u044F\u0450-\u045F"
    pattern = rf"[{uc}][{lc}]+(?:\s+[{uc}][{lc}]+)*"
    return {match.strip() for match in re.findall(pattern, str(title or "")) if match.strip()}
