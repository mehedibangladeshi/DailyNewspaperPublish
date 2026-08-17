import io

import pytest
import requests
from PIL import Image

from jugantor_epub import cover


def _opaque_rgba_png_bytes(width, height, color):
    image = Image.new("RGBA", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


# --- compose_cover (pure) ---------------------------------------------------


JUGANTOR_ACCENT_COLOR = (196, 12, 19)
PROTHOMALO_ACCENT_COLOR = (238, 65, 35)


def test_compose_cover_returns_canvas_at_expected_kindle_size():
    image = cover.compose_cover(None, "যুগান্তর", "১২ আগস্ট, ২০২৬", JUGANTOR_ACCENT_COLOR)

    assert image.size == (cover.COVER_WIDTH, cover.COVER_HEIGHT)


def test_compose_cover_background_is_white_at_top_left_corner():
    image = cover.compose_cover(None, "যুগান্তর", "১২ আগস্ট, ২০২৬", JUGANTOR_ACCENT_COLOR)

    assert image.getpixel((5, 5)) == cover.BACKGROUND_COLOR


def test_compose_cover_draws_accent_rule_in_given_color():
    image = cover.compose_cover(None, "যুগান্তর", "১২ আগস্ট, ২০২৬", JUGANTOR_ACCENT_COLOR)

    pixel = image.getpixel((cover.COVER_WIDTH // 2, cover.RULE_TOP + cover.RULE_HEIGHT // 2))

    assert pixel == JUGANTOR_ACCENT_COLOR


def test_compose_cover_draws_accent_rule_using_the_passed_source_color():
    image = cover.compose_cover(None, "প্রথম আলো", "১২ আগস্ট, ২০২৬", PROTHOMALO_ACCENT_COLOR)

    pixel = image.getpixel((cover.COVER_WIDTH // 2, cover.RULE_TOP + cover.RULE_HEIGHT // 2))

    assert pixel == PROTHOMALO_ACCENT_COLOR


def test_compose_cover_pastes_given_logo_image():
    logo = Image.new("RGBA", (500, 109), (0, 0, 255, 255))

    image = cover.compose_cover(logo, "যুগান্তর", "১২ আগস্ট, ২০২৬", JUGANTOR_ACCENT_COLOR)

    # center of the masthead area should now show the pasted (blue) logo
    pixel = image.getpixel((cover.COVER_WIDTH // 2, cover.LOGO_TOP + 20))
    assert pixel[2] > pixel[0]  # blue channel dominant, not background white


def test_compose_cover_renders_fallback_title_text_when_logo_missing():
    image = cover.compose_cover(None, "যুগান্তর", "১২ আগস্ট, ২০২৬", JUGANTOR_ACCENT_COLOR)

    region = image.crop((0, cover.LOGO_TOP, cover.COVER_WIDTH, cover.LOGO_TOP + 300))
    colors = region.getcolors(maxcolors=1_000_000)
    non_background = [c for _, c in colors if c != cover.BACKGROUND_COLOR]

    assert non_background, "expected fallback title text to be drawn"


def test_compose_cover_places_rule_at_the_original_fixed_position_for_jugantors_real_logo_size():
    """Regression: Jugantor's real masthead logo is 500x109. The dynamic
    rule/date placement (added to fix a taller logo overlapping them, see
    below) must still land at exactly the old fixed RULE_TOP/DATE_TOP for
    this size, so Jugantor's rendered cover is unchanged."""
    logo = Image.new("RGBA", (500, 109), (0, 0, 0, 255))

    image = cover.compose_cover(logo, "যুগান্তর", "১২ আগস্ট, ২০২৬", JUGANTOR_ACCENT_COLOR)

    pixel = image.getpixel((cover.COVER_WIDTH // 2, cover.RULE_TOP + cover.RULE_HEIGHT // 2))
    assert pixel == JUGANTOR_ACCENT_COLOR


def test_compose_cover_places_rule_below_a_taller_logo_instead_of_overlapping_it():
    """Regression: a taller logo (e.g. Prothom Alo's, before cropping) used
    to overlap the fixed RULE_TOP/DATE_TOP positions. The rule must now sit
    below wherever the logo actually ends."""
    tall_logo = Image.new("RGBA", (1200, 630), (0, 0, 255, 255))

    image = cover.compose_cover(tall_logo, "প্রথম আলো", "১২ আগস্ট, ২০২৬", PROTHOMALO_ACCENT_COLOR)

    scaled_height = round(630 * (cover.LOGO_MAX_WIDTH / 1200))
    logo_bottom = cover.LOGO_TOP + scaled_height
    expected_rule_top = logo_bottom + cover.LOGO_RULE_GAP

    pixel = image.getpixel((cover.COVER_WIDTH // 2, expected_rule_top + cover.RULE_HEIGHT // 2))
    assert pixel == PROTHOMALO_ACCENT_COLOR

    # and the rule must not fall inside the logo's own vertical span
    assert expected_rule_top >= logo_bottom


# --- _fetch_logo_image (I/O) -------------------------------------------------


def test_fetch_logo_image_returns_rgba_image_on_success(monkeypatch):
    png_bytes = _opaque_rgba_png_bytes(500, 109, (10, 20, 30, 255))
    monkeypatch.setattr(cover._session, "get", lambda url, timeout: _FakeResponse(png_bytes))

    image = cover._fetch_logo_image("https://cdn.jugantor.com/uploads/settings/logo-black.png")

    assert image is not None
    assert image.mode == "RGBA"
    assert image.size == (500, 109)


def test_fetch_logo_image_returns_none_on_request_failure(monkeypatch):
    def _boom(url, timeout):
        raise requests.RequestException("network down")

    monkeypatch.setattr(cover._session, "get", _boom)

    assert cover._fetch_logo_image("https://cdn.jugantor.com/uploads/settings/logo-black.png") is None


def test_fetch_logo_image_returns_none_on_undecodable_content(monkeypatch):
    monkeypatch.setattr(cover._session, "get", lambda url, timeout: _FakeResponse(b"not an image"))

    assert cover._fetch_logo_image("https://cdn.jugantor.com/uploads/settings/logo-black.png") is None


def test_fetch_logo_image_returns_none_when_url_is_falsy():
    assert cover._fetch_logo_image(None) is None
    assert cover._fetch_logo_image("") is None


# --- render_cover (wrapper: fetch + compose + encode) ------------------------


def test_render_cover_returns_valid_jpeg_of_kindle_cover_size(monkeypatch):
    png_bytes = _opaque_rgba_png_bytes(500, 109, (10, 20, 30, 255))
    monkeypatch.setattr(cover._session, "get", lambda url, timeout: _FakeResponse(png_bytes))

    result = cover.render_cover(
        "যুগান্তর",
        "১২ আগস্ট, ২০২৬",
        "https://cdn.jugantor.com/uploads/settings/logo-black.png",
        JUGANTOR_ACCENT_COLOR,
    )

    image = Image.open(io.BytesIO(result))
    assert image.format == "JPEG"
    assert image.size == (cover.COVER_WIDTH, cover.COVER_HEIGHT)


def test_render_cover_falls_back_to_text_cover_when_logo_fetch_fails(monkeypatch):
    def _boom(url, timeout):
        raise requests.RequestException("network down")

    monkeypatch.setattr(cover._session, "get", _boom)

    result = cover.render_cover(
        "যুগান্তর",
        "১২ আগস্ট, ২০২৬",
        "https://cdn.jugantor.com/uploads/settings/logo-black.png",
        JUGANTOR_ACCENT_COLOR,
    )

    image = Image.open(io.BytesIO(result))
    assert image.format == "JPEG"
    assert image.size == (cover.COVER_WIDTH, cover.COVER_HEIGHT)


def test_render_cover_skips_network_call_when_logo_url_is_none(monkeypatch):
    calls = []
    monkeypatch.setattr(cover._session, "get", lambda *a, **k: calls.append((a, k)))

    result = cover.render_cover("যুগান্তর", "১২ আগস্ট, ২০২৬", None, JUGANTOR_ACCENT_COLOR)

    assert calls == []
    image = Image.open(io.BytesIO(result))
    assert image.size == (cover.COVER_WIDTH, cover.COVER_HEIGHT)


def test_render_cover_applies_prepare_logo_hook_to_fetched_logo(monkeypatch):
    png_bytes = _opaque_rgba_png_bytes(500, 109, (10, 20, 30, 255))
    monkeypatch.setattr(cover._session, "get", lambda url, timeout: _FakeResponse(png_bytes))

    calls = []

    def fake_prepare(image):
        calls.append(image.size)
        return image.resize((300, 60))

    result = cover.render_cover(
        "প্রথম আলো",
        "১২ আগস্ট, ২০২৬",
        "https://x/logo.png",
        PROTHOMALO_ACCENT_COLOR,
        prepare_logo=fake_prepare,
    )

    assert calls == [(500, 109)], "prepare_logo should receive the freshly-fetched logo"
    image = Image.open(io.BytesIO(result))
    assert image.size == (cover.COVER_WIDTH, cover.COVER_HEIGHT)


def test_render_cover_skips_prepare_logo_hook_when_logo_fetch_fails(monkeypatch):
    def _boom(url, timeout):
        raise requests.RequestException("network down")

    monkeypatch.setattr(cover._session, "get", _boom)

    def _unexpected(image):
        raise AssertionError("prepare_logo should not run without a fetched logo")

    result = cover.render_cover(
        "প্রথম আলো", "১২ আগস্ট, ২০২৬", "https://x/logo.png", PROTHOMALO_ACCENT_COLOR, prepare_logo=_unexpected
    )

    image = Image.open(io.BytesIO(result))
    assert image.size == (cover.COVER_WIDTH, cover.COVER_HEIGHT)
