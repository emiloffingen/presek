import pytest
from prompts import (
    SUMMARY_SYSTEM_PROMPT, SYNTHESIS_SYSTEM_PROMPT, 
    DAILY_BRIEF_SYSTEM_PROMPT
)

def test_synthesis_prompt_requires_angle_content_schema():
    assert 'perspectives' in SYNTHESIS_SYSTEM_PROMPT
    assert 'angle' in SYNTHESIS_SYSTEM_PROMPT
    assert 'content' in SYNTHESIS_SYSTEM_PROMPT
    assert 'verification_report' in SYNTHESIS_SYSTEM_PROMPT

def test_summary_prompt_requires_plain_json_summary():
    assert '\"summary\"' in SUMMARY_SYSTEM_PROMPT
    assert 'JSON' in SUMMARY_SYSTEM_PROMPT
    assert 'емоџи' in SUMMARY_SYSTEM_PROMPT
    assert 'hashtag' in SUMMARY_SYSTEM_PROMPT

def test_daily_brief_prompt_requires_editorial_sections():
    assert "## Големата Слика" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Глобални и Локални Оски" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Медиумски Радар" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "## Што да се следи" in DAILY_BRIEF_SYSTEM_PROMPT
    assert "[[id]]" in DAILY_BRIEF_SYSTEM_PROMPT
