import pytest
from ai_engine import clean_json_response

def test_clean_json_response_raw_text():
    assert clean_json_response("Ова е обичен текст.") == "Ова е обичен текст."

def test_clean_json_response_markdown_json():
    # Markdown wrapped JSON
    text = "```json\n{\"summary\": \"Ова е резимето.\"}\n```"
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["summary"] == "Ова е резимето."

def test_clean_json_response_raw_json():
    # Raw JSON string
    text = "{\"summary\": \"Ова е резимето.\"}"
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["summary"] == "Ова е резимето."

def test_clean_json_response_malformed_json():
    # Malformed JSON, should fallback to string
    text = "{\"summary\": \"Ова е резимето.\", }" # trailing comma invalid in JSON
    # Since the string contains '{' and '}', it will try to parse.
    # Parsing fails, so it falls back to stripping the string and removing markdown if any.
    assert clean_json_response(text) == text.strip()

def test_clean_json_response_empty():
    assert clean_json_response("") == ""
    assert clean_json_response(None) == ""

def test_clean_json_response_json_with_summary_key():
    text = '{"summary": "Ова е резиме", "perspectives": ["а","б"]}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["summary"] == "Ова е резиме"
    assert res["perspectives"] == ["а", "б"]

def test_clean_json_response_json_with_entities_key():
    text = '{"entities": [{"name": "Заев", "type": "PERSON"}]}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert "entities" in res

def test_clean_json_response_json_array():
    text = '[{"tag": "политика"}, {"tag": "економија"}]'
    res = clean_json_response(text)
    assert isinstance(res, list)
    assert len(res) == 2

def test_clean_json_response_mixed_text_and_json():
    text = "Here is the result:\n```json\n{\"summary\": \"Резиме\"}\n```\nDone."
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert res["summary"] == "Резиме"

def test_clean_json_response_triple_backtick_no_json():
    text = "```\nJust some code\n```"
    res = clean_json_response(text)
    assert isinstance(res, str)
    assert "```" not in res

def test_clean_json_response_dict_without_known_keys():
    """JSON dict without summary/perspectives/entities returns cleaned string."""
    text = '{"unknown_key": "value"}'
    res = clean_json_response(text)
    # Should parse JSON but since no known keys, returns the cleaned string
    assert isinstance(res, str)

def test_clean_json_response_whitespace_only():
    assert clean_json_response("   ") == ""

def test_clean_json_response_deeply_nested():
    text = '{"summary": "Test", "perspectives": [{"source": "A", "view": "positive"}]}'
    res = clean_json_response(text)
    assert isinstance(res, dict)
    assert isinstance(res["perspectives"], list)