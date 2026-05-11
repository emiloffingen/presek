import os
import sys
import json
import re
import datetime
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clustering
from nlp.categories import detect_category, detect_topic


def simple_extract_entities(text):
    # Match capitalized words (simplified fallback for testing)
    return set(re.findall(r"[A-Za-z][a-z]+", text))


def test_clustering_suite():
    suite_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests/gold_standard_clustering.json",
    )
    if not os.path.exists(suite_path):
        print(f"Error: Gold standard file not found at {suite_path}")
        sys.exit(1)

    with open(suite_path, "r", encoding="utf-8") as f:
        suite = json.load(f)

    print(f"Running clustering regression suite ({len(suite)} cases)...\n")

    passed = 0
    failed = 0

    # Patch database.db_manager which is what clustering.py imports
    with patch("database.db_manager") as mock_db:
        for case in suite:
            title_a = case["title_a"]
            title_b = case["title_b"]
            should_cluster = case["should_cluster"]
            case_entities = set(case.get("entities", []))

            cid_a = "cluster-a"
            category_a = detect_category(title_a)
            topic_a = detect_topic(title_a)

            # Simulate entities in DB for the existing cluster
            mock_db.get_cluster_entities.return_value = {
                cid_a: case_entities or simple_extract_entities(title_a)
            }

            # Mock articles window - use a very recent date to avoid temporal decay
            recent_articles = [
                {
                    "title": title_a,
                    "cluster_id": cid_a,
                    "category": category_a,
                    "topic": topic_a,
                    "source": "Source A",
                    "created_at": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
            ]

            # Mock semantic search to focus on lexical/entity logic
            with patch("clustering.find_cluster_semantic", return_value=None):
                category_b = detect_category(title_b)
                topic_b = detect_topic(title_b)

                # Mock connection
                mock_conn = MagicMock()

                # Run the clustering logic
                result_cid = clustering.find_or_create_cluster(
                    mock_conn,
                    title_b,
                    recent_articles,
                    category=category_b,
                    topic=topic_b,
                    source="Source B",
                )

                is_clustered = result_cid == cid_a

                if is_clustered == should_cluster:
                    print(
                        f"✅ PASS: '{title_a[:30]}...' and '{title_b[:30]}...' -> {is_clustered}"
                    )
                    passed += 1
                else:
                    print(f"❌ FAIL: '{title_a[:30]}...' and '{title_b[:30]}...'")
                    print(f"   Expected: {should_cluster}, Got: {is_clustered}")
                    print(f"   Reason: {case['reason']}")
                    failed += 1

    print(f"\nResults: {passed} passed, {failed} failed.")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    test_clustering_suite()
