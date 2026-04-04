"""Tests for AI engine API call functions with mocked HTTP requests."""
import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO


class TestGeminiProvider:
    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    def test_successful_call(self, mock_urlopen):
        from ai_engine import GeminiProvider

        response_body = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Резиме на вестта."}]}}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = GeminiProvider()
        result = provider.call("Test prompt", "System prompt", max_tokens=200, json_mode=False)
        assert result == "Резиме на вестта."

    @patch('ai_engine.GOOGLE_API_KEY', '')
    def test_no_api_key(self):
        from ai_engine import GeminiProvider
        provider = GeminiProvider()
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None

    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    def test_empty_candidates(self, mock_urlopen):
        from ai_engine import GeminiProvider

        response_body = json.dumps({"candidates": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = GeminiProvider()
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None

    @patch('ai_engine.GOOGLE_API_KEY', 'test-key')
    @patch('ai_engine.urllib.request.urlopen')
    def test_network_error(self, mock_urlopen):
        from ai_engine import GeminiProvider
        mock_urlopen.side_effect = Exception("Network error")
        provider = GeminiProvider()
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None


class TestOpenAICompatibleProvider:
    @patch('ai_engine.urllib.request.urlopen')
    def test_successful_call(self, mock_urlopen):
        from ai_engine import OpenAICompatibleProvider

        response_body = json.dumps({
            "choices": [{"message": {"content": "OpenAI response text"}}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = OpenAICompatibleProvider("test", "api-key", "http://test-url", "test-model")
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result == "OpenAI response text"

    def test_no_key_returns_none(self):
        from ai_engine import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider("test", "", "http://test-url", "test-model")
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None

    @patch('ai_engine.urllib.request.urlopen')
    def test_network_error(self, mock_urlopen):
        from ai_engine import OpenAICompatibleProvider
        mock_urlopen.side_effect = Exception("Connection refused")
        provider = OpenAICompatibleProvider("test", "api-key", "http://test-url", "test-model")
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None


class TestCallAI:
    def _mock_providers(self, gemini=None, groq=None, cerebras=None, mistral=None, openrouter=None, local=None):
        """Return a PROVIDERS dict with mocked .call() results."""
        def make_provider(return_value):
            p = MagicMock()
            p.call.return_value = return_value
            return p

        return {
            "gemini":     make_provider(gemini),
            "groq":       make_provider(groq),
            "cerebras":   make_provider(cerebras),
            "mistral":    make_provider(mistral),
            "openrouter": make_provider(openrouter),
            "local":      make_provider(local),
        }

    @patch('utils.redis_client')
    def test_gemini_first(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(gemini="Gemini result")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Gemini result"
        assert tier == "gemini"

    @patch('utils.redis_client')
    def test_fallback_to_groq(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(gemini=None, groq="Groq result")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Groq result"
        assert tier == "groq"

    @patch('utils.redis_client')
    def test_all_fail_returns_none(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers()  # all None

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result is None
        assert tier is None

    @patch('utils.redis_client')
    def test_daily_limit_reached(self, mock_redis):
        from config import AI_DAILY_LIMIT
        mock_redis.incr.return_value = AI_DAILY_LIMIT + 1
        providers = self._mock_providers(gemini="Should not be called")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result is None
        assert tier == "limit_reached"
        providers["gemini"].call.assert_not_called()

    @patch('utils.redis_client')
    def test_redis_error_continues(self, mock_redis):
        """If Redis fails during limit check, should still try AI providers."""
        mock_redis.incr.side_effect = Exception("Redis down")
        providers = self._mock_providers(gemini="Works anyway")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Works anyway"
        assert tier == "gemini"

    @patch('utils.redis_client')
    def test_task_routing_translation(self, mock_redis):
        """Translation task uses translation chain (gemini first)."""
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(gemini="Translated")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Text", "System", task_type="translation")
        assert result == "Translated"
        assert tier == "gemini"


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
        """If AI returns JSON with a 'summary' key, translation should unwrap it."""
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ('{"summary": "Преведено"}', "gemini")
        result = translate_to_macedonian("Text")
        assert result == "Преведено"
