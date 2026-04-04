"""
Integrity tests to ensure the hybrid SSR/React architecture is whole and unified.
Verifies that critical assets, data structures, and theme markers are present.
"""
import pytest
from unittest.mock import patch, MagicMock
import os

@pytest.fixture
def app():
    """Create Flask test app with minimal mocks."""
    with patch.dict(os.environ, {"SECRET_KEY": "test-integrity-key"}), \
         patch('utils.redis_client'), \
         patch('database.db_manager.execute', return_value=[]), \
         patch('database.db_manager.execute_one', return_value={"count": 0, "n": 0}):
        from app import app as flask_app
        flask_app.config['TESTING'] = True
        yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

class TestArchitectureIntegrity:
    """Verifies that the core architecture isn't broken."""
    
    def test_ssr_mounting_point(self, client):
        """React needs #root to mount. Ensure it exists on all major pages."""
        pages = ["/", "/briefing", "/stats", "/izvori", "/arhiva"]
        for path in pages:
            resp = client.get(path)
            assert b'id="root"' in resp.data, f"Mounting point #root missing on {path}"

    def test_hydration_data_presence(self, client):
        """Major pages must provide hydration data to avoid flickers."""
        page_data_markers = [
            ("/", b"__INITIAL_DATA__"),
            ("/briefing", b"__INITIAL_BRIEFING_DATA__"),
            ("/stats", b"__INITIAL_STATS_DATA__"),
            ("/izvori", b"__INITIAL_SOURCES_DATA__"),
            ("/arhiva", b"__INITIAL_ARCHIVE_DATA__"),
        ]
        for path, marker in page_data_markers:
            resp = client.get(path)
            assert marker in resp.data, f"Hydration marker {marker} missing on {path}"

    def test_theme_sync_marker(self, client):
        """The <html> tag must have a theme class for SSR consistency."""
        resp = client.get("/")
        # Should have class="dark" or class="" (defaulting to dark in our logic)
        assert b'<html lang="mk" class="dark">' in resp.data or b'<html lang="mk" class="">' in resp.data

    def test_vite_asset_injection(self, client):
        """Vite assets must be injected into the head/body."""
        resp = client.get("/")
        # Check for module script injection
        assert b'type="module"' in resp.data
        # Check for stylesheet injection (either dist or dev server)
        assert b'rel="stylesheet"' in resp.data

class TestDataStructureSync:
    """Verifies that the data passed to SSR matches what React expects."""
    
    def test_initial_data_schema(self, client):
        """Check if __INITIAL_DATA__ contains the expected keys."""
        resp = client.get("/")
        # Very basic check that it looks like valid JSON-ish script
        assert b'"clusters"' in resp.data
        assert b'"trending"' in resp.data
        assert b'"theme"' in resp.data

    def test_sources_schema(self, client):
        """Check if __INITIAL_SOURCES_DATA__ contains expected keys."""
        resp = client.get("/izvori")
        assert b'"sources"' in resp.data
        assert b'"hot_sources"' in resp.data
