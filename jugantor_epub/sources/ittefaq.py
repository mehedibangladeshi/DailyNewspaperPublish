import logging
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .. import bengali_date, config
from .ld_json import select_by_type
from .text_utils import extract_text as _text
from .text_utils import normalize_text as _normalize

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ittefaq.com.bd"
COVER_LOGO_URL = "https://cdn.ittefaqbd.com/contents/themes/public/style/images/logo.png"
COVER_ACCENT_COLOR = (236, 28, 36)  # sampled from the site's own CSS accent rule, #ec1c24

SOURCE_NAME = "ইত্তেফাক"

# Ittefaq's nav mixes real editorial verticals with a few categories that
# aren't a good fit for a text digest - "video"/"photo" (no prose body) and
# "jobs" (classifieds, not news narrative) - plus "latest-news", a rolling
# aggregate of every other section's stories that would just duplicate them.
# Same "curated allowlist" spirit as Dhaka Tribune's CORE_SECTION_SLUGS.
CORE_SECTION_SLUGS = {
    "national",
    "capital",
    "country",
    "politics",
    "world-news",
    "sports",
    "entertainment",
    "business",
    "tech",
    "education",
    "health",
    "social-media",
    "projonmo",
    "probash",
    "campus",
    "literature",
    "religion",
    "lifestyle",
    "opinion",
    "news",
    "editorial",
    "law-and-court",
    "environment",
}

# Used only if live discovery finds nothing (defensive fallback), in the
# order they're encountered in the real nav.
FALLBACK_SECTIONS = [
    ("national", "জাতীয়"),
    ("capital", "রাজধানী"),
    ("country", "সারাদেশ"),
    ("politics", "রাজনীতি"),
    ("world-news", "বিশ্ব সংবাদ"),
    ("sports", "খেলা"),
    ("entertainment", "বিনোদন"),
    ("business", "অর্থনীতি"),
    ("tech", "টেক"),
    ("education", "শিক্ষা"),
    ("health", "স্বাস্থ্য"),
    ("social-media", "সোশ্যাল মিডিয়া"),
    ("projonmo", "প্রজন্ম"),
    ("probash", "প্রবাস"),
    ("campus", "ক্যাম্পাস"),
    ("literature", "সাহিত্য"),
    ("religion", "ধর্ম"),
    ("lifestyle", "লাইফস্টাইল"),
    ("opinion", "মতামত"),
    ("news", "অন্যান্য"),
    ("editorial", "সম্পাদকীয়"),
    ("law-and-court", "আইন-আদালত"),
    ("environment", "পরিবেশ"),
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

    sections = []
    seen_slugs = set()
    for link in soup.select("a[href]"):
        href = link["href"]
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != "www.ittefaq.com.bd":
            continue
        slug = parsed.path.strip("/")
        if slug not in CORE_SECTION_SLUGS or slug in seen_slugs:
            continue
        name = _text(link)
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
    seen_urls = set()
    for card in soup.select("div.each"):
        link_tag = card.select_one("h2.title a.link_overlay[href]")
        if not link_tag:
            continue

        url = urljoin(BASE_URL, link_tag["href"])
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Site's own class name, not a typo introduced here.
        summary_tag = card.select_one(".summery")
        time_tag = card.select_one("span.time")
        listing_time = ""
        if time_tag is not None:
            listing_time = time_tag.get("data-published") or _text(time_tag)

        articles.append(
            {
                "url": url,
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
    # The first ld+json block on an Ittefaq article page is an Organization
    # block (a Website block follows) - the article metadata is third.
    metadata = select_by_type(soup, "NewsArticle")

    paragraphs = []
    body_container = soup.select_one("div.jw_article_body")
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
    return bengali_date.format_bengali_date(edition_date)
