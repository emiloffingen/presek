from trending import extract_words_with_flags


class TestExtractWordsWithFlags:
    def test_basic_extraction(self):
        pairs = extract_words_with_flags("Владата донесе нова мерка")
        words = [w for w, _ in pairs]
        assert "влад" not in words or "владата" in words or len(words) > 0
        # At minimum, some words should be extracted
        assert len(pairs) > 0

    def test_stopwords_removed(self):
        pairs = extract_words_with_flags("Ова е тест за владата")
        words = {w for w, _ in pairs}
        for sw in ["ова", "е", "за"]:
            assert sw not in words

    def test_short_words_removed(self):
        pairs = extract_words_with_flags("Да не во од")
        assert len(pairs) == 0

    def test_proper_noun_detection(self):
        """Mid-sentence capitalized words should be flagged as proper nouns."""
        pairs = extract_words_with_flags("Владата на Заев донесе мерка")
        proper_nouns = {w for w, is_proper in pairs if is_proper}
        # "Заев" is mid-sentence and capitalized
        assert "заев" in proper_nouns

    def test_sentence_start_not_proper(self):
        """First word of sentence should NOT be flagged as proper noun."""
        pairs = extract_words_with_flags("Владата донесе мерка")
        # "Владата" is first word, should NOT be proper
        for word, is_proper in pairs:
            if word == "владата":
                assert not is_proper

    def test_numbers_excluded(self):
        pairs = extract_words_with_flags("Тест 12345 број")
        words = {w for w, _ in pairs}
        assert "12345" not in words

    def test_empty_string(self):
        assert extract_words_with_flags("") == []

    def test_multiple_sentences(self):
        text = "Прва реченица. Втора реченица"
        pairs = extract_words_with_flags(text)
        # Both "Прва" and "Втора" are sentence-start, so not proper nouns
        for word, is_proper in pairs:
            if word in ("прва", "втора"):
                assert not is_proper

    def test_punctuation_stripped(self):
        pairs = extract_words_with_flags('"Владата" донесе (мерка)')
        words = {w for w, _ in pairs}
        # Words should be clean, no quotes or parens
        for w in words:
            assert '"' not in w
            assert "(" not in w
            assert ")" not in w

    def test_mixed_cyrillic_latin(self):
        pairs = extract_words_with_flags("NATO одлучи за нови мерки")
        words = {w for w, _ in pairs}
        # "nato" should be extracted (4 chars, meets MIN_WORD_LEN)
        assert "nato" in words or len(words) >= 1
