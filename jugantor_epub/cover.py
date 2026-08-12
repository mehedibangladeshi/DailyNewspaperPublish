import io
import logging

import requests
from PIL import Image, ImageDraw, ImageFont

from . import config

logger = logging.getLogger(__name__)

_session = config.make_session()

COVER_WIDTH = 1600
COVER_HEIGHT = 2560

BACKGROUND_COLOR = (255, 255, 255)
ACCENT_COLOR = (196, 12, 19)  # jugantor.com's brand red, #c40c13
TEXT_COLOR = (51, 51, 51)  # #333333

LOGO_MAX_WIDTH = 1100
LOGO_TOP = 1000

RULE_WIDTH = 400
RULE_HEIGHT = 16
RULE_TOP = 1400

DATE_TOP = 1460
DATE_FONT_SIZE = 90
FALLBACK_TITLE_FONT_SIZE = 140


def _fetch_logo_image(url):
    """Fetch a masthead logo and return it as an RGBA PIL Image, or None if
    it can't be fetched or decoded."""
    if not url:
        return None

    try:
        response = _session.get(url, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except (requests.RequestException, OSError) as exc:
        logger.warning("Skipping cover logo %s: %s", url, exc)
        return None


def _draw_centered_text(draw, text, top, font, fill):
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    x = (COVER_WIDTH - (right - left)) // 2
    draw.text((x, top), text, font=font, fill=fill)


def _paste_logo(canvas, logo_image):
    scale = LOGO_MAX_WIDTH / logo_image.width
    resized = logo_image.resize((LOGO_MAX_WIDTH, round(logo_image.height * scale)), Image.LANCZOS)
    x = (COVER_WIDTH - resized.width) // 2
    canvas.paste(resized, (x, LOGO_TOP), mask=resized)


def compose_cover(logo_image, source_name, date_text):
    """Build the epub cover as a PIL Image: masthead logo (or source_name as
    a text fallback) + a brand-red accent rule + the formatted edition date,
    on a white background. Pure function - no I/O."""
    canvas = Image.new("RGB", (COVER_WIDTH, COVER_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(canvas)

    if logo_image is not None:
        _paste_logo(canvas, logo_image)
    else:
        title_font = ImageFont.truetype(config.FONT_PATH, size=FALLBACK_TITLE_FONT_SIZE)
        _draw_centered_text(draw, source_name, LOGO_TOP + 60, title_font, TEXT_COLOR)

    rule_left = (COVER_WIDTH - RULE_WIDTH) // 2
    draw.rectangle(
        [rule_left, RULE_TOP, rule_left + RULE_WIDTH, RULE_TOP + RULE_HEIGHT],
        fill=ACCENT_COLOR,
    )

    date_font = ImageFont.truetype(config.FONT_PATH, size=DATE_FONT_SIZE)
    _draw_centered_text(draw, date_text, DATE_TOP, date_font, TEXT_COLOR)

    return canvas


def render_cover(source_name, date_text, logo_url):
    """Fetch the source's masthead logo and render the epub cover, returning
    JPEG bytes. Falls back to a text-only cover if the logo can't be
    fetched, so a network hiccup never blocks the epub build."""
    logo_image = _fetch_logo_image(logo_url)
    canvas = compose_cover(logo_image, source_name, date_text)

    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
