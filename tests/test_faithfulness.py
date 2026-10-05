from tasks.intelligence import faithfulness as fh


def _stub_embeddings(monkeypatch, claim_hits):
    """Stub the embedding backend with two fixed orthogonal directions.

    Texts about resignation score along [1,0]; everything else along
    [0,1]. Deterministic: identical topics fully support, others don't.
    """
    import core.embeddings as emb

    def fake_query(text):
        if "оставка" in text or "корупциски" in text:
            return [1.0] + [0.0] * 7
        return [0.0, 1.0] + [0.0] * 6

    def fake_batch(texts):
        return [fake_query(t) for t in texts]

    monkeypatch.setattr(emb, "generate_query_embedding", fake_query)
    monkeypatch.setattr(emb, "generate_embeddings_batch", fake_batch)


def test_extract_claims_prefers_key_facts():
    claims = fh.extract_claims(
        "Краток преглед на настанот со сите детали за јавноста.",
        ["Бројот на жртви е 12", "ок"],
    )
    kinds = [k for k, _ in claims]
    assert kinds[0] == "key_fact"
    assert all(len(t) >= 12 for _, t in claims)


def test_chunk_articles_windows_sentences():
    rows = [{"title": "Наслов", "full_content": "Прва реченица за настанот. Втора реченица со детали. Трета реченица за контекст. Четврта реченица за крај."}]
    chunks = fh.chunk_articles(rows)
    assert chunks[0] == "Наслов"
    assert len(chunks) >= 2


def test_score_identical_claim_fully_supported(monkeypatch):
    _stub_embeddings(monkeypatch, None)
    rows = [{"title": "Скопје", "full_content": "Владата ја усвои новата мерка за субвенции во земјоделството денеска."}]
    score, unsupported = fh.score_faithfulness(
        "Владата ја усвои новата мерка за субвенции во земјоделството денеска.",
        [],
        rows,
        threshold=0.9,
    )
    assert score == 1.0
    assert unsupported == []


def test_score_unrelated_claim_flagged(monkeypatch):
    _stub_embeddings(monkeypatch, None)
    rows = [{"title": "Временска прогноза", "full_content": "Утре ќе биде сончево со температура до 25 степени целзиусови."}]
    score, unsupported = fh.score_faithfulness(
        "Претседателот поднесе оставка поради корупциски скандал со тендери.",
        [],
        rows,
        threshold=0.99,
    )
    assert score == 0.0
    assert len(unsupported) == 1


def test_score_returns_none_without_evidence():
    score, unsupported = fh.score_faithfulness("Некој текст овде.", [], [])
    assert score is None
    assert unsupported == []


def test_shadow_never_raises(monkeypatch):
    _stub_embeddings(monkeypatch, None)
    assert fh.log_faithfulness_shadow("abc", None, None, None) is None
    assert fh.log_faithfulness_shadow("abc", "x", ["y" * 5], [{"title": "t"}]) is None
