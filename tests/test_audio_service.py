import sys
import types


def test_auto_engine_uses_edge_for_sr_and_mk(monkeypatch):
    import core.audio_service as audio_service

    monkeypatch.setattr(audio_service, "_TTS_ENGINE", "auto")
    monkeypatch.setattr(audio_service, "_SR_TTS_ENGINE", "edge")
    monkeypatch.setattr(audio_service, "_MK_TTS_ENGINE", "edge")

    assert audio_service.AudioService._engine_for_lang("sr") == "edge"
    assert audio_service.AudioService._engine_for_lang("mk") == "edge"


def test_serbian_audio_paths_use_new_profile_without_changing_macedonian(monkeypatch, tmp_path):
    import core.audio_service as audio_service

    monkeypatch.setattr(audio_service, "_AUDIO_DIR", str(tmp_path))

    sr_path, sr_url = audio_service.AudioService.get_audio_path_and_url("2026-06-01", "sr")
    mk_path, mk_url = audio_service.AudioService.get_audio_path_and_url("2026-06-01", "mk")
    sr_cluster_path, sr_cluster_url = audio_service.AudioService.get_cluster_audio_path_and_url("abc123", "sr")
    mk_cluster_path, mk_cluster_url = audio_service.AudioService.get_cluster_audio_path_and_url("abc123", "mk")

    assert sr_path.endswith("briefing_2026-06-01_sr_v3.mp3")
    assert sr_url == "/static/uploads/audio/briefing_2026-06-01_sr_v3.mp3"
    assert mk_path.endswith("briefing_2026-06-01_mk.mp3")
    assert mk_url == "/static/uploads/audio/briefing_2026-06-01_mk.mp3"
    assert sr_cluster_path.endswith("cluster_abc123_sr_v3.mp3")
    assert sr_cluster_url == "/static/uploads/audio/cluster_abc123_sr_v3.mp3"
    assert mk_cluster_path.endswith("cluster_abc123_mk.mp3")
    assert mk_cluster_url == "/static/uploads/audio/cluster_abc123_mk.mp3"


def test_serbian_latin_to_cyrillic_uses_serbian_letters():
    import core.audio_service as audio_service

    result = audio_service.serbian_latin_to_cyrillic(
        "Danas: Đoković, Ljubiša, Njegoš, džez, Čačak, ćirilica, šuma, žito."
    )

    assert result == "Данас: Ђоковић, Љубиша, Његош, џез, Чачак, ћирилица, шума, жито."


def test_clean_briefing_text_joins_paragraphs_without_double_periods():
    import core.audio_service as audio_service

    cleaned = audio_service.clean_briefing_text_for_tts("Prvi pasus.\n\nDrugi pasus.")

    assert cleaned == "Prvi pasus. Drugi pasus."
    assert ". ." not in cleaned


def test_select_cluster_audio_text_uses_first_two_article_paragraphs():
    import core.audio_service as audio_service

    article = (
        "Lead vest sa dovoljno teksta da prođe prag za audio sintezu.\n"
        "Drugi pasus sa dodatnim kontekstom za slušaoce.\n"
        "Meta o izvorima i nepotvrđenim detaljima."
    )
    summary = "Kratak sažetak koji ne bi trebalo da se koristi."

    selected = audio_service.select_cluster_audio_text(article, summary)

    assert "Lead vest" in selected
    assert "Drugi pasus" in selected
    assert "Meta o izvorima" not in selected


def test_select_cluster_audio_text_falls_back_to_summary():
    import core.audio_service as audio_service

    selected = audio_service.select_cluster_audio_text("", "Sažetak prve vesti.\nDrugi deo.")

    assert selected == "Sažetak prve vesti.\nDrugi deo."


def test_serbian_edge_failure_falls_back_like_macedonian_without_gtts(monkeypatch, tmp_path):
    import core.audio_service as audio_service

    soundfile = types.ModuleType("soundfile")
    soundfile.def write(*args, **kwargs):
    return None
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)

    gtts_calls = []

    monkeypatch.setattr(audio_service, "_AUDIO_DIR", str(tmp_path))
    monkeypatch.setattr(audio_service, "_TTS_ENGINE", "auto")
    monkeypatch.setattr(audio_service, "_SR_TTS_ENGINE", "edge")
    monkeypatch.setattr(audio_service.AudioService, "_generate_edge_mp3", classmethod(lambda cls, *args: False))
    monkeypatch.setattr(
        audio_service.AudioService,
        "_generate_gtts_mp3",
        classmethod(lambda cls, *args: gtts_calls.append(args) or False),
    )
    monkeypatch.setattr(audio_service.AudioService, "_get_omnivoice_model", staticmethod(lambda: None))

    result = audio_service.AudioService.generate_briefing_audio("2026-06-01", "Danas je važna vest.", "sr")

    assert result is None
    assert gtts_calls == []
