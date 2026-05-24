import json
from unittest.mock import MagicMock, patch
from llama_cpp import LlamaGrammar
from nlp.local_analyst import (
    LocalAnalyst,
    DeepMetadataResponse,
    PluralismResponse,
    ResearchQueryResponse,
)

def test_pydantic_schema_gbnf_compilation():
    """Verify that we can successfully compile GBNF grammars dynamically from Pydantic schemas."""
    # Test DeepMetadataResponse schema
    schema_deep = DeepMetadataResponse.model_json_schema()
    grammar_deep = LlamaGrammar.from_json_schema(json.dumps(schema_deep))
    assert grammar_deep is not None

    # Test PluralismResponse schema
    schema_plural = PluralismResponse.model_json_schema()
    grammar_plural = LlamaGrammar.from_json_schema(json.dumps(schema_plural))
    assert grammar_plural is not None

    # Test ResearchQueryResponse schema
    schema_research = ResearchQueryResponse.model_json_schema()
    grammar_research = LlamaGrammar.from_json_schema(json.dumps(schema_research))
    assert grammar_research is not None


@patch.object(LocalAnalyst, "analyze")
def test_extract_deep_metadata_structured(mock_analyze):
    """Test that extract_deep_metadata calls analyze with the correct schema and parses correctly."""
    analyst = LocalAnalyst()
    mock_analyze.return_value = json.dumps({
        "facts": ["Fact 1", "Fact 2", "Fact 3"],
        "entities": ["Entity A"],
        "sentiment": "pozitiven",
        "pulse": 85
    })

    res = analyst.extract_deep_metadata("Some text context", lang="mk")

    mock_analyze.assert_called_once()
    args, kwargs = mock_analyze.call_args
    assert kwargs["response_schema"] == DeepMetadataResponse

    assert res["pulse"] == 85
    assert len(res["facts"]) == 3
    assert res["sentiment"] == "pozitiven"


@patch.object(LocalAnalyst, "analyze")
def test_assess_pluralism_structured(mock_analyze):
    """Test that assess_pluralism calls analyze with the correct schema and parses correctly."""
    analyst = LocalAnalyst()
    mock_analyze.return_value = json.dumps({
        "score": 90,
        "verdict": "Visok pluralizam.",
        "bias_detected": False
    })

    res = analyst.assess_pluralism(["Title 1 (Source A)", "Title 2 (Source B)"], lang="sr")

    mock_analyze.assert_called_once()
    args, kwargs = mock_analyze.call_args
    assert kwargs["response_schema"] == PluralismResponse

    assert res["score"] == 90
    assert res["bias_detected"] is False
    assert "Visok" in res["verdict"]


@patch.object(LocalAnalyst, "analyze")
def test_research_query_structured(mock_analyze):
    """Test that research_query calls analyze with the correct schema and parses correctly."""
    analyst = LocalAnalyst()
    mock_analyze.return_value = json.dumps({
        "answer": "This is a detailed answer [RTS].",
        "suggestions": ["Q1?", "Q2?", "Q3?"]
    })

    res = analyst.research_query("What is the cost?", "Context RTS", lang="sr")

    mock_analyze.assert_called_once()
    args, kwargs = mock_analyze.call_args
    assert kwargs["response_schema"] == ResearchQueryResponse

    assert "[RTS]" in res["answer"]
    assert len(res["suggestions"]) == 3
