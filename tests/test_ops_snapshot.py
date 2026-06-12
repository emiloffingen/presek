from unittest.mock import AsyncMock, patch

import pytest

from core.ops_snapshot import build_ops_snapshot


@pytest.mark.anyio
async def test_build_ops_snapshot_marks_critical_on_queue_backlog():
    with patch("core.ops_snapshot._probe_celery_queue", return_value={"total_depth": 600, "celery_depth": 600, "degraded": True}), patch(
        "core.ops_snapshot.queue_status_payload",
        return_value={"intel_status": "backlogged", "intel_heavy_depth": 600, "depths": {"ingestion": 600}},
    ), patch(
        "core.ops_snapshot.reader_pipeline_status",
        return_value={"busy": True, "intel_status": "backlogged", "intel_heavy_depth": 600},
    ), patch(
        "core.ops_snapshot.get_synthesis_quality_snapshot",
        return_value={"status": "ok", "primary": {"fallback_ratio": 0.0}, "history": {"fallback_ratio": 0.03}},
    ), patch("core.ops_snapshot._load_last_refresh_time", return_value="2026-06-12T12:00:00+00:00"), patch(
        "core.ops_snapshot._freshness_payload",
        return_value={"status": "fresh", "age_minutes": 5, "label": "Osvezeno skoro"},
    ), patch("core.ops_snapshot.db.async_execute_one", new=AsyncMock(return_value={"stale_count": 2, "sample_ids": ["abc123"]})):
        snapshot = await build_ops_snapshot()

    assert snapshot["status"] == "critical"
    assert any(alert["code"] == "queue_critical" for alert in snapshot["alerts"])
    assert snapshot["stale_clusters"]["count"] == 2


@pytest.mark.anyio
async def test_build_ops_snapshot_warns_on_stale_clusters():
    with patch("core.ops_snapshot._probe_celery_queue", return_value={"total_depth": 20, "celery_depth": 20, "degraded": False}), patch(
        "core.ops_snapshot.queue_status_payload",
        return_value={"intel_status": "ok", "intel_heavy_depth": 20, "depths": {"intel-heavy": 20}},
    ), patch(
        "core.ops_snapshot.reader_pipeline_status",
        return_value={"busy": False, "intel_status": "ok", "intel_heavy_depth": 20},
    ), patch(
        "core.ops_snapshot.get_synthesis_quality_snapshot",
        return_value={"status": "ok", "primary": {"fallback_ratio": 0.0}, "history": {"fallback_ratio": 0.03}},
    ), patch("core.ops_snapshot._load_last_refresh_time", return_value=None), patch(
        "core.ops_snapshot._freshness_payload",
        return_value={"status": "fresh", "age_minutes": 5, "label": "Osvezeno skoro"},
    ), patch("core.ops_snapshot.db.async_execute_one", new=AsyncMock(return_value={"stale_count": 10, "sample_ids": ["a", "b"]})):
        snapshot = await build_ops_snapshot()

    assert snapshot["status"] == "warn"
    assert any(alert["code"] == "stale_clusters" for alert in snapshot["alerts"])
