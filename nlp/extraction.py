import re
from typing import Set


def extract_title_entities_regex(title: str) -> Set[str]:
    """Fallback regex-based entity extraction using Macedonian Cyrillic ranges."""
    # Use precise Macedonian Cyrillic ranges to avoid matching lowercase words as entities
    uc = "А-ЯЁЂЃЄЅІЇЈЉЊЋЌЎЏ"
    lc = "а-яёђѓєѕіїјљњћќўџ"
    pattern = rf"[{uc}][{lc}]+(?:\s+[{uc}][{lc}]+)*"
    return {
        match.strip()
        for match in re.findall(pattern, str(title or ""))
        if match.strip()
    }
