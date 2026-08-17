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
TEXT_COLOR = (51, 51, 51)  # #333333

LOGO_MAX_WIDTH = 1100
LOGO_TOP = 1000

RULE_WIDTH = 400
RULE_HEIGHT = 16
# Gaps used when a logo image was pasted: the rule/date are placed this far
# below wherever the logo actually ends, rather than at a fixed position -
# a fixed RULE_TOP/DATE_TOP only worked by coincidence for Jugantor's own
# short, wide logo and overlapped taller logos from other sources (e.g.
# Prothom Alo's masthead asset). These gaps are calibrated so Jugantor's
# real logo (500x109, scaled to LOGO_MAX_WIDTH) still lands the rule/date at
# exactly RULE_TOP/DATE_TOP below, unchanged.
LOGO_RULE_GAP = 160
RULE_DATE_GAP = 44

# Fallback positions used only when no logo image was pasted (title text
# drawn instead) - there's no pasted height to measure in that case.
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
    return resized.height


def compose_cover(logo_image, source_name, date_text, accent_color):
    """Build the epub cover as a PIL Image: masthead logo (or source_name as
    a text fallback) + a source-specific accent rule + the formatted edition
    date, on a white background. Pure function - no I/O."""
    canvas = Image.new("RGB", (COVER_WIDTH, COVER_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(canvas)

    if logo_image is not None:
        logo_height = _paste_logo(canvas, logo_image)
        rule_top = LOGO_TOP + logo_height + LOGO_RULE_GAP
        date_top = rule_top + RULE_HEIGHT + RULE_DATE_GAP
    else:
        title_font = ImageFont.truetype(config.FONT_PATH, size=FALLBACK_TITLE_FONT_SIZE)
        _draw_centered_text(draw, source_name, LOGO_TOP + 60, title_font, TEXT_COLOR)
        rule_top = RULE_TOP
        date_top = DATE_TOP

    rule_left = (COVER_WIDTH - RULE_WIDTH) // 2
    draw.rectangle(
        [rule_left, rule_top, rule_left + RULE_WIDTH, rule_top + RULE_HEIGHT],
        fill=accent_color,
    )

    date_font = ImageFont.truetype(config.FONT_PATH, size=DATE_FONT_SIZE)
    _draw_centered_text(draw, date_text, date_top, date_font, TEXT_COLOR)

    return canvas


def render_cover(source_name, date_text, logo_url, accent_color, prepare_logo=None):
    """Fetch the source's masthead logo and render the epub cover, returning
    JPEG bytes. Falls back to a text-only cover if the logo can't be
    fetched, so a network hiccup never blocks the epub build. `prepare_logo`,
    if given, is a source-specific hook (image) -> image applied to the
    fetched logo before compositing (e.g. cropping/cleaning a source's own
    masthead asset) - most sources don't need one."""
    logo_image = _fetch_logo_image(logo_url)
    if logo_image is not None and prepare_logo is not None:
        logo_image = prepare_logo(logo_image)
    canvas = compose_cover(logo_image, source_name, date_text, accent_color)

    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()
