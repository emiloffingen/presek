from prompts import SYNTHESIS_SYSTEM_PROMPT
from prompts import SUMMARY_SYSTEM_PROMPT


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
