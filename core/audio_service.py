"""Cluster TTS briefings via Edge TTS (free, no API key).

Generates Macedonian (or Serbian) speech MP3s for cluster briefings and caches
them under static/uploads/audio/ as tts_<cluster>.<lang>.<hash>.mp3. Files are
served by the existing /static/uploads/audio/{filename} route (audio/mpeg with
range-request support for seeking).

generate_cluster_audio is synchronous on purpose: the API calls it inside
run_in_executor (see routes/news.py).
"""

import asyncio
import hashlib
import logging
import os
import re

log = logging.getLogger("presek")

MAX_TTS_CHARS = 3500
_TAG_RE = re.compile(r"<[^>]+>")
_MD_RE = re.compile(r"[#>*_`~\-]{1,3}")
_URL_RE = re.compile(r"https?://\S+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")

# Spoken-form replacements so the voice doesn't read symbols literally.
_SPEECH_SUBS = (
    ("%", " проценти "),
    ("&", " и "),
    ("€", " евра "),
    ("$", " долари "),
    ("°C", " степени целзиусови "),
    ("°", " степени "),
    ("+", " плус "),
    ("=", " еднакво на "),
)


def _normalize_for_speech(text: str) -> str:
    """Expand symbols/units into spoken words so the voice reads naturally."""
    for src, dst in _SPEECH_SUBS:
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\s+([.!?…,:;])", r"\1", text).strip()


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _to_ssml(text: str, voice: str, lang: str) -> str:
    """Wrap narration in SSML: news-reader pacing with pauses between sentences.

    Plain-text TTS reads headlines as one flat run-on stream. Sentence breaks
    plus a slightly reduced rate give it a human newsreader cadence.
    """
    locale = "sr-RS" if lang.startswith("sr") else "mk-MK"
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    body = '<break time="450ms"/>'.join(_xml_escape(s) for s in sentences)
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
        f'<voice name="{voice}"><prosody rate="-6%">{body}</prosody></voice></speak>'
    )


def _voice_for_lang(lang: str | None) -> str:
    lang = (lang or "mk").lower()
    if lang.startswith("sr"):
        return os.environ.get("TTS_VOICE_SR", "sr-RS-SophieNeural")
    return os.environ.get("TTS_VOICE_MK", "mk-MK-MarijaNeural")


def _clean_text(text: str | None) -> str:
    text = _URL_RE.sub(" ", text or "")
    text = _TAG_RE.sub(" ", text)
    text = _MD_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def select_cluster_audio_text(generated_article, summary) -> str:
    """Pick the narration text: editorial summary preferred, article fallback."""
    text = _clean_text(summary) or _clean_text(generated_article)
    return text[:MAX_TTS_CHARS].strip()


def _audio_dir() -> str:
    """Mirrors core.api_fast's _STATIC_ROOT resolution; served with range support."""
    home = os.environ.get("HOME") or os.path.expanduser("~")
    root = os.environ.get("STATIC_ROOT", os.path.join(home, "presek-runtime", "shared", "static"))
    if not os.path.exists(root):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
    d = os.path.join(root, "uploads", "audio")
    os.makedirs(d, exist_ok=True)
    return d


async def _synthesize_async(ssml: str, voice: str, path: str) -> None:
    import edge_tts

    communicator = edge_tts.Communicate(ssml, voice)
    await communicator.save(path)


def _prune_older_variants(directory: str, cluster_id: str, lang: str, keep_filename: str) -> None:
    prefix = f"tts_{cluster_id}.{lang}."
    try:
        for name in os.listdir(directory):
            if name.startswith(prefix) and name.endswith(".mp3") and name != keep_filename:
                try:
                    os.remove(os.path.join(directory, name))
                except OSError:
                    pass
    except OSError:
        pass


class AudioService:
    def __init__(self, *a, **kw):
        pass

    @staticmethod
    def get_cluster_audio_path_and_url(cluster_id: str, lang: str, content_hash: str):
        safe_cluster = re.sub(r"[^A-Za-z0-9_-]", "_", str(cluster_id))[:64]
        filename = f"tts_{safe_cluster}.{lang}.{content_hash}.mp3"
        path = os.path.join(_audio_dir(), filename)
        return path, f"/static/uploads/audio/{filename}"

    @staticmethod
    def generate_cluster_audio(cluster_id: str, content: str, lang: str = "mk"):
        """Synthesize (or reuse cached) cluster briefing MP3. Returns public URL or None."""
        text = _normalize_for_speech(_clean_text(content)[:MAX_TTS_CHARS]).strip()
        if not text:
            return None
        lang = (lang or "mk").lower()
        voice = _voice_for_lang(lang)
        safe_cluster = re.sub(r"[^A-Za-z0-9_-]", "_", str(cluster_id))[:64]
        digest = hashlib.sha1(f"{voice}|{text}".encode("utf-8")).hexdigest()[:10]
        path, url = AudioService.get_cluster_audio_path_and_url(safe_cluster, lang, digest)
        if os.path.isfile(path) and os.path.getsize(path) > 1024:
            return url
        try:
            asyncio.run(_synthesize_async(_to_ssml(text, voice, lang), voice, path))
        except Exception as e:
            log.warning("Edge TTS synthesis failed for cluster %s: %s", cluster_id, e)
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
            return None
        if not (os.path.isfile(path) and os.path.getsize(path) > 1024):
            return None
        _prune_older_variants(os.path.dirname(path), safe_cluster, lang, os.path.basename(path))
        return url

    async def generate_audio(self, text: str, lang: str = "mk", key: str = "misc"):
        """Async variant: synthesize ad-hoc text, cached by content hash."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, AudioService.generate_cluster_audio, f"adhoc_{key}", text, lang
        )
