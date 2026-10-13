from core.ingestion import is_supported_display_language
from core.language import detect_language, transliterate_lat_to_cyr


def test_lang():
    texts = [
        ("Ово је ћирилица", "Српски језик на ћирилици."),
        ("Ovo je latinica", "Srpski jezik na latinici."),
        ("Vučić se sastao sa Trampom", "Predsednik Srbije u Vašingtonu."),
        ("Вучиќ се соочи со Трамп", "Претседателот на Македонија во Вашингтон."),
    ]

    for title, desc in texts:
        supported = is_supported_display_language(title, desc)
        lang = detect_language(f"{title}. {desc}")
        print(f"Title: {title}")
        print(f"  Detected: {lang}")
        print(f"  Supported: {supported}")
        print("-" * 10)


def test_transliterate_vecer():
    assert transliterate_lat_to_cyr("Vecer") == "Вечер"
    assert transliterate_lat_to_cyr("vecer") == "вечер"
    assert transliterate_lat_to_cyr("VECER") == "ВЕЧЕР"
    assert transliterate_lat_to_cyr("VEcer") == "Вечер"


if __name__ == "__main__":
    test_lang()
