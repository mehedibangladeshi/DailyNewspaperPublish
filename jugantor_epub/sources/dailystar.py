import logging
import os
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .. import config, english_date
from .ld_json import select_by_type
from .text_utils import extract_text as _text
from .text_utils import normalize_text as _normalize

logger = logging.getLogger(__name__)

BASE_URL = "https://www.thedailystar.net"
TODAYS_NEWS_URL = f"{BASE_URL}/todays-news"

# The live masthead is only available as an SVG (logo.svg); the site's own
# og:image logo asset points at a subdomain that doesn't resolve
# (images.thedailystar.net), and the favicon is a 16x16 icon - neither
# usable for the cover. The SVG was rendered to PNG once (see
# jugantor_epub/assets/dailystar-logo-source.svg for the original) and that
# PNG is bundled in the repo instead of being fetched over the network like
# every other source's logo. cover._fetch_logo_image() treats any non-http
# string as a local file path.
COVER_LOGO_URL = os.path.join(config.PROJECT_ROOT, "jugantor_epub", "assets", "dailystar-logo.png")
COVER_ACCENT_COLOR = (4, 13, 51)  # the site's recurring UI navy, #040D33 - its wordmark itself is monochrome

SOURCE_NAME = "The Daily Star"

# Unlike every other source, Daily Star has no per-category listing page at
# all: /todays-news is a single Drupal "views" page already listing every
# story published today (confirmed bounded to today - every dated card on
# the page reads today's date - and not paginated, no pager/infinite-scroll
# markers found). "Section" here is therefore not a real nav category, it's
# derived from each article URL's first path segment (e.g.
# /business/economy/news/... -> "business").
SECTION_DISPLAY_NAMES = {
    "news": "News",
    "business": "Business",
    "sports": "Sports",
    "opinion": "Opinion",
    "culture": "Culture & Entertainment",
    "health": "Health",
    "historical": "Historical",
    "news-analysis": "News Analysis",
    "slow-reads": "Slow Reads",
    "life-living": "Life & Living",
    "lifestyle": "Lifestyle",
    "youth": "Youth",
}

# star-multimedia is a video hub - its article pages carry an embedded
# video player and an essentially empty text body, the same "not usable for
# a text reading digest" reasoning as Prothom Alo's excluded "video"
# section (see EXCLUDED_SECTION_SLUGS there).
EXCLUDED_SECTION_SLUGS = {"star-multimedia"}

# Used only if the /todays-news fetch itself fails outright (defensive
# fallback) - a representative subset of the slugs normally found live.
FALLBACK_SECTIONS = [
    ("news", "News"),
    ("business", "Business"),
    ("sports", "Sports"),
    ("opinion", "Opinion"),
    ("culture", "Culture & Entertainment"),
    ("health", "Health"),
]

_session = config.make_session()

# The whole day's listing lives on one URL, so every discover_sections()/
# list_articles() call in a single run shares one fetch+parse instead of
# re-requesting the same page once per section.
_listing_cache = {}


def _get(url):
    time.sleep(config.REQUEST_DELAY_SECONDS)
    response = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _section_slug(url):
    path = urlparse(url).path.strip("/")
    return path.split("/", 1)[0] if path else ""


def parse_todays_news(html):
    """Pure parsing step; takes /todays-news' raw HTML, returns a dict of
    {section_slug: [article dict, ...]}, deduped by URL across the whole
    page (the same story commonly appears in more than one listing widget),
    excluding EXCLUDED_SECTION_SLUGS entirely."""
    soup = BeautifulSoup(html, "html.parser")

    grouped = {}
    seen_urls = set()
    for row in soup.select(".views-row"):
        link_tag = row.select_one(".card-title a[href]")
        if link_tag is None:
            continue

        url = urljoin(BASE_URL, link_tag["href"])
        if url in seen_urls:
            continue

        slug = _section_slug(url)
        if not slug or slug in EXCLUDED_SECTION_SLUGS:
            continue
        seen_urls.add(url)

        img_tag = row.select_one("img[src]")

        grouped.setdefault(slug, []).append(
            {
                "url": url,
                "headline": _text(link_tag),
                "summary": _text(row.select_one(".card-intro")),
                "listing_time": _text(row.select_one(".card-info")),
                "thumbnail": urljoin(BASE_URL, img_tag["src"]) if img_tag else None,
            }
        )

    return grouped


def _get_grouped_listing():
    if "grouped" not in _listing_cache:
        html = _get(TODAYS_NEWS_URL)
        _listing_cache["grouped"] = parse_todays_news(html)
    return _listing_cache["grouped"]


def discover_sections():
    try:
        grouped = _get_grouped_listing()
    except requests.RequestException:
        logger.warning("Could not reach %s, using fallback section list", TODAYS_NEWS_URL)
        return list(FALLBACK_SECTIONS)

    if not grouped:
        logger.warning("No sections discovered on %s, using fallback list", TODAYS_NEWS_URL)
        return list(FALLBACK_SECTIONS)

    return [(slug, SECTION_DISPLAY_NAMES.get(slug, slug.replace("-", " ").title())) for slug in grouped]


def list_articles(slug, edition_date=None):
    grouped = _get_grouped_listing()
    return grouped.get(slug, [])


def _extract_author(author_field):
    # Seen as a plain string ("The Daily Star" for staff/editorial pieces),
    # and as a dict whose own "name" is either a plain string or - for
    # wire-service pieces with a dateline, e.g. ["AFP", "Paris"] - a list of
    # strings, unlike Jugantor/Dhaka Tribune's plain-string/dict-only shapes.
    if isinstance(author_field, dict):
        name = author_field.get("name")
        if isinstance(name, list):
            return ", ".join(str(part) for part in name if part)
        return name or ""
    if isinstance(author_field, str):
        return author_field
    return ""


def parse_article(html, url):
    """Pure parsing step for fetch_article; takes raw article-page HTML
    and the article's URL, returns the article detail dict."""
    soup = BeautifulSoup(html, "html.parser")
    # The single ld+json block on a Daily Star article page bundles every
    # entity (NewsArticle, Organization) into one schema.org "@graph" array
    # rather than emitting separate blocks - select_by_type() looks inside
    # @graph too. Notably absent from it: datePublished and image, both
    # pulled from elsewhere below.
    metadata = select_by_type(soup, "NewsArticle")

    paragraphs = []
    body_container = soup.select_one("div.block-field-blocknodenewsbody")
    if body_container is not None:
        for p in body_container.find_all("p"):
            text = _text(p)
            if text:
                paragraphs.append(text)

    date_tag = soup.select_one("span.text-gray-600.font-medium")
    image_tag = soup.select_one('meta[property="og:image"]')

    return {
        "url": url,
        "headline": _normalize(" ".join((metadata.get("headline") or "").split())),
        "author": _normalize(" ".join(_extract_author(metadata.get("author")).split())),
        "date_published": _text(date_tag),
        "image_url": (image_tag.get("content") or "") if image_tag else "",
        "paragraphs": paragraphs,
    }


def fetch_article(url):
    html = _get(url)
    return parse_article(html, url)


def get_cover_logo_url():
    return COVER_LOGO_URL


def format_date(edition_date):
    return english_date.format_english_date(edition_date)
