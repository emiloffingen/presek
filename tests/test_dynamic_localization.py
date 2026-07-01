from core.localization import ENTITY_NOISE_WORDS, TAG_MAPPINGS, TAG_NOISE_WORDS, localization_engine
from nlp.keywords import is_valid_focus_entity, normalize_tag_name


def test_localization_engine_loaded():
    """Verify that rules are loaded properly on startup and global references are populated."""
    assert len(ENTITY_NOISE_WORDS) > 0
    assert len(TAG_NOISE_WORDS) > 0
    assert len(TAG_MAPPINGS) > 0
    assert "dnes" in TAG_NOISE_WORDS
    assert "reuters" in localization_engine.get_rules_dict()["source_noise_words"]


def test_dynamic_hashing_and_normalizer():
    """Verify normalize_tag_name respects dynamic config rules."""
    # Test built-in mapping
    assert normalize_tag_name("mickoski") == "Hristijan Mickoski"
    assert normalize_tag_name("makedonsk") == "Makedonija"
    assert normalize_tag_name("srbije") == "Srbija"
    assert normalize_tag_name("srbiji") == "Srbija"
    assert normalize_tag_name("srbiju") == "Srbija"
    assert normalize_tag_name("srbijom") == "Srbija"
    assert normalize_tag_name("srbija") == "Srbija"


def test_localization_hot_reload():
    """Verify that update_rules hot-reloads configurations and updates global sets in-place."""
    original_rules = localization_engine.get_rules_dict()
    
    try:
        # Create modified rules with custom values
        new_rules = dict(original_rules)
        new_rules["tag_noise_words"] = ["customtagnoise1", "customtagnoise2"]
        new_rules["tag_mappings"] = {"customkey": "Custom Normalized Value"}

        # Perform the update/reload
        success = localization_engine.update_rules(new_rules)
        assert success is True

        # Verify global sets were updated in-place (identity remains the same, but values change)
        assert "customtagnoise1" in TAG_NOISE_WORDS
        assert "customtagnoise2" in TAG_NOISE_WORDS
        assert "dnes" not in TAG_NOISE_WORDS  # Cleared out for the duration of this test
        
        # Verify tag mapping conversion works dynamically
        assert normalize_tag_name("customkey") == "Custom Normalized Value"
        assert is_valid_focus_entity("customtagnoise1") is False

    finally:
        # Crucial: Restore original rules so subsequent tests are unaffected
        localization_engine.update_rules(original_rules)
        assert "dnes" in TAG_NOISE_WORDS
        assert "customtagnoise1" not in TAG_NOISE_WORDS
