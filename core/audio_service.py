import os
import re
import logging
import subprocess
import threading
import time
import asyncio
from typing import Optional

log = logging.getLogger("presek.audio")

# Model caching to avoid repeated loading
_omnivoice_model = None
_model_lock = threading.Lock()
_model_load_attempts = 0
_max_model_load_attempts = 3

# Rate limiting settings
_last_generation_time = 0
_min_generation_interval = 2.0  # seconds between generations

# Shared static path for uploads in Presek runtime
_STATIC_ROOT = "/home/emiloffingen/presek-runtime/shared/static"
if not os.path.exists(_STATIC_ROOT):
    # Fallback to local dev path
    _STATIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))

_AUDIO_DIR = os.path.join(_STATIC_ROOT, "uploads", "audio")
_TTS_ENGINE = os.environ.get("AUDIO_TTS_ENGINE", "auto").strip().lower()
_SR_TTS_ENGINE = os.environ.get("AUDIO_TTS_ENGINE_SR", "gtts").strip().lower()
_MK_TTS_ENGINE = os.environ.get("AUDIO_TTS_ENGINE_MK", "omnivoice").strip().lower()
_OMNIVOICE_NUM_STEP = max(1, int(os.environ.get("OMNIVOICE_NUM_STEP", "8")))
_SR_TTS_SPEED_FACTOR = max(1.0, min(2.0, float(os.environ.get("SR_TTS_SPEED_FACTOR", "1.2"))))

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
    def _get_omnivoice_model() -> Optional[any]:
        """Get cached OmniVoice model with singleton pattern to avoid repeated CPU-intensive loading."""
        global _omnivoice_model, _model_load_attempts
        
        with _model_lock:
            if _omnivoice_model is not None:
                return _omnivoice_model
            
            if _model_load_attempts >= _max_model_load_attempts:
                log.error("[audio] Max model load attempts reached, returning None")
                return None
                
            try:
                log.info("[audio] Loading OmniVoice model (first time - this may take CPU resources)...")
                _model_load_attempts += 1
                
                # Try to use GPU if available, otherwise fall back to CPU
                import torch
                device = "cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() else "cpu")
                
                from omnivoice import OmniVoice
                _omnivoice_model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device)
                
                log.info(f"[audio] OmniVoice model loaded successfully on {device}")
                return _omnivoice_model
                
            except Exception as e:
                log.error(f"[audio] Failed to load OmniVoice model: {e}")
                return None

    @classmethod
    def _generate_edge_mp3(cls, text: str, filepath: str, lang: str) -> bool:
        """Generate audio using Microsoft Edge TTS (async wrapper)."""
        try:
            import edge_tts
            
            # Map languages to high-quality neural voices
            voice_map = {
                "mk": "mk-MK-MarijaNeural",
                "sr": "sr-RS-SophieNeural",
                "en": "en-US-AvaNeural"
            }
            
            voice = voice_map.get(lang, "en-US-AvaNeural")
            
            async def _do_generate():
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(filepath)
            
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(_do_generate())
            else:
                result: dict[str, Optional[BaseException]] = {"error": None}

                def run_in_thread():
                    try:
                        asyncio.run(_do_generate())
                    except BaseException as exc:
                        result["error"] = exc

                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()
                thread.join()
                if result["error"]:
                    raise result["error"]
            
            return os.path.exists(filepath) and os.path.getsize(filepath) > 1000
        except Exception as e:
            log.error(f"[audio] Edge TTS audio generation failed: {e}")
            return False

    @staticmethod
    def _enforce_rate_limit():
        """Enforce minimum interval between audio generations to prevent CPU overload."""
        global _last_generation_time
        
        current_time = time.time()
        elapsed = current_time - _last_generation_time
        
        if elapsed < _min_generation_interval:
            sleep_time = _min_generation_interval - elapsed
            log.info(f"[audio] Rate limiting: sleeping for {sleep_time:.2f}s to prevent CPU overload")
            time.sleep(sleep_time)
            
        _last_generation_time = time.time()

    @staticmethod
    def _generate_audio_in_chunks(
        model,
        text: str,
        instruct_desc: str,
        lang: str,
        max_chunk_size: int = 400,
    ) -> any:
        """
        Generate audio in chunks to reduce memory usage and prevent CPU spikes.
        This is especially important for long texts that could cause OOM errors.
        """
        import numpy as np
        
        if len(text) <= max_chunk_size:
            # Short text, generate normally
            chunk_audio = model.generate(
                text=text,
                language=lang,
                instruct=instruct_desc,
                num_step=_OMNIVOICE_NUM_STEP,
            )
            if not chunk_audio or len(chunk_audio) == 0:
                log.error("[audio] OmniVoice generated empty array for single chunk")
                return np.array([], dtype=np.float32)
            return np.concatenate(chunk_audio) if isinstance(chunk_audio, (list, tuple)) else chunk_audio
        
        # Split long text into chunks
        chunks = []
        current_chunk = ""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_chunk_size:
                current_chunk += (" " + sentence) if current_chunk else sentence
            else:
                chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        log.info(f"[audio] Processing {len(chunks)} text chunks to reduce CPU/memory usage")
        
        # Generate audio for each chunk and concatenate
        audio_segments = []
        for i, chunk in enumerate(chunks):
            log.debug(f"[audio] Generating chunk {i+1}/{len(chunks)}...")
            chunk_audio = model.generate(
                text=chunk,
                language=lang,
                instruct=instruct_desc,
                num_step=_OMNIVOICE_NUM_STEP,
            )
            if not chunk_audio or len(chunk_audio) == 0:
                log.error(f"[audio] OmniVoice generated empty array for chunk {i+1}")
                continue
            audio_segments.extend(chunk_audio)
            
            # Small delay between chunks to prevent CPU overload
            if i < len(chunks) - 1:
                time.sleep(0.1)  # 100ms between chunks
        
        return np.concatenate(audio_segments)

    @staticmethod
    def _coerce_audio_array(audio) -> any:
        """Normalize OmniVoice output into a one-dimensional NumPy array."""
        import numpy as np

        if audio is None:
            return np.array([], dtype=np.float32)
        if isinstance(audio, np.ndarray):
            return audio.reshape(-1)
        if isinstance(audio, (list, tuple)):
            if len(audio) == 0:
                return np.array([], dtype=np.float32)
            return np.concatenate(audio).reshape(-1)

        return np.asarray(audio).reshape(-1)

    @staticmethod
    def _lower_process_priority():
        """Lower process priority to reduce impact on system performance."""
        try:
            # Linux/Unix systems
            os.nice(10)  # Lower priority (0-19, higher is lower priority)
            log.debug("[audio] Lowered process priority to reduce CPU impact")
        except (AttributeError, OSError):
            # Windows or unsupported system
            pass

    @staticmethod
    def _espeak_voice(lang: str) -> str:
        if lang == "mk":
            return "mk"
        if lang == "sr":
            return "sr"
        return "en"

    @staticmethod
    def _engine_for_lang(lang: str) -> str:
        if _TTS_ENGINE != "auto":
            return _TTS_ENGINE
        if lang == "mk":
            return _MK_TTS_ENGINE
        if lang == "sr":
            return _SR_TTS_ENGINE
        return "gtts"

    @staticmethod
    def _gtts_lang(lang: str) -> str:
        if lang == "sr":
            return "sr"
        if lang == "mk":
            return "mk"
        return "en"

    @classmethod
    def _generate_gtts_mp3(cls, text: str, filepath: str, lang: str) -> bool:
        """Generate MP3 using gTTS. Falls back to caller if unsupported/network fails."""
        try:
            from gtts import gTTS

            tts = gTTS(text=text, lang=cls._gtts_lang(lang), slow=False)
            tts.save(filepath)
            
            # Apply speed adjustment for Serbian to fix slow speech
            if lang == "sr" and os.path.exists(filepath):
                cls._adjust_audio_speed(filepath, speed_factor=_SR_TTS_SPEED_FACTOR)
            
            return os.path.exists(filepath) and os.path.getsize(filepath) > 1000
        except Exception as e:
            log.error(f"[audio] gTTS audio generation failed: {e}")
            return False

    @classmethod
    def _adjust_audio_speed(cls, filepath: str, speed_factor: float = 1.0) -> bool:
        """Adjust audio playback speed using ffmpeg."""
        try:
            import subprocess
            temp_file = filepath.replace(".mp3", "_temp.mp3")
            
            # Use ffmpeg atempo filter to adjust speed (1.0 = normal, >1.0 = faster)
            cmd = [
                "ffmpeg", "-i", filepath,
                "-filter:a", f"atempo={speed_factor}",
                "-y", temp_file,
                "-loglevel", "error"
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(temp_file):
                # Replace original file with adjusted version
                os.replace(temp_file, filepath)
                log.info(f"[audio] Adjusted audio speed by factor {speed_factor}")
                return True
            else:
                log.error(f"[audio] ffmpeg speed adjustment failed: {result.stderr.decode() if result.stderr else 'unknown error'}")
                # Clean up temp file if it exists
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return False
        except Exception as e:
            log.error(f"[audio] Audio speed adjustment failed: {e}")
            return False

    @classmethod
    def _generate_espeak_mp3(cls, text: str, filepath: str, lang: str) -> bool:
        """Generate a small local MP3 using espeak-ng and ffmpeg."""
        wav_path = filepath.replace(".mp3", ".wav")
        try:
            subprocess.run(
                [
                    "espeak-ng",
                    "-v",
                    cls._espeak_voice(lang),
                    "-s",
                    "155",
                    "-w",
                    wav_path,
                    text,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    wav_path,
                    "-codec:a",
                    "libmp3lame",
                    "-qscale:a",
                    "4",
                    "-threads",
                    "1",
                    "-loglevel",
                    "quiet",
                    filepath,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
            return os.path.exists(filepath) and os.path.getsize(filepath) > 1000
        except Exception as e:
            log.error(f"[audio] espeak-ng audio generation failed: {e}")
            return False
        finally:
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except Exception as cleanup_e:
                log.warning(f"[audio] Failed to cleanup WAV file {wav_path}: {cleanup_e}")

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
        Uses the configured engine for the target language, with fallbacks.
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

        engine = cls._engine_for_lang(lang)
        if engine == "gtts":
            if cls._generate_gtts_mp3(clean_text, filepath, lang):
                log.info(f"[audio] Successfully synthesized audio using gTTS at {filepath}")
                return urlpath
            log.info("[audio] Falling back to espeak-ng for audio")
            if cls._generate_espeak_mp3(clean_text, filepath, lang):
                return urlpath
            return None

        if engine == "edge":
            if cls._generate_edge_mp3(clean_text, filepath, lang):
                log.info(f"[audio] Successfully synthesized audio using Edge TTS at {filepath}")
                return urlpath
            
            log.info(f"[audio] Edge TTS failed for {lang}, attempting high-quality fallback.")
            if lang == "sr":
                if cls._generate_gtts_mp3(clean_text, filepath, lang):
                    log.info(f"[audio] Successfully synthesized audio using gTTS (sr) at {filepath}")
                    return urlpath
            elif lang == "mk":
                # Set engine to omnivoice and continue to the OmniVoice section
                engine = "omnivoice"
            
            if engine != "omnivoice":
                log.info(f"[audio] No high-quality fallback for {lang}, using espeak-ng.")
                if cls._generate_espeak_mp3(clean_text, filepath, lang):
                    return urlpath
                return None

        if engine != "omnivoice":
            if cls._generate_espeak_mp3(clean_text, filepath, lang):
                log.info(f"[audio] Successfully synthesized audio using espeak-ng at {filepath}")
                return urlpath
            return None

        max_retries = 3
        retry_delay = 2.0  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                log.info(f"[audio] Attempting local OmniVoice speech synthesis (attempt {attempt}/{max_retries})...")
                import soundfile as sf

                # Load pretrained OmniVoice model dynamically on CPU
                # Use cached model instead of loading each time
                model = cls._get_omnivoice_model()
                if model is None:
                    log.error("[audio] Could not load OmniVoice model, aborting briefing audio generation")
                    return None
                
                cls._lower_process_priority()
                cls._enforce_rate_limit()
                
                # Use voice design to select premium male/female regional accents
                instruct_desc = "female, young adult" if lang == "sr" or lang == "mk" else "male, young adult"
                
                log.info(f"[audio] Synthesizing text with OmniVoice [Instruct: {instruct_desc}]...")
                # Process text in chunks to reduce memory usage and prevent CPU spikes
                audio = cls._coerce_audio_array(
                    cls._generate_audio_in_chunks(model, clean_text, instruct_desc, lang)
                )
                if audio.size == 0:
                    log.error("[audio] OmniVoice returned empty audio array")
                    return None
                
                # Write to WAV temporarily (OmniVoice sample rate is 24000)
                wav_path = filepath.replace(".mp3", ".wav")
                sf.write(wav_path, audio, 24000)
                
                # Compress to MP3 using ffmpeg with CPU-friendly settings
                try:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", wav_path,
                            "-codec:a", "libmp3lame",
                            "-qscale:a", "4",  # Lower quality = faster encoding
                            "-threads", "1",   # Limit to 1 thread to prevent CPU overload
                            "-loglevel", "quiet",  # Suppress output
                            filepath
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    log.info(f"[audio] Successfully synthesized briefing using local OmniVoice at {filepath}")
                    return urlpath
                finally:
                    # Cleanup WAV file in finally block to ensure it always gets removed
                    try:
                        if os.path.exists(wav_path):
                            os.remove(wav_path)
                            log.debug(f"[audio] Cleaned up temporary WAV file: {wav_path}")
                    except Exception as cleanup_e:
                        log.warning(f"[audio] Failed to cleanup WAV file {wav_path}: {cleanup_e}")
            except Exception as e:
                log.error(f"[audio] Local OmniVoice speech synthesis attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    import time
                    log.info(f"[audio] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

        log.error("[audio] Failed to synthesize briefing audio since OmniVoice failed after all retries.")
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
        Uses the configured engine for the target language, with fallbacks.
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

        engine = cls._engine_for_lang(lang)
        if engine == "gtts":
            if cls._generate_gtts_mp3(clean_text, filepath, lang):
                log.info(f"[audio] Successfully synthesized audio using gTTS at {filepath}")
                return urlpath
            log.info("[audio] Falling back to espeak-ng for audio")
            if cls._generate_espeak_mp3(clean_text, filepath, lang):
                return urlpath
            return None

        if engine == "edge":
            if cls._generate_edge_mp3(clean_text, filepath, lang):
                log.info(f"[audio] Successfully synthesized audio using Edge TTS at {filepath}")
                return urlpath
            
            log.info(f"[audio] Edge TTS failed for {lang}, attempting high-quality fallback.")
            if lang == "sr":
                if cls._generate_gtts_mp3(clean_text, filepath, lang):
                    log.info(f"[audio] Successfully synthesized audio using gTTS (sr) at {filepath}")
                    return urlpath
            elif lang == "mk":
                # Set engine to omnivoice and continue to the OmniVoice section
                engine = "omnivoice"
            
            if engine != "omnivoice":
                log.info(f"[audio] No high-quality fallback for {lang}, using espeak-ng.")
                if cls._generate_espeak_mp3(clean_text, filepath, lang):
                    return urlpath
                return None

        if engine != "omnivoice":
            if cls._generate_espeak_mp3(clean_text, filepath, lang):
                log.info(f"[audio] Successfully synthesized audio using espeak-ng at {filepath}")
                return urlpath
            return None

        max_retries = 3
        retry_delay = 2.0  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                log.info(f"[audio] Attempting local OmniVoice speech synthesis for cluster (attempt {attempt}/{max_retries})...")
                import soundfile as sf

                # Use cached model instead of loading each time
                model = cls._get_omnivoice_model()
                if model is None:
                    log.error("[audio] Could not load OmniVoice model, aborting cluster audio generation")
                    return None
                
                cls._lower_process_priority()
                cls._enforce_rate_limit()
                
                instruct_desc = "female, young adult" if lang == "sr" or lang == "mk" else "male, young adult"
                
                # Process text in chunks to reduce memory usage and prevent CPU spikes
                audio = cls._coerce_audio_array(
                    cls._generate_audio_in_chunks(model, clean_text, instruct_desc, lang)
                )
                if audio.size == 0:
                    log.error("[audio] OmniVoice returned empty cluster audio array")
                    return None
                
                wav_path = filepath.replace(".mp3", ".wav")
                sf.write(wav_path, audio, 24000)
                
                # Compress to MP3 using ffmpeg with CPU-friendly settings
                try:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", wav_path,
                            "-codec:a", "libmp3lame",
                            "-qscale:a", "4",  # Lower quality = faster encoding
                            "-threads", "1",   # Limit to 1 thread to prevent CPU overload
                            "-loglevel", "quiet",  # Suppress output
                            filepath
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    log.info(f"[audio] Successfully synthesized cluster audio using local OmniVoice at {filepath}")
                    return urlpath
                finally:
                    # Cleanup WAV file in finally block to ensure it always gets removed
                    try:
                        if os.path.exists(wav_path):
                            os.remove(wav_path)
                            log.debug(f"[audio] Cleaned up temporary WAV file: {wav_path}")
                    except Exception as cleanup_e:
                        log.warning(f"[audio] Failed to cleanup WAV file {wav_path}: {cleanup_e}")
            except Exception as e:
                log.error(f"[audio] Local OmniVoice cluster speech synthesis attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    import time
                    log.info(f"[audio] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

        log.error("[audio] Failed to synthesize cluster audio since OmniVoice failed after all retries.")
        return None
