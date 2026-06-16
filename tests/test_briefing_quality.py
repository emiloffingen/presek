"""Unit tests for extracted briefing quality gates."""

from tasks.delivery.briefing_quality import (
    _briefing_title_penalty,
    _has_valid_daily_brief_structure,
    _is_grounded_daily_brief,
    _is_high_quality_briefing,
)


def test_briefing_title_penalty_party_release():
    assert _briefing_title_penalty("VMRO-DPMNE: Vo ocajna potraga po dobra vest") > 3.0
    assert _briefing_title_penalty("Zemjotres od 4,8 stepeni me potrese Srbija") == 0.0


def test_mk_brief_structure_requires_sections():
    malformed = "## Gol\n\nNesto se desilo."
    valid = "## Golemata Slika\n\nTekst.\n\n## Kljucni temi\n\nTekst.\n\n## Mediumski Radar\n\nTekst."
    assert _has_valid_daily_brief_structure(malformed, lang="mk") is False
    assert _has_valid_daily_brief_structure(valid, lang="mk") is True


def test_grounded_brief_rejects_invented_entity():
    context = (
        "### klaster 1\n"
        "Naslov: Interpelacija na vladata\n"
        "Kratok kontekst: Opozicijata podnese interpelacija.\n"
    )
    brief = (
        "### 1. Interpelacijata\n"
        "- Sto e novoto: Premierot Dimitar Kovacevski me oceni kako neizdrzana.\n"
    )
    assert _is_grounded_daily_brief(brief, context) is False


def test_high_quality_briefing_rejects_vague_filler():
    brief = "\n".join(
        [
            "Vreme ce pokazati sta ce se desiti.",
            "Ostaje vazno da se prati razvoj.",
            "Vredi da se sledi situacija.",
            "Ostaje da se vidi kako ce se zavrsiti.",
        ]
    )
    assert _is_high_quality_briefing(brief) is False
