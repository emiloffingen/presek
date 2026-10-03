import logging
import os
import time
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image

try:
    import pillow_avif  # noqa: F401

    _ = pillow_avif  # Reference to suppress unused import warning
    HAS_AVIF = True
except ImportError:
    HAS_AVIF = False

from utils import _peer_ip, _peer_is_public, _resolve_public_ips

log = logging.getLogger("presek.image_service")

# Use absolute path linked to shared storage to persist across releases
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _resolve_upload_root() -> str:
    """Resolve upload dir without crashing CI/containers.

    Prefers explicit env override, then the production shared path when it
    exists, otherwise falls back to repo-local static/uploads so imports
    never raise PermissionError (e.g. /home/emiloffingen on CI runners).
    """
    env_root = os.environ.get("PRESEK_UPLOAD_ROOT")
    if env_root:
        return env_root
    static_root = os.environ.get("STATIC_ROOT")
    if static_root:
        return os.path.join(static_root, "uploads")
    default = os.path.join("/home/emiloffingen/presek-runtime", "shared", "static", "uploads")
    try:
        if os.path.isdir(default) or os.path.isdir(os.path.dirname(default)):
            return default
    except Exception:
        pass
    return os.path.normpath(os.path.join(_PROJECT_ROOT, "..", "static", "uploads"))


# Use shared directory for uploads since release directory is read-only
_UPLOAD_ROOT = _resolve_upload_root()

_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
_MIN_DIMENSION = 200  # Skip tiny logos/icons
_TARGET_WIDTH = 1200  # High-res "master" for the proxy to use


class ImageService:
    def __init__(self):
        try:
            os.makedirs(_UPLOAD_ROOT, exist_ok=True)
        except OSError as e:
            log.warning(f"Upload dir not writable ({_UPLOAD_ROOT}): {e}")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def process_and_save(self, url: str, article_id: int) -> Optional[str]:
        """
        Downloads, validates, optimizes, and saves an image locally.
        Returns the relative path to the saved file.
        """
        if not url or not url.startswith("http"):
            return None

        # Create a stable local filename
        ext = "webp"
        filename = f"art_{article_id}.{ext}"
        local_path = os.path.join(_UPLOAD_ROOT, filename)
        rel_path = filename

        # If we already have it and it's not empty, skip processing
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            return rel_path

        try:
            _resolve_public_ips(url)  # raises for private/reserved hostnames
            async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=10.0) as client:
                async with client.stream("GET", url) as resp:
                    p_ip = _peer_ip(resp)
                    if not p_ip or not _peer_is_public(resp):
                        log.warning(f"SSRF blocked for image {url}: {p_ip}")
                        return None
                    content = await resp.aread()
                    if resp.status_code != 200:
                        return None

                if len(content) > _MAX_IMAGE_SIZE:
                    log.warning(f"Image too large: {url}")
                    return None

                # Open and validate with PIL
                img = Image.open(BytesIO(content))

                # Filter out small icons/logos
                if img.width < _MIN_DIMENSION or img.height < _MIN_DIMENSION:
                    log.info(f"Image too small ({img.width}x{img.height}): {url}")
                    return None

                # Basic aspect ratio check (avoid extremely thin banners)
                ratio = img.width / img.height
                if ratio > 4.0 or ratio < 0.25:
                    log.info(f"Extreme aspect ratio ({ratio:.2f}): {url}")
                    return None

                # Normalize and Resize
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                if img.width > _TARGET_WIDTH:
                    new_height = int(img.height * (_TARGET_WIDTH / img.width))
                    img = img.resize((_TARGET_WIDTH, new_height), Image.Resampling.LANCZOS)

                # Save as optimized WebP
                img.save(local_path, "WEBP", quality=80, method=4)

                log.info(f"Saved optimized image for article {article_id} to {local_path}")
                return f"/static/uploads/{filename}"

        except Exception as e:
            log.error(f"Failed to process image {url}: {e}")
            return None

    async def cleanup_storage(self, valid_article_ids: set[int]):
        """
        Removes local images that are no longer referenced by active articles.
        Also prunes old logs.
        """
        try:
            # 1. Image Cleanup
            now = time.time()
            max_age_seconds = 30 * 24 * 60 * 60  # 30 days

            if os.path.exists(_UPLOAD_ROOT):
                for filename in os.listdir(_UPLOAD_ROOT):
                    if filename.startswith("art_") and filename.endswith(".webp"):
                        try:
                            file_path = os.path.join(_UPLOAD_ROOT, filename)

                            # Check age first
                            if (now - os.path.getmtime(file_path)) > max_age_seconds:
                                os.remove(file_path)
                                log.info(f"Pruned old image (30d+): {filename}")
                                continue

                            # Check if still in DB
                            art_id = int(filename.replace("art_", "").replace(".webp", ""))
                            if art_id not in valid_article_ids:
                                os.remove(file_path)
                                log.info(f"Removed orphaned image: {filename}")
                        except (ValueError, OSError):
                            continue

            # 2. Log Pruning (Keep last 10MB of logs if they grow too large)
            log_dir = os.path.join(_PROJECT_ROOT, "logs")
            if os.path.exists(log_dir):
                for log_file in os.listdir(log_dir):
                    path = os.path.join(log_dir, log_file)
                    if os.path.isfile(path) and os.path.getsize(path) > 10 * 1024 * 1024:
                        # Simple truncate: keep last 1MB
                        try:
                            with open(path, "rb+") as f:
                                f.seek(-1024 * 1024, os.SEEK_END)
                                data = f.read()
                                f.seek(0)
                                f.write(data)
                                f.truncate()
                            log.info(f"Pruned large log file: {log_file}")
                        except Exception as e:
                            log.warning(f"Failed to prune log file {log_file}: {e}")
                            continue
        except Exception as e:
            log.error(f"Cleanup storage failed: {e}")


image_service = ImageService()
