import json
import logging
import time
from datetime import date, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .. import bengali_date, config
from .ld_json import select_by_type
from .text_utils import extract_text as _text
from .text_utils import normalize_text as _normalize

logger = logging.getLogger(__name__)

BASE_URL = "https://www.prothomalo.com"
MEDIA_BASE_URL = "https://media.prothomalo.com"
COVER_LOGO_URL = (
    "https://media.prothomalo.com/prothomalo-bangla/2021-01/"
    "1d75151c-eff9-4e9f-ac28-aebc4618d00f/palo_bangla_og.png"
)
COVER_ACCENT_COLOR = (238, 65, 35)  # prothomalo.com's sun-mark red-orange, #ee4123

# The og:image asset above is the only non-SVG masthead asset available (see
# COVER_LOGO_URL), but it's a 1200x630 banner with a near-white background,
# a subtitle line ("prothomalo.com") and an oversized sun-circle graphic -
# not a tightly-cropped wordmark like Jugantor's. These crop it down to just
# the wordmark + small sun accent, matching that tighter style.
LOGO_CROP_BOX = (450, 270, 1170, 445)
LOGO_BACKGROUND_RGB = (245, 245, 245)
LOGO_BACKGROUND_TOLERANCE = 12

SOURCE_NAME = "প্রথম আলো"

# Prothom Alo is Bangladesh's paper, so "today" for date-filtering purposes
# means the Asia/Dhaka calendar day, regardless of what timezone this
# process happens to run in (main.py's edition_date is computed once, in
# whatever local time the run has, and is compared against here).
DHAKA_TZ = ZoneInfo("Asia/Dhaka")

# Used only if live discovery finds nothing (defensive fallback). Unlike
# Jugantor, Prothom Alo has no separate print-edition site - these are its
# regular web nav categories, discovered from the homepage's #navbar.
# "video" and "chakri" are deliberately excluded here (see
# EXCLUDED_SECTION_SLUGS below) - Kindle can't play video, and job listings
# aren't news narrative the way the rest of the paper is.
FALLBACK_SECTIONS = [
    ("bangladesh", "বাংলাদেশ"),
    ("politics", "রাজনীতি"),
    ("world", "বিশ্ব"),
    ("business", "বাণিজ্য"),
    ("opinion", "মতামত"),
    ("sports", "খেলা"),
    ("entertainment", "বিনোদন"),
    ("lifestyle", "জীবনযাপন"),
]

# Nav categories that are discovered live (via parse_sections) or would
# otherwise appear in FALLBACK_SECTIONS, but don't fit a daily reading
# digest: "video" is a format Kindle can't play (a video-story page's body
# is a player + caption, not prose), and "chakri" (jobs/classifieds) isn't
# news narrative. Same "curated allowlist over generic filter" spirit as
# Dhaka Tribune's CORE_SECTION_SLUGS, expressed as a denylist since only
# two of Prothom Alo's ~10 nav categories need excluding.
EXCLUDED_SECTION_SLUGS = {"video", "chakri"}

_session = config.make_session()


def _get(url):
    time.sleep(config.REQUEST_DELAY_SECONDS)
    response = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def parse_sections(html):
    """Pure parsing step for discover_sections; takes the homepage's raw
    HTML, returns a list of (slug, section_name) or [] if none were found."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#navbar") or soup

    sections = []
    seen_slugs = set()
    for link in container.select("a[href]"):
        href = link["href"]
        if not href.startswith(BASE_URL):
            continue
        path = urlparse(href).path.strip("/")
        # Only single-segment paths are real nav categories; this also
        # naturally excludes /collection/latest, /search, oauth links, etc.
        if not path or "/" in path:
            continue
        if path in seen_slugs or path in EXCLUDED_SECTION_SLUGS:
            continue
        name = _normalize(link.get("aria-label") or link.get_text(strip=True))
        if not name:
            continue
        seen_slugs.add(path)
        sections.append((path, name))

    return sections


def discover_sections():
    try:
        html = _get(BASE_URL)
    except requests.RequestException:
        logger.warning("Could not reach %s, using fallback section list", BASE_URL)
        return list(FALLBACK_SECTIONS)

    sections = parse_sections(html)
    if not sections:
        logger.warning("No sections discovered on %s, using fallback list", BASE_URL)
        return list(FALLBACK_SECTIONS)

    return sections


def _find_stories(node, seen_urls, out):
    """Recursively collect type=='story' nodes from the Quintype CMS
    collection tree embedded in the static-page JSON blob. The same story
    commonly appears more than once (different listing widgets reuse it),
    so callers dedupe by url via seen_urls."""
    if isinstance(node, dict):
        if node.get("type") == "story":
            story = node.get("story") or {}
            url = story.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                out.append(story)
            return
        for value in node.values():
            _find_stories(value, seen_urls, out)
    elif isinstance(node, list):
        for item in node:
            _find_stories(item, seen_urls, out)


def _story_date(published_at):
    """Convert a Quintype `published-at` epoch-ms timestamp to its
    Asia/Dhaka calendar date. Returns None if the value is missing or
    malformed - callers should fail open (keep the story) rather than drop
    it, since this is a newly-relied-on field with no track record yet of
    being reliably present across every section's JSON shape."""
    if not isinstance(published_at, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(published_at / 1000, tz=DHAKA_TZ).date()
    except (OverflowError, OSError, ValueError):
        return None


def parse_articles(html, edition_date):
    """Pure parsing step for list_articles; takes raw section-page HTML and
    the run's edition_date (ISO "YYYY-MM-DD" string). Unlike Jugantor, the
    listing data isn't in scrapeable DOM cards - it's embedded as a
    <script type="application/json" id="static-page"> blob (Quintype CMS's
    hydration state), so this parses that JSON instead of selecting HTML
    cards.

    Unlike Jugantor's print-edition pages, a category page has no natural
    "today only" bound - it's a rolling feed of recent stories regardless of
    date. Each story carries its own published-at epoch-ms timestamp, so
    this filters to stories whose Asia/Dhaka calendar date matches
    edition_date, dropping the rest before any per-article fetch happens."""
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.select_one("script#static-page")
    if script_tag is None:
        return []

    try:
        data = json.loads(script_tag.string or "{}", strict=False)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse static-page JSON")
        return []

    collection = ((data.get("qt") or {}).get("data") or {}).get("collection") or {}
    stories = []
    _find_stories(collection.get("items") or [], set(), stories)

    target_date = date.fromisoformat(edition_date)
    warned_missing_date = False

    articles = []
    for story in stories:
        story_date = _story_date(story.get("published-at"))
        if story_date is not None and story_date != target_date:
            continue
        if story_date is None and not warned_missing_date:
            logger.warning(
                "Story listing missing/invalid published-at, keeping it: %s",
                story.get("url"),
            )
            warned_missing_date = True

        thumbnail = None
        s3_key = story.get("hero-image-s3-key")
        if s3_key:
            thumbnail = f"{MEDIA_BASE_URL}/{s3_key}?w=400&auto=format,compress&fit=max"

        articles.append(
            {
                "url": story["url"],
                "headline": _normalize(story.get("headline") or ""),
                "summary": _normalize(story.get("subheadline") or ""),
                "listing_time": "",
                "thumbnail": thumbnail,
            }
        )

    return articles


def list_articles(slug, edition_date):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html, edition_date)


def _extract_author(author_field):
    # Prothom Alo's ld+json represents author as a list of Person dicts,
    # unlike Jugantor's single dict/string - take the first entry, then
    # apply the same dict/string branching as Jugantor.
    if isinstance(author_field, list):
        author_field = author_field[0] if author_field else None

    if isinstance(author_field, dict):
        return author_field.get("name") or ""
    if isinstance(author_field, str):
        return author_field
    return ""


def parse_article(html, url):
    """Pure parsing step for fetch_article; takes raw article-page HTML
    and the article's URL, returns the article detail dict."""
    soup = BeautifulSoup(html, "html.parser")
    # Unlike Jugantor, the first ld+json block on a Prothom Alo article page
    # is a BreadcrumbList, not the article metadata.
    metadata = select_by_type(soup, "NewsArticle")

    if metadata.get("isAccessibleForFree") is False:
        raise ValueError(f"Skipping subscriber-only article: {url}")

    paragraphs = []
    for element in soup.select("div.story-element-text"):
        text = _text(element)
        if text:
            paragraphs.append(text)

    author = _extract_author(metadata.get("author"))

    image_url = ""
    image_field = metadata.get("image")
    if isinstance(image_field, dict):
        image_url = image_field.get("url") or ""
    elif isinstance(image_field, str):
        image_url = image_field

    return {
        "url": url,
        "headline": _normalize(" ".join((metadata.get("headline") or "").split())),
        "author": _normalize(" ".join(author.split())),
        "date_published": metadata.get("datePublished", ""),
        "image_url": image_url,
        "paragraphs": paragraphs,
    }


def fetch_article(url):
    html = _get(url)
    return parse_article(html, url)


def get_cover_logo_url():
    return COVER_LOGO_URL


def format_date(edition_date):
    return bengali_date.format_bengali_date(edition_date)


def prepare_logo_image(image):
    """Crop the fetched og:image masthead down to just the wordmark + small
    sun accent (see LOGO_CROP_BOX), and make its near-white background
    transparent so it composites cleanly onto the cover - cover.render_cover
    calls this on the fetched logo before compositing."""
    cropped = image.convert("RGBA").crop(LOGO_CROP_BOX)
    pixels = cropped.load()
    width, height = cropped.size
    bg_r, bg_g, bg_b = LOGO_BACKGROUND_RGB
    tolerance = LOGO_BACKGROUND_TOLERANCE

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if abs(r - bg_r) <= tolerance and abs(g - bg_g) <= tolerance and abs(b - bg_b) <= tolerance:
                pixels[x, y] = (r, g, b, 0)

    return cropped
