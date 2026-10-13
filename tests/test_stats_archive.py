from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# Top-level import binds collection-era modules once. Deferred (function-level)
# imports would re-execute app modules mid-session against whatever happens
# to be in sys.modules then, creating duplicate class objects that escape
# narrow pytest.raises checks (see _raise_http_error note in routes/security).
from routes.stats import get_archive


@pytest.mark.anyio
async def test_archive_invalid_date_returns_400_not_500():
    with pytest.raises(HTTPException) as exc:
        await get_archive(
            date='2026-06-08" AND 1=1 --',
            q="",
            source="",
            topic="",
            lang="sr",
            page=0,
            page_size=50,
        )

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_archive_valid_date_does_not_raise_validation_error():
    with _patched(_mock_db()):
        result = await get_archive(
            date="2026-06-08",
            q="",
            source="",
            topic="",
            lang="sr",
            page=0,
            page_size=50,
        )

    assert result["date"] == "2026-06-08"
    assert result["clusters"] == []


def _patched(db, **extra):
    """Patch names in the module get_archive really executes in (robust to sys.modules re-imports)."""
    names = {"db": db, "cached_response": lambda key: None, "set_cache": lambda *a, **k: None}
    names.update(extra)
    return patch.dict(get_archive.__globals__, names)


def _mock_db(execute_rows=None, one_row=None):
    mock_db = AsyncMock()
    rows = execute_rows or []

    async def _execute(sql, *args, **kwargs):
        # only the main article query returns rows; facets / cluster_metadata lookups are empty
        return rows if sql.lstrip().startswith("SELECT") and "ORDER BY created_at DESC" in sql else []

    mock_db.async_execute = AsyncMock(side_effect=_execute)
    mock_db.async_execute_one = AsyncMock(return_value=one_row or {"total": 0, "source_count": 0})
    mock_db.async_get_synthesis_ids = AsyncMock(return_value=[])
    return mock_db


@pytest.mark.anyio
async def test_archive_missing_date_defaults_to_today():
    from datetime import datetime

    with _patched(_mock_db()):
        result = await get_archive(date="", q="", source="", topic="", lang="mk", page=0, page_size=15)

    assert result["date"] == datetime.now().strftime("%Y-%m-%d")


@pytest.mark.anyio
async def test_archive_facets_ignore_their_own_filter():
    mock_db = _mock_db()
    with _patched(mock_db):
        await get_archive(date="2026-06-08", q="", source="MIA", topic="Politika", lang="mk", page=0, page_size=15)

    facet_calls = {
        "topic": next(c for c in mock_db.async_execute.await_args_list if "GROUP BY topic" in c.args[0]),
        "source": next(c for c in mock_db.async_execute.await_args_list if "GROUP BY source" in c.args[0]),
    }
    topic_sql, topic_params = facet_calls["topic"].args
    source_sql, source_params = facet_calls["source"].args
    # topic facet keeps the source filter but not the topic filter, and vice versa
    assert "source = %s" in topic_sql and "topic = %s" not in topic_sql
    assert "MIA" in topic_params and "Politika" not in topic_params
    assert "topic = %s" in source_sql and "source = %s" not in source_sql
    assert "Politika" in source_params and "MIA" not in source_params


@pytest.mark.anyio
async def test_archive_empty_result_reports_nearest_days():
    from datetime import datetime

    mock_db = _mock_db()
    mock_db.async_execute_one = AsyncMock(
        side_effect=[
            {"total": 0, "source_count": 0},
            {"d": datetime(2026, 5, 20, 14, 30)},
            {"d": datetime(2026, 6, 2, 9, 0)},
        ]
    )
    with _patched(mock_db):
        result = await get_archive(date="2026-05-27", q="", source="", topic="Kultura", lang="mk", page=0, page_size=15)

    assert result["clusters"] == []
    assert result["nearest"] == {"prev": "2026-05-20", "next": "2026-06-02"}


@pytest.mark.anyio
async def test_archive_nonempty_result_has_no_nearest():
    row = {
        "id": 1,
        "cluster_id": "c1",
        "title": "t",
        "source": "MIA",
        "topic": "Politika",
        "created_at": "2026-06-08T10:00:00",
        "description": "d",
    }
    with _patched(
        _mock_db(execute_rows=[row], one_row={"total": 1, "source_count": 1}),
        rank_articles_in_cluster=lambda arts: arts,
        score_cluster=lambda c: 1.0,
        is_balanced=lambda c: False,
    ):
        result = await get_archive(date="2026-06-08", q="", source="", topic="", lang="mk", page=0, page_size=15)

    assert result["nearest"] is None
