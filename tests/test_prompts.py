from core.prompts import (
    DAILY_BRIEF_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT_MK,
)


def test_synthesis_prompt_requires_angle_content_schema():
    assert "perspectives" in SYNTHESIS_SYSTEM_PROMPT
    assert "angle" in SYNTHESIS_SYSTEM_PROMPT
    assert "content" in SYNTHESIS_SYSTEM_PROMPT
    assert "verification_report" in SYNTHESIS_SYSTEM_PROMPT
    assert "Mora zvučati kao rad iskusnog urednika" in SYNTHESIS_SYSTEM_PROMPT
    assert "ZABRANJENE AI FRAZE" in SYNTHESIS_SYSTEM_PROMPT


def test_synthesis_prompt_requires_long_editorial_structure():
    assert "tačno 5 kratkih" in SYNTHESIS_SYSTEM_PROMPT
    assert "ŠTA SE DESILO" in SYNTHESIS_SYSTEM_PROMPT
    assert "ŠTA JE NEVERIFIKOVANO" in SYNTHESIS_SYSTEM_PROMPT
    assert "Dužinu gradi dodavanjem slojeva značenja" in SYNTHESIS_SYSTEM_PROMPT

    assert "точно 5 кратки" in SYNTHESIS_SYSTEM_PROMPT_MK
    assert "ШТО СЕ СЛУЧИ" in SYNTHESIS_SYSTEM_PROMPT_MK
    assert "ШТО Е НЕВЕРИФИКУВАНО" in SYNTHESIS_SYSTEM_PROMPT_MK


def test_summary_prompt_requires_plain_json_summary():
    assert '"summary"' in SUMMARY_SYSTEM_PROMPT
    assert "JSON" in SUMMARY_SYSTEM_PROMPT
    assert "emodžije" in SUMMARY_SYSTEM_PROMPT
    assert "hashtag" in SUMMARY_SYSTEM_PROMPT


def test_daily_brief_prompt_requires_editorial_sections():
    assert "## Velika Slika" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Ključne teme" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Medijski Radar" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Šta pratiti" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "[[id]]" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "3-5 konkretnih signala" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "Svaka rečenica mora dodati" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "Ne izmišljaj aktere" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "Prvo reci šta je potvrđeno" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "Zabranjene apstrakcije" in DAILY_BRIEF_SYSTEM_PROMPT
