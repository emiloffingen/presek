import pytest
from ai_engine import clean_json_response

def test_clean_json_response_raw_text():
    assert clean_json_response("Ова е обичен текст.") == "Ова е обичен текст."

def test_clean_json_response_markdown_json():
    # Markdown wrapped JSON
    text = "```json\n{\"summary\": \"Ова е резимето.\"}\n```"
    assert clean_json_response(text) == "Ова е резимето."

def test_clean_json_response_raw_json():
    # Raw JSON string
    text = "{\"summary\": \"Ова е резимето.\"}"
    assert clean_json_response(text) == "Ова е резимето."

def test_clean_json_response_malformed_json():
    # Malformed JSON, should fallback to string
    text = "{\"summary\": \"Ова е резимето.\", }" # trailing comma invalid in JSON
    # Since the string contains '{' and '}', it will try to parse.
    # Parsing fails, so it falls back to stripping the string and removing markdown if any.
    assert clean_json_response(text) == text.strip()

def test_clean_json_response_empty():
    assert clean_json_response("") == ""
    assert clean_json_response(None) == ""