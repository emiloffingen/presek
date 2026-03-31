"""Tests for AI engine API call functions with mocked HTTP requests."""
import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO


class TestCallGemini:
    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    def test_successful_call(self, mock_urlopen):
        from ai_engine import _call_gemini

        response_body = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Резиме на вестта."}]}}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _call_gemini("Test prompt", "System prompt")
        assert result == "Резиме на вестта."

    @patch('ai_engine.GOOGLE_API_KEY', '')
    def test_no_api_key(self):
        from ai_engine import _call_gemini
        result = _call_gemini("Test", "System")
        assert result is None

    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    def test_empty_candidates(self, mock_urlopen):
        from ai_engine import _call_gemini

        response_body = json.dumps({"candidates": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _call_gemini("Test", "System")
        assert result is None

    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    def test_network_error(self, mock_urlopen):
        from ai_engine import _call_gemini
        mock_urlopen.side_effect = Exception("Network error")
        result = _call_gemini("Test", "System")
        assert result is None

    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    @patch('ai_engine.time.sleep')  # Don't actually sleep in tests
    def test_429_retries(self, mock_sleep, mock_urlopen):
        import urllib.error
        from ai_engine import _call_gemini

        error_429 = urllib.error.HTTPError(
            url="http://test", code=429, msg="Too Many Requests",
            hdrs={}, fp=BytesIO(b"rate limited")
        )
        # First 3 calls fail with 429, fourth succeeds
        success_resp = MagicMock()
        success_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
        }).encode()
        success_resp.__enter__ = MagicMock(return_value=success_resp)
        success_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [error_429, error_429, success_resp]
        result = _call_gemini("Test", "System")
        assert result == "OK"


class TestCallOpenAICompatible:
    @patch('ai_engine.urllib.request.urlopen')
    def test_successful_call(self, mock_urlopen):
        from ai_engine import _call_openai_compatible

        response_body = json.dumps({
            "choices": [{"message": {"content": "OpenAI response text"}}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _call_openai_compatible("Test", "System", "key", "http://url", "model", "provider")
        assert result == "OpenAI response text"

    def test_no_key(self):
        from ai_engine import _call_openai_compatible
        result = _call_openai_compatible("Test", "System", "", "http://url", "model", "provider")
        assert result is None


class TestCallAI:
    @patch('ai_engine._call_openrouter')
    @patch('ai_engine._call_mistral')
    @patch('ai_engine._call_cerebras')
    @patch('ai_engine._call_groq')
    @patch('ai_engine._call_gemini')
    @patch('utils.redis_client')
    def test_gemini_first(self, mock_redis, mock_gemini, mock_groq, mock_cerebras, mock_mistral, mock_openrouter):
        from ai_engine import _call_ai
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_gemini.return_value = "Gemini result"

        result, tier = _call_ai("Test", "System")
        assert result == "Gemini result"
        assert tier == "gemini"

    @patch('ai_engine._call_openrouter')
    @patch('ai_engine._call_mistral')
    @patch('ai_engine._call_cerebras')
    @patch('ai_engine._call_groq')
    @patch('ai_engine._call_gemini')
    @patch('utils.redis_client')
    def test_fallback_to_groq(self, mock_redis, mock_gemini, mock_groq, mock_cerebras, mock_mistral, mock_openrouter):
        from ai_engine import _call_ai
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_gemini.return_value = None
        mock_groq.return_value = "Groq result"
        mock_cerebras.return_value = None
        mock_mistral.return_value = None
        mock_openrouter.return_value = None

        result, tier = _call_ai("Test", "System")
        assert result == "Groq result"
        assert tier == "groq"

    @patch('ai_engine._call_openrouter')
    @patch('ai_engine._call_mistral')
    @patch('ai_engine._call_cerebras')
    @patch('ai_engine._call_groq')
    @patch('ai_engine._call_gemini')
    @patch('utils.redis_client')
    def test_all_fail(self, mock_redis, mock_gemini, mock_groq, mock_cerebras, mock_mistral, mock_openrouter):
        from ai_engine import _call_ai
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_gemini.return_value = None
        mock_groq.return_value = None
        mock_cerebras.return_value = None
        mock_mistral.return_value = None
        mock_openrouter.return_value = None

        result, tier = _call_ai("Test", "System")
        assert result is None
        assert tier is None

    @patch('ai_engine._call_openrouter')
    @patch('ai_engine._call_mistral')
    @patch('ai_engine._call_cerebras')
    @patch('ai_engine._call_groq')
    @patch('ai_engine._call_gemini')
    @patch('utils.redis_client')
    def test_daily_limit_reached(self, mock_redis, mock_gemini, mock_groq, mock_cerebras, mock_mistral, mock_openrouter):
        from ai_engine import _call_ai
        from config import AI_DAILY_LIMIT
        mock_redis.incr.return_value = AI_DAILY_LIMIT + 1

        result, tier = _call_ai("Test", "System")
        assert result is None
        assert tier == "limit_reached"
        mock_gemini.assert_not_called()

    @patch('ai_engine._call_openrouter')
    @patch('ai_engine._call_mistral')
    @patch('ai_engine._call_cerebras')
    @patch('ai_engine._call_groq')
    @patch('ai_engine._call_gemini')
    @patch('utils.redis_client')
    def test_redis_error_continues(self, mock_redis, mock_gemini, mock_groq, mock_cerebras, mock_mistral, mock_openrouter):
        """If Redis fails during limit check, should still try AI providers."""
        from ai_engine import _call_ai
        mock_redis.incr.side_effect = Exception("Redis down")
        mock_gemini.return_value = "Works anyway"

        result, tier = _call_ai("Test", "System")
        assert result == "Works anyway"
        assert tier == "gemini"

    @patch('ai_engine._call_openrouter')
    @patch('ai_engine._call_mistral')
    @patch('ai_engine._call_cerebras')
    @patch('ai_engine._call_groq')
    @patch('ai_engine._call_gemini')
    @patch('utils.redis_client')
    def test_task_routing_uses_correct_chain(self, mock_redis, mock_gemini, mock_groq, mock_cerebras, mock_mistral, mock_openrouter):
        """Tagging task should try cerebras first, not gemini."""
        from ai_engine import _call_ai
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_cerebras.return_value = "Cerebras tagged"
        mock_gemini.return_value = None
        mock_groq.return_value = None

        result, tier = _call_ai("Test", "System", task_type="tagging")
        assert result == "Cerebras tagged"
        assert tier == "cerebras"


class TestTranslateToMacedonian:
    @patch('ai_engine._call_ai')
    def test_successful_translation(self, mock_call_ai):
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ("Преведен текст", "gemini")
        result = translate_to_macedonian("English text to translate")
        assert result == "Преведен текст"

    @patch('ai_engine._call_ai')
    def test_ai_returns_none(self, mock_call_ai):
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = (None, None)
        result = translate_to_macedonian("Text")
        assert result is None

    def test_empty_text(self):
        from ai_engine import translate_to_macedonian
        assert translate_to_macedonian("") == ""
        assert translate_to_macedonian(None) is None
        assert translate_to_macedonian("   ") == "   "

    @patch('ai_engine._call_ai')
    def test_json_response_unwrapped(self, mock_call_ai):
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ('{"summary": "Преведено"}', "gemini")
        result = translate_to_macedonian("Text")
        assert result == "Преведено"
