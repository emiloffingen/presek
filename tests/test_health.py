import pytest
import json
from unittest.mock import patch, MagicMock
from health import record_refresh, _REDIS_KEY


class TestRecordRefresh:
    def _make_redis(self):
        store = {}
        r = MagicMock()
        r.set.side_effect = lambda k, v, **kw: store.update({k: v})
        r.get.side_effect = lambda k: store.get(k)
        return r, store

    def test_record_refresh_stores_data(self):
        r, store = self._make_redis()
        with patch('health._get_redis', return_value=r):
            record_refresh(42, ["error1"])
        data = json.loads(store[_REDIS_KEY])
        assert data["count"] == 42
        assert data["errors"] == ["error1"]
        assert data["time"] is not None

    def test_record_refresh_no_errors(self):
        r, store = self._make_redis()
        with patch('health._get_redis', return_value=r):
            record_refresh(10)
        data = json.loads(store[_REDIS_KEY])
        assert data["count"] == 10
        assert data["errors"] == []

    def test_record_refresh_overwrites(self):
        r, store = self._make_redis()
        with patch('health._get_redis', return_value=r):
            record_refresh(5)
            record_refresh(15, ["e"])
        data = json.loads(store[_REDIS_KEY])
        assert data["count"] == 15
