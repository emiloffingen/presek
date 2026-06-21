import pytest

from core.limits import briefing_remote_provider, resolve_briefing_ai_providers


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("nvidia", "nvidia"),
        ("local", "local"),
        ("gemini", "gemini"),
        ("", None),
        ("none", None),
        ("default", None),
    ],
)
def test_briefing_remote_provider(monkeypatch, env_value, expected):
    monkeypatch.setenv("BRIEFING_REMOTE_PROVIDER", env_value)
    assert briefing_remote_provider() == expected


@pytest.mark.parametrize(
    ("env_value", "task_override", "expected_provider", "expected_exclusions"),
    [
        ("nvidia", None, "nvidia", ["local"]),
        ("local", None, "local", ["nvidia", "gemini"]),
        ("", None, None, None),
        ("nvidia", "local", "local", ["nvidia", "gemini"]),
        ("gemini", None, "gemini", ["local"]),
        ("nvidia", "gemini", "gemini", ["local"]),
    ],
)
def test_resolve_briefing_ai_providers(
    monkeypatch, env_value, task_override, expected_provider, expected_exclusions
):
    monkeypatch.setenv("BRIEFING_REMOTE_PROVIDER", env_value)
    provider, exclusions = resolve_briefing_ai_providers(task_override)
    assert provider == expected_provider
    assert exclusions == expected_exclusions
