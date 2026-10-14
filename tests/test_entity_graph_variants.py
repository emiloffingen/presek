import asyncio
from unittest.mock import AsyncMock, patch

from routes.news import get_entity_graph


def test_entity_graph_prefers_the_exact_spelling_over_case_variants():
    ent = {"name": "Мицкоски", "type": "MISC", "total_mentions": 663, "first_seen": None, "last_seen": None}
    one = AsyncMock(side_effect=[ent, {"n": 179}])
    with (
        patch("routes.news.cached_response", return_value=None),
        patch("routes.news.set_cache"),
        patch("routes.news.db.async_execute_one", new=one),
        patch("routes.news.db.async_execute", new=AsyncMock(return_value=[])),
    ):
        result = asyncio.run(get_entity_graph("Мицкоски", lang="mk"))
    sql, params = one.await_args_list[0].args[0], one.await_args_list[0].args[1]
    assert "ORDER BY (name = %s) DESC, total_mentions DESC" in sql and "LIMIT 1" in sql
    assert params == ("Мицкоски", "Мицкоски")
    assert result["data"]["total_mentions"] == 663
    assert result["data"]["cluster_count"] == 179
