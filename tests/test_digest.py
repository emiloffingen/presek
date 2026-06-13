from datetime import datetime

import core.database as database
import core.digest as digest
from core.digest import SR_DAYS, SR_MONTHS, render_html, sr_date


class TestMkDate:
    def test_known_date(self):
        dt = datetime(2026, 3, 29)  # Sunday
        result = sr_date(dt)
        assert "Nedelja" in result
        assert "29" in result
        assert "mart" in result
        assert "2026" in result

    def test_monday(self):
        dt = datetime(2026, 3, 23)  # Monday
        result = sr_date(dt)
        assert "Ponedeljak" in result

    def test_all_months_covered(self):
        assert len(SR_MONTHS) == 12
        assert SR_MONTHS[0] == "januar"
        assert SR_MONTHS[11] == "decembar"

    def test_all_days_covered(self):
        assert len(SR_DAYS) == 7


class TestRenderHtml:
    def test_basic_render(self):
        stories = {
            "Srbija": [
                {
                    "title": "Test naslov",
                    "link": "https://example.com",
                    "source": "MIA",
                    "summary": "rezime",
                    "source_count": 3,
                }
            ]
        }
        start = datetime(2026, 3, 22)
        end = datetime(2026, 3, 29)
        html = render_html(stories, start, end)

        assert "PRESEK" in html
        assert "Test naslov" in html
        assert "https://example.com" in html
        assert "MIA" in html
        assert "3 izvori" in html

    def test_empty_stories(self):
        html = render_html({}, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert "PRESEK" in html
        # Should render without errors even with no stories

    def test_no_summary(self):
        stories = {
            "Svet": [
                {
                    "title": "Naslov",
                    "link": "https://x.com",
                    "source": "CNN",
                    "summary": None,
                    "source_count": 1,
                }
            ]
        }
        html = render_html(stories, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert "Naslov" in html
        # No summary paragraph should appear
        assert "…</p>" not in html or "summary" not in html

    def test_multiple_categories(self):
        stories = {
            "Srbija": [
                {
                    "title": "MK vest",
                    "link": "#",
                    "source": "A",
                    "summary": None,
                    "source_count": 1,
                }
            ],
            "Balkan": [
                {
                    "title": "BK vest",
                    "link": "#",
                    "source": "B",
                    "summary": None,
                    "source_count": 1,
                }
            ],
        }
        html = render_html(stories, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert "Srbija" in html
        assert "Balkan" in html

    def test_synthetic_prioritization(self):
        stories = {
            "Srbija": [
                {
                    "title": "Raw Title",
                    "synthetic_headline": "Premium Synthetic Headline",
                    "link": "https://example.com/synth",
                    "source": "MIA",
                    "summary": "Raw summary text",
                    "synthesis_summary": "Premium synthesis summary text",
                    "source_count": 2,
                }
            ]
        }
        html = render_html(stories, datetime(2026, 3, 22), datetime(2026, 3, 29))
        assert "Premium Synthetic Headline" in html
        assert "Raw Title" not in html
        assert "Premium synthesis summary text" in html
        assert "Raw summary text" not in html

    def test_html_structure(self):
        html = render_html({}, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert 'lang="sr"' in html


class TestNewsletterDelivery:
    def test_newsletter_unsubscribe_links_are_locale_specific(self, monkeypatch):
        class FakeDb:
            def execute(self, *_args, **_kwargs):
                return [
                    {"email": "reader+sr@example.com", "locale": "sr"},
                    {"email": "reader+mk@example.com", "locale": "mk"},
                ]

        sent = []

        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("SMTP_PASS", "secret")
        monkeypatch.setattr(database, "db_manager", FakeDb())
        monkeypatch.setattr(
            digest,
            "fetch_daily_briefing",
            lambda **_kwargs: {
                "date": "2026-06-13",
                "content": "# Test brifing\n\n## Velika Slika\n\nGlavna vest dana.\n\n- Prvi signal\n",
                "metadata": {"stats": {"total_articles": 12, "pluralism_score": 4}},
            },
        )
        monkeypatch.setattr(
            digest,
            "fetch_top_stories",
            lambda **_kwargs: {"Politics": [{"title": "Story", "link": "#", "source": "A", "source_count": 1}]},
        )
        monkeypatch.setattr(
            digest,
            "send_email",
            lambda html, subject, _user, _password, to_address: sent.append((to_address, subject, html)) or True,
        )

        assert digest.send_newsletter_to_all_subscribers(days=1) == 2

        by_email = {email: html for email, _subject, html in sent}
        assert "lang=sr" in by_email["reader+sr@example.com"]
        assert "email=reader%2Bsr%40example.com" in by_email["reader+sr@example.com"]
        assert "lang=mk" in by_email["reader+mk@example.com"]
        assert "email=reader%2Bmk%40example.com" in by_email["reader+mk@example.com"]
        assert "Test brifing" in by_email["reader+sr@example.com"]
        assert "Glavna vest dana." in by_email["reader+sr@example.com"]


class TestMorningBriefingEmail:
    def test_parse_briefing_for_email_extracts_headline_and_big_picture(self):
        content = "# Geopoliticka napetost\n\n## Velika Slika\n\nGrcki ministar izjavio je da je ulazak u EU neminovnost.\n\n- Prvi signal za pracenje\n"
        parsed = digest.parse_briefing_for_email(content)
        assert parsed["title"] == "Geopoliticka napetost"
        assert "Grcki ministar" in parsed["big_picture"]
        assert parsed["bullets"] == ["Prvi signal za pracenje"]

    def test_render_morning_briefing_email_includes_briefing_links(self):
        html = digest.render_morning_briefing_email(
            {
                "date": "2026-06-13",
                "content": "# Test\n\n## Velika Slika\n\nTekst dana.\n",
                "metadata": {"stats": {"total_articles": 8, "pluralism_score": 3}},
            },
            datetime(2026, 6, 12),
            datetime(2026, 6, 13),
            locale="sr",
            stories_by_cat={"Srbija": [{"title": "Story", "link": "https://example.com", "source": "MIA"}]},
        )
        assert "Test" in html
        assert "Tekst dana." in html
        assert "https://presek.live/briefing?date=2026-06-13" in html
        assert "#audio" in html
        assert "Story" in html
