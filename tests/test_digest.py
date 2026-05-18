from datetime import datetime

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

    def test_html_structure(self):
        html = render_html({}, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert 'lang="sr"' in html
