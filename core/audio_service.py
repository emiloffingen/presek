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
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")
_WS_RE = re.compile(r"\s+")

# Spoken-form replacements so the voice doesn't read symbols literally.
# Order matters: multi-char units must be replaced before their prefixes.
_SPEECH_SUBS = (
    ("°C", " степени целзиусови "),
    ("°", " степени "),
    ("%", " проценти "),
    ("&", " и "),
    ("€", " евра "),
    ("$", " долари "),
    ("+", " плус "),
    ("=", " еднакво на "),
    ("№", " број "),
    ("→", " кон "),
)

# Long digit runs are read as one giant number; group them so the voice chunks
# (e.g. "2028" stays fine, but "1234567" becomes "1 234 567").
_BIG_NUMBER_RE = re.compile(r"\d{5,}")

# Scorelines like "3:2" / "3-0" / "2 : 1" are read as times or subtraction.
_SCORE_RE = re.compile(r"(?<![\d])(\d{1,2})\s*[:\-–]\s*(\d{1,2})(?![\d])")

# Abbreviations the voice spells as one odd word need dots so it reads letters.
_ABBREV_SUBS = (
    ("САД", "С.А.Д."),
    ("ЕУ", "Е.У."),
    ("ЕН", "Е.Н."),
    ("МВР", "М.В.Р."),
    ("МАНУ", "М.А.Н.У."),
    ("ООН", "О.О.Н."),
    ("НАТО", "НАТО"),  # NATO is said as a word, keep as-is
    ("ФИФА", "ФИФА"),
    ("УЕФА", "УЕФА"),
)


def _score_to_words(match: re.Match) -> str:
    return f"{match.group(1)} спрема {match.group(2)}"


def _group_digits(match: re.Match) -> str:
    digits = match.group(0)
    groups = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    return " ".join(groups)


def _normalize_for_speech(text: str) -> str:
    """Expand symbols/units/scorelines into spoken words so the voice reads naturally."""
    text = _BIG_NUMBER_RE.sub(_group_digits, text)
    text = _SCORE_RE.sub(_score_to_words, text)
    for src, dst in _SPEECH_SUBS:
        text = text.replace(src, dst)
    for src, dst in _ABBREV_SUBS:
        # Whole-word only, so "ЕУ" doesn't match inside another word.
        text = re.sub(rf"(?<!\w){re.escape(src)}(?!\w)", dst, text)
    text = _WS_RE.sub(" ", text)
    return re.sub(r"\s+([.!?…,:;])", r"\1", text).strip()


def _sentences(text: str) -> list[str]:
    """Split narration into sentences so we can insert natural pauses."""
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _join_for_speech(text: str) -> str:
    """Plain text with sentence breaks the engine pauses on naturally.

    edge-tts does NOT accept raw SSML: it escapes whatever we pass and wraps it
    in its own <speak>/<prosody>, so sending ``<break>``/``<prosody>`` markup
    made the voice read the tags literally (garbled, hugely padded audio). We
    send plain text and let the voice's own sentence prosody do the pacing.
    We only ensure each sentence ends with terminal punctuation so the engine
    registers the boundary (headlines often arrive without a trailing period).
    """
    sentences = _sentences(text)
    if not sentences:
        return text
    out = []
    for s in sentences:
        if s[-1] not in ".!?…":
            s = f"{s}."
        out.append(s)
    return " ".join(out)


def _voice_for_lang(lang: str | None) -> str:
    lang = (lang or "mk").lower()
    if lang.startswith("sr"):
        return os.environ.get("TTS_VOICE_SR", "sr-RS-SophieNeural")
    return os.environ.get("TTS_VOICE_MK", "mk-MK-MarijaNeural")


def _rate_for_lang(lang: str | None) -> str:
    """Newsreader cadence: a touch slower than default for clarity."""
    return os.environ.get("TTS_RATE", "-8%")


def _pitch_for_lang(lang: str | None) -> str:
    """Slightly lowered pitch reads warmer/less robotic than the flat default."""
    return os.environ.get("TTS_PITCH", "-2Hz")


def _volume_for_lang(lang: str | None) -> str:
    return os.environ.get("TTS_VOLUME", "+0%")


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


async def _synthesize_async(
    text: str, voice: str, path: str, rate: str = "-8%", pitch: str = "-2Hz", volume: str = "+0%"
) -> None:
    import edge_tts

    # Plain text only: edge-tts escapes the input and wraps it in its own SSML,
    # so rate/pitch/volume must be passed as parameters, never as markup.
    communicator = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    await communicator.save(path)


def _run_synthesis_sync(text: str, voice: str, path: str, rate: str, pitch: str, volume: str) -> None:
    """Run the async edge-tts call from sync code, even inside a running event loop.

    routes/news.py runs generate_cluster_audio in the default executor (no loop),
    but routes/home.py schedules it on the main loop while it's running, where
    asyncio.run() raises "cannot be called from a running event loop". In that
    case run the coroutine on a dedicated thread with its own loop.
    """

    def factory():
        return _synthesize_async(text, voice, path, rate, pitch, volume)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(factory())
        return
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: asyncio.run(factory())).result()


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
        pitch = _pitch_for_lang(lang)
        volume = _volume_for_lang(lang)
        speech_text = _join_for_speech(text)
        safe_cluster = re.sub(r"[^A-Za-z0-9_-]", "_", str(cluster_id))[:64]
        digest = hashlib.sha1(f"{voice}|{rate}|{pitch}|{volume}|{speech_text}".encode("utf-8")).hexdigest()[:10]
        path, url = AudioService.get_cluster_audio_path_and_url(safe_cluster, lang, digest)
        if os.path.isfile(path) and os.path.getsize(path) > 1024:
            return url
        try:
            _run_synthesis_sync(speech_text, voice, path, rate, pitch, volume)
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
        return await loop.run_in_executor(None, AudioService.generate_cluster_audio, f"adhoc_{key}", text, lang)
