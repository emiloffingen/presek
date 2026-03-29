import pytest
import time
from health import record_refresh, _last_refresh, _refresh_lock


class TestRecordRefresh:
    def test_record_refresh_stores_data(self):
        record_refresh(42, ["error1"])
        with _refresh_lock:
            assert _last_refresh["count"] == 42
            assert _last_refresh["errors"] == ["error1"]
            assert _last_refresh["time"] is not None

    def test_record_refresh_no_errors(self):
        record_refresh(10)
        with _refresh_lock:
            assert _last_refresh["count"] == 10
            assert _last_refresh["errors"] == []

    def test_record_refresh_overwrites(self):
        record_refresh(5)
        record_refresh(15, ["e"])
        with _refresh_lock:
            assert _last_refresh["count"] == 15
