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

        # 1. Attempt Local Piper ONNX Speech Synthesis (First-class choice)
        try:
            import wave
            from piper import PiperVoice

            # Locate local ONNX weights in shared models path
            onnx_path = "/home/emiloffingen/presek-runtime/shared/models/sr_RS-serbski_institut-medium.onnx"
            config_path = "/home/emiloffingen/presek-runtime/shared/models/sr_RS-serbski_institut-medium.onnx.json"
            
            if os.path.exists(onnx_path) and os.path.exists(config_path):
                # Set system espeak-ng data path to override hardcoded paths in precompiled wheels
                os.environ["ESPEAK_DATA_PATH"] = "/usr/lib/x86_64-linux-gnu/espeak-ng-data"
                log.info("[audio] Initializing local Piper ONNX model...")
                voice = PiperVoice.load(onnx_path, config_path=config_path)
                
                # If Macedonian is requested, maps characters phonetically to Serbian for the model
                text_to_speak = clean_text
                if lang == "mk":
                    # Transliterate Macedonian Cyrillic letters that do not exist in Serbian Cyrillic
                    # to their closest Serbian Cyrillic phonetic equivalents.
                    mapping = {
                        'ѓ': 'ђ', 'Ѓ': 'Ђ',
                        'ќ': 'ћ', 'Ќ': 'Ћ',
                        'ѕ': 'з', 'Ѕ': 'З',
                    }
                    for k, v in mapping.items():
                        text_to_speak = text_to_speak.replace(k, v)
                
                # Write to WAV temporarily
                wav_path = filepath.replace(".mp3", ".wav")
                with wave.open(wav_path, "wb") as wav_file:
                    voice.synthesize_wav(text_to_speak, wav_file)
                
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
                    
                log.info(f"[audio] Successfully synthesized briefing using local Piper ONNX at {filepath}")
                return urlpath
        except Exception as e:
            log.debug(f"[audio] Local Piper ONNX pipeline not fully initialized or skipped: {e}")

        # 2. Attempt OmniVoice Fallback (Massively multilingual zero-shot TTS fallback)
        try:
            log.info("[audio] Attempting OmniVoice fallback...")
            import soundfile as sf
            from omnivoice import OmniVoice
            
            # Load pretrained OmniVoice model dynamically on CPU
            log.info("[audio] Initializing local OmniVoice model on CPU...")
            model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu")
            
            # Use voice design to select premium male/female regional accents
            instruct_desc = "female, clear regional voice" if lang == "sr" or lang == "mk" else "male, clear voice"
            
            log.info(f"[audio] Synthesizing text with OmniVoice [Instruct: {instruct_desc}]...")
            audio = model.generate(
                text=clean_text,
                instruct=instruct_desc,
                num_step=16
            )
            
            # Write to WAV temporarily (OmniVoice sample rate is 24000)
            wav_path = filepath.replace(".mp3", ".wav")
            sf.write(wav_path, audio, 24000)
            
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
                
            log.info(f"[audio] Successfully synthesized briefing using OmniVoice fallback at {filepath}")
            return urlpath
        except Exception as e:
            log.debug(f"[audio] OmniVoice fallback skipped or failed: {e}")

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

        # 1. Attempt Local Piper ONNX Speech Synthesis
        try:
            import wave
            from piper import PiperVoice

            onnx_path = "/home/emiloffingen/presek-runtime/shared/models/sr_RS-serbski_institut-medium.onnx"
            config_path = "/home/emiloffingen/presek-runtime/shared/models/sr_RS-serbski_institut-medium.onnx.json"
            
            if os.path.exists(onnx_path) and os.path.exists(config_path):
                os.environ["ESPEAK_DATA_PATH"] = "/usr/lib/x86_64-linux-gnu/espeak-ng-data"
                log.info("[audio] Initializing local Piper ONNX model for cluster TTS...")
                voice = PiperVoice.load(onnx_path, config_path=config_path)
                
                # If Macedonian is requested, maps characters phonetically to Serbian for the model
                text_to_speak = clean_text
                if lang == "mk":
                    # Transliterate Macedonian Cyrillic letters that do not exist in Serbian Cyrillic
                    # to their closest Serbian Cyrillic phonetic equivalents.
                    mapping = {
                        'ѓ': 'ђ', 'Ѓ': 'Ђ',
                        'ќ': 'ћ', 'Ќ': 'Ћ',
                        'ѕ': 'з', 'Ѕ': 'З',
                    }
                    for k, v in mapping.items():
                        text_to_speak = text_to_speak.replace(k, v)
                
                wav_path = filepath.replace(".mp3", ".wav")
                with wave.open(wav_path, "wb") as wav_file:
                    voice.synthesize_wav(text_to_speak, wav_file)
                
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", filepath],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                    
                log.info(f"[audio] Successfully synthesized cluster audio using local Piper ONNX at {filepath}")
                return urlpath
        except Exception as e:
            log.debug(f"[audio] Local Piper ONNX cluster audio synthesis failed/skipped: {e}")

        # 2. Attempt OmniVoice Fallback
        try:
            log.info("[audio] Attempting OmniVoice fallback for cluster audio...")
            import soundfile as sf
            from omnivoice import OmniVoice
            
            log.info("[audio] Initializing local OmniVoice model for cluster TTS fallback on CPU...")
            model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cpu")
            
            instruct_desc = "female, clear regional voice" if lang == "sr" or lang == "mk" else "male, clear voice"
            
            audio = model.generate(
                text=clean_text,
                instruct=instruct_desc,
                num_step=16
            )
            
            wav_path = filepath.replace(".mp3", ".wav")
            sf.write(wav_path, audio, 24000)
            
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", filepath],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            if os.path.exists(wav_path):
                os.remove(wav_path)
                
            log.info(f"[audio] Successfully synthesized cluster audio using OmniVoice fallback at {filepath}")
            return urlpath
        except Exception as e:
            log.debug(f"[audio] OmniVoice cluster fallback failed: {e}")

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
