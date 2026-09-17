# NLP module - simplified for MK-only minimal AI version

# Import from existing modules
from nlp.utils import cleanAndDecode, deShout
from nlp.text_processing import lemmatize_sr

# Export for easier access
__all__ = [
    "cleanAndDecode",
    "deShout",
    "lemmatize_sr",
]
