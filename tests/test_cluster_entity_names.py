import asyncio
from unittest.mock import AsyncMock, patch

from routes.news import _cluster_entity_names


def test_cluster_entity_names_returns_names_in_query_order():
    rows = [{"entity_name": "Мицкоски"}, {"entity_name": "Скопје"}, {"entity_name": None}]
    with patch("routes.news.db.async_execute", new=AsyncMock(return_value=rows)) as run:
        assert asyncio.run(_cluster_entity_names("abc")) == ["Мицкоски", "Скопје"]
    sql, params = run.call_args.args[0], run.call_args.args[1]
    assert "entity_type = 'LOC'" in sql  # people and organisations before places
    assert params == ("abc", 8)


def test_cluster_entity_names_swallows_database_errors():
    with patch("routes.news.db.async_execute", new=AsyncMock(side_effect=RuntimeError("down"))):
        assert asyncio.run(_cluster_entity_names("abc")) == []
