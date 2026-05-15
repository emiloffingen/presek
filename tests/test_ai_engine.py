from core.ai_engine import clean_json_response


def test_clean_json_response_raw_text():
    assert clean_json_response("ova e obicen tekst.") == "ova e obicen tekst."


def test_clean_json_response_markdown_json():
    # Markdown wrapped JSON
    text = '```json\n{"summary": "ova e rezimeto."}\n```'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["answer"] == "ova e rezimeto."


def test_clean_json_response_raw_json():
    # Raw JSON string
    text = '{"summary": "ova e rezimeto."}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["answer"] == "ova e rezimeto."


def test_clean_json_response_malformed_json():
    # Malformed JSON, should fallback to string
    text = '{"summary": "ova e rezimeto.", }'  # trailing comma invalid in JSON
    # Since the string contains '{' and '}', it will try to parse.
    # Parsing fails, so it falls back to stripping the string and removing markdown if any.
    assert clean_json_response(text) == {"answer": "ova e rezimeto.", "suggestions": []}


def test_clean_json_response_empty():
    assert clean_json_response("") == ""
    assert clean_json_response(None) == ""


def test_clean_json_response_json_with_summary_key():
    text = '{"summary": "ova e rezime", "perspectives": ["a","b"]}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["summary"] == "ova e rezime"
    assert res["perspectives"] == ["a", "b"]


def test_clean_json_response_json_with_entities_key():
    text = '{"entities": [{"name": "Zaev", "type": "PERSON"}]}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert "entities" in res


def test_clean_json_response_json_array():
    text = '[{"tag": "Politika"}, {"tag": "Ekonomija"}]'
    res = clean_json_response(text)
    assert isinstance(res, list)
    assert len(res) == 2


def test_clean_json_response_mixed_text_and_json():
    text = 'Here is the result:\n```json\n{"summary": "rezime"}\n```\nDone.'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["answer"] == "rezime"


def test_clean_json_response_triple_backtick_no_json():
    text = "```\nJust some code\n```"
    res = clean_json_response(text)
    assert isinstance(res, str)
    assert "```" not in res


def test_clean_json_response_dict_without_known_keys():
    """JSON dict without summary/perspectives/entities returns cleaned string."""
    text = '{"unknown_key": "value value"}'
    res = clean_json_response(text)
    # Should parse JSON but since no known keys, returns the unwrapped single value if it has space
    assert isinstance(res, dict)
    assert res["answer"] == "value value"


def test_clean_json_response_whitespace_only():
    assert clean_json_response("   ") == ""


def test_clean_json_response_deeply_nested():
    text = '{"summary": "Test", "perspectives": [{"source": "A", "view": "positive"}]}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert isinstance(res["perspectives"], list)
