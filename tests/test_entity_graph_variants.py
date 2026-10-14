import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from routes.news import get_entity_graph


def test_entity_graph_prefers_the_exact_spelling_over_case_variants():
    ent = {"name": "Мицкоски", "type": "MISC", "total_mentions": 663, "first_seen": None, "last_seen": None}
    one = AsyncMock(side_effect=[ent, {"n": 179}])
    db = MagicMock(async_execute_one=one, async_execute=AsyncMock(return_value=[]))
    # Patch the globals of the function itself: other tests reload routes.news, so a
    # "routes.news.x" patch target can point at a different module object than this function.
    with patch.dict(
        get_entity_graph.__globals__,
        {"db": db, "cached_response": lambda *a, **k: None, "set_cache": lambda *a, **k: None},
    ):
        result = asyncio.run(get_entity_graph("Мицкоски", lang="mk"))
    sql, params = one.await_args_list[0].args[0], one.await_args_list[0].args[1]
    assert "ORDER BY (name = %s) DESC, total_mentions DESC" in sql and "LIMIT 1" in sql
    assert params == ("Мицкоски", "Мицкоски")
    assert result["data"]["total_mentions"] == 663
    assert result["data"]["cluster_count"] == 179
