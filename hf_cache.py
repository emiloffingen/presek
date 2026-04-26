import os


def configure_huggingface_cache() -> str:
    """Point model caches at a writable, persistent app-owned directory."""
    # Check for production shared directory first (unless in test)
    production_shared = "/home/emiloffingen/presek-runtime/shared/huggingface"
    if "PYTEST_CURRENT_TEST" in os.environ:
        production_shared = "/non/existent/path/for/tests"
    
    app_root = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(app_root) == "current":
        shared_root = os.path.join(os.path.dirname(app_root), "shared", "huggingface")
    else:
        shared_root = ""

    if shared_root and os.path.isdir(os.path.dirname(shared_root)):
        cache_root = shared_root
    elif os.path.isdir(os.path.dirname(production_shared)):
        cache_root = production_shared
    else:
        cache_root = os.path.join(app_root, ".cache", "huggingface")

    os.makedirs(cache_root, exist_ok=True)
    os.makedirs(os.path.join(cache_root, "hub"), exist_ok=True)
    os.makedirs(os.path.join(cache_root, "transformers"), exist_ok=True)
    os.makedirs(os.path.join(cache_root, "sentence_transformers"), exist_ok=True)

    os.environ.setdefault("HF_HOME", cache_root)
    os.environ.setdefault("HF_HUB_CACHE", os.path.join(cache_root, "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(cache_root, "transformers"))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(cache_root, "sentence_transformers"))
    return cache_root
