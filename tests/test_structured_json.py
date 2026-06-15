import asyncio
import json
from unittest.mock import patch
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


@patch("core.config.ENABLE_EXPENSIVE_STYLE_TASKS", True)
@patch("tasks.intelligence.style.db")
@patch.object(LocalAnalyst, "normalize_headline")
def test_standardize_article_style_task_language_mapping(mock_normalize, mock_db):
    """Verify that standardize_article_style_task queries country and maps it to lang correctly."""
    from tasks.intelligence import standardize_article_style_task
    
    # Case 1: Serbian article
    mock_db.execute_one.return_value = {
        "title": "Neki senzacionalan naslov o politici!!!",
        "description": "Neki opis.",
        "topic": "Politika",
        "category": "Politika",
        "country": "RS",
    }
    mock_normalize.return_value = "Neki senzacionalan naslov o politici!!!"
    
    standardize_article_style_task(123)
    
    mock_db.execute_one.assert_called_with(
        "SELECT title, description, topic, category, country FROM articles WHERE id = %s",
        (123,)
    )
    mock_normalize.assert_called_with("Neki senzacionalan naslov o politici!!!", lang="sr")
    
    # Case 2: Macedonian article
    mock_db.execute_one.return_value = {
        "title": "Nekoj senzacionalen naslov za politika!!!",
        "description": "Nekoj opis.",
        "topic": "Politika",
        "category": "Politika",
        "country": "MK",
    }
    
    standardize_article_style_task(124)
    mock_normalize.assert_called_with("Nekoj senzacionalen naslov za politika!!!", lang="mk")


@patch("core.services.research_service.async_call_ai")
@patch("core.services.research_service._build_gemma_research_context")
@patch("core.services.research_service.get_query_embedding_async")
@patch("core.services.research_service.ResearchService._public_web_search")
def test_research_service_structured_integration(mock_public_search, mock_embedding, mock_build_context, mock_async_call):
    """Test that ResearchService.get_cluster_research passes response_schema successfully."""
    from core.services.research_service import ResearchService
    
    mock_build_context.return_value = ("context text", ["source_a"])
    mock_embedding.return_value = [0.1, 0.2, 0.3]
    mock_public_search.return_value = []
    mock_async_call.side_effect = [
        ("plan raw", "provider_x"),  # Plan call
        (json.dumps({
            "answer": "Answer text [source_a]",
            "suggestions": ["S1?", "S2?", "S3?"]
        }), "provider_x")  # Report call
    ]
    
    res = asyncio.run(ResearchService.get_cluster_research("cluster_1", "facts", "", "sr"))
    
    # Assert plan was called, then standard report call with response_schema
    assert mock_async_call.call_count == 2
    args, kwargs = mock_async_call.call_args_list[1]
    assert kwargs["response_schema"] == ResearchQueryResponse
    assert res["answer"] == "Answer text [source_a]"


@patch.object(LocalAnalyst, "analyze")
def test_zero_token_metadata_fallback(mock_analyze):
    """Verify that extract_deep_metadata falls back gracefully to zero-token heuristics on failure."""
    # Simulate LLM returning None
    mock_analyze.return_value = None
    
    analyst = LocalAnalyst()
    sample_text = (
        "Vučić je danas najavio značajne promene. Vlada Srbije podržava projekte u Skupštini. "
        "Ovo donosi stabilnost u regionu i nova ulaganja od 50 miliona evra."
    )
    
    # Run fallback in Serbian
    res_sr = analyst.extract_deep_metadata(sample_text, lang="sr")
    
    assert "facts" in res_sr
    assert len(res_sr["facts"]) == 3
    assert "entities" in res_sr
    assert "Vlada" in res_sr["entities"] or "Vučić" in res_sr["entities"] or "Skupštini" in res_sr["entities"]
    assert res_sr["sentiment"] in ["pozitivan", "negativan", "neutralan"]
    assert 1 <= res_sr["pulse"] <= 100
    
    # Test Macedonian fallback
    sample_text_mk = (
        "Mickoski deneska najavi golem uspeh. Vladata na Makedonija ima stabilen plan vo Sobranieto. "
        "Ova nosi ekonomski razvoj i novi investicii."
    )
    res_mk = analyst.extract_deep_metadata(sample_text_mk, lang="mk")
    assert "facts" in res_mk
    assert len(res_mk["facts"]) == 3
    assert res_mk["sentiment"] == "pozitiven"


def test_zero_token_metadata_direct():
    """Directly test the zero-token metadata parser logic."""
    analyst = LocalAnalyst()
    
    # Test Serbian positive context
    text_pos = "Odličan razvoj i saradnja sa partnerima. Vlada Srbije beleži uspeh."
    meta = analyst.get_zero_token_metadata(text_pos, lang="sr")
    assert meta["sentiment"] == "pozitivan"
    assert any("Vlada" in e for e in meta["entities"])
    
    # Test Serbian negative context
    text_neg = "Teška kriza i pad ekonomije. Sukob u najavi u Skupštini."
    meta_neg = analyst.get_zero_token_metadata(text_neg, lang="sr")
    assert meta_neg["sentiment"] == "negativan"


@patch.object(LocalAnalyst, "analyze")
def test_zero_token_pluralism_fallback(mock_analyze):
    """Verify that assess_pluralism falls back gracefully to TIER_MAP calculations on failure."""
    mock_analyze.return_value = None
    
    analyst = LocalAnalyst()
    
    # 1. High Pluralism: 3 distinct tiers: N1 Info (Independent), RTS (Mainstream), Alternativni (Regional/Alt)
    sources_high = [
        "N1 Info: Title 1",
        "RTS: Title 2",
        "Alternativni: Title 3"
    ]
    res_high = analyst.assess_pluralism(sources_high, lang="sr")
    assert res_high["score"] == 85
    assert res_high["bias_detected"] is False
    assert "zastupljenošću" in res_high["verdict"]
    
    # 2. Medium Pluralism: 2 distinct tiers: Informer (Tabloid), Politika (Mainstream)
    sources_med = [
        "Informer: Title 1",
        "Politika: Title 2"
    ]
    res_med = analyst.assess_pluralism(sources_med, lang="mk")
    assert res_med["score"] == 65
    assert res_med["bias_detected"] is False
    
    # 3. Low Pluralism / Echo Chamber: 1 tier: Kurir, Informer (both Tabloidi)
    sources_low = [
        "Kurir: Title 1",
        "Informer: Title 2"
    ]
    res_low = analyst.assess_pluralism(sources_low, lang="sr")
    assert res_low["score"] == 35
    assert res_low["bias_detected"] is True


@patch.object(LocalAnalyst, "analyze")
def test_zero_token_headline_normalization_fallback(mock_analyze):
    """Verify that normalize_headline falls back to zero-token clickbait stripping on LLM failure."""
    mock_analyze.return_value = None
    
    analyst = LocalAnalyst()
    headline = "ŠOKANTNO: Vučić razgovarao sa ministrima!!!"
    
    res = analyst.normalize_headline(headline, lang="sr")
    assert "ŠOKANTNO" not in res
    assert "!!!" not in res
    assert res == "Vučić razgovarao sa ministrima"



@patch.object(LocalAnalyst, "analyze")
def test_zero_token_detect_echo_fallback(mock_analyze):
    """Verify that detect_echo falls back to zero-token Jaccard similarity index on LLM failure."""
    mock_analyze.return_value = None
    
    analyst = LocalAnalyst()
    
    # 1. Identical/Copy-paste text -> echo should be 0.0 (highly duplicated)
    art_text = "Vlada je danas donela novu odluku o energetskoj stabilnosti i reformama."
    ctx_text = "Vlada je danas donela novu odluku o energetskoj stabilnosti i reformama."
    
    res_echo = analyst.detect_echo(art_text, ctx_text, lang="sr")
    assert res_echo == 0.0
    
    # 2. Completely distinct text -> echo should be 1.0 (uniquely written)
    art_text_2 = "Sportski uspesi naših plivača na olimpijskim igrama u Parizu."
    ctx_text_2 = "Politički pregovori o budžetu u Narodnoj skupštini."
    
    res_unique = analyst.detect_echo(art_text_2, ctx_text_2, lang="sr")
    assert res_unique == 1.0


def test_determine_relationship_direction_heuristic():
    """Verify that determine_relationship_direction correctly determines active influencer."""
    from core.entities import determine_relationship_direction

    # Test case 1: PERSON vs non-PERSON (PERSON should influence ORG)
    res = determine_relationship_direction(
        ent_a_name="Mickoski", ent_a_type="PERSON",
        ent_b_name="Vlada", ent_b_type="ORG",
        context_text="Vlada i Mickoski su se sastali."
    )
    assert res == "a_to_b"

    # Test case 2: Order of first appearance (Same types - initiator appears first)
    res2 = determine_relationship_direction(
        ent_a_name="Vlada", ent_a_type="ORG",
        ent_b_name="Skupština", ent_b_type="ORG",
        context_text="Vlada je uputila predlog zakona u Skupštinu."
    )
    assert res2 == "a_to_b"

    # Test case 3: Mutual fallback if no context is supplied
    res3 = determine_relationship_direction(
        ent_a_name="Vučić", ent_a_type="PERSON",
        ent_b_name="Brnabić", ent_b_type="PERSON",
        context_text=""
    )
    assert res3 == "mutual"


