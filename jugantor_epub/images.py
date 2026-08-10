import hashlib
import io
import logging

import requests
from PIL import Image

from . import config

logger = logging.getLogger(__name__)

_session = config.make_session()


def download_image(url, max_width=config.IMAGE_MAX_WIDTH):
    """Fetch an image and re-encode it as a size-capped JPEG.

    Returns (filename, jpeg_bytes), or None if the image couldn't be
    fetched or decoded.
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

    if image.width > max_width:
        new_height = round(image.height * (max_width / image.width))
        image = image.resize((max_width, new_height), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=config.IMAGE_JPEG_QUALITY, optimize=True)

    filename = f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"
    return filename, buffer.getvalue()
