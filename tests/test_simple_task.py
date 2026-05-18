#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, "/home/emiloffingen/presek")

# Set up environment
os.environ["VIBE_HOME"] = "/home/emiloffingen/presek"

from core.database import db_manager as db
from tasks.delivery import generate_daily_brief_task


def test_simple_briefing():
    """Test a simple briefing generation with direct execution."""
    print("Testing simple briefing generation...")

    # Try to generate a briefing directly without Celery
    print("\n1. Testing Serbian briefing generation (direct execution)...")
    try:
        # This will run the task directly in the current process
        result = generate_daily_brief_task(0, "sr")
        print(f"   ✅ Serbian briefing generated: {result}")
    except Exception as e:
        print(f"   ❌ Serbian briefing failed: {e}")
        import traceback

        traceback.print_exc()

    # Check if briefing was stored
    print("\n2. Checking database for generated briefing...")
    briefing = db.execute_one(
        "SELECT lang, LENGTH(content) as length FROM daily_briefings " "WHERE date = CURRENT_DATE AND lang = 'sr'"
    )

    if briefing:
        print(f"   ✅ Briefing found: {briefing['length']} characters")
        if briefing["length"] > 100:  # Should be much longer than test content
            print("   🎉 Looks like real AI-generated content!")
        else:
            print("   ⚠️  Content is short - might be fallback or test data")
    else:
        print("   ❌ No briefing found")


if __name__ == "__main__":
    test_simple_briefing()
