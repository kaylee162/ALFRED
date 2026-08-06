from services.voice_service import VoiceService


def test_prepare_for_speech_removes_markdown_and_urls() -> None:
    spoken = VoiceService.prepare_for_speech(
        "**Done.** Open [GitHub](https://github.com/example) and `VSCode`."
    )
    assert "**" not in spoken
    assert "https://" not in spoken
    assert "Git Hub" in spoken
    assert "V S Code" in spoken


def test_prepare_for_speech_rejects_blank_text() -> None:
    assert VoiceService.prepare_for_speech("   ") == ""


def test_cache_key_is_deterministic() -> None:
    assert VoiceService._cache_key("Hello") == VoiceService._cache_key("Hello")
    assert VoiceService._cache_key("Hello") != VoiceService._cache_key("Goodbye")
