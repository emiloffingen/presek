import os
import re
import logging
import subprocess
import asyncio
from typing import Optional

log = logging.getLogger("presek.audio")

# Shared static path for uploads in Presek runtime
_STATIC_ROOT = "/home/emiloffingen/presek-runtime/shared/static"
if not os.path.exists(_STATIC_ROOT):
    # Fallback to local dev path
    _STATIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))

_AUDIO_DIR = os.path.join(_STATIC_ROOT, "uploads", "audio")

def clean_briefing_text_for_tts(text: str) -> str:
    """Sanitizes markdown briefing content to read naturally in spoken audio."""
    if not text:
        return ""
    # Remove cluster links like [[12345678abcdef]]
    text = re.sub(r"\[\[[0-9a-fA-F]+\]\]", "", text)
    # Remove other markdown links [text](url)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove markdown headers and indicators
    text = re.sub(r"##+", "", text)
    text = re.sub(r"###+", "", text)
    # Remove markdown bold/italic tags
    text = text.replace("**", "").replace("*", "").replace("`", "")
    # Remove markdown bullets/list dashes
    text = re.sub(r"^\s*[\-\*•]\s*", "", text, flags=re.MULTILINE)
    # Clean whitespace
    text = re.sub(r"\n+", " . ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

class AudioService:
    @staticmethod
    def get_audio_path_and_url(date_str: str, lang: str) -> tuple[str, str]:
        """Returns the absolute file path and the public URL path for the briefing audio."""
        filename = f"briefing_{date_str}_{lang}.mp3"
        filepath = os.path.join(_AUDIO_DIR, filename)
        urlpath = f"/static/uploads/audio/{filename}"
        return filepath, urlpath

    @classmethod
    def generate_briefing_audio(cls, date_str: str, content: str, lang: str) -> Optional[str]:
        """
        Synthesizes daily briefing text into high-quality speech.
        Uses local lightweight ONNX Kokoro TTS if possible, with a robust fallback pipeline.
        """
        os.makedirs(_AUDIO_DIR, exist_ok=True)
        filepath, urlpath = cls.get_audio_path_and_url(date_str, lang)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            log.info(f"[audio] Audio briefing already exists for {date_str} ({lang}).")
            return urlpath

        clean_text = clean_briefing_text_for_tts(content)
        if not clean_text:
            log.warning("[audio] Empty briefing content, skipping audio synthesis.")
            return None

        log.info(f"[audio] Synthesizing daily briefing for {date_str} ({lang}) [Length: {len(clean_text)} chars]...")

        # 1. Attempt Local Kokoro ONNX Speech Synthesis (First-class choice)
        try:
            import kokoro_onnx
            import soundfile as sf
            import numpy as np

            # Locate local ONNX weights in shared models path
            onnx_path = "/home/emiloffingen/presek-runtime/shared/models/kokoro-v0_19.onnx"
            voices_bin = "/home/emiloffingen/presek-runtime/shared/models/voices.bin"
            
            if os.path.exists(onnx_path) and os.path.exists(voices_bin):
                # Set system espeak-ng data path to override hardcoded paths in precompiled wheels
                os.environ["ESPEAK_DATA_PATH"] = "/usr/lib/x86_64-linux-gnu/espeak-ng-data"
                log.info("[audio] Initializing local Kokoro ONNX model on CPU...")
                kokoro = kokoro_onnx.Kokoro(onnx_path, voices_bin)
                
                # Pick a premium voice (af_bella is female, am_adam is male)
                voice_name = "af_bella" if lang == "sr" else "am_adam"
                
                # Kokoro ONNX generate returns audio array and sample rate
                samples, sample_rate = kokoro.create(
                    clean_text,
                    voice=voice_name,
                    speed=1.0,
                    lang="en-us" # Kokoro handles international mappings elegantly
                )
                
                # Write to WAV temporarily
                wav_path = filepath.replace(".mp3", ".wav")
                sf.write(wav_path, samples, sample_rate)
                
                # Compress to premium MP3 using ffmpeg
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", filepath],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                # Cleanup WAV
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                    
                log.info(f"[audio] Successfully synthesized briefing using local Kokoro ONNX at {filepath}")
                return urlpath
        except Exception as e:
            log.debug(f"[audio] Local Kokoro ONNX pipeline not fully initialized or skipped: {e}")

        # 2. Attempt Google TTS (gTTS) Fallback (Extremely lightweight, zero-compile CPU fallback)
        try:
            log.info("[audio] Attempting gTTS fallback...")
            from gtts import gTTS
            
            # Select regional locales (using Bulgarian 'bg' as closest phonetic fallback for Macedonian 'mk' which is unsupported by Google TTS)
            gtts_lang = "sr" if lang == "sr" else "bg"
            tts = gTTS(text=clean_text, lang=gtts_lang, slow=False)
            tts.save(filepath)
            
            log.info(f"[audio] Successfully synthesized briefing using gTTS fallback at {filepath}")
            return urlpath
        except Exception as e:
            log.debug(f"[audio] gTTS fallback skipped or not installed: {e}")

        # 3. Last Resort: Simple Shell Synthesis / Mock
        # If all else fails, create a clean placeholder voice notification so the player still has content
        try:
            log.info("[audio] Running shell backup voice generation...")
            # We create a silent MP3 or call local 'espeak' if available
            wav_path = filepath.replace(".mp3", ".wav")
            subprocess.run(
                ["espeak", "-w", wav_path, f"Dnevni brifing za {date_str}."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if os.path.exists(wav_path):
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", filepath],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                os.remove(wav_path)
                return urlpath
        except Exception as e:
            log.error(f"[audio] Shell backup voice generation failed: {e}")

        log.error("[audio] Failed to synthesize briefing audio using all available pipelines.")
        return None

    @staticmethod
    def get_cluster_audio_path_and_url(cluster_id: str, lang: str) -> tuple[str, str]:
        """Returns the absolute file path and the public URL path for the cluster synthesis audio."""
        filename = f"cluster_{cluster_id}_{lang}.mp3"
        filepath = os.path.join(_AUDIO_DIR, filename)
        urlpath = f"/static/uploads/audio/{filename}"
        return filepath, urlpath

    @classmethod
    def generate_cluster_audio(cls, cluster_id: str, content: str, lang: str) -> Optional[str]:
        """
        Synthesizes cluster generated article/synthesis text into high-quality speech.
        """
        os.makedirs(_AUDIO_DIR, exist_ok=True)
        filepath, urlpath = cls.get_cluster_audio_path_and_url(cluster_id, lang)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            log.info(f"[audio] Cluster audio already exists for {cluster_id} ({lang}).")
            return urlpath

        clean_text = clean_briefing_text_for_tts(content)
        if not clean_text:
            log.warning("[audio] Empty cluster content, skipping audio synthesis.")
            return None

        log.info(f"[audio] Synthesizing cluster audio for {cluster_id} ({lang}) [Length: {len(clean_text)} chars]...")

        # 1. Attempt Local Kokoro ONNX Speech Synthesis
        try:
            import kokoro_onnx
            import soundfile as sf
            import numpy as np

            onnx_path = "/home/emiloffingen/presek-runtime/shared/models/kokoro-v0_19.onnx"
            voices_bin = "/home/emiloffingen/presek-runtime/shared/models/voices.bin"
            
            if os.path.exists(onnx_path) and os.path.exists(voices_bin):
                os.environ["ESPEAK_DATA_PATH"] = "/usr/lib/x86_64-linux-gnu/espeak-ng-data"
                log.info("[audio] Initializing local Kokoro ONNX model for cluster TTS...")
                kokoro = kokoro_onnx.Kokoro(onnx_path, voices_bin)
                
                voice_name = "af_bella" if lang == "sr" else "am_adam"
                
                samples, sample_rate = kokoro.create(
                    clean_text,
                    voice=voice_name,
                    speed=1.0,
                    lang="en-us"
                )
                
                wav_path = filepath.replace(".mp3", ".wav")
                sf.write(wav_path, samples, sample_rate)
                
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", filepath],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                    
                log.info(f"[audio] Successfully synthesized cluster audio using local Kokoro ONNX at {filepath}")
                return urlpath
        except Exception as e:
            log.debug(f"[audio] Local Kokoro ONNX cluster audio synthesis failed/skipped: {e}")

        # 2. Attempt gTTS Fallback
        try:
            log.info("[audio] Attempting gTTS fallback for cluster audio...")
            from gtts import gTTS
            gtts_lang = "sr" if lang == "sr" else "bg"
            tts = gTTS(text=clean_text, lang=gtts_lang, slow=False)
            tts.save(filepath)
            log.info(f"[audio] Successfully synthesized cluster audio using gTTS fallback at {filepath}")
            return urlpath
        except Exception as e:
            log.debug(f"[audio] gTTS cluster fallback failed: {e}")

        # 3. Last Resort: Shell Synthesis / Mock
        try:
            log.info("[audio] Running shell backup voice generation for cluster audio...")
            wav_path = filepath.replace(".mp3", ".wav")
            subprocess.run(
                ["espeak", "-w", wav_path, f"Sinteza vesti za klaster {cluster_id}."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if os.path.exists(wav_path):
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", filepath],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                os.remove(wav_path)
                return urlpath
        except Exception as e:
            log.error(f"[audio] Shell backup voice generation for cluster audio failed: {e}")

        return None
