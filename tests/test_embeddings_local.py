import math
from unittest.mock import patch

import pytest

from core import embeddings as emb


class _FakeModel:
    """Stands in for fastembed.TextEmbedding; records the texts it was given."""

    def __init__(self):
        self.seen = []

    def embed(self, texts, batch_size=32):
        self.seen.extend(texts)
        for i, _ in enumerate(texts):
            vec = [0.0] * emb.EMBEDDING_DIM
            vec[i % emb.EMBEDDING_DIM] = 1.0
            yield vec


def _norm(vec):
    return math.sqrt(sum(x * x for x in vec))


class TestCalibration:
    def test_endpoints_and_anchor(self):
        assert emb.local_distance(0.0) == 0.0
        assert emb.local_distance(0.28) == pytest.approx(0.427)
        assert emb.local_distance(2.0) == 2.0

    def test_monotonic_and_roundtrip(self):
        prev = -1.0
        for i in range(0, 201):
            d = i / 100
            local = emb.local_distance(d)
            assert local >= prev
            prev = local
            assert emb.jina_distance(local) == pytest.approx(d, abs=1e-6)

    def test_similarity_helpers_invert_each_other(self):
        assert emb.local_similarity(0.65) == pytest.approx(1 - emb.local_distance(0.35))
        assert emb.jina_similarity(emb.local_similarity(0.8)) == pytest.approx(0.8, abs=1e-6)

    def test_out_of_range_is_clamped(self):
        assert emb.local_distance(-1.0) == 0.0
        assert emb.local_distance(5.0) == 2.0


class TestEmbedding:
    def setup_method(self):
        emb._query_cache.clear()

    def test_vectors_are_centred_and_unit_length(self):
        with patch.object(emb, "_get_model", return_value=_FakeModel()):
            vecs = emb.generate_embeddings_batch(["a", "b"])
        assert len(vecs) == 2
        for v in vecs:
            assert len(v) == emb.EMBEDDING_DIM
            assert _norm(v) == pytest.approx(1.0, abs=1e-3)
        assert vecs[0] != vecs[1]

    def test_prefixes_distinguish_passages_and_queries(self):
        model = _FakeModel()
        with patch.object(emb, "_get_model", return_value=model):
            emb.generate_embeddings_batch(["Влада"])
            emb.generate_query_embedding("Влада")
        assert model.seen == ["passage: Влада", "query: Влада"]

    def test_unavailable_model_degrades_to_empty(self):
        with patch.object(emb, "_get_model", return_value=None):
            assert emb.generate_embeddings_batch(["a", "b"]) == [None, None]
            assert emb.generate_query_embedding("a") == []

    def test_model_error_returns_none_not_raise(self):
        class Boom:
            def embed(self, *a, **k):
                raise RuntimeError("onnx exploded")

        with patch.object(emb, "_get_model", return_value=Boom()):
            assert emb.generate_embeddings_batch(["a"]) == [None]

    def test_query_vectors_are_cached(self):
        model = _FakeModel()
        with patch.object(emb, "_get_model", return_value=model):
            first = emb.generate_query_embedding("избори")
            second = emb.generate_query_embedding("избори")
        assert first == second
        assert len(model.seen) == 1

    def test_empty_input(self):
        assert emb.generate_embeddings_batch([]) == []
        assert emb.generate_query_embedding("") == []


class TestArticleText:
    def test_strips_html_and_truncates(self):
        text = emb.article_text("Наслов", "<p>Прв   пасус</p>" + "х" * 1000)
        assert text.startswith("Наслов. Прв пасус")
        assert "<" not in text
        assert len(text) <= len("Наслов. ") + 300

    def test_missing_description(self):
        assert emb.article_text("Наслов", None) == "Наслов."


def test_search_sql_has_no_unresolved_placeholders():
    from core.database import SQL_ARTICLE_SEARCH

    assert "@SEM_" not in SQL_ARTICLE_SEARCH
    assert f"{emb.local_distance(0.6):.3f}" in SQL_ARTICLE_SEARCH


def test_mean_vector_matches_embedding_dim():
    assert len(emb._load_mean()) == emb.EMBEDDING_DIM


@pytest.mark.skipif(
    __import__("os").environ.get("PRESEK_TEST_REAL_EMBED") != "1",
    reason="loads the real e5 model; set PRESEK_TEST_REAL_EMBED=1 with fastembed installed",
)
def test_real_model_ranks_paraphrases_above_unrelated():
    emb._query_cache.clear()
    a, b, c = emb.generate_embeddings_batch(
        [
            "Владата донесе нови мерки за поддршка на македонското стопанство",
            "Нови економски мерки на Владата за помош на компаниите во Македонија",
            "Фудбалската репрезентација загуби во квалификациите со 2:0",
        ]
    )
    dot = lambda x, y: sum(p * q for p, q in zip(x, y))  # noqa: E731
    assert dot(a, b) > dot(a, c) + 0.2
    q = emb.generate_query_embedding("мерки за економијата")
    assert dot(q, a) > dot(q, c)
