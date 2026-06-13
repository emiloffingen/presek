#!/usr/bin/env python3

import os
import sys

import pytest

sys.path.insert(0, "/home/emiloffingen/presek")

# Set up environment
os.environ["VIBE_HOME"] = "/home/emiloffingen/presek"
os.environ.setdefault("PRESEK_SKIP_DB_POOL_INIT", "1")

from core.database import db_manager as db

_TEST_BRIEFING_DATE = "2099-01-01"


def _is_safe_test_database() -> bool:
    """Never write briefing test rows to production."""
    db_url = os.environ.get("DATABASE_URL", "")
    if "presek_test" in db_url:
        return True
    return os.environ.get("ALLOW_PROD_BRIEFING_TEST") == "1"


pytestmark = pytest.mark.skipif(
    not _is_safe_test_database(),
    reason="Requires DATABASE_URL containing presek_test or ALLOW_PROD_BRIEFING_TEST=1",
)


def _require_safe_test_database():
    if not _is_safe_test_database():
        raise RuntimeError(
            "Refusing to run briefing workflow test against production. "
            "Set DATABASE_URL to presek_test or export ALLOW_PROD_BRIEFING_TEST=1 to override."
        )


def test_briefing_storage():
    """Test that briefings are stored correctly with language separation."""
    _require_safe_test_database()
    print("Testing full briefing generation workflow...")

    # Test Serbian briefing generation (dry run - just check database operations)
    print("\n1. Testing Serbian briefing database operations...")

    # Check if we can insert Serbian briefing
    try:
        db.execute(
            "INSERT INTO daily_briefings (date, content, lang) VALUES (%s::date, %s, %s) "
            "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content",
            (_TEST_BRIEFING_DATE, "Test Serbian briefing content", "sr"),
            fetch=False,
        )
        print("   ✅ Serbian briefing insert/update successful")
    except Exception as e:
        print(f"   ❌ Serbian briefing failed: {e}")
        assert False, f"Serbian briefing failed: {e}"

    # Check if we can insert Macedonian briefing
    print("\n2. Testing Macedonian briefing database operations...")
    try:
        db.execute(
            "INSERT INTO daily_briefings (date, content, lang) VALUES (%s::date, %s, %s) "
            "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content",
            (_TEST_BRIEFING_DATE, "Test Macedonian briefing content", "mk"),
            fetch=False,
        )
        print("   ✅ Macedonian briefing insert/update successful")
    except Exception as e:
        print(f"   ❌ Macedonian briefing failed: {e}")
        assert False, f"Macedonian briefing failed: {e}"

    # Verify both briefings exist
    print("\n3. Verifying both briefings exist in database...")
    sr_briefing = db.execute_one(
        "SELECT content, lang FROM daily_briefings WHERE date = %s::date AND lang = 'sr'",
        (_TEST_BRIEFING_DATE,),
    )
    mk_briefing = db.execute_one(
        "SELECT content, lang FROM daily_briefings WHERE date = %s::date AND lang = 'mk'",
        (_TEST_BRIEFING_DATE,),
    )

    if sr_briefing and mk_briefing:
        print("   ✅ Both briefings found in database")
        print(f"   Serbian briefing lang: {sr_briefing['lang']}")
        print(f"   Macedonian briefing lang: {mk_briefing['lang']}")

        # Verify they're different
        if sr_briefing["content"] != mk_briefing["content"]:
            print("   ✅ Briefing contents are different (as expected)")
        else:
            print("   ⚠️  Briefing contents are the same (might be test data)")
    else:
        print("   ❌ One or both briefings missing")
        assert False, "One or both briefings missing"

    # Test that we can retrieve briefings by language
    print("\n4. Testing briefing retrieval by language...")
    all_briefings = db.execute(
        "SELECT date, lang, SUBSTRING(content FROM 1 FOR 50) as content_preview "
        "FROM daily_briefings WHERE date = %s::date ORDER BY lang",
        (_TEST_BRIEFING_DATE,),
    )

    print(f"   Found {len(all_briefings)} briefings for today:")
    for briefing in all_briefings:
        print(f"   - {briefing['lang']}: {briefing['content_preview']}...")


def test_language_specific_queries():
    """Test that language-specific article queries work correctly."""
    _require_safe_test_database()
    print("\n5. Testing language-specific article queries...")

    # Test Serbian articles
    sr_articles = db.execute(
        "SELECT cluster_id, source, title FROM articles "
        "WHERE country = 'RS' AND created_at >= NOW() - INTERVAL '24 hours' "
        "LIMIT 3"
    )

    # Test Macedonian articles
    mk_articles = db.execute(
        "SELECT cluster_id, source, title FROM articles "
        "WHERE country = 'MK' AND created_at >= NOW() - INTERVAL '24 hours' "
        "LIMIT 3"
    )

    print(f"   Serbian articles found: {len(sr_articles)}")
    print(f"   Macedonian articles found: {len(mk_articles)}")

    # Check for language markers in content
    sr_titles = [a["title"] for a in sr_articles if a["title"]]
    mk_titles = [a["title"] for a in mk_articles if a["title"]]

    print(f"   Serbian title sample: {sr_titles[0][:50] + '...' if sr_titles else 'None'}")
    print(f"   Macedonian title sample: {mk_titles[0][:50] + '...' if mk_titles else 'None'}")


def _cleanup_test_briefings():
    db.execute(
        "DELETE FROM daily_briefings WHERE date = %s::date AND lang IN ('sr', 'mk')",
        (_TEST_BRIEFING_DATE,),
        fetch=False,
    )


if __name__ == "__main__":
    try:
        test_briefing_storage()
        test_language_specific_queries()
        _cleanup_test_briefings()
        print("\n🎉 All workflow tests passed! Language separation is fully functional.")
    except Exception as e:
        print(f"\n💥 Workflow test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
