import re
from typing import Set

from nlp.keywords import LAT_LOWER_CLASS, LAT_UPPER_CLASS


def extract_title_entities_regex(title: str) -> Set[str]:
    """Fallback regex-based entity extraction using Latin and Cyrillic characters."""
    pattern = rf"[{LAT_UPPER_CLASS}][{LAT_LOWER_CLASS}]+(?:\s+[{LAT_UPPER_CLASS}][{LAT_LOWER_CLASS}]+)*"
    return {match.strip() for match in re.findall(pattern, str(title or "")) if match.strip()}
