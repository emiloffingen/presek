import datetime
import json
import logging
import os
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


def _default_remote_provider() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return "nvidia"


class SmartModelRouter:
    _provider_performance = {}  # {provider: {success: int, total: int, latency: [float]}}
    _provider_quality = {}  # {provider: [{cluster_id: str, score: float, timestamp: datetime}]}
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

            redis_client.set(
                _ROUTER_PERF_KEY,
                json.dumps(SmartModelRouter._provider_performance),
                ex=_ROUTER_METRICS_TTL,
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
            redis_client.set(_ROUTER_QUALITY_KEY, json.dumps(quality_payload), ex=_ROUTER_METRICS_TTL)
        except Exception as e:
            log.debug(f"[router] Failed to persist metrics to Redis: {e}")

    @staticmethod
    def _update_performance_metrics(provider, success, latency):
        """Update performance statistics for a provider"""
        if provider not in SmartModelRouter._provider_performance:
            SmartModelRouter._provider_performance[provider] = {"success": 0, "total": 0, "latency": []}

        SmartModelRouter._provider_performance[provider]["total"] += 1
        if success:
            SmartModelRouter._provider_performance[provider]["success"] += 1
            SmartModelRouter._provider_performance[provider]["latency"].append(latency)

        # Keep last 100 samples
        if len(SmartModelRouter._provider_performance[provider]["latency"]) > 100:
            SmartModelRouter._provider_performance[provider]["latency"] = SmartModelRouter._provider_performance[
                provider
            ]["latency"][-100:]

        SmartModelRouter._persist_metrics_to_redis()

    @staticmethod
    def _get_provider_performance(provider):
        """Get performance statistics for a provider"""
        stats = SmartModelRouter._provider_performance.get(provider, {})
        return {
            "success_rate": stats.get("success", 0) / max(1, stats.get("total", 1)),
            "avg_latency": sum(stats.get("latency", [])) / max(1, len(stats.get("latency", [1]))),
        }

    @staticmethod
    def _record_quality_feedback(provider, cluster_id, quality_score):
        """Store quality metrics to inform future routing"""
        if provider not in SmartModelRouter._provider_quality:
            SmartModelRouter._provider_quality[provider] = []

        SmartModelRouter._provider_quality[provider].append(
            {"cluster_id": cluster_id, "score": quality_score, "timestamp": datetime.datetime.now()}
        )

        # Keep last 1000 samples per provider
        if len(SmartModelRouter._provider_quality[provider]) > 1000:
            SmartModelRouter._provider_quality[provider] = SmartModelRouter._provider_quality[provider][-1000:]

        SmartModelRouter._persist_metrics_to_redis()

    @staticmethod
    def _get_recent_quality_average(
        provider: str,
        *,
        min_samples: int | None = None,
        window_hours: int | None = None,
    ) -> float | None:
        """Rolling average quality score for a provider, or None if insufficient data."""
        min_samples = int(min_samples or os.environ.get("ROUTER_QUALITY_MIN_SAMPLES", "5"))
        window_hours = int(window_hours or os.environ.get("ROUTER_QUALITY_WINDOW_HOURS", "168"))
        samples = SmartModelRouter._provider_quality.get(provider, [])
        if not samples:
            return None

        cutoff = datetime.datetime.now() - datetime.timedelta(hours=window_hours)
        recent_scores = [
            float(sample["score"]) for sample in samples if sample.get("timestamp", datetime.datetime.min) >= cutoff
        ]
        if len(recent_scores) < min_samples:
            return None
        return sum(recent_scores) / len(recent_scores)

    @staticmethod
    def _apply_quality_adjustment(
        candidate: str,
        *,
        article_count: int,
        has_high_weight: bool,
        is_high_complexity: bool,
        routing_decision: dict,
    ) -> str:
        """Promote/demote provider candidates using recorded synthesis quality."""
        from core.runtime_limits import synthesis_local_only

        if synthesis_local_only() and candidate == "local":
            return candidate

        local_min = float(os.environ.get("ROUTER_LOCAL_MIN_QUALITY", "0.80"))

        if candidate == "local":
            if article_count >= 3 and not routing_decision.get("allow_local_multi_source"):
                synthesis_profile = (os.environ.get("SYNTHESIS_PROFILE") or "balanced").strip().lower()
                balanced_local_max = int(os.environ.get("ROUTER_BALANCED_LOCAL_MAX_ARTICLES", "5"))
                if (
                    synthesis_profile == "balanced"
                    and article_count <= balanced_local_max
                    and not is_high_complexity
                    and not has_high_weight
                ):
                    routing_decision["quality_adjustment"] = "balanced_local_medium"
                    return candidate

                routing_decision["quality_adjustment"] = "multi_source_avoids_local"
                return _default_remote_provider()

            local_avg = SmartModelRouter._get_recent_quality_average("local")
            if local_avg is not None and local_avg < local_min:
                routing_decision["quality_adjustment"] = "local_quality_below_threshold"
                routing_decision["local_quality_avg"] = round(local_avg, 3)
                return _default_remote_provider()

        return candidate

    @staticmethod
    def _finalize_route(
        candidate: str,
        reason: str,
        routing_decision: dict,
        *,
        article_count: int,
        has_high_weight: bool,
        is_high_complexity: bool,
    ) -> str:
        routing_decision["initial_candidate"] = candidate
        routing_decision["reason"] = reason
        chosen = SmartModelRouter._apply_quality_adjustment(
            candidate,
            article_count=article_count,
            has_high_weight=has_high_weight,
            is_high_complexity=is_high_complexity,
            routing_decision=routing_decision,
        )
        if chosen != candidate:
            routing_decision["reason"] = f"{reason}_quality_adjusted"
        from core.runtime_limits import local_synthesis_enabled

        if chosen == "local" and not local_synthesis_enabled():
            chosen = _default_remote_provider()
            routing_decision["reason"] = f"{routing_decision.get('reason', reason)}_local_disabled"
        routing_decision["chosen_provider"] = chosen
        log.info(f"[router] Decision: {json.dumps(routing_decision, ensure_ascii=False)}")
        return chosen

    @staticmethod
    def _synthesis_fallback_pressure() -> str:
        """Return synthesis quality pressure: ok, warn, or critical."""
        if os.environ.get("ROUTER_FALLBACK_PRESSURE_LOCAL", "true").lower() != "true":
            return "ok"
        try:
            from core.health import get_synthesis_quality_snapshot

            status = str((get_synthesis_quality_snapshot() or {}).get("status") or "ok").lower()
            if status in ("warn", "critical"):
                return status
        except Exception:
            log.debug("LLM router fallback")
        return "ok"

    @staticmethod
    def get_dynamic_fallback_order(task_type="synthesis"):
        """Generate fallback order based on recent provider performance"""
        from core.runtime_limits import synthesis_local_only

        if synthesis_local_only() and task_type in ("synthesis", "summarize", "translation"):
            return ["local"]

        SmartModelRouter._load_metrics_from_redis()
        from core.config import PROVIDER_FALLBACK_ORDER_SUMMARY, PROVIDER_RESERVE_FOR_SYNTHESIS

        base_order = list(PROVIDER_FALLBACK_ORDER_SUMMARY)

        # Exclude providers reserved for synthesis from non-synthesis tasks
        if PROVIDER_RESERVE_FOR_SYNTHESIS and task_type != "synthesis":
            base_order = [p for p in base_order if p not in PROVIDER_RESERVE_FOR_SYNTHESIS]

        # Sort by performance (success rate descending, latency ascending)
        providers_with_stats = []
        for provider in base_order:
            stats = SmartModelRouter._get_provider_performance(provider)
            providers_with_stats.append(
                {
                    "name": provider,
                    "score": stats["success_rate"] / max(0.1, stats["avg_latency"]),  # Balance success and speed
                }
            )

        # Sort by score, but keep local as final fallback
        sorted_providers = sorted(providers_with_stats, key=lambda x: x["score"], reverse=True)
        dynamic_order = [p["name"] for p in sorted_providers]

        from core.runtime_limits import local_synthesis_enabled

        if task_type == "synthesis" and not local_synthesis_enabled():
            return [provider for provider in dynamic_order if provider != "local"]

        # Ensure local is last
        if "local" in dynamic_order:
            dynamic_order.remove("local")
            dynamic_order.append("local")

        return dynamic_order

    @staticmethod
    def route_cluster(articles: list[dict], lang: str = "mk") -> str:
        """
        Determines the optimal LLM provider or local fallback for a given news cluster.
        Returns one of: 'local', 'nvidia', or 'enhanced_fallback' (empty input only).
        """
        from core.runtime_limits import synthesis_local_only

        SmartModelRouter._load_metrics_from_redis()
        if not articles:
            return "enhanced_fallback"

        if synthesis_local_only():
            if _local_model_available():
                return SmartModelRouter._finalize_route(
                    "local",
                    "synthesis_local_only",
                    {
                        "article_count": len(articles),
                        "local_available": True,
                        "prefer_local_synthesis": True,
                        "force_remote_high_complexity": False,
                        "is_system_busy": False,
                        "is_peak_hour": False,
                        "chosen_provider": "local",
                        "fallback_pressure": "ok",
                    },
                    article_count=len(articles),
                    has_high_weight=False,
                    is_high_complexity=False,
                )
            return "enhanced_fallback"

        article_count = len(articles)
        all_titles = " ".join([a.get("title") or "" for a in articles])
        all_text = all_titles + " " + " ".join([a.get("description") or "" for a in articles])

        # 1. Sport check & sports score conflicts
        is_sport = detect_topic(all_titles) == "Sport" or any(
            bool(_extract_sports_scores(a.get("title") or "")) for a in articles
        )
        has_score_conflict = False
        if is_sport and article_count > 1:
            scores = [
                set(_extract_sports_scores(a.get("title") or ""))
                | set(_extract_sports_scores(a.get("description") or ""))
                for a in articles
            ]
            all_scores = set().union(*scores)
            conflicting_scores = [s for s in all_scores if sum(1 for ms in scores if s in ms) < len(articles)]
            if conflicting_scores:
                has_score_conflict = True

        # 2. Political or economic weight check (requires deep analytical models)
        lowered_text = all_text.lower()
        political_terms = {
            "izbor",
            "glasanje",
            "vlada",
            "sobranie",
            "skupština",
            "парламент",
            "избор",
            "влада",
            "собрание",
            "mickos",
            "vucic",
        }
        economic_terms = {
            "cena",
            "inflacija",
            "budzet",
            "plata",
            "tržište",
            "ekonom",
            "цена",
            "инфлација",
            "буџет",
            "плата",
            "пазар",
        }

        has_high_weight = any(term in lowered_text for term in political_terms) or any(
            term in lowered_text for term in economic_terms
        )

        log.debug(
            f"[router] Routing info: count={article_count}, is_sport={is_sport}, score_conflict={has_score_conflict}, high_weight={has_high_weight}"
        )

        local_available = _local_model_available()
        prefer_local_synthesis = os.environ.get("LOCAL_SYNTHESIS_PREFER_LOCAL", "true").lower() == "true"
        synthesis_profile = (os.environ.get("SYNTHESIS_PROFILE") or "balanced").strip().lower()
        force_remote_high_complexity = (
            os.environ.get("LOCAL_SYNTHESIS_HIGH_COMPLEXITY_REMOTE", "true").lower() == "true"
        )

        # Check system load for adaptive routing
        system_load = os.getloadavg()[0]  # 1-minute load average
        cpu_count = os.cpu_count() or 1
        is_system_busy = system_load > cpu_count * 0.8  # >80% load

        is_high_complexity = article_count >= 5 or has_score_conflict or (article_count >= 3 and has_high_weight)

        # A/B testing: randomly override for experimentation
        ab_testing_enabled = os.environ.get("ROUTER_AB_TESTING", "false").lower() == "true"
        ab_test_triggered = False
        if ab_testing_enabled and random.random() < 0.1:  # 10% of requests
            ab_test_triggered = True

        # --- Decision Matrix ---

        # Enhanced logging for observability
        routing_decision = {
            "article_count": article_count,
            "is_sport": is_sport,
            "has_score_conflict": has_score_conflict,
            "has_high_weight": has_high_weight,
            "is_high_complexity": is_high_complexity,
            "local_available": local_available,
            "prefer_local_synthesis": prefer_local_synthesis,
            "force_remote_high_complexity": force_remote_high_complexity,
            "is_system_busy": is_system_busy,
            "is_peak_hour": False,
            "chosen_provider": None,
        }

        # Check if peak hour for cost optimization
        current_hour = datetime.datetime.now().hour
        routing_decision["is_peak_hour"] = 8 <= current_hour <= 20  # 8AM-8PM

        # A/B testing override
        if ab_test_triggered:
            override_target = random.choice(["local", _default_remote_provider()])
            log.info(f"[router/ab] Overriding to {override_target} for experimentation")
            routing_decision["ab_test"] = True
            return SmartModelRouter._finalize_route(
                override_target,
                "ab_test",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        # Free API / quality profile: remote APIs for medium+ complexity only.
        free_apis_enabled = os.environ.get("FREE_API_KEYS_ENABLED", "false").lower() == "true"
        use_quality_profile = synthesis_profile == "quality" or free_apis_enabled

        if synthesis_profile == "cost" and local_available and not is_high_complexity:
            return SmartModelRouter._finalize_route(
                "local",
                "cost_profile_local_first",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        if use_quality_profile and not is_high_complexity and article_count >= 3:
            return SmartModelRouter._finalize_route(
                _default_remote_provider(),
                "free_api_quality_optimization",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        fallback_pressure = SmartModelRouter._synthesis_fallback_pressure()
        routing_decision["fallback_pressure"] = fallback_pressure
        balanced_local_max = int(os.environ.get("ROUTER_BALANCED_LOCAL_MAX_ARTICLES", "5"))
        if synthesis_profile == "balanced" and local_available and not is_high_complexity:
            if article_count <= balanced_local_max and not has_high_weight:
                routing_decision["allow_local_multi_source"] = True

        if fallback_pressure == "critical" and not is_high_complexity and article_count >= 2:
            return SmartModelRouter._finalize_route(
                _default_remote_provider(),
                "fallback_pressure_quality_recovery",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        if fallback_pressure == "warn" and local_available and not is_high_complexity and article_count >= 2:
            routing_decision["allow_local_multi_source"] = True
            return SmartModelRouter._finalize_route(
                "local",
                "fallback_pressure_local_first",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        # Original cost-aware routing for when APIs aren't free
        if (
            (routing_decision["is_peak_hour"] or is_system_busy)
            and local_available
            and prefer_local_synthesis
            and not is_high_complexity
        ):
            return SmartModelRouter._finalize_route(
                "local",
                "peak_hour_cost_optimization",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        # If local is available, preferred, and it's NOT a high complexity story that we want to force remote for
        if local_available and prefer_local_synthesis and not (is_high_complexity and force_remote_high_complexity):
            return SmartModelRouter._finalize_route(
                "local",
                "local_preferred",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        # High Complexity: Serious disputes, large clusters, high political/economic weight, or sports conflicts
        if is_high_complexity:
            return SmartModelRouter._finalize_route(
                _default_remote_provider(),
                "high_complexity",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        # Medium Complexity: Standard news, moderate cluster size
        if article_count >= 3 or has_high_weight:
            return SmartModelRouter._finalize_route(
                _default_remote_provider(),
                "medium_complexity",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        # Low Complexity: 1-2 articles, straightforward routine news
        if local_available and prefer_local_synthesis:
            return SmartModelRouter._finalize_route(
                "local",
                "low_complexity",
                routing_decision,
                article_count=article_count,
                has_high_weight=has_high_weight,
                is_high_complexity=is_high_complexity,
            )

        return SmartModelRouter._finalize_route(
            _default_remote_provider(),
            "low_complexity_remote",
            routing_decision,
            article_count=article_count,
            has_high_weight=has_high_weight,
            is_high_complexity=is_high_complexity,
        )
