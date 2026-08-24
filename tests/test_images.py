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


def test_fetch_raw_image_returns_decoded_image(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(_png_bytes(300, 200))
    )

    image = images.fetch_raw_image("https://example.com/pic.png")

    assert image is not None
    assert image.size == (300, 200)


def test_fetch_raw_image_returns_none_for_empty_url():
    assert images.fetch_raw_image("") is None
    assert images.fetch_raw_image(None) is None


def test_fetch_raw_image_returns_none_on_undecodable_content(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(b"not an image")
    )

    assert images.fetch_raw_image("https://example.com/broken.jpg") is None


def test_fetch_raw_image_returns_none_on_request_failure(monkeypatch):
    import requests

    def _raise(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr(images._session, "get", _raise)

    assert images.fetch_raw_image("https://example.com/unreachable.jpg") is None


def test_encode_image_resizes_when_wider_than_max_width():
    image = Image.new("RGB", (1600, 800), color=(200, 50, 50))

    filename, data = images.encode_image(image, "https://example.com/pic.png", max_width=800, quality=75)

    assert filename.endswith(".jpg")
    resized = Image.open(io.BytesIO(data))
    assert resized.width == 800
    assert resized.height == 400


def test_encode_image_leaves_smaller_images_untouched():
    image = Image.new("RGB", (300, 200), color=(200, 50, 50))

    _filename, data = images.encode_image(image, "https://example.com/small.png", max_width=800, quality=75)

    resized = Image.open(io.BytesIO(data))
    assert resized.size == (300, 200)


def test_encode_image_at_lower_quality_produces_smaller_output():
    image = Image.new("RGB", (800, 800), color=(120, 60, 200))

    _f1, high_quality_bytes = images.encode_image(image, "https://x/a.jpg", max_width=800, quality=90)
    _f2, low_quality_bytes = images.encode_image(image, "https://x/a.jpg", max_width=500, quality=40)

    assert len(low_quality_bytes) < len(high_quality_bytes)


def test_encode_image_does_not_mutate_the_passed_in_image():
    image = Image.new("RGB", (1600, 800), color=(200, 50, 50))

    images.encode_image(image, "https://x/a.jpg", max_width=800, quality=75)

    assert image.size == (1600, 800)


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
