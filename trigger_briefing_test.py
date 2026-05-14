#!/usr/bin/env python3

import os
import sys
sys.path.insert(0, '/home/emiloffingen/presek')

# Set up environment
os.environ['VIBE_HOME'] = '/home/emiloffingen/presek'

from tasks.delivery import generate_daily_brief_task

def test_direct_briefing_generation():
    """Test direct briefing generation for both languages."""
    print("Testing direct briefing generation...")
    
    print("\n1. Generating Serbian briefing...")
    try:
        result_sr = generate_daily_brief_task.apply_async(args=(0, "sr"))
        print(f"   ✅ Serbian task started: {result_sr.id}")
    except Exception as e:
        print(f"   ❌ Serbian task failed: {e}")
    
    print("\n2. Generating Macedonian briefing...")
    try:
        result_mk = generate_daily_brief_task.apply_async(args=(0, "mk"))
        print(f"   ✅ Macedonian task started: {result_mk.id}")
    except Exception as e:
        print(f"   ❌ Macedonian task failed: {e}")
    
    print(f"\n💡 Both tasks have been queued for Celery workers.")
    print(f"🔄 Use 'python verify_briefings.py' to check progress.")

if __name__ == "__main__":
    test_direct_briefing_generation()