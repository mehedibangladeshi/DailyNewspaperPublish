import io

from PIL import Image

from jugantor_epub import images


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def _png_bytes(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 50, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_download_image_resizes_when_wider_than_max_width(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(_png_bytes(1600, 800))
    )

    result = images.download_image("https://example.com/pic.png", max_width=800)

    assert result is not None
    filename, data = result
    assert filename.endswith(".jpg")
    resized = Image.open(io.BytesIO(data))
    assert resized.width == 800
    assert resized.height == 400  # aspect ratio preserved


def test_download_image_leaves_smaller_images_untouched(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(_png_bytes(300, 200))
    )

    filename, data = images.download_image("https://example.com/small.png", max_width=800)

    resized = Image.open(io.BytesIO(data))
    assert resized.size == (300, 200)


def test_download_image_returns_none_for_empty_url():
    assert images.download_image("") is None
    assert images.download_image(None) is None


def test_download_image_returns_none_on_undecodable_content(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(b"not an image")
    )

    assert images.download_image("https://example.com/broken.jpg") is None


def test_download_image_returns_none_on_request_failure(monkeypatch):
    import requests

    def _raise(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr(images._session, "get", _raise)

    assert images.download_image("https://example.com/unreachable.jpg") is None
