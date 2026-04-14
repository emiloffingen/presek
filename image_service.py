import os
import re
import logging
import httpx
from io import BytesIO
from PIL import Image
from typing import Optional, Tuple

log = logging.getLogger("presek.image_service")

_UPLOAD_ROOT = "static/uploads"
_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
_MIN_DIMENSION = 200  # Skip tiny logos/icons
_TARGET_WIDTH = 1200  # High-res "master" for the proxy to use

class ImageService:
    def __init__(self):
        os.makedirs(_UPLOAD_ROOT, exist_ok=True)
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
        
        # If we already have it, don't re-download (unless we want to force refresh)
        # For now, let's keep it simple.
        
        try:
            async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                
                content = resp.content
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

image_service = ImageService()
