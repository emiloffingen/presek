from unittest.mock import MagicMock

import pytest

from core import api_fast


class TestGeneratedFilePath:
    def test_rejects_path_traversal(self):
        assert api_fast._generated_file_path("../.env") is None
        assert api_fast._generated_file_path("../../etc/passwd") is None
        assert api_fast._generated_file_path("foo/bar.jpg") is None

    def test_rejects_invalid_extensions(self):
        assert api_fast._generated_file_path("cluster_abc.exe") is None
        assert api_fast._generated_file_path("cluster_abc.mp3") is None

    def test_accepts_safe_filename(self, tmp_path, monkeypatch):
        generated_dir = tmp_path / "generated"
        generated_dir.mkdir()
        image_path = generated_dir / "cluster_abc123.svg"
        image_path.write_text("<svg></svg>", encoding="utf-8")

        monkeypatch.setattr(api_fast, "_STATIC_ROOT", str(tmp_path))
        monkeypatch.setattr(api_fast, "_GENERATED_DIR", str(generated_dir))

        resolved = api_fast._generated_file_path("cluster_abc123.svg")
        assert resolved == str(image_path.resolve())


class TestMetricsAccess:
    @pytest.mark.anyio
    async def test_metrics_allowed_for_localhost(self):
        request = MagicMock()
        request.client = MagicMock(host="127.0.0.1")

        response = await api_fast.metrics(request)

        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_metrics_denied_for_remote_clients(self):
        request = MagicMock()
        request.client = MagicMock(host="203.0.113.10")

        response = await api_fast.metrics(request)

        assert response.status_code == 403
        assert response.body == b'{"detail":"Forbidden"}'


class TestUploadImageFilePath:
    def test_rejects_path_traversal(self):
        assert api_fast._upload_image_file_path("../.env") is None
        assert api_fast._upload_image_file_path("audio/briefing.mp3") is None
        assert api_fast._upload_image_file_path("art_abc.webp") is None

    def test_accepts_safe_filename(self, tmp_path, monkeypatch):
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir()
        image_path = uploads_dir / "art_42.webp"
        image_path.write_bytes(b"webp")

        monkeypatch.setattr(api_fast, "_STATIC_ROOT", str(tmp_path))
        monkeypatch.setattr(api_fast, "_UPLOADS_DIR", str(uploads_dir))

        resolved = api_fast._upload_image_file_path("art_42.webp")
        assert resolved == str(image_path.resolve())
