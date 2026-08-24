import hashlib
import io
import logging

import requests
from PIL import Image

from . import config

logger = logging.getLogger(__name__)

_session = config.make_session()


def fetch_raw_image(url):
    """Fetch and decode an image, without resizing or re-encoding it.

    Returns a PIL Image, or None if the URL is empty or the image
    couldn't be fetched or decoded.
    """
    if not url:
        return None

    try:
        response = _session.get(url, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        image = image.convert("RGB")
    except (requests.RequestException, OSError) as exc:
        logger.warning("Skipping image %s: %s", url, exc)
        return None

    return image


def encode_image(image, url, max_width, quality):
    """Re-encode an already-decoded image as a size-capped JPEG.

    Does not mutate `image` - callers may encode the same decoded image
    more than once (e.g. at a fallback size/quality on retry).

    Returns (filename, jpeg_bytes).
    """
    if image.width > max_width:
        new_height = round(image.height * (max_width / image.width))
        image = image.resize((max_width, new_height), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)

    filename = f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"
    return filename, buffer.getvalue()


def download_image(url, max_width=config.IMAGE_MAX_WIDTH, quality=config.IMAGE_JPEG_QUALITY):
    """Fetch an image and re-encode it as a size-capped JPEG.

    Returns (filename, jpeg_bytes), or None if the image couldn't be
    fetched or decoded.
    """
    image = fetch_raw_image(url)
    if image is None:
        return None
    return encode_image(image, url, max_width, quality)
