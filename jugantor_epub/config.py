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
SOURCES = ["jugantor", "prothomalo"]

def _clean_env(name):
    """Strip whitespace, including non-breaking spaces copy-pasted from

    Google's App Password page, which otherwise crash smtplib's ASCII-only
    credential encoding.
    """
    value = os.environ.get(name)
    if value is None:
        return None
    return value.replace("\xa0", "").strip()


SEND_TO_KINDLE = os.environ.get("SEND_TO_KINDLE", "false").lower() == "true"
KINDLE_EMAIL = _clean_env("KINDLE_EMAIL")
GMAIL_ADDRESS = _clean_env("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = _clean_env("GMAIL_APP_PASSWORD")
if GMAIL_APP_PASSWORD:
    GMAIL_APP_PASSWORD = GMAIL_APP_PASSWORD.replace(" ", "")

PUBLISH_OPDS = os.environ.get("PUBLISH_OPDS", "false").lower() == "true"
OPDS_RETENTION_COUNT = 7
GH_PAGES_DIR = os.environ.get("GH_PAGES_DIR", "gh-pages-checkout")


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session
