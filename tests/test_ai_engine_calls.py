"""Tests for AI engine API call functions with mocked HTTP requests."""
import asyncio
import pytest
import json
import sys
import types
from unittest.mock import patch, MagicMock
from io import BytesIO


class TestOpenAICompatibleProvider:
    @patch('httpx.Client.post')
    def test_successful_call(self, mock_post):
        from ai_engine import OpenAICompatibleProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI response text"}}]
        }
        mock_post.return_value = mock_resp

        provider = OpenAICompatibleProvider("test", "api-key", "http://test-url", "test-model")
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result == "OpenAI response text"

    def test_no_key_returns_none(self):
        from ai_engine import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider("test", "", "http://test-url", "test-model")
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None

    @patch('httpx.Client.post')
    def test_network_error(self, mock_post):
        import httpx
        from ai_engine import OpenAICompatibleProvider
        mock_post.side_effect = httpx.RequestError("Connection refused", request=MagicMock())
        provider = OpenAICompatibleProvider("test", "api-key", "http://test-url", "test-model")
        result = provider.call("Test", "System", max_tokens=200, json_mode=False)
        assert result is None


class TestCallAI:
    def _mock_providers(self, mistral=None, local=None):
        """Return the active PROVIDERS dict with mocked .call() results."""
        def make_provider(return_value):
            p = MagicMock()
            p.call.return_value = return_value
            return p

        return {
            "mistral":    make_provider(mistral),
            "local":      make_provider(local),
        }

    @patch('utils.redis_client')
    def test_default_uses_remote_before_local(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(mistral="Remote result", local="Local result")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Remote result"
        assert tier == "mistral"
        providers["mistral"].call.assert_called_once()
        providers["local"].call.assert_not_called()

    @patch('utils.redis_client')
    def test_all_fail_returns_none(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(local=None)

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
        providers = self._mock_providers(local="Local result")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Local result"
        assert tier == "local"
        providers["local"].call.assert_called_once()

    @patch('utils.redis_client')
    def test_redis_error_continues(self, mock_redis):
        """If Redis fails during limit check, should still try AI providers."""
        mock_redis.incr.side_effect = Exception("Redis down")
        providers = self._mock_providers(local="Works anyway")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Works anyway"
        assert tier == "local"

    @patch('utils.redis_client')
    def test_task_routing_translation_prefers_remote_before_local(self, mock_redis):
        """Translation should try remote providers before the local rewrite fallback."""
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(mistral="Translated", local="Local translated")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Text", "System", task_type="translation")
        assert result == "Translated"
        assert tier == "mistral"
        providers["local"].call.assert_not_called()

    @patch('utils.redis_client')
    def test_stream_falls_back_when_first_provider_yields_nothing(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True

        class EmptyStreamProvider:
            async def stream_call(self, prompt, system, max_tokens):
                if False:
                    yield ""

            def call(self, prompt, system, max_tokens, json_mode, topic=None):
                return None

        class LocalStreamProvider:
            async def stream_call(self, prompt, system, max_tokens):
                yield "локален"

            def call(self, prompt, system, max_tokens, json_mode, topic=None):
                return "локален"

        providers = {
            "mistral": EmptyStreamProvider(),
            "local": LocalStreamProvider(),
        }

        async def run_check():
            with patch.dict('ai_engine.PROVIDERS', providers), \
                 patch('ai_engine.redis_client', mock_redis):
                from ai_engine import _call_ai_async
                stream, provider = await _call_ai_async("Text", "System", stream=True, task_type="chat")
                chunks = [chunk async for chunk in stream]
            return provider, chunks

        provider, chunks = asyncio.run(run_check())
        assert provider == "local"
        assert chunks == ["локален"]


class TestLocalProvider:
    def test_translation_rewrites_common_english_news_terms(self):
        from ai_engine import LocalProvider
        provider = LocalProvider()
        result = provider.call(
            "Government announced new tariffs on Tuesday",
            "Translate this to Macedonian",
            max_tokens=120,
            json_mode=False,
        )
        assert "владата" in result.lower()
        assert "царини" in result.lower()
        assert "вторник" in result.lower()

    def test_summary_strips_summarize_prefix(self):
        from ai_engine import LocalProvider
        provider = LocalProvider()
        result = provider.call(
            "Summarize: Владата усвои пакет од 120 милиони евра. Опозицијата го критикува рокот за спроведување.",
            "Return a concise 2-sentence news summary in Macedonian.",
            max_tokens=120,
            json_mode=False,
        )
        assert "Summarize:" not in result
        assert "120 милиони евра" in result


class TestTranslateToMacedonian:
    @patch('ai_engine.record_runtime_event')
    @patch('nllb_translate.translate')
    @patch('config.LOCAL_TRANSLATION_ENABLED', True)
    def test_records_nllb_translation_path(self, mock_nllb_translate, mock_record_runtime_event):
        from ai_engine import translate_to_macedonian
        mock_nllb_translate.return_value = "Владата најави нов пакет мерки."

        translate_to_macedonian("Government announced a new package of measures.")

        mock_record_runtime_event.assert_any_call("translation_path", source_lang="en", mode="nllb")

    @patch('nllb_translate.translate')
    @patch('config.LOCAL_TRANSLATION_ENABLED', True)
    def test_prefers_nllb_when_it_returns_valid_macedonian(self, mock_nllb_translate):
        from ai_engine import translate_to_macedonian
        mock_nllb_translate.return_value = "Владата најави нов пакет мерки."

        result = translate_to_macedonian("Government announced a new package of measures.")

        assert "Владата" in result

    @patch('nllb_translate.translate')
    @patch('ai_engine._call_ai')
    @patch('config.LOCAL_TRANSLATION_ENABLED', True)
    def test_ignores_unchanged_nllb_output_and_uses_ai_translation(self, mock_call_ai, mock_nllb_translate):
        from ai_engine import translate_to_macedonian
        mock_nllb_translate.return_value = "Government announced a new package of measures."
        mock_call_ai.return_value = ('{"summary": "Владата најави нов пакет мерки."}', "mistral")

        result = translate_to_macedonian("Government announced a new package of measures.")

        assert "Владата" in result

    @patch('nllb_translate.translate')
    @patch('ai_engine._call_ai')
    def test_successful_translation(self, mock_call_ai, mock_nllb_translate):
        from ai_engine import translate_to_macedonian
        mock_nllb_translate.return_value = None
        mock_call_ai.return_value = ('{"summary": "Преведен текст"}', "mistral")
        result = translate_to_macedonian("English text to translate")
        assert result == "Преведен текст"

    @patch('nllb_translate.translate')
    @patch('ai_engine._call_ai')
    def test_ai_returns_none(self, mock_call_ai, mock_nllb_translate):
        from ai_engine import translate_to_macedonian
        mock_nllb_translate.side_effect = RuntimeError("nllb unavailable")
        mock_call_ai.return_value = (None, None)
        result = translate_to_macedonian("Text")
        assert result == "Text"

    def test_empty_text(self):
        from ai_engine import translate_to_macedonian
        assert translate_to_macedonian("") == ""
        assert translate_to_macedonian(None) is None
        assert translate_to_macedonian("   ") == "   "

    @patch('ai_engine._call_ai')
    def test_json_response_unwrapped(self, mock_call_ai):
        """If AI returns JSON with a 'summary' key, translation should unwrap it."""
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ('{"summary": "Преведено"}', "mistral")
        result = translate_to_macedonian("Text")
        assert result == "Преведено"

    @patch('nllb_translate.translate')
    @patch('ai_engine._call_ai')
    def test_ai_unchanged_text_falls_back_to_original_when_local_rewrite_cannot_translate(self, mock_call_ai, mock_nllb_translate):
        from ai_engine import translate_to_macedonian
        mock_nllb_translate.return_value = "Qxzv blorf snth"
        mock_call_ai.return_value = ("Qxzv blorf snth", "mistral")

        result = translate_to_macedonian("Qxzv blorf snth")

        assert result == "Qxzv blorf snth"

    @patch('ai_engine.log')
    @patch('ai_engine._call_ai')
    def test_translation_error_logs_and_falls_back_to_original(self, mock_call_ai, mock_log):
        from ai_engine import translate_to_macedonian
        mock_call_ai.side_effect = RuntimeError("provider down")
        result = translate_to_macedonian("Text")
        assert result == "Text"
        mock_log.warning.assert_called()


class TestGenerateCoverArt:
    @patch('ai_engine.log')
    def test_generates_local_placeholder_art(self, mock_log):
        from ai_engine import generate_cover_art

        mock_db = MagicMock()
        mock_db.execute_one.return_value = {"category": "Вести"}

        with patch('ai_engine.POLLINATIONS_API_KEY', None), \
             patch('local_nlp.generate_local_placeholder', return_value="<svg />"), \
             patch('os.makedirs'), \
             patch('database.db_manager', mock_db), \
             patch('builtins.open', MagicMock()):
            result = generate_cover_art("abc123", "Title")

        assert result == "/static/generated/abc123.svg"
        mock_log.warning.assert_not_called()


class TestAutoSummarizeTopClusters:
    @patch("utils.get_source_health_map", return_value={})
    def test_refreshes_cluster_when_existing_synthesis_is_stale(self, _mock_health):
        import ai_engine
        import datetime

        now = datetime.datetime.now()
        rows = [
            {
                "id": 1,
                "cluster_id": "cluster1",
                "source": "MIA",
                "title": "Владата најави пакет од 100 милиони",
                "description": "Прв извештај.",
                "created_at": now - datetime.timedelta(hours=2, minutes=30),
                "summary": "Постоечко резиме",
            },
            {
                "id": 2,
                "cluster_id": "cluster1",
                "source": "Reuters",
                "title": "Reuters пишува за 120 милиони и нов рок",
                "description": "Нов извор и различна бројка.",
                "created_at": now - datetime.timedelta(minutes=20),
                "summary": "",
            },
        ]

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            rows,
            [{"cluster_id": "cluster1", "created_at": now - datetime.timedelta(hours=2)}],
        ]
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        summarize_delay = MagicMock()
        synthesize_delay = MagicMock()
        fake_tasks = types.SimpleNamespace(
            summarize_article_task=types.SimpleNamespace(delay=summarize_delay),
            synthesize_cluster_task=types.SimpleNamespace(delay=synthesize_delay),
        )

        with patch("database.db_manager", mock_db), \
             patch("utils.redis_client", mock_redis), \
             patch.dict(sys.modules, {"tasks": fake_tasks}), \
             patch("config.AUTO_SUMMARIZE_TOP_N", 5), \
             patch("config.AUTO_SUMMARIZE_MIN_SRC", 2):
            ai_engine.auto_summarize_top_clusters()

        synthesize_delay.assert_called_once()

    @patch("utils.get_source_health_map", return_value={})
    def test_does_not_refresh_minor_recent_followup(self, _mock_health):
        import ai_engine
        import datetime

        now = datetime.datetime.now()
        rows = [
            {
                "id": 1,
                "cluster_id": "cluster2",
                "source": "MIA",
                "title": "Трамп најави царини",
                "description": "Прв извештај.",
                "created_at": now - datetime.timedelta(minutes=18),
                "summary": "Постоечко резиме",
            },
            {
                "id": 2,
                "cluster_id": "cluster2",
                "source": "MIA",
                "title": "Трамп најави царини за увоз",
                "description": "Мало дополнување.",
                "created_at": now - datetime.timedelta(minutes=5),
                "summary": "",
            },
        ]

        mock_db = MagicMock()
        mock_db.execute.side_effect = [
            rows,
            [{"cluster_id": "cluster2", "created_at": now - datetime.timedelta(minutes=10)}],
        ]
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        summarize_delay = MagicMock()
        synthesize_delay = MagicMock()
        fake_tasks = types.SimpleNamespace(
            summarize_article_task=types.SimpleNamespace(delay=summarize_delay),
            synthesize_cluster_task=types.SimpleNamespace(delay=synthesize_delay),
        )

        with patch("database.db_manager", mock_db), \
             patch("utils.redis_client", mock_redis), \
             patch.dict(sys.modules, {"tasks": fake_tasks}), \
             patch("config.AUTO_SUMMARIZE_TOP_N", 5), \
             patch("config.AUTO_SUMMARIZE_MIN_SRC", 2):
            ai_engine.auto_summarize_top_clusters()

        synthesize_delay.assert_not_called()
