#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, "/home/emiloffingen/presek")

# Set up environment
os.environ["VIBE_HOME"] = "/home/emiloffingen/presek"

from core.database import db_manager as db
from tasks.delivery import _load_daily_brief_clusters


def test_language_filtering():
    """Test that the language filtering works correctly."""
    print("Testing language filtering in briefing generation...")

    # Test Serbian clusters
    print("\n1. Testing Serbian language filtering (lang='sr')...")
    sr_clusters = _load_daily_brief_clusters(3, "sr")
    print(f"   Found {len(sr_clusters)} Serbian clusters")

    # Test Macedonian clusters
    print("\n2. Testing Macedonian language filtering (lang='mk')...")
    mk_clusters = _load_daily_brief_clusters(3, "mk")
    print(f"   Found {len(mk_clusters)} Macedonian clusters")

    # Verify no overlap
    sr_cluster_ids = set(cluster["cluster_id"] for cluster in sr_clusters)
    mk_cluster_ids = set(cluster["cluster_id"] for cluster in mk_clusters)
    overlap = sr_cluster_ids.intersection(mk_cluster_ids)

    print("\n3. Verification:")
    print(f"   Serbian cluster IDs: {list(sr_cluster_ids)[:5]}...")  # Show first 5
    print(f"   Macedonian cluster IDs: {list(mk_cluster_ids)[:5]}...")  # Show first 5
    print(f"   Overlapping clusters: {len(overlap)} (should be 0)")

    if len(overlap) == 0:
        print("   ✅ SUCCESS: No overlap between languages!")
    else:
        print("   ❌ FAILURE: Found overlapping clusters!")
        return False

    # Test country filtering in database
    print("\n4. Testing direct database filtering...")
    sr_count = db.execute_one(
        "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = 'RS'"
    )["count"]
    mk_count = db.execute_one(
        "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' AND country = 'MK'"
    )["count"]

    print(f"   Serbian articles (last 24h): {sr_count}")
    print(f"   Macedonian articles (last 24h): {mk_count}")

    return True


if __name__ == "__main__":
    try:
        success = test_language_filtering()
        if success:
            print("\n🎉 All tests passed! Language separation is working correctly.")
        else:
            print("\n💥 Some tests failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
