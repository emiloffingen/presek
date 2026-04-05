from prompts import SYNTHESIS_SYSTEM_PROMPT
from prompts import SUMMARY_SYSTEM_PROMPT
from prompts import DAILY_BRIEF_SYSTEM_PROMPT


def test_synthesis_prompt_requires_angle_content_schema():
    assert '"summary"' in SYNTHESIS_SYSTEM_PROMPT
    assert '"perspectives"' in SYNTHESIS_SYSTEM_PROMPT
    assert '"angle"' in SYNTHESIS_SYSTEM_PROMPT
    assert '"content"' in SYNTHESIS_SYSTEM_PROMPT
    assert '"label"' not in SYNTHESIS_SYSTEM_PROMPT
    assert '"text"' not in SYNTHESIS_SYSTEM_PROMPT


def test_summary_prompt_requires_plain_json_summary():
    assert '"summary"' in SUMMARY_SYSTEM_PROMPT
    assert 'JSON' in SUMMARY_SYSTEM_PROMPT
    assert 'емоџи' in SUMMARY_SYSTEM_PROMPT
    assert 'hashtag' in SUMMARY_SYSTEM_PROMPT


def test_daily_brief_prompt_requires_editorial_sections():
    assert "## Што го движи денот" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Каде се разликува известувањето" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Што да се следи понатаму" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "### 1." in DAILY_BRIEF_SYSTEM_PROMPT
    assert "- Што е новото:" in DAILY_BRIEF_SYSTEM_PROMPT
