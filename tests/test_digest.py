from datetime import datetime
from digest import mk_date, render_html, MK_MONTHS, MK_DAYS


class TestMkDate:
    def test_known_date(self):
        dt = datetime(2026, 3, 29)  # Sunday
        result = mk_date(dt)
        assert "Недела" in result
        assert "29" in result
        assert "март" in result
        assert "2026" in result

    def test_monday(self):
        dt = datetime(2026, 3, 23)  # Monday
        result = mk_date(dt)
        assert "Понеделник" in result

    def test_all_months_covered(self):
        assert len(MK_MONTHS) == 12
        assert MK_MONTHS[0] == "јануари"
        assert MK_MONTHS[11] == "декември"

    def test_all_days_covered(self):
        assert len(MK_DAYS) == 7


class TestRenderHtml:
    def test_basic_render(self):
        stories = {
            "Srbija": [
                {
                    "title": "Тест наслов",
                    "link": "https://example.com",
                    "source": "MIA",
                    "summary": "Резиме",
                    "source_count": 3,
                }
            ]
        }
        start = datetime(2026, 3, 22)
        end = datetime(2026, 3, 29)
        html = render_html(stories, start, end)

        assert "PRESEK" in html
        assert "Тест наслов" in html
        assert "https://example.com" in html
        assert "MIA" in html
        assert "3 извори" in html

    def test_empty_stories(self):
        html = render_html({}, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert "PRESEK" in html
        # Should render without errors even with no stories

    def test_no_summary(self):
        stories = {
            "Свет": [
                {
                    "title": "Наслов",
                    "link": "https://x.com",
                    "source": "CNN",
                    "summary": None,
                    "source_count": 1,
                }
            ]
        }
        html = render_html(stories, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert "Наслов" in html
        # No summary paragraph should appear
        assert "…</p>" not in html or "summary" not in html

    def test_multiple_categories(self):
        stories = {
            "Srbija": [
                {
                    "title": "МК Вест",
                    "link": "#",
                    "source": "A",
                    "summary": None,
                    "source_count": 1,
                }
            ],
            "Балкан": [
                {
                    "title": "БК Вест",
                    "link": "#",
                    "source": "B",
                    "summary": None,
                    "source_count": 1,
                }
            ],
        }
        html = render_html(stories, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert "Srbija" in html
        assert "Балкан" in html

    def test_html_structure(self):
        html = render_html({}, datetime(2026, 1, 1), datetime(2026, 1, 2))
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert 'lang="mk"' in html
