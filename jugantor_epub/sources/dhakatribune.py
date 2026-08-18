import logging
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .. import config, english_date
from .ld_json import select_by_type
from .text_utils import extract_text as _text
from .text_utils import normalize_text as _normalize

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dhakatribune.com"
COVER_LOGO_URL = "https://ecdn.dhakatribune.net/contents/themes/public/style/images/logo-en.png"
COVER_ACCENT_COLOR = (227, 6, 19)  # sampled from the logo's red "Tribune" wordmark, #e30613

SOURCE_NAME = "Dhaka Tribune"

# Dhaka Tribune's nav is a full mega-menu mixing real editorial verticals
# with subcategories, an aggregate "News" page, and vague catch-alls ("More",
# "Magazine") - unlike Jugantor/Prothom Alo's flatter navs, a generic filter
# rule (single path segment, etc.) can't tell those apart. This is a curated
# allowlist instead, confirmed against the live nav during development.
# "Bangladesh" - the flagship section - is nested one level under a "News"
# dropdown in the real menu, not top-level itself; parse_sections() below
# scans the whole nav (not just top-level items) so it's still found.
CORE_SECTION_SLUGS = {
    "bangladesh",
    "world",
    "business",
    "sport",
    "opinion",
    "showtime",
    "feature",
    "arts-and-letters",
}

# Used only if live discovery finds nothing (defensive fallback), in the
# order they're encountered in the real nav.
FALLBACK_SECTIONS = [
    ("bangladesh", "Bangladesh"),
    ("business", "Business"),
    ("world", "World"),
    ("sport", "Sport"),
    ("opinion", "Opinion"),
    ("showtime", "Showtime"),
    ("feature", "D2"),
    ("arts-and-letters", "Arts & Letters"),
]

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
    container = soup.select_one("#main_menu") or soup

    sections = []
    seen_slugs = set()
    for link in container.select("a[href]"):
        href = link["href"]
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != "www.dhakatribune.com":
            continue
        slug = parsed.path.strip("/")
        if slug not in CORE_SECTION_SLUGS or slug in seen_slugs:
            continue
        name = _normalize(link.get_text(strip=True))
        if not name:
            continue
        seen_slugs.add(slug)
        sections.append((slug, name))

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


def parse_articles(html):
    """Pure parsing step for list_articles; takes raw section-page HTML,
    returns a list of article listing dicts."""
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    for card in soup.select("div.each"):
        link_tag = card.select_one("h2.title a.link_overlay[href]")
        if not link_tag:
            continue

        # Site's own class name, not a typo we introduced.
        summary_tag = card.select_one(".summery")
        time_tag = card.select_one("span.time")
        listing_time = ""
        if time_tag is not None:
            listing_time = time_tag.get("data-published") or _text(time_tag)

        articles.append(
            {
                "url": urljoin(BASE_URL, link_tag["href"]),
                "headline": _text(link_tag),
                "summary": _text(summary_tag),
                "listing_time": listing_time,
                # Thumbnails are lazy-loaded via a JS-resolved data-ari blob
                # (a partial media path missing the CDN's size/upload
                # segments), not a plain <img src> - not worth reverse
                # engineering since fetch_article's ld+json image is
                # reliable and preferred by main.py anyway.
                "thumbnail": None,
            }
        )

    return articles


def list_articles(slug, edition_date=None):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html)


def parse_article(html, url):
    """Pure parsing step for fetch_article; takes raw article-page HTML
    and the article's URL, returns the article detail dict."""
    soup = BeautifulSoup(html, "html.parser")
    # The first ld+json block on a Dhaka Tribune article page is an
    # Organization block, not the article metadata.
    metadata = select_by_type(soup, "NewsArticle")

    paragraphs = []
    body_container = soup.select_one("article.jw_detail_content_body")
    if body_container is not None:
        for p in body_container.find_all("p"):
            text = _text(p)
            if text:
                paragraphs.append(text)

    author = ""
    author_field = metadata.get("author")
    if isinstance(author_field, dict):
        author = author_field.get("name") or ""
    elif isinstance(author_field, str):
        author = author_field

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
    return english_date.format_english_date(edition_date)
