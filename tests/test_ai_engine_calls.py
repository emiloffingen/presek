"""Tests for AI engine API call functions with mocked HTTP requests."""
import asyncio
import pytest
import json
import sys
import types
from unittest.mock import patch, MagicMock


class TestCallAI:
    def _mock_providers(self, nvidia=None, gemini=None, local=None):
        """Return the active PROVIDERS dict with mocked .call() results."""
        def make_provider(return_value):
            p = MagicMock()
            p.call.return_value = return_value
            return p

        return {
            "nvidia":     make_provider(nvidia),
            "gemini":     make_provider(gemini),
            "local":      make_provider(local),
        }

    @patch('utils.redis_client')
    def test_default_uses_local_before_remote(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(nvidia="Remote result", local="Local result")

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result == "Local result"
        assert tier == "local"
        providers["local"].call.assert_called_once()
        providers["nvidia"].call.assert_not_called()

    @patch('utils.redis_client')
    def test_all_fail_returns_none(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        providers = self._mock_providers(local=None, nvidia=None, gemini=None)

        with patch.dict('ai_engine.PROVIDERS', providers), \
             patch('ai_engine.redis_client', mock_redis):
            from ai_engine import _call_ai
            result, tier = _call_ai("Test", "System")
        assert result in (None, "")
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
    def test_stream_falls_back_when_first_provider_yields_nothing(self, mock_redis):
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True

        class EmptyStreamProvider:
            async def stream_call(self, prompt, system, max_tokens):
                if False:
                    yield ""

            def call(self, prompt, system, max_tokens, json_mode, topic=None, task_type="default"):
                return None

        class LocalStreamProvider:
            async def stream_call(self, prompt, system, max_tokens):
                yield "локален"

            def call(self, prompt, system, max_tokens, json_mode, topic=None, task_type="default"):
                return "локален"

        providers = {
            "nvidia": EmptyStreamProvider(),
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
        from unittest.mock import patch
        provider = LocalProvider()
        with patch("local_analyst.analyst.analyze") as mock_analyze:
            mock_analyze.return_value = "Владата најави нови царини во вторник"
            result = provider.call(
                "Government announced new tariffs on Tuesday",
                "Translate this to Macedonian",
                max_tokens=120,
                json_mode=False,
            )
        assert any(term in result.lower() for term in ("владата", "претседателството", "најави"))
        assert any(term in result.lower() for term in ("царини", "даноци", "тарифи"))
        assert "вторник" in result.lower()

    def test_summary_strips_summarize_prefix(self):
        from ai_engine import LocalProvider
        from unittest.mock import patch
        provider = LocalProvider()
        with patch("local_analyst.analyst.analyze") as mock_analyze:
            mock_analyze.return_value = "Владата усвои пакет од 120 милиони евра."
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
    @patch('ai_engine._call_ai')
    def test_records_ai_translation_path(self, mock_call_ai, mock_record_runtime_event):
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ('{"summary": "Владата најави нов пакет мерки."}', "nvidia")

        translate_to_macedonian("Government announced a new package of measures.")

        mock_record_runtime_event.assert_any_call("translation_path", source_lang="en", mode="ai", provider="nvidia")

    @patch('ai_engine._call_ai')
    def test_successful_translation_via_ai(self, mock_call_ai):
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ('{"summary": "Преведен текст"}', "nvidia")
        result = translate_to_macedonian("English text to translate")
        assert result == "Преведен текст"

    @patch('ai_engine._call_ai')
    def test_ai_returns_none_falls_back_to_original(self, mock_call_ai):
        from ai_engine import translate_to_macedonian
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
        mock_call_ai.return_value = ('{"summary": "Преведено"}', "nvidia")
        result = translate_to_macedonian("Text")
        assert result == "Преведено"

    @patch('ai_engine._call_ai')
    def test_ai_unchanged_text_falls_back_to_original_when_local_rewrite_cannot_translate(self, mock_call_ai):
        from ai_engine import translate_to_macedonian
        mock_call_ai.return_value = ("Qxzv blorf snth", "nvidia")

        result = translate_to_macedonian("Qxzv blorf snth")

        # It stays the same because it's already "normalized" or can't be translated better
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
             patch('nlp.generate_local_placeholder', return_value="<svg />"), \
             patch('os.makedirs'), \
             patch('database.db_manager', mock_db), \
             patch('builtins.open', MagicMock()):
            result = generate_cover_art("abc123", "Title")

        assert result == "/static/generated/abc123.svg"
        mock_log.warning.assert_not_called()

    def test_pollinations_429_sets_cooldown_and_falls_back(self):
        from ai_engine import generate_cover_art
        import httpx

        mock_db = MagicMock()
        mock_db.execute_one.return_value = {"category": "Вести"}
        mock_redis = MagicMock()
        request = MagicMock()
        response = MagicMock()
        response.status_code = 429

        client = MagicMock()
        client.__enter__.return_value = client
        client.get.side_effect = httpx.HTTPStatusError("rate limited", request=request, response=response)

        with patch('ai_engine.POLLINATIONS_API_KEY', "enabled"), \
             patch('ai_engine.redis_client', mock_redis), \
             patch('ai_engine.httpx.Client', return_value=client), \
             patch('nlp.generate_local_placeholder', return_value="<svg />"), \
             patch('os.makedirs'), \
             patch('database.db_manager', mock_db), \
             patch('builtins.open', MagicMock()):
            result = generate_cover_art("abc123", "Title")

        assert result == "/static/generated/abc123.svg"
        mock_redis.setex.assert_called_once_with("ai:cover_art:pollinations:cooldown", 1800, "1")


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
            synthesize_cluster_task=types.SimpleNamespace(delay=synthesize_delay, apply_async=MagicMock()),
        )

        with patch("database.db_manager", mock_db), \
             patch("utils.redis_client", mock_redis), \
             patch.dict(sys.modules, {"tasks": fake_tasks}), \
             patch("config.AUTO_SUMMARIZE_TOP_N", 5), \
             patch("config.AUTO_SUMMARIZE_MIN_SRC", 2):
            ai_engine.auto_summarize_top_clusters()

        fake_tasks.synthesize_cluster_task.delay.assert_called()

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
            synthesize_cluster_task=types.SimpleNamespace(delay=synthesize_delay, apply_async=MagicMock()),
        )

        with patch("database.db_manager", mock_db), \
             patch("utils.redis_client", mock_redis), \
             patch.dict(sys.modules, {"tasks": fake_tasks}), \
             patch("config.AUTO_SUMMARIZE_TOP_N", 5), \
             patch("config.AUTO_SUMMARIZE_MIN_SRC", 2):
            ai_engine.auto_summarize_top_clusters()

        fake_tasks.synthesize_cluster_task.apply_async.assert_not_called()
        synthesize_delay.assert_not_called()
