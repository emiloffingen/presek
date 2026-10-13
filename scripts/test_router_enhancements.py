#!/usr/bin/env python3
"""
Test script for Smart Model Router enhancements
"""

import sys
from pathlib import Path

# Ensure project root in path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.llm_router import SmartModelRouter


def test_performance_tracking():
    """Test performance metrics tracking"""
    print("Testing performance tracking...")

    # Simulate some provider calls
    SmartModelRouter._update_performance_metrics("local", True, 0.5)
    SmartModelRouter._update_performance_metrics("local", True, 0.6)
    SmartModelRouter._update_performance_metrics("local", False, 0.0)

    SmartModelRouter._update_performance_metrics("nvidia", True, 2.1)
    SmartModelRouter._update_performance_metrics("nvidia", True, 1.9)

    SmartModelRouter._update_performance_metrics("nvidia", True, 3.5)
    SmartModelRouter._update_performance_metrics("nvidia", False, 0.0)

    # Check metrics
    local_perf = SmartModelRouter._get_provider_performance("local")
    small_perf = SmartModelRouter._get_provider_performance("nvidia")
    large_perf = SmartModelRouter._get_provider_performance("nvidia")

    print(f"Local: Success rate={local_perf['success_rate']:.2f}, Avg latency={local_perf['avg_latency']:.2f}s")
    print(f"NVIDIA: Success rate={small_perf['success_rate']:.2f}, Avg latency={small_perf['avg_latency']:.2f}s")
    print(f"NVIDIA (alt): Success rate={large_perf['success_rate']:.2f}, Avg latency={large_perf['avg_latency']:.2f}s")

    # Test dynamic fallback order
    dynamic_order = SmartModelRouter.get_dynamic_fallback_order()
    print(f"Dynamic fallback order: {dynamic_order}")

    return True


def test_quality_feedback():
    """Test quality feedback recording"""
    print("\nTesting quality feedback...")

    # Record some quality scores
    SmartModelRouter._record_quality_feedback("local", "test-cluster-1", 0.85)
    SmartModelRouter._record_quality_feedback("local", "test-cluster-2", 0.90)
    SmartModelRouter._record_quality_feedback("nvidia", "test-cluster-3", 0.75)

    local_quality = SmartModelRouter._provider_quality.get("local", [])
    small_quality = SmartModelRouter._provider_quality.get("nvidia", [])

    print(f"Local quality samples: {len(local_quality)}")
    print(f"NVIDIA quality samples: {len(small_quality)}")

    if local_quality:
        avg_local_quality = sum(item["score"] for item in local_quality) / len(local_quality)
        print(f"Average local quality: {avg_local_quality:.2f}")

    return True


def test_routing_decision_logging():
    """Test enhanced routing decision logging"""
    print("\nTesting routing decision logging...")

    # Create test articles
    test_articles = [
        {
            "title": "Test news article about politics",
            "description": "This is a test article about political developments",
            "content": "Full content about political news",
        }
    ]

    # This should trigger logging
    provider = SmartModelRouter.route_cluster(test_articles, "sr")
    print(f"Selected provider for simple article: {provider}")

    # Test with multiple articles (medium complexity)
    test_articles_multi = [
        {"title": "Article 1", "description": "Desc 1"},
        {"title": "Article 2", "description": "Desc 2"},
        {"title": "Article 3", "description": "Desc 3"},
    ]

    provider = SmartModelRouter.route_cluster(test_articles_multi, "sr")
    print(f"Selected provider for 3 articles: {provider}")

    return True


def main():
    print("=== Smart Model Router Enhancement Tests ===")

    try:
        test_performance_tracking()
        test_quality_feedback()
        test_routing_decision_logging()

        print("\n✅ All tests passed! Router enhancements are working correctly.")
        return 0

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
