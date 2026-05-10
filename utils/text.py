import math

def format_sources(count: int) -> str:
    """Pluralization helper for Macedonian sources."""
    if count == 1:
        return "1 извор"
    elif 2 <= count <= 4:
        return f"{count} извора"
    return f"{count} извори"

def calculate_reading_time(text: str) -> int:
    """Estimates reading time in minutes."""
    if not text:
        return 1
    return max(1, math.ceil(len(text.split()) / 200))
