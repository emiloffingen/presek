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
            "web/src/pages/cluster/[id].astro",
            "web/src/pages/subjekt/[name].astro",
        ):
            assert (ROOT / rel_path).is_file(), f"Missing Astro route: {rel_path}"

    def test_layout_keeps_theme_sync_and_canonical_metadata(self):
        layout = _read("web/src/layouts/Layout.astro")
        assert "<html lang=\"mk\">" in layout
        assert "const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('theme') : null;" in layout
        assert "window.localStorage.setItem('theme', theme);" not in layout
        assert "<link rel=\"canonical\" href={canonicalUrl} />" in layout
        assert "<meta property=\"og:url\" content={canonicalUrl} />" in layout

    def test_canonical_url_uses_astro_site_and_strips_trailing_slash(self):
        layout = _read("web/src/layouts/Layout.astro")
        # Must use Astro.site (not just env var) for canonical construction
        assert "Astro.site" in layout
        assert "new URL(" in layout
        # Must strip trailing slashes
        assert "replace(/\\/+$/" in layout or 'replace(/\\/+$/' in layout

    def test_astro_config_enforces_trailing_slash_never(self):
        config = _read("web/astro.config.mjs")
        assert "trailingSlash: 'never'" in config
        assert "site: 'https://presek.live'" in config

    def test_primary_pages_fetch_api_through_supported_base_url(self):
        # Pages can either import the shared apiBaseUrl() helper (which
        # centralises PUBLIC_API_URL + SSR/client fallback logic) or inline
        # the env lookup directly. Either pattern is acceptable.
        for rel_path in (
            "web/src/pages/index.astro",
            "web/src/pages/briefing.astro",
            "web/src/pages/stats.astro",
            "web/src/pages/cluster/[id].astro",
            "web/src/pages/subjekt/[name].astro",
            "web/src/pages/archive.astro",
        ):
            content = _read(rel_path)
            uses_helper = "apiBaseUrl" in content
            uses_inline_env = "PUBLIC_API_URL" in content
            assert uses_helper or uses_inline_env, (
                f"Missing apiBaseUrl()/PUBLIC_API_URL in {rel_path}"
            )
            if uses_inline_env:
                assert "127.0.0.1:5001/api" in content or "\"/api\"" in content, (
                    f"Missing FastAPI fallback in {rel_path}"
                )

        # The shared helper must still contain the canonical fallback values
        # so that the assertion above is actually meaningful.
        helper = _read("web/src/lib/apiBase.ts")
        assert "PUBLIC_API_URL" in helper
        assert "127.0.0.1:5001/api" in helper
        assert "'/api'" in helper or "\"/api\"" in helper

    def test_status_route_renders_live_health_page(self):
        status_page = _read("web/src/pages/status.astro")
        assert "fetch(`${API_URL}/health`)" in status_page
        assert "Состојба на системот" in status_page

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

    def test_public_news_routes_use_article_serializer_instead_of_returning_raw_rows(self):
        news = _read("routes/news.py")
        assert "def _public_article_payload(article):" in news
        assert '"articles": [_public_article_payload(article) for article in arts]' in news
        assert '"articles": public_articles' in news
        assert '"image_caption"' in news
        assert '"is_redundant"' in news

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
        fastapi_service = _read("deploy/systemd/presek-fastapi.service")
        astro_service = _read("deploy/systemd/presek-astro.service")

        assert "uvicorn api_fast:app" in fastapi_service
        assert "--port 5001" in fastapi_service
        assert "ensure_astro_build.sh" in astro_service
        assert "node ./dist/server/entry.mjs" in astro_service
        assert "PORT=3000" in astro_service

    def test_systemd_services_have_security_hardening(self):
        for svc in (
            "deploy/systemd/presek-fastapi.service",
            "deploy/systemd/presek-astro.service",
            "deploy/systemd/presek-beat.service",
            "deploy/systemd/presek-worker.service",
        ):
            content = _read(svc)
            assert "ProtectSystem=strict" in content, f"Missing ProtectSystem in {svc}"
            assert "NoNewPrivileges=yes" in content, f"Missing NoNewPrivileges in {svc}"
            assert "PrivateTmp=yes" in content, f"Missing PrivateTmp in {svc}"

    def test_systemd_services_have_memory_limits(self):
        for svc in (
            "deploy/systemd/presek-fastapi.service",
            "deploy/systemd/presek-astro.service",
            "deploy/systemd/presek-beat.service",
            "deploy/systemd/presek-worker.service",
        ):
            content = _read(svc)
            assert "MemoryMax=" in content, f"Missing MemoryMax in {svc}"

    def test_nginx_routes_api_and_site_to_separate_upstreams(self):
        nginx_conf = _read("deploy/nginx/presek.live.conf")
        assert "upstream presek_fastapi" in nginx_conf
        assert "upstream presek_astro" in nginx_conf
        assert "location ^~ /api/" in nginx_conf
        assert "proxy_pass http://presek_fastapi;" in nginx_conf
        assert "location / {" in nginx_conf
        assert "proxy_pass http://presek_astro;" in nginx_conf

    def test_nginx_applies_security_headers_to_astro_responses(self):
        nginx_conf = _read("deploy/nginx/presek.live.conf")
        headers_snippet = _read("deploy/nginx/security-headers.conf")
        assert "add_header Cache-Control \"no-transform\"" in nginx_conf
        assert "presek-security-headers.conf" in nginx_conf
        assert "add_header Strict-Transport-Security" in headers_snippet
        assert "add_header Content-Security-Policy" in headers_snippet
        assert "default-src 'self'" in headers_snippet

    def test_release_flow_reloads_nginx_before_smoke_checks(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "sudo nginx -t" in deploy_script
        assert "sudo systemctl reload \"$NGINX_SERVICE\"" in deploy_script
        assert "sudo systemctl restart \"$SYSTEMD_TARGET\"" in deploy_script

    def test_deploy_uses_file_locking(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "flock" in deploy_script

    def test_gitignore_covers_common_patterns(self):
        gitignore = _read(".gitignore")
        for pattern in (".env", "venv/", "__pycache__/", "node_modules/",
                        ".mypy_cache/", ".ruff_cache/", "web/dist/"):
            assert pattern in gitignore, f"Missing {pattern} in .gitignore"

    def test_smoke_check_covers_public_status_and_security_headers(self):
        smoke = _read("deploy/smoke_check.sh")
        assert "Public status page" in smoke
        assert "Content-Security-Policy" in smoke
        assert "Strict-Transport-Security" in smoke


class TestRuntimeDependencyIntegrity:
    def test_requirements_include_live_api_server_dependencies(self):
        pkg_names = {
            line.strip().split("==")[0].split(">=")[0].split("~=")[0].lower()
            for line in _read("requirements.txt").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        assert "fastapi" in pkg_names
        assert "uvicorn" in pkg_names
