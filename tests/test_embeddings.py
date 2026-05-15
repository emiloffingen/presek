from core.embeddings import average_embeddings, parse_embedding_value


def test_parse_embedding_value_handles_wrapped_json_payload():
    raw = '{"embedding":[0.1,0.2,0.3]}'
    assert parse_embedding_value(raw) == [0.1, 0.2, 0.3]


def test_average_embeddings_skips_malformed_rows():
    values = [
        "[1,2,3]",
        '{"vec":[3,4,5]}',
        '{"unexpected":"shape"}',
        "not-a-vector",
    ]

    assert average_embeddings(values) == [2.0, 3.0, 4.0]


def test_parse_embedding_value_unwraps_single_item_vector_wrappers():
    raw = ["[0.1,0.2,0.3]"]
    assert parse_embedding_value(raw) == [0.1, 0.2, 0.3]
