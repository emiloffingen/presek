from nlp.categories import (
    ALLOWED_CATEGORIES,
    detect_category,
    detect_country,
    detect_subcategory,
    detect_topic,
    normalize_headline,
    validate_category,
)

# ── validate_category ─────────────────────────────────────────────


class TestValidateCategory:
    def test_valid_categories(self):
        for cat in ALLOWED_CATEGORIES:
            assert validate_category(cat) == cat

    def test_invalid_falls_back(self):
        assert validate_category("Politika") == "Srbija"
        assert validate_category("") == "Srbija"
        assert validate_category("Random") == "Srbija"

    def test_case_sensitive(self):
        assert validate_category("Srbija") == "Srbija"
        assert validate_category("EVROPA") == "Srbija"


# ── detect_category ───────────────────────────────────────────────


class TestDetectCategory:
    # Forced category
    def test_forced_category_valid(self):
        assert detect_category("Anything", forced_category="Evropa") == "Evropa"

    def test_forced_category_invalid_ignored(self):
        # Invalid forced category should be ignored, fall through to keyword scan
        result = detect_category("Berlin nov zakon", forced_category="Nevalidna")
        assert result == "Germanija"

    # Germany
    def test_germany_keywords(self):
        assert detect_category("Solc se sretna so delegacijata") == "Germanija"
        assert detect_category("Nov zakon vo Berlin") == "Germanija"
        assert detect_category("Bundestag glasase za budzetot") == "Germanija"

    # Balkan (Regional neighbors, excluding Serbia/Macedonia)
    def test_balkan_keywords(self):
        assert detect_category("Bugarija odrza konferencija") == "Balkan"
        assert detect_category("Protesti vo Tirana") == "Balkan"
        assert detect_category("Kurti i Rama na dijalog") == "Balkan"
        assert detect_category("Erdogan poseti Ankara") == "Balkan"

    # Serbia
    def test_serbia_keywords(self):
        assert detect_category("Vucic odrza konferencija") == "Srbija"
        assert detect_category("Protesti vo Belgrad") == "Srbija"
        assert detect_category("Kurti i Vucic na dijalog") == "Srbija"

    # Amerika
    def test_america_keywords(self):
        assert detect_category("Tramp potpisa ukaz") == "Amerika"
        assert detect_category("Pentagon soopsti") == "Amerika"
        assert detect_category("Kanada vovede vizi") == "Amerika"

    # Europa
    def test_europa_keywords(self):
        assert detect_category("Evropska unija donese odluka") == "Evropa"
        assert detect_category("Makron poseti Pariz") == "Evropa"
        assert detect_category("Britanski parlament glasase") == "Evropa"

    # Svet
    def test_svet_keywords(self):
        assert detect_category("Putin odrza govor") == "Svet"
        assert detect_category("Zelenski pobara pomos") == "Svet"
        assert detect_category("Napad vo Gaza") == "Svet"
        assert detect_category("Nato formira nova strategija") == "Svet"

    # Default
    def test_default_srbija(self):
        assert detect_category("Vremeto sutra ce bide soncevo") == "Srbija"

    # Description also scanned
    def test_description_matters(self):
        assert detect_category("nova odluka", description="Bundestag glasase") == "Germanija"

    # Short keyword boundary check (e.g., "sad" should not match "nasadi")
    def test_short_keyword_word_boundary(self):
        # "kina" should not match inside "prekinato"
        result = detect_category("Pregovorite se prekinati")
        assert result == "Srbija"  # Should NOT be "Svet"

    # Germany before Europa (order matters)
    def test_germany_before_europa(self):
        assert detect_category("Germanija vo Evropa") == "Germanija"

    # Serbia and Rusija -> Serbia should win for Serbian audience if it has keywords
    def test_serbia_before_svet(self):
        assert detect_category("Srbija i Rusija") == "Srbija"

    def test_category_scores_richer_group_over_stray_keyword(self):
        result = detect_category(
            "Evropska komisija vo Brisel rasprava za nov paket",
            description="Samit na Evropskata unija so novi merki i komisijata.",
        )
        assert result == "Evropa"

    def test_category_understands_common_english_geo_terms(self):
        assert detect_category("White House announces new tariffs") == "Amerika"
        assert detect_category("European Commission opens new Brussels talks") == "Evropa"

    def test_foreign_sports_clubs_do_not_default_to_macedonia(self):
        assert detect_category("Liam Rozenior vece ne e trener na Celzi") == "Evropa"
        assert detect_category("PSZ ga pobedi Nant so 3:0") == "Evropa"
        assert detect_category("Lebron ga predvodese Lejkers do pobeda nad Hjuston") == "Amerika"


# ── detect_subcategory ────────────────────────────────────────────


class TestDetectSubcategory:
    def test_skopje(self):
        # Skopje keywords with MK country
        assert detect_subcategory("Nastan vo Skopje", country="MK") == "Skopje"
        assert detect_subcategory("Karpos dobi nov park", country="MK") == "Skopje"
        # Skopje keywords with RS country should NOT match
        assert detect_subcategory("Karpos dobi nov park", country="RS") is None

    def test_beograd(self):
        # Beograd keywords with RS country
        assert detect_subcategory("Nastan vo Beograd", country="RS") == "Beograd"
        # Beograd keywords with MK country should NOT match (currently)
        assert detect_subcategory("Nastan vo Beograd", country="MK") is None

    def test_novi_sad(self):
        assert detect_subcategory("Festival u Novom Sadu", country="RS") == "Novi Sad"
        assert detect_subcategory("Vojvodina dobija nove investicije", country="RS") == "Novi Sad"

    def test_nis(self):
        assert detect_subcategory("Nis dostiže rekorde u turizmu", country="RS") == "Nis"
        assert detect_subcategory("Mediana je opština u Nišu", country="RS") == "Nis"

    def test_republika(self):
        assert detect_subcategory("Festival vo Ohrid", country="MK") == "Republika"
        assert detect_subcategory("Bitola dobiva nova bolnica", country="MK") == "Republika"

    def test_no_match(self):
        assert detect_subcategory("Vladata donese odluka", country="MK") is None

    def test_description_helps(self):
        assert detect_subcategory("Nov proekt", description="izgradba vo Beograd", country="RS") == "Beograd"


# ── detect_country ────────────────────────────────────────────────


class TestDetectCountry:
    def test_known_sources(self):
        assert detect_country("Tagesschau") == "DE"
        assert detect_country("CNN") == "US"
        assert detect_country("BBC News") == "GB"
        assert detect_country("Reuters") == "GB"
        assert detect_country("N1 Info") == "RS"

    def test_unknown_default(self):
        assert detect_country("Unknown Source") == "RS"
        assert detect_country("") == "RS"


class TestDetectTopic:
    def test_detects_topic_from_macedonian_keywords(self):
        assert detect_topic("Vladata usvoi nov budzet i merki") == "Ekonomija"
        assert detect_topic("Protesti i debata vo parlamentot") == "Politika"

    def test_detects_topic_from_common_english_news_words(self):
        assert detect_topic("Government announces election summit") == "Politika"
        assert detect_topic("Markets react to inflation and tariffs") == "Ekonomija"
        assert detect_topic("New software and AI chip launch") == "Tehnologija"


# ── normalize_headline ────────────────────────────────────────────


class TestNormalizeHeadline:
    def test_strip_prefixes(self):
        assert normalize_headline("VIDEO: ova e naslov") == "Ova e naslov"
        assert normalize_headline("FOTO: Galerija") == "Galerija"
        assert normalize_headline("BREJKING: Itni vesti") == "Itni vesti"
        assert normalize_headline("EKSKLUZIVNO: Intervju") == "Intervju"

    def test_strip_html(self):
        assert normalize_headline("<b>Naslov</b> so HTML") == "Naslov so HTML"

    def test_whitespace(self):
        assert normalize_headline("  Mnogu    prazni   mesta  ") == "Mnogu prazni mesta"

    def test_empty(self):
        assert normalize_headline("") == ""
        assert normalize_headline(None) == ""

    def test_normal_headline_unchanged(self):
        assert normalize_headline("Normalen naslov bez prefiksi") == "Normalen naslov bez prefiksi"

    def test_case_insensitive_prefix(self):
        assert normalize_headline("video: mal naslov") == "Mal naslov"
        assert normalize_headline("HAOS: Neredi na ulicama") == "Neredi na ulicama"
        assert normalize_headline("PANIKA u gradu: svi na ulicama") == "Svi na ulicama"
        assert normalize_headline("BRUTALNO! Oglasio se premijer") == "Oglasio se premijer"
        assert normalize_headline("SKANDALOZNO - Novi detalji") == "Novi detalji"
        assert normalize_headline("VAŽNO: Hitna sednica") == "Hitna sednica"
        assert normalize_headline("NEĆETE VEROVATI - šta se desilo") == "Šta se desilo"


    def test_strip_sources_suffix(self):
        assert normalize_headline("Naslov - 360 stepeni") == "Naslov"
        assert normalize_headline("vest | Sitel") == "Vest"
        assert normalize_headline("Informacija – SDK.mk") == "Informacija"

    def test_de_shouting(self):
        assert normalize_headline("ova E CELOSNO GLASEN NASLOV") == "Ova e celosno glasen naslov"
        # Prefix "SKANDAL" is stripped first, then the rest is de-shouted if it was screaming
        assert normalize_headline("SKANDAL VO MVR I VMRO") == "Vo MVR i VMRO"

    def test_quote_standardization(self):
        assert normalize_headline('Naslov so "citat"') == "Naslov so „citat“"
        assert normalize_headline("Naslov so ''citat''") == "Naslov so „citat“"
        assert normalize_headline("Naslov so 'citat'") == "Naslov so „citat“"

    def test_professional_polish(self):
        assert normalize_headline("Dali e ova kraj???") == "Dali e ova kraj?"
        assert normalize_headline("ova pocnuva so mala") == "Ova pocnuva so mala"

    def test_typographical_and_mathematical_rules(self):
        # Range En-dashes
        assert normalize_headline("Od 10-15 časova") == "Od 10–15 časova"
        assert normalize_headline("Vo periodot 2024 - 2026 godina") == "Vo periodot 2024–2026 godina"
        
        # Spaced En-dashes for clauses
        assert normalize_headline("Vlada - spremni sme za pregovori") == "Vlada – spremni sme za pregovori"
        assert normalize_headline("Vesti -- novi informacii") == "Vesti – novi informacii"
        
        # Ellipses conversion
        assert normalize_headline("Kraj na dramata...") == "Kraj na dramata…"
        assert normalize_headline("Dali e vozmožno....") == "Dali e vozmožno…"
        
        # Punctuation spacing (no space before, space after)
        assert normalize_headline("Ova e najvažno , veli toj .") == "Ova e najvažno, veli toj."
        assert normalize_headline("Dali e ova kraj?Da.") == "Dali e ova kraj? Da."
        
        # Multiplication sign
        assert normalize_headline("Stan od 3x4 metri") == "Stan od 3 × 4 metri"
        assert normalize_headline("Rezultat 5 * 6") == "Rezultat 5 × 6"
        
        # Quote compatibility and protection of apostrophes
        assert normalize_headline("D'Onofrio don't go") == "D'Onofrio don't go"
        assert normalize_headline('Veli: "Ova e „najvažno“"') == "„Ova e „najvažno““"


    def test_restores_known_person_and_political_bloc_casing(self):
        title = (
            "Manasievski: SDSM stana servis za interesite na srpskata opozicija, basanovic i zaev im krojat politikite"
        )
        # 'Manasievski:' is stripped because it matches the prefix regex
        assert normalize_headline(title) == (
            "SDSM stana servis za interesite na Srpskata opozicija, " "Basanovic i Zaev im krojat politikite"
        )

    def test_restores_known_country_casing(self):
        title = "Tramp veli oti saka da igra leka-poleka: ne brzam da ga zavrsam konfliktot vo iran"
        # This whole part matches the prefix regex and is stripped
        assert normalize_headline(title) == ("Ne brzam da ga zavrsam konfliktot vo Iran")
        assert normalize_headline("Direkten sudir na vozovi vo danska: nekolku lica bea povredeni") == (
            "Nekolku lica bea povredeni"
        )
        assert normalize_headline("Poranesen sef na NATO: evropa mora da stane voeno nezavisna od SAD") == (
            "Evropa mora da stane voeno nezavisna od SAD"
        )
        assert normalize_headline(
            "Najbogatiot covek vo jugoslavija ne bil tito: misteriozniot ugostitel od Srbija zarabotil milioni"
        ) == ("Misteriozniot ugostitel od Srbija zarabotil milioni")
