import pytest
from unittest.mock import AsyncMock, patch

from core.ops_report import build_weekly_ops_report


@pytest.mark.asyncio
async def test_build_weekly_ops_report_shape():
    async def _fake_execute(query, *args, **kwargs):
        if "generation_provider" in query:
            return [{"provider": "nvidia", "count": 12}]
        if "unnest(tags)" in query:
            return []
        return []

    with patch(
        "core.ops_report.build_ops_snapshot",
        new=AsyncMock(return_value={"status": "warn", "alerts": []}),
    ), patch(
        "core.ops_report.db.async_execute",
        new=AsyncMock(side_effect=_fake_execute),
    ):
        report = await build_weekly_ops_report()

    assert report["window_days"] == 7
    assert "synthesis" in report
    assert report["synthesis"]["total_7d"] == 12
