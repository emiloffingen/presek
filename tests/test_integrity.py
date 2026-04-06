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
            "web/src/pages/entity/[name].astro",
        ):
            assert (ROOT / rel_path).is_file(), f"Missing Astro route: {rel_path}"

    def test_layout_keeps_theme_sync_and_canonical_metadata(self):
        layout = _read("web/src/layouts/Layout.astro")
        assert "<html lang=\"mk\">" in layout
        assert "window.localStorage.setItem('theme', theme);" in layout
        assert "<link rel=\"canonical\" href={canonicalUrl} />" in layout
        assert "<meta property=\"og:url\" content={canonicalUrl} />" in layout

    def test_primary_pages_fetch_api_through_supported_base_url(self):
        for rel_path in (
            "web/src/pages/index.astro",
            "web/src/pages/briefing.astro",
            "web/src/pages/stats.astro",
            "web/src/pages/cluster/[id].astro",
            "web/src/pages/entity/[name].astro",
            "web/src/pages/archive.astro",
        ):
            content = _read(rel_path)
            assert "PUBLIC_API_URL" in content, f"Missing PUBLIC_API_URL fallback in {rel_path}"
            assert "127.0.0.1:5001/api" in content or "\"/api\"" in content, f"Missing FastAPI fallback in {rel_path}"

    def test_status_route_renders_live_health_page(self):
        status_page = _read("web/src/pages/status.astro")
        assert "fetch(`${API_URL}/health`)" in status_page
        assert "Состојба На Системот" in status_page


class TestDeploymentIntegrity:
    def test_systemd_targets_fastapi_and_astro_runtime(self):
        fastapi_service = _read("deploy/systemd/presek-fastapi.service")
        astro_service = _read("deploy/systemd/presek-astro.service")

        assert "uvicorn api_fast:app" in fastapi_service
        assert "--port 5001" in fastapi_service
        assert "node ./dist/server/entry.mjs" in astro_service
        assert "PORT=3000" in astro_service

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
        assert "add_header Cache-Control \"no-transform\"" in nginx_conf
        assert "add_header Strict-Transport-Security" in nginx_conf
        assert "add_header Content-Security-Policy" in nginx_conf
        assert "default-src 'self'" in nginx_conf

    def test_release_flow_reloads_nginx_before_smoke_checks(self):
        deploy_script = _read("deploy/deploy_release.sh")
        assert "sudo nginx -t" in deploy_script
        assert "sudo systemctl reload \"$NGINX_SERVICE\"" in deploy_script
        assert "sudo systemctl restart \"$SYSTEMD_TARGET\"" in deploy_script

    def test_smoke_check_covers_public_status_and_security_headers(self):
        smoke = _read("deploy/smoke_check.sh")
        assert "<html lang=\\\"mk\\\">" in smoke
        assert "Public status page" in smoke
        assert "Content-Security-Policy" in smoke
        assert "Strict-Transport-Security" in smoke


class TestRuntimeDependencyIntegrity:
    def test_requirements_include_live_api_server_dependencies(self):
        requirements = {
            line.strip()
            for line in _read("requirements.txt").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        assert "fastapi" in requirements
        assert "uvicorn" in requirements
