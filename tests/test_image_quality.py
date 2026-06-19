from nlp.image_quality import (
    classify_image_url,
    is_weak_image,
    pick_best_image_url,
    score_image_url,
)


def test_generated_cover_art_is_not_weak():
    assert is_weak_image("/static/generated/cluster-1.svg") is False
    quality, reason = classify_image_url("/static/generated/cluster-1.svg")
    assert quality == "ok"
    assert reason == "generated cover art"


def test_logo_urls_are_weak():
    assert is_weak_image("https://example.com/site/logo.png") is True
    quality, reason = classify_image_url("https://example.com/site/logo.png")
    assert quality == "weak"
    assert "logo" in reason


def test_online_in_hostname_is_not_weak():
    url = "https://strugaonline.mk/wp-content/uploads/2024/photo-1200x800.jpg"
    assert is_weak_image(url) is False
    quality, _reason = classify_image_url(url)
    assert quality == "ok"


def test_pick_best_image_url_prefers_editorial_photo():
    candidates = [
        ("https://cdn.example.com/thumb/logo-small.png", "Portal"),
        ("https://cdn.example.com/uploads/hero-1600x900.jpg", "SDK"),
    ]
    assert pick_best_image_url(candidates) == "https://cdn.example.com/uploads/hero-1600x900.jpg"


def test_score_image_url_rewards_high_quality_source():
    base = "https://cdn.example.com/uploads/story-1200x800.jpg"
    assert score_image_url(base, "SDK") > score_image_url(base, "Portal")
