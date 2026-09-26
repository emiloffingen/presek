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


def _sentences(text: str) -> list[str]:
    """Split narration into sentences so we can insert natural pauses."""
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _join_for_speech(text: str) -> str:
    """Plain text with punctuation-only pauses.

    edge-tts does NOT accept raw SSML: it escapes whatever we pass and wraps it
    in its own <speak>/<prosody>, so sending ``<break>``/``<prosody>`` markup
    made the voice read the tags literally (garbled, hugely padded audio). We
    therefore send plain text and add breathing room between sentences using
    punctuation the engine already pauses on.
    """
    return " … ".join(_sentences(text))


def _voice_for_lang(lang: str | None) -> str:
    lang = (lang or "mk").lower()
    if lang.startswith("sr"):
        return os.environ.get("TTS_VOICE_SR", "sr-RS-SophieNeural")
    return os.environ.get("TTS_VOICE_MK", "mk-MK-MarijaNeural")


def _rate_for_lang(lang: str | None) -> str:
    """Slightly slower-than-default newsreader cadence (edge-tts prosody rate)."""
    return os.environ.get("TTS_RATE", "-6%")


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


async def _synthesize_async(text: str, voice: str, path: str, rate: str = "-6%") -> None:
    import edge_tts

    # Plain text only: edge-tts escapes the input and wraps it in its own SSML,
    # so rate/pitch/volume must be passed as parameters, never as markup.
    communicator = edge_tts.Communicate(text, voice, rate=rate)
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
    def get_cluster_audio_path_and_url(cluster_id: str, lang: str, content_hash: str | None = None):
        safe_cluster = re.sub(r"[^A-Za-z0-9_-]", "_", str(cluster_id))[:64]
        directory = _audio_dir()
        if content_hash:
            filename = f"tts_{safe_cluster}.{lang}.{content_hash}.mp3"
            return os.path.join(directory, filename), f"/static/uploads/audio/{filename}"
        # content_hash unknown: reuse any existing cached variant for this cluster/lang
        prefix = f"tts_{safe_cluster}.{lang}."
        try:
            for name in sorted(os.listdir(directory)):
                if name.startswith(prefix) and name.endswith(".mp3"):
                    return os.path.join(directory, name), f"/static/uploads/audio/{name}"
        except OSError:
            pass
        filename = f"tts_{safe_cluster}.{lang}..mp3"
        return os.path.join(directory, filename), f"/static/uploads/audio/{filename}"

    @staticmethod
    def generate_cluster_audio(cluster_id: str, content: str, lang: str = "mk"):
        """Synthesize (or reuse cached) cluster briefing MP3. Returns public URL or None."""
        text = _normalize_for_speech(_clean_text(content)[:MAX_TTS_CHARS]).strip()
        if not text:
            return None
        lang = (lang or "mk").lower()
        voice = _voice_for_lang(lang)
        rate = _rate_for_lang(lang)
        speech_text = _join_for_speech(text)
        safe_cluster = re.sub(r"[^A-Za-z0-9_-]", "_", str(cluster_id))[:64]
        digest = hashlib.sha1(f"{voice}|{rate}|{speech_text}".encode("utf-8")).hexdigest()[:10]
        path, url = AudioService.get_cluster_audio_path_and_url(safe_cluster, lang, digest)
        if os.path.isfile(path) and os.path.getsize(path) > 1024:
            return url
        try:
            asyncio.run(_synthesize_async(speech_text, voice, path, rate))
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
