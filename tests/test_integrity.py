from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


class TestAstroFrontendIntegrity:
    def test_layout_contains_required_seo_structures(self):
        layout = _read("web/src/layouts/Layout.astro")
        head = _read("web/src/components/layout/LayoutHead.astro")
        boot = _read("web/public/js/presek-boot.js")
        # MK-only edition: html lang is fixed to "mk" (was dynamic per-locale).
        assert '<html lang="mk"' in layout
        assert "lang={lang}" in layout
        # Check for core SEO tags
        assert '<link rel="canonical"' in head
        assert '<link rel="alternate" hreflang=' in head
        # Check for theme logic usage
        assert "typeof localStorage !== 'undefined'" in boot

    def test_canonical_url_uses_logic(self):
        layout = _read("web/src/layouts/Layout.astro")
        locale_paths = _read("web/src/lib/localePaths.ts")
        layout_meta = _read("web/src/lib/layoutMeta.ts")
        # Canonical URL logic lives in the shared locale helper.
        assert "function buildCanonicalUrl" in locale_paths
        assert "buildCanonicalUrl" in layout_meta
        assert "resolveLayoutUrls" in layout
        assert "canonicalUrl" in layout

    def test_astro_config_has_correct_routing(self):
        config = _read("web/astro.config.mjs")
        assert "i18n:" in config
        assert "routing:" in config
        assert "site:" in config

    def test_status_route_renders_live_health_page(self):
        status_page = _read("web/src/pages/admin/status.astro")
        assert "fetch(`${API_URL}/health`" in status_page
        assert "Sostojba na sistemot" in status_page

    def test_header_fetches_stats_summary_when_page_does_not_supply_stats(self):
        header = _read("web/src/components/NYTHeader.astro")
        assert "shouldFetchStats" in header
        assert "fetchJsonCached" in header
        assert "/stats/summary" in header
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

    def test_homepage_cards_render_ingestion_aware_time(self):
        homepage = _read("web/src/components/NewsCard.astro")
        interactive_card = _read("web/src/components/NewsCard.tsx")
        lead = _read("web/src/components/home/LeadHero.astro")

        assert "getTimeStr(main.ingested_at || main.created_at)" in homepage
        assert "getTimeStr(main.ingested_at || main.created_at)" in interactive_card
        assert "getTimeStr(leadCluster.articles?.[0].ingested_at || leadCluster.articles?.[0].created_at)" in lead

    def test_generated_article_footnotes_are_sanitized_before_html_rendering(self):
        cluster_page = _read("web/src/pages/cluster/[slug].astro")
        layout = _read("web/src/lib/clusterPageLayout.ts")
        text_utils = _read("web/src/utils/textUtils.ts")

        assert "resolveHasCitationSources" in cluster_page
        assert "shouldShowExecutiveSummary" in layout
        assert "stripCitationMarkers" in text_utils
        assert "timeZone: 'Europe/Skopje'" in text_utils

    def test_macedonian_topic_and_entity_pages_keep_locale_contract(self):
        topic_page = _read("web/src/pages/mk/tema/[topic].astro")
        topic_component = _read("web/src/components/topic/TopicPage.astro")
        entity_page = _read("web/src/pages/mk/subjekt/[name].astro")
        entity_view = _read("web/src/components/entity/EntitySubjectView.astro")

        assert '<TopicPage locale="mk" />' in topic_page
        assert "locale?: 'sr' | 'mk'" in topic_component
        assert "loadTopicPageData" in topic_component
        assert "lang={lang}" in topic_component
        assert "Tema trenutno nije dostupna." not in topic_component
        assert "pojavljivanja" not in topic_component

        assert "EntitySubjectView" in entity_page
        assert "loadEntitySubject" in entity_page
        assert "homePath(lang, hostHeader)" in entity_view
        assert 'lang={lang}' in entity_view

    def test_editorial_interactive_widgets_avoid_placeholder_and_nan_output(self):
        source_comparison = _read("web/src/components/SourceComparisonIsland.tsx")
        research_qa = _read("web/src/lib/buildResearchQA.ts")

        assert "\n...\n" not in source_comparison
        assert (
            "const totalOverlap = Math.max(1, overlap.shared_clusters + overlap.s1_exclusive + overlap.s2_exclusive);"
            in source_comparison
        )
        assert "Math.max(0, Math.min(100" in source_comparison
        assert "buildResearchQA" in research_qa

    def test_homepage_maps_category_filter_to_api_category_param(self):
        homepage_data = _read("web/src/lib/homepageData.ts")
        assert "newsUrl.searchParams.set('category', category);" in homepage_data
        assert "newsUrl.searchParams.set('topic', category);" not in homepage_data

    def test_sync_token_is_not_sent_in_query_strings(self):
        # AccountSyncIsland/BriefingDeliveryIsland were removed in the MK-only
        # simplify; the remaining client helper must still use a header.
        personalization = _read("web/src/lib/personalization.js")

        assert "X-Sync-Token" in personalization
        assert "?token=" not in personalization
        # No client component should leak the sync token as a query param.
        for name in ("AdminDashboard.tsx", "ForYouIsland.tsx"):
            assert "?token=" not in _read(f"web/src/components/{name}")

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
        assert "def _public_article_payload(article, lang=" in news
        assert '"articles": [_public_article_payload(article, lang=lang) for article in arts]' in news
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

    def test_admin_synthesis_console_sends_csrf(self):
        # The old IntelligenceGraph.tsx / intelligence/synthesize-nodes flow was
        # removed in the MK-only simplify; the admin console now owns the
        # synthesis surface and must still send CSRF headers on its calls.
        dashboard = _read("web/src/components/AdminDashboard.tsx")
        assert "buildCsrfHeadersAsync" in dashboard
        assert "admin/synthesis-traces/recent" in dashboard

    def test_static_mount_disables_symlink_following(self):
        api_fast = _read("core/api_fast.py")
        assert 'StaticFiles(directory="static", follow_symlink=False)' in api_fast
        assert "serve_uploaded_image" in api_fast

    def test_request_size_limit_matches_api_max_query_length(self):
        security = _read("routes/security.py")
        assert "from core.runtime_limits import" in security
        assert "MAX_QUERY_PARAM_LENGTH" in security
        limits = _read("core/runtime_limits.py")
        assert "MAX_QUERY_PARAM_LENGTH = API_MAX_Q_LEN" in limits

    def test_delivery_component_decodes_vapid_key_before_subscribing(self):
        # BriefingDeliveryIsland was removed in the MK-only simplify; if any
        # component still subscribes to push it must decode the VAPID key first.
        candidates = sorted(ROOT.glob("web/src/components/**/*.tsx"))
        subscribers = [
            p for p in candidates
            if "applicationServerKey" in p.read_text(encoding="utf-8")
        ]
        for path in subscribers:
            text = path.read_text(encoding="utf-8")
            assert "decodeVapidPublicKey(" in text, f"{path} must decode the VAPID key"


class TestDeploymentIntegrity:
    def test_systemd_targets_fastapi_and_astro_runtime(self):
        fastapi_service = _read("deploy/systemd/presek-fastapi-unified.service")
        astro_service = _read("deploy/systemd/presek-astro.service")
        
        # Check for service runtime components
        assert "ExecStart=" in fastapi_service
        assert "ExecStart=" in astro_service
        assert "PORT=" in fastapi_service or "PORT=" in astro_service
        assert "UVICORN_WORKERS" in fastapi_service
        assert "--workers ${UVICORN_WORKERS:-2}" in fastapi_service

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
        rate_zones = _read("deploy/nginx/rate-limit-zones.conf")
        assert "upstream presek_fastapi" in nginx_conf
        assert "upstream presek_astro" in nginx_conf
        assert "limit_req_zone" not in nginx_conf
        assert "limit_req_zone" in rate_zones
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

    def test_preflight_runs_release_import_verification(self):
        preflight = _read("deploy/preflight_check.sh")
        assert "verify_release_imports.sh" in preflight

    def test_split_worker_units_have_systemd_hardening(self):
        for service_name in (
            "presek-worker-synthesis.service",
            "presek-worker-fasttrack.service",
            "presek-worker-maintenance.service",
        ):
            content = _read(f"deploy/systemd/{service_name}")
            assert "ProtectSystem=strict" in content
            assert "MemoryMax=" in content
            assert "--queues=" in content

    def test_deploy_restarts_explicit_services_in_order(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "restart_services_in_order" in deploy_script
        assert "presek-fastapi-unified.service" in deploy_script
        assert "presek-astro.service" in deploy_script

    def test_deploy_runs_post_deploy_smoke_and_auto_rollback(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "run_post_deploy_smoke_checks" in deploy_script
        assert "attempt_auto_rollback" in deploy_script
        assert "AUTO_ROLLBACK_ON_FAILURE" in deploy_script

    def test_ci_deploy_entrypoint_exists(self):
        ci_deploy = _read("deploy/ci_deploy.sh")
        assert "deploy/deploy_release.sh" in ci_deploy
        assert "DEPLOY_GIT_DIR" in ci_deploy

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
