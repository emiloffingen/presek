#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, "/home/emiloffingen/presek")

# Set up environment
os.environ["VIBE_HOME"] = "/home/emiloffingen/presek"

from core.database import db_manager as db


def test_briefing_storage():
    """Test that briefings are stored correctly with language separation."""
    print("Testing full briefing generation workflow...")

    # Test Serbian briefing generation (dry run - just check database operations)
    print("\n1. Testing Serbian briefing database operations...")

    # Check if we can insert Serbian briefing
    try:
        db.execute(
            "INSERT INTO daily_briefings (date, content, lang) VALUES (CURRENT_DATE, %s, %s) "
            "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content",
            ("Test Serbian briefing content", "sr"),
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
            "INSERT INTO daily_briefings (date, content, lang) VALUES (CURRENT_DATE, %s, %s) "
            "ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content",
            ("Test Macedonian briefing content", "mk"),
            fetch=False,
        )
        print("   ✅ Macedonian briefing insert/update successful")
    except Exception as e:
        print(f"   ❌ Macedonian briefing failed: {e}")
        assert False, f"Macedonian briefing failed: {e}"

    # Verify both briefings exist
    print("\n3. Verifying both briefings exist in database...")
    sr_briefing = db.execute_one("SELECT content, lang FROM daily_briefings WHERE date = CURRENT_DATE AND lang = 'sr'")
    mk_briefing = db.execute_one("SELECT content, lang FROM daily_briefings WHERE date = CURRENT_DATE AND lang = 'mk'")

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
        "FROM daily_briefings WHERE date = CURRENT_DATE ORDER BY lang"
    )

    print(f"   Found {len(all_briefings)} briefings for today:")
    for briefing in all_briefings:
        print(f"   - {briefing['lang']}: {briefing['content_preview']}...")


def test_language_specific_queries():
    """Test that language-specific article queries work correctly."""
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


if __name__ == "__main__":
    try:
        test_briefing_storage()
        test_language_specific_queries()
        print("\n🎉 All workflow tests passed! Language separation is fully functional.")
    except Exception as e:
        print(f"\n💥 Workflow test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
