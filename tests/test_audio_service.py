"""Regression tests for the Edge TTS briefing service.

The important invariant: edge-tts does NOT accept raw SSML. Its Communicate()
escapes the input and wraps it in its own <speak>/<prosody>, so any markup we
pass is read aloud literally (garbled, heavily padded audio). These tests fail
if that regresses.
"""

from unittest.mock import MagicMock, patch

import core.audio_service as audio


def test_join_for_speech_contains_no_ssml_markup():
    text = "Владата донесе одлука. Министерот изјави дека е усвоена!"
    out = audio._join_for_speech(text)
    assert "<" not in out and ">" not in out
    assert "<break" not in out and "<prosody" not in out and "speak" not in out


def test_join_for_speech_adds_terminal_punctuation_per_sentence():
    # Headlines frequently arrive without trailing punctuation.
    out = audio._join_for_speech("Прва вест\nВтора вест. Трета вест")
    assert out == "Прва вест. Втора вест. Трета вест."


def test_normalize_for_speech_expands_units_and_groups_big_numbers():
    out = audio._normalize_for_speech("Инвестициите се 1234567 евра, раст од 25%.")
    assert "1234567" not in out
    assert "1 234 567" in out
    assert "проценти" in out
    assert "евра" in out


def test_normalize_for_speech_reads_scorelines_as_words():
    assert audio._normalize_for_speech("Швајцарија со 3-0 над Македонија") == (
        "Швајцарија со 3 спрема 0 над Македонија"
    )
    assert "3 спрема 2" in audio._normalize_for_speech("заврши 3:2 на Вембли")
    # A dash inside non-score text must survive.
    assert "спрема" not in audio._normalize_for_speech("2024-2026 година")


def test_normalize_for_speech_respects_abbreviations():
    assert "С.А.Д." in audio._normalize_for_speech("договор меѓу САД и Кина")
    assert "Е.У." in audio._normalize_for_speech("раст во ЕУ")
    # Acronyms pronounced as words are left intact.
    assert "НАТО" in audio._normalize_for_speech("членка на НАТО")
    # No partial-word corruption.
    assert "ЕУРОПА" in audio._normalize_for_speech("ЕУРОПА")


def test_synthesize_async_never_passes_markup_to_edge_tts():
    captured = {}

    class FakeCommunicate:
        def __init__(self, text, voice, **kwargs):
            captured["text"] = text
            captured["voice"] = voice
            captured["kwargs"] = kwargs

        async def save(self, path):
            captured["path"] = path

    fake_module = MagicMock()
    fake_module.Communicate = FakeCommunicate

    with patch.dict("sys.modules", {"edge_tts": fake_module}):
        import asyncio

        asyncio.run(
            audio._synthesize_async("Plain narration.", "mk-MK-MarijaNeural", "/tmp/x.mp3", "-8%", "-2Hz", "+0%")
        )

    assert "<" not in captured["text"] and ">" not in captured["text"]
    assert captured["kwargs"] == {"rate": "-8%", "pitch": "-2Hz", "volume": "+0%"}
    assert captured["kwargs"].get("rate", "").startswith("-")


def test_prosody_helpers_return_edge_tts_values_not_markup():
    for lang in ("mk", "sr"):
        assert not audio._rate_for_lang(lang).startswith("<")
        assert audio._rate_for_lang(lang).endswith("%")
        assert audio._pitch_for_lang(lang).endswith("Hz")
        assert audio._volume_for_lang(lang).endswith("%")


def test_generate_cluster_audio_passes_plain_text(monkeypatch, tmp_path):
    monkeypatch.setenv("STATIC_ROOT", str(tmp_path))
    seen = {}

    def fake_synth(text, voice, path, rate="-8%", pitch="-2Hz", volume="+0%"):
        seen["text"] = text
        with open(path, "wb") as fh:
            fh.write(b"\x00" * 4096)

    async def fake_synth_async(*args, **kwargs):
        fake_synth(*args, **kwargs)

    monkeypatch.setattr(audio, "_synthesize_async", fake_synth_async)

    url = audio.AudioService.generate_cluster_audio(
        "cluster123", "Прва реченица. Втора реченица со 30% раст.", "mk"
    )

    assert url and url.endswith(".mp3")
    assert "<" not in seen["text"] and ">" not in seen["text"]
    assert "проценти" in seen["text"]
