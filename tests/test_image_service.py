import asyncio

import core.image_service as image_service


class _FakeResponse:
    def __init__(self, content, status_code=200):
        self._content = content
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aread(self):
        return self._content


class _FakeClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url):
        assert method == "GET"
        assert url == "https://example.com/image.png"
        return self._response


class _FakeImage:
    def __init__(self, width=400, height=300, mode="RGB"):
        self.width = width
        self.height = height
        self.mode = mode

    def convert(self, mode):
        self.mode = mode
        return self

    def resize(self, size, resample):
        self.width, self.height = size
        return self

    def save(self, path, fmt, quality, method):
        with open(path, "wb") as fh:
            fh.write(b"fake-webp")


def test_process_and_save_uses_async_stream(monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "_UPLOAD_ROOT", str(tmp_path))
    monkeypatch.setattr(
        image_service, "_resolve_public_ips", lambda url: {"203.0.113.10"}
    )
    monkeypatch.setattr(image_service, "_peer_ip", lambda resp: "203.0.113.10")
    monkeypatch.setattr(image_service.Image, "open", lambda buf: _FakeImage())
    monkeypatch.setattr(
        image_service.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeClient(_FakeResponse(b"fake-image-bytes")),
    )

    result = asyncio.run(
        image_service.image_service.process_and_save(
            "https://example.com/image.png", 42
        )
    )

    assert result == "/static/uploads/art_42.webp"
    assert (tmp_path / "art_42.webp").exists()
