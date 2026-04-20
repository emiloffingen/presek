import os


def configure_huggingface_cache() -> str:
    """Point model caches at a writable, persistent app-owned directory."""
    app_root = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(app_root) == "current":
        shared_root = os.path.join(os.path.dirname(app_root), "shared")
    else:
        shared_root = ""

    preferred_cache = os.path.join(shared_root, "huggingface") if shared_root else ""
    fallback_cache = os.path.join(app_root, ".cache", "huggingface")
    cache_root = preferred_cache if shared_root and os.path.isdir(shared_root) else fallback_cache

    os.makedirs(cache_root, exist_ok=True)
    os.makedirs(os.path.join(cache_root, "hub"), exist_ok=True)
    os.makedirs(os.path.join(cache_root, "transformers"), exist_ok=True)
    os.makedirs(os.path.join(cache_root, "sentence_transformers"), exist_ok=True)

    os.environ.setdefault("HF_HOME", cache_root)
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(cache_root, "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(cache_root, "transformers"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(cache_root, "sentence_transformers"))
    return cache_root
