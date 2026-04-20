import asyncio
from unittest.mock import patch


class _FakeStreamResponse:
    def __init__(self, content=b"fake-image", status_code=200):
        self._content = content
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aread(self):
        return self._content


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.stream_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method, url):
        self.stream_calls.append((method, url))
        return _FakeStreamResponse()


def test_process_and_save_uses_async_stream_context():
    from image_service import image_service

    fake_image = type(
        "FakeImage",
        (),
        {
            "width": 1200,
            "height": 800,
            "mode": "RGB",
            "resize": lambda self, size, resampling: self,
            "save": lambda self, path, fmt, quality=80, method=4: None,
        },
    )()

    with patch("image_service._resolve_public_ips", return_value=["1.2.3.4"]), \
         patch("image_service._peer_ip", return_value="1.2.3.4"), \
         patch("image_service.httpx.AsyncClient", _FakeAsyncClient), \
         patch("image_service.Image.open", return_value=fake_image):
        result = asyncio.run(image_service.process_and_save("https://example.com/image.jpg", 123))

    assert result == "/static/uploads/art_123.webp"
