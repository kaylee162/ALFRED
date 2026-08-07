from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import threading
from collections import OrderedDict
import time
from pathlib import Path
from typing import Any

from core.voice_config import VOICE_CONFIG

LOGGER = logging.getLogger(__name__)


class VoiceUnavailableError(RuntimeError):
    """Raised when the configured speech provider cannot be loaded."""


class VoiceService:
    def __init__(self) -> None:
        self._pipeline: Any | None = None
        self._pipeline_lock = threading.Lock()
        self._synthesis_lock = threading.Lock()
        self._cache_dir = Path(VOICE_CONFIG.cache_directory)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._warming = False
        self._ready = False
        self._last_error = ""
        self._load_seconds: float | None = None
        self._last_synthesis_seconds: float | None = None
        self._memory_cache: OrderedDict[str, bytes] = OrderedDict()

    def _configure_hugging_face(self) -> None:
        # Once the model has been downloaded, cache-only mode prevents a HEAD
        # request to huggingface.co on every ALFRED restart.
        if VOICE_CONFIG.offline:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    def _get_pipeline(self) -> Any:
        if not VOICE_CONFIG.enabled:
            raise VoiceUnavailableError("ALFRED voice is disabled by configuration.")
        if VOICE_CONFIG.provider != "kokoro":
            raise VoiceUnavailableError(
                f"Unsupported voice provider: {VOICE_CONFIG.provider}."
            )

        if self._pipeline is None:
            with self._pipeline_lock:
                if self._pipeline is None:
                    self._configure_hugging_face()
                    try:
                        import warnings

                        warnings.filterwarnings(
                            "ignore",
                            message="dropout option adds dropout",
                            category=UserWarning,
                        )

                        warnings.filterwarnings(
                            "ignore",
                            message=".*weight_norm.*deprecated.*",
                            category=FutureWarning,
                        )
                        from kokoro import KPipeline
                    except ImportError as exc:
                        raise VoiceUnavailableError(
                            "Kokoro is not installed in the backend virtual environment."
                        ) from exc

                    started = time.perf_counter()
                    try:
                        self._pipeline = KPipeline(
                            lang_code=VOICE_CONFIG.language_code,
                            repo_id=VOICE_CONFIG.repo_id,
                        )
                    except Exception as exc:
                        if VOICE_CONFIG.offline:
                            raise VoiceUnavailableError(
                                "Kokoro is in cache-only mode, but its model or selected "
                                "voice is not fully cached. Temporarily set "
                                "ALFRED_VOICE_OFFLINE=false, restart once, and test speech."
                            ) from exc
                        raise
                    finally:
                        self._load_seconds = time.perf_counter() - started

                    LOGGER.info(
                        "Kokoro pipeline loaded in %.2fs from %s (offline=%s)",
                        self._load_seconds,
                        VOICE_CONFIG.repo_id,
                        VOICE_CONFIG.offline,
                    )
        return self._pipeline

    @staticmethod
    def prepare_for_speech(text: str) -> str:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"[*_#>]", "", cleaned)
        cleaned = re.sub(r"https?://\S+", "the attached link", cleaned)

        replacements = {
            r"\bUI\b": "user interface",
            r"\bAPI\b": "A P I",
            r"\bGitHub\b": "Git Hub",
            r"\bVS\s?Code\b": "V S Code",
            r"\bOllama\b": "oh-lama",
            r"\bALFRED\b": "Alfred",
        }
        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        limit = max(100, VOICE_CONFIG.max_spoken_characters)
        if len(cleaned) > limit:
            shortened = cleaned[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
            cleaned = f"{shortened}. The remaining details are on screen."
        return cleaned

    @staticmethod
    def _cache_key(text: str) -> str:
        payload = "|".join(
            (
                VOICE_CONFIG.provider,
                VOICE_CONFIG.repo_id,
                VOICE_CONFIG.voice_id,
                str(VOICE_CONFIG.speed),
                str(VOICE_CONFIG.sample_rate),
                text,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _remember_audio(self, cache_key: str, audio_bytes: bytes) -> None:
        self._memory_cache[cache_key] = audio_bytes
        self._memory_cache.move_to_end(cache_key)
        while len(self._memory_cache) > max(1, VOICE_CONFIG.memory_cache_entries):
            self._memory_cache.popitem(last=False)

    def warm_up(self) -> None:
        """Load Kokoro and the configured voice before the first real reply."""
        if not VOICE_CONFIG.enabled or not VOICE_CONFIG.warm_on_startup:
            return
        if self._ready or self._warming:
            return

        self._warming = True
        self._last_error = ""
        try:
            # Calling synthesize performs one tiny inference, which also loads
            # bm_george.pt. This avoids making the user's first reply pay that cost.
            self.synthesize("Good evening, Kaylee. Alfred is ready.")
            self._ready = True
            LOGGER.info("ALFRED voice warm-up complete.")
        except Exception as exc:
            self._last_error = str(exc)
            LOGGER.exception("ALFRED voice warm-up failed")
        finally:
            self._warming = False

    def health(self) -> dict[str, object]:
        if not VOICE_CONFIG.enabled:
            return {
                "enabled": False,
                "available": False,
                "ready": False,
                "provider": VOICE_CONFIG.provider,
                "voice_id": VOICE_CONFIG.voice_id,
                "message": "Voice is disabled by configuration.",
            }
        return {
            "enabled": True,
            "available": not bool(self._last_error),
            "ready": self._ready,
            "warming": self._warming,
            "provider": VOICE_CONFIG.provider,
            "repo_id": VOICE_CONFIG.repo_id,
            "voice_id": VOICE_CONFIG.voice_id,
            "offline": VOICE_CONFIG.offline,
            "sample_rate": VOICE_CONFIG.sample_rate,
            "load_seconds": self._load_seconds,
            "last_synthesis_seconds": self._last_synthesis_seconds,
            "message": (
                self._last_error
                or ("Voice synthesis is ready." if self._ready else "Voice is loading.")
            ),
        }

    def synthesize(self, text: str) -> bytes:
        spoken_text = self.prepare_for_speech(text)
        if not spoken_text:
            raise ValueError("No speakable text was provided.")

        cache_key = self._cache_key(spoken_text)
        cached_bytes = self._memory_cache.get(cache_key)
        if cached_bytes is not None:
            self._memory_cache.move_to_end(cache_key)
            return cached_bytes

        cache_path = self._cache_dir / f"{cache_key}.wav"
        if cache_path.exists() and cache_path.stat().st_size > 44:
            audio_bytes = cache_path.read_bytes()
            self._remember_audio(cache_key, audio_bytes)
            return audio_bytes

        with self._synthesis_lock:
            cached_bytes = self._memory_cache.get(cache_key)
            if cached_bytes is not None:
                self._memory_cache.move_to_end(cache_key)
                return cached_bytes
            if cache_path.exists() and cache_path.stat().st_size > 44:
                audio_bytes = cache_path.read_bytes()
                self._remember_audio(cache_key, audio_bytes)
                return audio_bytes

            try:
                import numpy as np
                import soundfile as sf
            except ImportError as exc:
                raise VoiceUnavailableError(
                    "Voice dependencies numpy and soundfile are required."
                ) from exc

            synthesis_started = time.perf_counter()
            pipeline = self._get_pipeline()
            audio_parts = []
            for _, _, audio in pipeline(
                spoken_text,
                voice=VOICE_CONFIG.voice_id,
                speed=VOICE_CONFIG.speed,
            ):
                part = np.asarray(audio, dtype=np.float32).reshape(-1)
                if part.size:
                    audio_parts.append(part)

            if not audio_parts:
                raise RuntimeError("Kokoro produced no audio.")

            audio = np.concatenate(audio_parts)
            buffer = io.BytesIO()
            sf.write(buffer, audio, VOICE_CONFIG.sample_rate, format="WAV")
            audio_bytes = buffer.getvalue()
            if len(audio_bytes) <= 44:
                raise RuntimeError("Kokoro produced an invalid WAV file.")

            temporary_path = cache_path.with_suffix(".tmp")
            temporary_path.write_bytes(audio_bytes)
            temporary_path.replace(cache_path)
            self._last_synthesis_seconds = time.perf_counter() - synthesis_started
            self._remember_audio(cache_key, audio_bytes)
            self._ready = True
            LOGGER.info("Speech synthesized in %.2fs (%d characters)", self._last_synthesis_seconds, len(spoken_text))
            return audio_bytes


voice_service = VoiceService()
