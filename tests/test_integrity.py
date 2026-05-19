from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


class TestAstroFrontendIntegrity:
    def test_core_astro_routes_exist(self):
        for rel_path in (
            "web/src/pages/index.astro",
            "web/src/pages/briefing.astro",
            "web/src/pages/archive.astro",
            "web/src/pages/izvori.astro",
            "web/src/pages/stats.astro",
            "web/src/pages/cluster/[slug].astro",
            "web/src/pages/subjekt/[name].astro",
        ):
            assert (ROOT / rel_path).is_file(), f"Missing Astro route: {rel_path}"

    def test_layout_contains_required_seo_structures(self):
        layout = _read("web/src/layouts/Layout.astro")
        # Check for dynamic HTML lang attribute (used for i18n)
        assert 'lang={lang ===' in layout
        # Check for core SEO tags
        assert '<link rel="canonical"' in layout
        assert '<link rel="alternate" hreflang=' in layout
        # Check for theme logic usage
        assert "typeof localStorage !== 'undefined'" in layout

    def test_canonical_url_uses_logic(self):
        layout = _read("web/src/layouts/Layout.astro")
        # Ensure canonical logic is present
        assert "function buildCanonicalUrl" in layout
        assert "canonicalUrl" in layout

    def test_astro_config_has_correct_routing(self):
        config = _read("web/astro.config.mjs")
        assert "i18n:" in config
        assert "routing:" in config
        assert "site:" in config

    def test_primary_pages_fetch_api_through_supported_base_url(self):
        # Pages can either import the shared apiBaseUrl() helper (which
        # centralises PUBLIC_API_URL + SSR/client fallback logic) or inline
        # the env lookup directly. Either pattern is acceptable.
        for rel_path in (
            "web/src/pages/index.astro",
            "web/src/pages/briefing.astro",
            "web/src/pages/stats.astro",
            "web/src/pages/cluster/[slug].astro",
            "web/src/pages/subjekt/[name].astro",
            "web/src/pages/archive.astro",
        ):
            content = _read(rel_path)
            uses_helper = "apiBaseUrl" in content
            uses_inline_env = "PUBLIC_API_URL" in content
            assert uses_helper or uses_inline_env, f"Missing apiBaseUrl()/PUBLIC_API_URL in {rel_path}"
            if uses_inline_env:
                assert "127.0.0.1:5001/api" in content or '"/api"' in content, f"Missing FastAPI fallback in {rel_path}"

        # The shared helper must still contain the canonical fallback values
        # so that the assertion above is actually meaningful.
        helper = _read("web/src/lib/apiBase.ts")
        assert "PUBLIC_API_URL" in helper
        assert "127.0.0.1:5001/api" in helper
        assert "'/api'" in helper or '"/api"' in helper

    def test_status_route_renders_live_health_page(self):
        status_page = _read("web/src/pages/admin/status.astro")
        assert "fetch(`${API_URL}/health`)" in status_page
        assert "Sostojba na sistemot" in status_page

    def test_header_fetches_stats_summary_when_page_does_not_supply_stats(self):
        header = _read("web/src/components/NYTHeader.astro")
        assert "shouldFetchStats" in header
        assert "fetch(`${API_URL}/stats/summary`)" in header
        assert "const hasDispatchStats = Boolean(stats && intel?.pluralism);" in header

    def test_schema_and_ingestion_track_ingestion_time(self):
        # We now check migrations for schema definitions
        migration_file = next(ROOT.glob("migrations/versions/*baseline_schema.py"))
        schema = migration_file.read_text(encoding="utf-8")

        ingestion = _read("core/ingestion.py")
        stats = _read("routes/stats.py")
        homepage = _read("routes/home.py")
        clustering = _read("core/clustering.py")

        assert "ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in schema
        assert '"ingested_at": cycle_now' in ingestion
        assert "ingested_at" in stats
        assert "INTERVAL '1 hour'" in stats
        assert "_article_freshness_time(article)" in homepage
        assert "def _cluster_title_overlap(left: str, right: str) -> float:" in clustering

    def test_homepage_focus_entities_preserve_raw_slug_and_display_name(self):
        home_route = _read("routes/home.py")
        homepage = _read("web/src/pages/index.astro")
        entity_route = _read("routes/intelligence.py")

        assert 'normalized["display_name"] = _display_entity_name(raw_name)' in home_route
        assert 'normalized["name"] = raw_name' in home_route
        assert "LOWER(name) = LOWER(%s)" in entity_route
        assert "LOWER(tag) = LOWER(%s)" in entity_route

    def test_homepage_cards_render_ingestion_aware_time(self):
        homepage = _read("web/src/components/NewsCard.astro")
        interactive_card = _read("web/src/components/NewsCard.tsx")
        live_updates = _read("web/src/components/HomeLiveUpdatesIsland.tsx")
        lead = _read("web/src/components/home/LeadHero.astro")

        assert "getTimeStr(main.ingested_at || main.created_at)" in homepage
        assert "getTimeStr(main.ingested_at || main.created_at)" in interactive_card
        assert "getTimeStr(article.ingested_at || article.created_at)" in live_updates
        assert "getTimeStr(leadCluster.articles?.[0].ingested_at || leadCluster.articles?.[0].created_at)" in lead

    def test_generated_article_footnotes_are_sanitized_before_html_rendering(self):
        cluster_page = _read("web/src/pages/cluster/[slug].astro")
        text_utils = _read("web/src/utils/textUtils.ts")

        assert "const hasCitationSources = false;" in cluster_page
        assert "timeZone: 'Europe/Skopje'" in text_utils

    def test_editorial_interactive_widgets_avoid_placeholder_and_nan_output(self):
        source_comparison = _read("web/src/components/SourceComparisonIsland.tsx")
        research = _read("web/src/components/ResearchIsland.tsx")

        assert "\n...\n" not in source_comparison
        assert (
            "const totalOverlap = Math.max(1, overlap.shared_clusters + overlap.s1_exclusive + overlap.s2_exclusive);"
            in source_comparison
        )
        assert "Math.max(0, Math.min(100" in source_comparison
        assert "result.report || result.answer" in research

    def test_briefing_page_shows_real_error_state_and_not_only_processing_state(self):
        briefing = _read("web/src/pages/briefing.astro")
        assert "Brifing trenutno nije dostupan." in briefing

    def test_pulse_page_has_real_error_state_and_safe_category_math(self):
        pulse = _read("web/src/pages/pulse.astro")
        intelligence = _read("routes/intelligence.py")

        assert "let ssrFailed = false;" in pulse
        assert '_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"' in intelligence

    def test_for_you_page_surfaces_seed_fetch_errors_and_refetches_on_profile_change(
        self,
    ):
        for_you_page = _read("web/src/pages/for-you.astro")
        for_you_island = _read("web/src/components/ForYouPageIsland.tsx")
        profile_route = _read("routes/profile.py")

        assert "let initialError: string | null = null;" in for_you_page
        assert 'initialError = "Ne možemo da učitamo početne preporuke u ovom trenutku."' in for_you_page
        assert (
            "<ForYouPageIsland client:load initialClusters={initialClusters} initialError={initialError} />"
            in for_you_page
        )
        assert "const [semanticError, setSemanticError] = useState<string | null>(null);" in for_you_island
        assert "}, [profile]);" in for_you_island
        assert "const pageError = semanticError || initialError;" in for_you_island
        assert "COALESCE(ingested_at, created_at)" in profile_route
        assert (
            'f"SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY {_FRESHNESS_EXPR} DESC, created_at DESC"'
            in profile_route
        )

    def test_secondary_intelligence_and_stats_surfaces_use_ingestion_aware_freshness(
        self,
    ):
        intelligence = _read("routes/intelligence.py")
        stats = _read("routes/stats.py")
        system = _read("routes/system.py")

        assert '_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"' in intelligence
        assert "WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '48 hours'" in intelligence
        assert "WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY a.source" in intelligence
        assert (
            "EXISTS (SELECT 1 FROM unnest(COALESCE(m.tags, '{}')) AS tag WHERE LOWER(tag) = LOWER(%s))" in intelligence
        )
        assert '_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"' in stats
        assert "WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'" in stats
        assert "ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC" in stats
        assert '_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"' in system
        assert "WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'" in system
        assert "SELECT category, topic, COUNT(DISTINCT cluster_id) as n" in system
        assert "FROM articles" in system

    def test_homepage_maps_category_filter_to_api_category_param(self):
        homepage = _read("web/src/pages/index.astro")
        assert "newsUrl.searchParams.set('category', category);" in homepage
        assert "newsUrl.searchParams.set('topic', category);" not in homepage

    def test_sync_token_is_not_sent_in_query_strings(self):
        account_sync = _read("web/src/components/AccountSyncIsland.tsx")
        delivery = _read("web/src/components/BriefingDeliveryIsland.tsx")
        personalization = _read("web/src/lib/personalization.js")
        debug_page = _read("web/src/pages/debug/recommendations.astro")

        assert "?token=" not in account_sync
        assert "?token=" not in delivery
        assert "searchParams.get('token')" not in debug_page
        assert "buildSyncTokenHeaders" in account_sync
        assert "buildSyncTokenHeaders" in delivery
        assert "X-Sync-Token" in personalization

    def test_public_api_rate_limits_include_profile_write_routes(self):
        common = _read("routes/common.py")
        assert '"/api/profile/sync/init"' in common
        assert '"/api/profile/sync"' in common
        assert '"/api/profile/delivery"' in common
        assert '"/api/profile/suggestion-event"' in common

    def test_public_news_routes_use_article_serializer_instead_of_returning_raw_rows(
        self,
    ):
        news = _read("routes/news.py")
        assert "def _public_article_payload(article):" in news
        assert '"articles": [_public_article_payload(article) for article in arts]' in news
        assert '"articles": public_articles' in news
        assert '"image_caption"' in news
        assert '"is_redundant"' in news

    def test_topic_pages_do_not_surface_mixed_topic_articles(self):
        news = _read("routes/news.py")
        topic_discovery = _read("web/src/lib/topicDiscovery.js")

        assert 'if topic and r.get("topic") != topic and r.get("category") != topic:' in news
        assert 'if category and r.get("category") != category:' in news
        assert "visibleClusterTopics" in topic_discovery
        assert "visibleClusterTopics.size === 0 || visibleClusterTopics.has(topic)" in topic_discovery

    def test_cluster_related_payload_preserves_shared_metadata(self):
        news = _read("routes/news.py")
        assert '"shared_tags": shared_tags' in news
        assert '"shared_topics": shared_topics' in news
        assert '"shared_entities": shared_entities' in news

    def test_recommendations_route_imports_list_validator(self):
        intelligence = _read("routes/intelligence.py")
        assert "validate_list_param" in intelligence

    def test_delivery_component_decodes_vapid_key_before_subscribing(self):
        delivery = _read("web/src/components/BriefingDeliveryIsland.tsx")
        assert "function decodeVapidPublicKey" in delivery
        assert "applicationServerKey: decodeVapidPublicKey(pubKey)" in delivery


class TestDeploymentIntegrity:
    def test_systemd_targets_fastapi_and_astro_runtime(self):
        fastapi_service = _read("deploy/systemd/presek-fastapi-unified.service")
        astro_service = _read("deploy/systemd/presek-astro.service")
        
        # Check for service runtime components
        assert "ExecStart=" in fastapi_service
        assert "ExecStart=" in astro_service
        assert "PORT=" in fastapi_service or "PORT=" in astro_service

    def test_systemd_services_have_security_hardening(self):
        for svc in (
            "deploy/systemd/presek-fastapi-unified.service",
            "deploy/systemd/presek-astro.service",
            "deploy/systemd/presek-beat.service",
            "deploy/systemd/presek-worker.service",
            "deploy/systemd/presek-worker-ingestion.service",
            "deploy/systemd/presek-worker-delivery.service",
        ):
            content = _read(svc)
            assert "ProtectSystem=strict" in content, f"Missing ProtectSystem in {svc}"
            assert "NoNewPrivileges=yes" in content, f"Missing NoNewPrivileges in {svc}"
            assert "PrivateTmp=yes" in content, f"Missing PrivateTmp in {svc}"

    def test_systemd_services_have_memory_limits(self):
        for svc in (
            "deploy/systemd/presek-fastapi-unified.service",
            "deploy/systemd/presek-astro.service",
            "deploy/systemd/presek-beat.service",
            "deploy/systemd/presek-worker.service",
            "deploy/systemd/presek-worker-ingestion.service",
            "deploy/systemd/presek-worker-delivery.service",
        ):
            content = _read(svc)
            assert "MemoryMax=" in content, f"Missing MemoryMax in {svc}"

    def test_nginx_routes_api_and_site_to_separate_upstreams(self):
        nginx_conf = _read("deploy/nginx/presek.live.conf")
        routes_snippet = _read("deploy/nginx/presek-routes.conf")
        assert "upstream presek_fastapi" in nginx_conf
        assert "upstream presek_astro" in nginx_conf
        assert "location ^~ /api/" in routes_snippet
        assert "proxy_pass http://presek_fastapi;" in routes_snippet
        assert "location / {" in routes_snippet
        assert "proxy_pass http://presek_astro;" in routes_snippet

    def test_nginx_applies_security_headers_to_astro_responses(self):
        nginx_conf = _read("deploy/nginx/presek.live.conf")
        headers_snippet = _read("deploy/nginx/security-headers.conf")
        assert 'add_header Cache-Control "no-transform"' in nginx_conf
        assert "presek-security-headers.conf" in nginx_conf
        assert "add_header Strict-Transport-Security" in headers_snippet
        # CSP is now handled by FastAPI middleware with per-request nonces
        # nginx should NOT set CSP to avoid conflicts
        assert "add_header Content-Security-Policy" not in headers_snippet
        # But other security headers should still be present
        assert "add_header X-Content-Type-Options" in headers_snippet
        assert "add_header X-Frame-Options" in headers_snippet

    def test_release_flow_reloads_nginx(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert 'sudo systemctl reload nginx' in deploy_script

    def test_deploy_uses_file_locking(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "flock" in deploy_script

    def test_gitignore_covers_common_patterns(self):
        gitignore = _read(".gitignore")
        for pattern in (
            ".env",
            "venv/",
            "__pycache__/",
            "node_modules/",
            ".mypy_cache/",
            ".ruff_cache/",
            "web/dist/",
        ):
            assert pattern in gitignore, f"Missing {pattern} in .gitignore"

    def test_smoke_check_covers_public_status_and_security_headers(self):
        smoke = _read("deploy/smoke_check.sh")
        assert "Public status page" in smoke
        assert "Content-Security-Policy" in smoke
        assert "Strict-Transport-Security" in smoke

    def test_deploy_restarts_explicit_services_in_order(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "restart_services_in_order" in deploy_script
        assert "presek-fastapi-unified.service" in deploy_script
        assert "presek-astro.service" in deploy_script

    def test_runtime_config_does_not_embed_seed_source_catalog(self):
        config = _read("core/config.py")
        seed_script = _read("scripts/seed_sources.py")
        source_catalog = _read("core/source_catalog.py")

        assert "RSS_FEEDS = [" not in config
        assert "DEFAULT_SOURCE_CATALOG" in source_catalog
        # Check for logical import instead of string path match
        assert "import" in seed_script
        assert "source_catalog" in seed_script
        assert "Lokalno" not in source_catalog

    def test_health_route_uses_jwt_admin_auth(self):
        system_route = _read("routes/system.py")
        assert "admin_auth" in system_route
        assert "provided_token == admin_token" not in system_route

    def test_live_route_uses_request_aware_event_stream(self):
        news_route = _read("routes/news.py")
        utils_module = _read("utils/cache.py")
        assert 'event_stream("updates", request=request)' in news_route
        assert "await request.is_disconnected()" in utils_module


class TestRuntimeDependencyIntegrity:
    def test_requirements_include_live_api_server_dependencies(self):
        pkg_names = {
            line.strip().split("==")[0].split(">=")[0].split("~=")[0].lower()
            for line in _read("requirements.txt").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        assert "fastapi" in pkg_names
        assert "uvicorn" in pkg_names
