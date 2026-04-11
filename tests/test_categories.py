import pytest
from categories import (
    validate_category, detect_category, detect_subcategory, detect_topic,
    detect_country, normalize_headline, ALLOWED_CATEGORIES
)


# ── validate_category ─────────────────────────────────────────────

class TestValidateCategory:
    def test_valid_categories(self):
        for cat in ALLOWED_CATEGORIES:
            assert validate_category(cat) == cat

    def test_invalid_falls_back(self):
        assert validate_category("Политика") == "Македонија"
        assert validate_category("") == "Македонија"
        assert validate_category("Random") == "Македонија"

    def test_case_sensitive(self):
        assert validate_category("македонија") == "Македонија"
        assert validate_category("ЕВРОПА") == "Македонија"


# ── detect_category ───────────────────────────────────────────────

class TestDetectCategory:
    # Forced category
    def test_forced_category_valid(self):
        assert detect_category("Anything", forced_category="Европа") == "Европа"

    def test_forced_category_invalid_ignored(self):
        # Invalid forced category should be ignored, fall through to keyword scan
        result = detect_category("Берлин нов закон", forced_category="Невалидна")
        assert result == "Германија"

    # Germany
    def test_germany_keywords(self):
        assert detect_category("Шолц се сретна со делегацијата") == "Германија"
        assert detect_category("Нов закон во Берлин") == "Германија"
        assert detect_category("Бундестаг гласаше за буџетот") == "Германија"

    # Balkan
    def test_balkan_keywords(self):
        assert detect_category("Вучиќ одржа конференција") == "Балкан"
        assert detect_category("Протести во Белград") == "Балкан"
        assert detect_category("Курти и Вучиќ на дијалог") == "Балкан"
        assert detect_category("Ердоган посети Анкара") == "Балкан"

    # Amerika
    def test_america_keywords(self):
        assert detect_category("Трамп потпиша указ") == "Америка"
        assert detect_category("Пентагон соопшти") == "Америка"
        assert detect_category("Канада воведе визи") == "Америка"

    # Europa
    def test_europa_keywords(self):
        assert detect_category("Европска унија донесе одлука") == "Европа"
        assert detect_category("Макрон посети Париз") == "Европа"
        assert detect_category("Британски парламент гласаше") == "Европа"

    # Svet
    def test_svet_keywords(self):
        assert detect_category("Путин одржа говор") == "Свет"
        assert detect_category("Зеленски побара помош") == "Свет"
        assert detect_category("Напад во Газа") == "Свет"
        assert detect_category("Нато формира нова стратегија") == "Свет"

    # Default
    def test_default_makedonija(self):
        assert detect_category("Нов мост во Скопје") == "Македонија"
        assert detect_category("Времето утре ќе биде сончево") == "Македонија"

    # Description also scanned
    def test_description_matters(self):
        assert detect_category("Нова одлука", description="Бундестаг гласаше") == "Германија"

    # Short keyword boundary check (e.g., "сад" should not match "насади")
    def test_short_keyword_word_boundary(self):
        # "кина" should not match inside "прекинато"
        result = detect_category("Преговорите се прекинати")
        assert result == "Македонија"  # Should NOT be "Свет"

    # Germany before Europa (order matters)
    def test_germany_before_europa(self):
        assert detect_category("Германија во Европа") == "Германија"

    # Balkan before Svet
    def test_balkan_before_svet(self):
        assert detect_category("Србија и Русија") == "Балкан"

    def test_category_scores_richer_group_over_stray_keyword(self):
        result = detect_category(
            "Европска комисија во Брисел расправа за нов пакет",
            description="Самит на Европската унија со нови мерки и комисијата."
        )
        assert result == "Европа"

    def test_category_understands_common_english_geo_terms(self):
        assert detect_category("White House announces new tariffs") == "Америка"
        assert detect_category("European Commission opens new Brussels talks") == "Европа"


# ── detect_subcategory ────────────────────────────────────────────

class TestDetectSubcategory:
    def test_skopje(self):
        assert detect_subcategory("Настан во Скопје") == "Скопје"
        assert detect_subcategory("Карпош доби нов парк") == "Скопје"

    def test_republika(self):
        assert detect_subcategory("Фестивал во Охрид") == "Република"
        assert detect_subcategory("Битола добива нова болница") == "Република"

    def test_no_match(self):
        assert detect_subcategory("Владата донесе одлука") is None

    def test_description_helps(self):
        assert detect_subcategory("Нов проект", description="изградба во Скопје") == "Скопје"


# ── detect_country ────────────────────────────────────────────────

class TestDetectCountry:
    def test_known_sources(self):
        assert detect_country("Tagesschau") == "DE"
        assert detect_country("CNN") == "US"
        assert detect_country("BBC News") == "GB"
        assert detect_country("Reuters") == "GB"
        assert detect_country("N1 Info") == "RS"

    def test_unknown_default(self):
        assert detect_country("Unknown Source") == "MK"
        assert detect_country("") == "MK"


class TestDetectTopic:
    def test_detects_topic_from_macedonian_keywords(self):
        assert detect_topic("Владата усвои нов буџет и мерки") == "Економија"
        assert detect_topic("Протести и дебата во парламентот") == "Политика"

    def test_detects_topic_from_common_english_news_words(self):
        assert detect_topic("Government announces election summit") == "Политика"
        assert detect_topic("Markets react to inflation and tariffs") == "Економија"
        assert detect_topic("New software and AI chip launch") == "Технологија"


# ── normalize_headline ────────────────────────────────────────────

class TestNormalizeHeadline:
    def test_strip_prefixes(self):
        assert normalize_headline("ВИДЕО: Ова е наслов") == "Ова е наслов"
        assert normalize_headline("ФОТО: Галерија") == "Галерија"
        assert normalize_headline("БРЕЈКИНГ: Итни вести") == "Итни вести"
        assert normalize_headline("ЕКСКЛУЗИВНО: Интервју") == "Интервју"

    def test_strip_html(self):
        assert normalize_headline("<b>Наслов</b> со HTML") == "Наслов со HTML"

    def test_whitespace(self):
        assert normalize_headline("  Многу    празни   места  ") == "Многу празни места"

    def test_empty(self):
        assert normalize_headline("") == ""
        assert normalize_headline(None) == ""

    def test_normal_headline_unchanged(self):
        assert normalize_headline("Нормален наслов без префикси") == "Нормален наслов без префикси"

    def test_case_insensitive_prefix(self):
        assert normalize_headline("видео: мал наслов") == "мал наслов"
