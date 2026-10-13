from unittest.mock import AsyncMock, patch

import pytest

from core.ops_snapshot import build_ops_snapshot


@pytest.mark.anyio
async def test_build_ops_snapshot_marks_critical_on_queue_backlog():
    with (
        patch(
            "core.ops_snapshot._probe_celery_queue",
            return_value={"total_depth": 600, "celery_depth": 600, "degraded": True},
        ),
        patch(
            "core.ops_snapshot.queue_status_payload",
            return_value={"intel_status": "backlogged", "intel_heavy_depth": 600, "depths": {"ingestion": 600}},
        ),
        patch(
            "core.ops_snapshot.reader_pipeline_status",
            return_value={"busy": True, "intel_status": "backlogged", "intel_heavy_depth": 600},
        ),
        patch(
            "core.ops_snapshot.get_synthesis_quality_snapshot",
            return_value={"status": "ok", "primary": {"fallback_ratio": 0.0}, "history": {"fallback_ratio": 0.03}},
        ),
        patch("core.ops_snapshot._load_last_refresh_time", return_value="2026-06-12T12:00:00+00:00"),
        patch(
            "core.ops_snapshot._freshness_payload",
            return_value={"status": "fresh", "age_minutes": 5, "label": "Osvezeno skoro"},
        ),
        patch(
            "core.ops_snapshot.db.async_execute_one",
            new=AsyncMock(return_value={"stale_count": 2, "sample_ids": ["abc123"]}),
        ),
    ):
        snapshot = await build_ops_snapshot()

    assert snapshot["status"] == "critical"
    assert any(alert["code"] == "queue_critical" for alert in snapshot["alerts"])
    assert snapshot["stale_clusters"]["count"] == 2


@pytest.mark.anyio
async def test_build_ops_snapshot_warns_on_stale_clusters():
    with (
        patch(
            "core.ops_snapshot._probe_celery_queue",
            return_value={"total_depth": 20, "celery_depth": 20, "degraded": False},
        ),
        patch(
            "core.ops_snapshot.queue_status_payload",
            return_value={"intel_status": "ok", "intel_heavy_depth": 20, "depths": {"intel-heavy": 20}},
        ),
        patch(
            "core.ops_snapshot.reader_pipeline_status",
            return_value={"busy": False, "intel_status": "ok", "intel_heavy_depth": 20},
        ),
        patch(
            "core.ops_snapshot.get_synthesis_quality_snapshot",
            return_value={"status": "ok", "primary": {"fallback_ratio": 0.0}, "history": {"fallback_ratio": 0.03}},
        ),
        patch("core.ops_snapshot._load_last_refresh_time", return_value=None),
        patch(
            "core.ops_snapshot._freshness_payload",
            return_value={"status": "fresh", "age_minutes": 5, "label": "Osvezeno skoro"},
        ),
        patch(
            "core.ops_snapshot.db.async_execute_one",
            new=AsyncMock(return_value={"stale_count": 10, "sample_ids": ["a", "b"]}),
        ),
    ):
        snapshot = await build_ops_snapshot()

    assert snapshot["status"] == "warn"
    assert any(alert["code"] == "stale_clusters" for alert in snapshot["alerts"])


def _patched_snapshot(stale_row):
    return (
        patch(
            "core.ops_snapshot._probe_celery_queue",
            return_value={"total_depth": 20, "celery_depth": 20, "degraded": False},
        ),
        patch(
            "core.ops_snapshot.queue_status_payload",
            return_value={"intel_status": "ok", "intel_heavy_depth": 20, "depths": {"intel-heavy": 20}},
        ),
        patch(
            "core.ops_snapshot.reader_pipeline_status",
            return_value={"busy": False, "intel_status": "ok", "intel_heavy_depth": 20},
        ),
        patch(
            "core.ops_snapshot.get_synthesis_quality_snapshot",
            return_value={"status": "ok", "primary": {"fallback_ratio": 0.0}, "history": {"fallback_ratio": 0.03}},
        ),
        patch("core.ops_snapshot._load_last_refresh_time", return_value=None),
        patch(
            "core.ops_snapshot._freshness_payload",
            return_value={"status": "fresh", "age_minutes": 5, "label": "Osvezeno skoro"},
        ),
        patch("core.ops_snapshot.db.async_execute_one", new=AsyncMock(return_value=stale_row)),
    )


@pytest.mark.anyio
async def test_stale_clusters_not_alerted_while_synthesis_is_recent():
    row = {"stale_count": 163, "newest_synthesis_age_min": 40.0, "sample_ids": ["a"]}
    p = _patched_snapshot(row)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        snapshot = await build_ops_snapshot()

    assert not any(alert["code"] == "stale_clusters" for alert in snapshot["alerts"])
    assert snapshot["stale_clusters"]["count"] == 163
    assert snapshot["stale_clusters"]["newest_synthesis_age_min"] == 40.0


@pytest.mark.anyio
async def test_stale_clusters_alert_when_synthesis_is_overdue():
    row = {"stale_count": 163, "newest_synthesis_age_min": 400.0, "sample_ids": ["a"]}
    p = _patched_snapshot(row)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6]:
        snapshot = await build_ops_snapshot()

    alert = next(a for a in snapshot["alerts"] if a["code"] == "stale_clusters")
    assert "400 min old" in alert["message"]


@pytest.mark.anyio
async def test_build_ops_snapshot_alerts_on_stuck_fast_synthesis():
    with (
        patch(
            "core.ops_snapshot._probe_celery_queue",
            return_value={"total_depth": 20, "celery_depth": 20, "degraded": False},
        ),
        patch(
            "core.ops_snapshot.queue_status_payload",
            return_value={"intel_status": "ok", "intel_heavy_depth": 20, "depths": {"intel-heavy": 20}},
        ),
        patch(
            "core.ops_snapshot.reader_pipeline_status",
            return_value={"busy": False, "intel_status": "ok", "intel_heavy_depth": 20},
        ),
        patch(
            "core.ops_snapshot.get_synthesis_quality_snapshot",
            return_value={
                "status": "critical",
                "primary": {"fallback_ratio": 0.0},
                "history": {"fallback_ratio": 0.03},
                "stuck_fast_synthesis_count": 3,
                "provisional_count_24h": 5,
                "fallback_count_24h": 10,
            },
        ),
        patch("core.ops_snapshot._load_last_refresh_time", return_value=None),
        patch(
            "core.ops_snapshot._freshness_payload",
            return_value={"status": "fresh", "age_minutes": 5, "label": "Osvezeno skoro"},
        ),
        patch(
            "core.ops_snapshot.db.async_execute_one", new=AsyncMock(return_value={"stale_count": 0, "sample_ids": []})
        ),
    ):
        snapshot = await build_ops_snapshot()

    assert snapshot["status"] == "critical"
    assert any(alert["code"] == "stuck_fast_synthesis" for alert in snapshot["alerts"])
    assert snapshot["synthesis"]["provisional_count_24h"] == 5
