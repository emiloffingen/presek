import logging
import os
import json
import datetime
import random
from nlp.categories import detect_topic
from nlp.generation import _extract_sports_scores

log = logging.getLogger("presek.router")

_ROUTER_PERF_KEY = "router:provider_performance:v1"
_ROUTER_QUALITY_KEY = "router:provider_quality:v1"
_ROUTER_METRICS_TTL = 86400


def _local_model_available() -> bool:
    configured_path = os.environ.get("LOCAL_MODEL_PATH")
    if configured_path:
        return os.path.exists(configured_path)
    return os.path.exists("models/gemma-4-E2B-it-Q4_K_M.gguf")


class SmartModelRouter:
    _provider_performance = {}  # {provider: {success: int, total: int, latency: [float]}}
    _provider_quality = {}    # {provider: [{cluster_id: str, score: float, timestamp: datetime}]}
    _metrics_loaded = False

    @staticmethod
    def _load_metrics_from_redis() -> None:
        if SmartModelRouter._metrics_loaded:
            return
        SmartModelRouter._metrics_loaded = True
        try:
            from utils.cache import redis_client

            perf_raw = redis_client.get(_ROUTER_PERF_KEY)
            if perf_raw:
                SmartModelRouter._provider_performance.update(json.loads(perf_raw))

            quality_raw = redis_client.get(_ROUTER_QUALITY_KEY)
            if quality_raw:
                loaded = json.loads(quality_raw)
                for provider, samples in loaded.items():
                    SmartModelRouter._provider_quality[provider] = [
                        {
                            **sample,
                            "timestamp": datetime.datetime.fromisoformat(sample["timestamp"]),
                        }
                        for sample in samples
                    ]
        except Exception as e:
            log.debug(f"[router] Failed to load metrics from Redis: {e}")

    @staticmethod
    def _persist_metrics_to_redis() -> None:
        try:
            from utils.cache import redis_client

            redis_client.setex(
                _ROUTER_PERF_KEY,
                _ROUTER_METRICS_TTL,
                json.dumps(SmartModelRouter._provider_performance),
            )
            quality_payload = {
                provider: [
                    {
                        **sample,
                        "timestamp": sample["timestamp"].isoformat()
                        if isinstance(sample.get("timestamp"), datetime.datetime)
                        else sample.get("timestamp"),
                    }
                    for sample in samples
                ]
                for provider, samples in SmartModelRouter._provider_quality.items()
            }
            redis_client.setex(_ROUTER_QUALITY_KEY, _ROUTER_METRICS_TTL, json.dumps(quality_payload))
        except Exception as e:
            log.debug(f"[router] Failed to persist metrics to Redis: {e}")

    @staticmethod
    def _update_performance_metrics(provider, success, latency):
        """Update performance statistics for a provider"""
        if provider not in SmartModelRouter._provider_performance:
            SmartModelRouter._provider_performance[provider] = {'success': 0, 'total': 0, 'latency': []}
        
        SmartModelRouter._provider_performance[provider]['total'] += 1
        if success:
            SmartModelRouter._provider_performance[provider]['success'] += 1
            SmartModelRouter._provider_performance[provider]['latency'].append(latency)
        
        # Keep last 100 samples
        if len(SmartModelRouter._provider_performance[provider]['latency']) > 100:
            SmartModelRouter._provider_performance[provider]['latency'] = SmartModelRouter._provider_performance[provider]['latency'][-100:]

        SmartModelRouter._persist_metrics_to_redis()

    @staticmethod
    def _get_provider_performance(provider):
        """Get performance statistics for a provider"""
        stats = SmartModelRouter._provider_performance.get(provider, {})
        return {
            'success_rate': stats.get('success', 0) / max(1, stats.get('total', 1)),
            'avg_latency': sum(stats.get('latency', [])) / max(1, len(stats.get('latency', [1])))
        }

    @staticmethod
    def _record_quality_feedback(provider, cluster_id, quality_score):
        """Store quality metrics to inform future routing"""
        if provider not in SmartModelRouter._provider_quality:
            SmartModelRouter._provider_quality[provider] = []
        
        SmartModelRouter._provider_quality[provider].append({
            'cluster_id': cluster_id,
            'score': quality_score,
            'timestamp': datetime.datetime.now()
        })
        
        # Keep last 1000 samples per provider
        if len(SmartModelRouter._provider_quality[provider]) > 1000:
            SmartModelRouter._provider_quality[provider] = SmartModelRouter._provider_quality[provider][-1000:]

        SmartModelRouter._persist_metrics_to_redis()

    @staticmethod
    def get_dynamic_fallback_order(task_type="synthesis"):
        """Generate fallback order based on recent provider performance"""
        SmartModelRouter._load_metrics_from_redis()
        from core.config import PROVIDER_FALLBACK_ORDER_SUMMARY
        
        base_order = list(PROVIDER_FALLBACK_ORDER_SUMMARY)
        
        # Sort by performance (success rate descending, latency ascending)
        providers_with_stats = []
        for provider in base_order:
            stats = SmartModelRouter._get_provider_performance(provider)
            providers_with_stats.append({
                'name': provider,
                'score': stats['success_rate'] / max(0.1, stats['avg_latency'])  # Balance success and speed
            })

        # Sort by score, but keep local as final fallback
        sorted_providers = sorted(providers_with_stats, key=lambda x: x['score'], reverse=True)
        dynamic_order = [p['name'] for p in sorted_providers]
        
        # Ensure local is last
        if 'local' in dynamic_order:
            dynamic_order.remove('local')
            dynamic_order.append('local')
        
        return dynamic_order

    @staticmethod
    def route_cluster(articles: list[dict], lang: str = "sr") -> str:
        """
        Determines the optimal LLM provider or local fallback for a given news cluster.
        Returns one of: 'local', 'mistral_small', 'mistral_large', 'nvidia', or 'enhanced_fallback' (empty input only).
        """
        SmartModelRouter._load_metrics_from_redis()
        if not articles:
            return "enhanced_fallback"

        article_count = len(articles)
        all_titles = " ".join([a.get("title") or "" for a in articles])
        all_text = all_titles + " " + " ".join([a.get("description") or "" for a in articles])

        # 1. Sport check & sports score conflicts
        is_sport = detect_topic(all_titles) == "Sport" or any(bool(_extract_sports_scores(a.get("title") or "")) for a in articles)
        has_score_conflict = False
        if is_sport and article_count > 1:
            scores = [
                set(_extract_sports_scores(a.get("title") or "")) | set(_extract_sports_scores(a.get("description") or ""))
                for a in articles
            ]
            all_scores = set().union(*scores)
            conflicting_scores = [
                s for s in all_scores if sum(1 for ms in scores if s in ms) < len(articles)
            ]
            if conflicting_scores:
                has_score_conflict = True

        # 2. Political or economic weight check (requires deep analytical models)
        lowered_text = all_text.lower()
        political_terms = {
            "izbor", "glasanje", "vlada", "sobranie", "skupština", "парламент", "избор", "влада", "собрание", "mickos", "vucic"
        }
        economic_terms = {
            "cena", "inflacija", "budzet", "plata", "tržište", "ekonom", "цена", "инфлација", "буџет", "плата", "пазар"
        }
        
        has_high_weight = (
            any(term in lowered_text for term in political_terms) or
            any(term in lowered_text for term in economic_terms)
        )

        log.debug(f"[router] Routing info: count={article_count}, is_sport={is_sport}, score_conflict={has_score_conflict}, high_weight={has_high_weight}")

        local_available = _local_model_available()
        prefer_local_synthesis = os.environ.get("LOCAL_SYNTHESIS_PREFER_LOCAL", "true").lower() == "true"
        force_remote_high_complexity = (
            os.environ.get("LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE", "true").lower() == "true"
        )
        
        # Check system load for adaptive routing
        system_load = os.getloadavg()[0]  # 1-minute load average
        cpu_count = os.cpu_count() or 1
        is_system_busy = system_load > cpu_count * 0.8  # >80% load

        is_high_complexity = (
            article_count >= 5 or 
            has_score_conflict or 
            (article_count >= 3 and has_high_weight)
        )
        
        # A/B testing: randomly override for experimentation
        ab_testing_enabled = os.environ.get("ROUTER_AB_TESTING", "false").lower() == "true"
        ab_test_triggered = False
        if ab_testing_enabled and random.random() < 0.1:  # 10% of requests
            ab_test_triggered = True

        # --- Decision Matrix ---
        
        # Enhanced logging for observability
        routing_decision = {
            'article_count': article_count,
            'is_sport': is_sport,
            'has_score_conflict': has_score_conflict,
            'has_high_weight': has_high_weight,
            'is_high_complexity': is_high_complexity,
            'local_available': local_available,
            'prefer_local_synthesis': prefer_local_synthesis,
            'force_remote_high_complexity': force_remote_high_complexity,
            'is_system_busy': is_system_busy,
            'is_peak_hour': False,
            'chosen_provider': None
        }
        
        # Check if peak hour for cost optimization
        current_hour = datetime.datetime.now().hour
        routing_decision['is_peak_hour'] = 8 <= current_hour <= 20  # 8AM-8PM
        
        # A/B testing override
        if ab_test_triggered:
            override_target = random.choice(["local", "mistral_small", "mistral_large"])
            log.info(f"[router/ab] Overriding to {override_target} for experimentation")
            routing_decision['chosen_provider'] = override_target
            routing_decision['ab_test'] = True
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return override_target
        
        # Free API optimization: use Mistral for better quality when APIs are free
        free_apis_enabled = os.environ.get("FREE_API_KEYS_ENABLED", "false").lower() == "true"
        
        if free_apis_enabled and not is_high_complexity:
            # Even for low complexity, use Mistral Small for better quality when free
            routing_decision['chosen_provider'] = "mistral_small"
            routing_decision['reason'] = "free_api_quality_optimization"
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return "mistral_small"
        
        # Original cost-aware routing for when APIs aren't free
        if (routing_decision['is_peak_hour'] or is_system_busy) and local_available and not is_high_complexity:
            routing_decision['chosen_provider'] = "local"
            routing_decision['reason'] = "peak_hour_cost_optimization"
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return "local"
        
        # If local is available, preferred, and it's NOT a high complexity story that we want to force remote for
        if local_available and prefer_local_synthesis and not (is_high_complexity and force_remote_high_complexity):
            routing_decision['chosen_provider'] = "local"
            routing_decision['reason'] = "local_preferred"
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return "local"
        
        # High Complexity: Serious disputes, large clusters, high political/economic weight, or sports conflicts
        if is_high_complexity:
            routing_decision['chosen_provider'] = "mistral_large"
            routing_decision['reason'] = "high_complexity"
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return "mistral_large"

        # Medium Complexity: Standard news, moderate cluster size
        if article_count >= 3 or has_high_weight:
            routing_decision['chosen_provider'] = "mistral_small"
            routing_decision['reason'] = "medium_complexity"
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return "mistral_small"

        # Low Complexity: 1-2 articles, straightforward routine news
        if local_available:
            routing_decision['chosen_provider'] = "local"
            routing_decision['reason'] = "low_complexity"
            log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
            return "local"

        routing_decision['chosen_provider'] = "mistral_small"
        routing_decision['reason'] = "low_complexity_local_unavailable"
        log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
        return "mistral_small"
