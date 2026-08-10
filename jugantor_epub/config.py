import os

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
FONT_PATH = os.path.join(PROJECT_ROOT, "fonts", "NotoSansBengali-Regular.ttf")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
REQUEST_DELAY_SECONDS = 0.7

IMAGE_MAX_WIDTH = 800
IMAGE_JPEG_QUALITY = 75

# Each entry is a module under jugantor_epub/sources/ exposing:
#   discover_sections() -> list[(slug, section_name)]
#   list_articles(slug) -> list[dict]
#   fetch_article(url) -> dict
# Adding a new newspaper later means adding a module here with the same
# shape and listing its name below - main.py already loops over this list.
SOURCES = ["jugantor"]

# Not implemented yet - see plan's "Deferred For Later" section.
SEND_TO_KINDLE = False


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session
