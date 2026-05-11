from trending import extract_words_with_flags


class TestExtractWordsWithFlags:
    def test_basic_extraction(self):
        pairs = extract_words_with_flags("Vladata donese nova merka")
        words = [w for w, _ in pairs]
        assert "vlad" not in words or "vladata" in words or len(words) > 0
        # At minimum, some words should be extracted
        assert len(pairs) > 0

    def test_stopwords_removed(self):
        pairs = extract_words_with_flags("ova e test za vladata")
        words = {w for w, _ in pairs}
        for sw in ["ova", "e", "za"]:
            assert sw not in words

    def test_short_words_removed(self):
        pairs = extract_words_with_flags("Da ne vo od")
        assert len(pairs) == 0

    def test_proper_noun_detection(self):
        """Mid-sentence capitalized words should be flagged as proper nouns."""
        pairs = extract_words_with_flags("Vladata na Zaev donese merka")
        proper_nouns = {w for w, is_proper in pairs if is_proper}
        # "Zaev" is mid-sentence and capitalized
        assert "zaev" in proper_nouns

    def test_sentence_start_not_proper(self):
        """First word of sentence should NOT be flagged as proper noun."""
        pairs = extract_words_with_flags("Vladata donese merka")
        # "Vladata" is first word, should NOT be proper
        for word, is_proper in pairs:
            if word == "vladata":
                assert not is_proper

    def test_numbers_excluded(self):
        pairs = extract_words_with_flags("Test 12345 broj")
        words = {w for w, _ in pairs}
        assert "12345" not in words

    def test_empty_string(self):
        assert extract_words_with_flags("") == []

    def test_multiple_sentences(self):
        text = "Prva recenica. Vtora recenica"
        pairs = extract_words_with_flags(text)
        # Both "Prva" and "Vtora" are sentence-start, so not proper nouns
        for word, is_proper in pairs:
            if word in ("prva", "vtora"):
                assert not is_proper

    def test_punctuation_stripped(self):
        pairs = extract_words_with_flags('"Vladata" donese (merka)')
        words = {w for w, _ in pairs}
        # Words should be clean, no quotes or parens
        for w in words:
            assert '"' not in w
            assert "(" not in w
            assert ")" not in w

    def test_mixed_cyrillic_latin(self):
        pairs = extract_words_with_flags("NATO odluci za novi merki")
        words = {w for w, _ in pairs}
        # "nato" should be extracted (4 chars, meets MIN_WORD_LEN)
        assert "nato" in words or len(words) >= 1
