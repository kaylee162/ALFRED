from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    enabled: bool = True
    provider: str = "kokoro"
    repo_id: str = "hexgrad/Kokoro-82M"
    offline: bool = True
    warm_on_startup: bool = True
    voice_id: str = "bm_george"
    language_code: str = "b"
    speed: float = 0.96
    sample_rate: int = 24_000
    max_spoken_characters: int = 900
    cache_directory: Path = BACKEND_ROOT / "data" / "audio_cache"


VOICE_CONFIG = VoiceConfig(
    enabled=_env_bool("ALFRED_VOICE_ENABLED", True),
    provider=os.getenv("ALFRED_VOICE_PROVIDER", "kokoro").strip().casefold(),
    repo_id=os.getenv("ALFRED_VOICE_REPO_ID", "hexgrad/Kokoro-82M").strip() or "hexgrad/Kokoro-82M",
    offline=_env_bool("ALFRED_VOICE_OFFLINE", True),
    warm_on_startup=_env_bool("ALFRED_VOICE_WARM_STARTUP", True),
    voice_id=os.getenv("ALFRED_VOICE_ID", "bm_george").strip() or "bm_george",
    language_code=os.getenv("ALFRED_VOICE_LANGUAGE", "b").strip() or "b",
    speed=float(os.getenv("ALFRED_VOICE_SPEED", "0.96")),
    sample_rate=int(os.getenv("ALFRED_VOICE_SAMPLE_RATE", "24000")),
    max_spoken_characters=int(os.getenv("ALFRED_VOICE_MAX_CHARS", "900")),
    cache_directory=Path(
        os.getenv(
            "ALFRED_VOICE_CACHE_DIR",
            str(BACKEND_ROOT / "data" / "audio_cache"),
        )
    ),
)
