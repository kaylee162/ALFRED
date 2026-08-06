from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services.voice_service import VoiceUnavailableError, voice_service

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)


@router.get("/health")
async def voice_health() -> dict[str, object]:
    return await asyncio.to_thread(voice_service.health)


@router.post("/speak", response_class=Response)
async def speak(request: SpeechRequest) -> Response:
    try:
        audio = await asyncio.to_thread(voice_service.synthesize, request.text)
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": 'inline; filename="alfred-response.wav"',
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VoiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        LOGGER.exception("Voice synthesis failed")
        raise HTTPException(
            status_code=500,
            detail="ALFRED was unable to generate speech.",
        ) from exc
