#!/usr/bin/env python3

import os
import sys
import time
sys.path.insert(0, '/home/emiloffingen/presek')

# Set up environment
os.environ['VIBE_HOME'] = '/home/emiloffingen/presek'

from database import db_manager as db

def check_briefings():
    """Check if briefings have been generated."""
    print("Checking generated briefings...")
    
    # Check for Serbian briefing
    sr_briefing = db.execute_one(
        "SELECT date, lang, LENGTH(content) as content_length, "
        "SUBSTRING(content FROM 1 FOR 100) as preview "
        "FROM daily_briefings WHERE date = CURRENT_DATE AND lang = 'sr'"
    )
    
    # Check for Macedonian briefing
    mk_briefing = db.execute_one(
        "SELECT date, lang, LENGTH(content) as content_length, "
        "SUBSTRING(content FROM 1 FOR 100) as preview "
        "FROM daily_briefings WHERE date = CURRENT_DATE AND lang = 'mk'"
    )
    
    print(f"\n📊 Briefing Generation Status:")
    print(f"   Date: {sr_briefing['date'] if sr_briefing else 'N/A'}")
    
    if sr_briefing:
        print(f"\n🇷🇸 Serbian Briefing:")
        print(f"   Language: {sr_briefing['lang']}")
        print(f"   Content length: {sr_briefing['content_length']} characters")
        print(f"   Preview: {sr_briefing['preview']}...")
    else:
        print(f"\n🇷🇸 Serbian Briefing: Not generated yet")
    
    if mk_briefing:
        print(f"\n🇲🇰 Macedonian Briefing:")
        print(f"   Language: {mk_briefing['lang']}")
        print(f"   Content length: {mk_briefing['content_length']} characters")
        print(f"   Preview: {mk_briefing['preview']}...")
    else:
        print(f"\n🇲🇰 Macedonian Briefing: Not generated yet")
    
    # Check if both are complete
    if sr_briefing and mk_briefing:
        print(f"\n✅ SUCCESS: Both briefings have been generated!")
        return True
    else:
        print(f"\n⏳ Still generating... Check back in a few minutes.")
        return False

if __name__ == "__main__":
    try:
        success = check_briefings()
        if not success:
            print(f"\n💡 The AI generation process can take several minutes.")
            print(f"🔄 You can run this script again later to check progress.")
    except Exception as e:
        print(f"\n💥 Error checking briefings: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)