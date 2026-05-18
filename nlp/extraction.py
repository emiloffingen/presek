import re
from typing import Set


def extract_title_entities_regex(title: str) -> Set[str]:
    """Fallback regex-based entity extraction using Latin characters."""
    # Use Latin character ranges for Serbian
    uc = "A-Z"
    lc = "a-z0-9"
    pattern = rf"[{uc}][{lc}]+(?:\s+[{uc}][{lc}]+)*"
    return {match.strip() for match in re.findall(pattern, str(title or "")) if match.strip()}
