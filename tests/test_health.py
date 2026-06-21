import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.health import (
    _REDIS_KEY,
    _SOURCE_POLICY_REDIS_KEY,
    _SOURCE_REDIS_KEY,
    _TASK_REDIS_KEY,
    _freshness_payload,
    _probe_database,
    _probe_redis,
    _source_quality_payload,
    load_last_refresh_time,
    record_refresh,
    record_source_fetch,
    record_task_event,
    reset_source_policy,
    update_source_policy,
)


class TestRecordRefresh:
    def _make_redis(self):
        store = {}
        r = MagicMock()
        r.set.side_effect = lambda k, v, **kw: store.update({k: v})
        r.get.side_effect = lambda k: store.get(k)
        hash_store = {}
        r.hset.side_effect = lambda k, field, value: hash_store.setdefault(k, {}).update({field: value})
        r.hgetall.side_effect = lambda k: hash_store.get(k, {})
        r.hget.side_effect = lambda k, field: hash_store.get(k, {}).get(field)
        r.hdel.side_effect = lambda k, field: hash_store.get(k, {}).pop(field, None)
        r.expire.side_effect = lambda *args, **kwargs: True
        r._hash_store = hash_store
        return r, store

    def test_record_refresh_stores_data(self):
        r, store = self._make_redis()
        with patch("core.health._get_redis", return_value=r):
            record_refresh(42, ["error1"])
        data = json.loads(store[_REDIS_KEY])
        assert data["count"] == 42
        assert data["errors"] == ["error1"]
        assert data["time"] is not None

    def test_record_refresh_no_errors(self):
        r, store = self._make_redis()
        with patch("core.health._get_redis", return_value=r):
            record_refresh(10)
        data = json.loads(store[_REDIS_KEY])
        assert data["count"] == 10
        assert data["errors"] == []

    def test_record_refresh_overwrites(self):
        r, store = self._make_redis()
        with patch("core.health._get_redis", return_value=r):
            record_refresh(5)
            record_refresh(15, ["e"])
        data = json.loads(store[_REDIS_KEY])
        assert data["count"] == 15


class TestTaskEvents:
    def test_record_task_event_stores_payload(self):
        r, _store = TestRecordRefresh()._make_redis()
        with patch("core.health._get_redis", return_value=r):
            record_task_event("daily_brief", "fallback", "date:current")
        raw = r._hash_store[_TASK_REDIS_KEY]["daily_brief"]
        data = json.loads(raw)
        assert data["task"] == "daily_brief"
        assert data["status"] == "fallback"
        assert data["detail"] == "date:current"


class TestSourceEvents:
    def test_record_source_fetch_stores_payload(self):
        r, _store = TestRecordRefresh()._make_redis()
        with patch("core.health._get_redis", return_value=r):
            record_source_fetch("MIA", "ok", fetched=10, accepted=4)
        raw = r._hash_store[_SOURCE_REDIS_KEY]["MIA"]
        data = json.loads(raw)
        assert data["source"] == "MIA"
        assert data["status"] == "ok"
        assert data["fetched"] == 10
        assert data["accepted"] == 4
        assert "quality_score" in data
        assert "auto_flagged" in data


class TestSourceQuality:
    def test_source_quality_payload_for_healthy_source(self):
        data = _source_quality_payload("ok", 10, 8)
        assert data["quality_score"] >= 0.85
        assert data["degraded"] is False

    def test_source_quality_payload_for_broken_source(self):
        data = _source_quality_payload("error", 10, 0, error="timeout")
        assert data["quality_score"] < 0.6
        assert data["degraded"] is True


class TestSourcePolicy:
    def test_source_policy_flags_low_acceptance(self):
        r, _store = TestRecordRefresh()._make_redis()
        with patch("core.health._get_redis", return_value=r):
            state = None
            for _ in range(3):
                state = update_source_policy("Feed", "warning", fetched=10, accepted=1)
        assert state["auto_flagged"] is True
        assert state["should_auto_pause"] is False

    def test_source_policy_auto_pauses_after_repeated_errors(self):
        r, _store = TestRecordRefresh()._make_redis()
        with patch("core.health._get_redis", return_value=r):
            state = None
            for _ in range(3):
                state = update_source_policy("Feed", "error", fetched=0, accepted=0)
        assert state["should_auto_pause"] is True

    def test_reset_source_policy_clears_state(self):
        r, _store = TestRecordRefresh()._make_redis()
        with patch("core.health._get_redis", return_value=r):
            update_source_policy("Feed", "error", fetched=0, accepted=0)
            assert "Feed" in r._hash_store[_SOURCE_POLICY_REDIS_KEY]
            reset_source_policy("Feed")
        assert "Feed" not in r._hash_store[_SOURCE_POLICY_REDIS_KEY]


class TestFreshnessPayload:
    def test_freshness_payload_recent(self):
        recent = "2026-04-04T22:00:00+00:00"
        with patch("core.health.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 4, 4, 22, 10, tzinfo=timezone.utc)
            mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
            result = _freshness_payload(recent)
        assert result["status"] == "fresh"

    def test_freshness_payload_stale(self):
        stale = "2026-04-04T20:00:00+00:00"
        with patch("core.health.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 4, 4, 22, 0, tzinfo=timezone.utc)
            mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
            result = _freshness_payload(stale)
        assert result["status"] == "stale"


class TestLoadLastRefreshTime:
    def test_load_last_refresh_time_prefers_redis(self):
        r, store = TestRecordRefresh()._make_redis()
        store[_REDIS_KEY] = json.dumps({"time": "2026-06-13T12:00:00+00:00"})
        with (
            patch("core.health._get_redis", return_value=r),
            patch("core.health.database.db_manager.execute_one") as db_one,
        ):
            assert load_last_refresh_time() == "2026-06-13T12:00:00+00:00"
            db_one.assert_not_called()

    def test_load_last_refresh_time_falls_back_to_database(self):
        r, _store = TestRecordRefresh()._make_redis()
        with (
            patch("core.health._get_redis", return_value=r),
            patch(
                "core.health.database.db_manager.execute_one",
                return_value={"latest_at": datetime(2026, 6, 13, 11, 30, tzinfo=timezone.utc)},
            ),
        ):
            assert load_last_refresh_time() == "2026-06-13T11:30:00+00:00"


class TestHealthProbes:
    def test_probe_database_stays_ok_when_size_lookup_fails(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [12]
        mock_conn.execute.return_value = mock_cursor
        with (
            patch("core.health.database.get_db", return_value=mock_conn),
            patch(
                "core.health.database.get_db_size",
                side_effect=RuntimeError("permission denied"),
            ),
        ):
            result = _probe_database()
        assert result["ok"] is True
        assert result["article_count"] == 12
        assert result["size_mb"] == 0.0
        assert "db_size probe failed" in result["error"]

    def test_probe_redis_returns_error_details(self):
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = RuntimeError("connection refused")
        with patch("core.health._get_redis", return_value=mock_redis):
            result = _probe_redis()
        assert result["ok"] is False
        assert "connection refused" in result["error"]
