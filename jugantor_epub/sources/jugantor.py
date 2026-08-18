import json
import logging
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .. import bengali_date, config
from .text_utils import extract_text as _text
from .text_utils import normalize_text as _normalize

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jugantor.com"
TODAYS_PAPER_URL = f"{BASE_URL}/todays-paper"
COVER_LOGO_URL = "https://cdn.jugantor.com/uploads/settings/logo-black.png"
COVER_ACCENT_COLOR = (196, 12, 19)  # jugantor.com's brand red, #c40c13

SOURCE_NAME = "যুগান্তর"

# Used only if live discovery finds nothing (defensive fallback).
FALLBACK_SECTIONS = [
    ("tp-firstpage", "প্রথম পাতা"),
    ("tp-lastpage", "শেষ পাতা"),
    ("tp-city", "নগর-মহানগর"),
    ("tp-sports", "খেলা"),
    ("tp-anando-nagar", "আনন্দ নগর"),
    ("tp-news", "খবর"),
    ("tp-second-edition", "দ্বিতীয় সংস্করণ"),
    ("tp-ten-horizon", "দশ দিগন্ত"),
    ("tp-bangla-face", "বাংলার মুখ"),
    ("tp-editorial", "সম্পাদকীয়"),
    ("tp-ub-editorial", "উপসম্পাদকীয়"),
    ("tp-suranjona", "সুরঞ্জনা"),
    ("tp-letter", "চিঠিপত্র"),
]

_session = config.make_session()


def _get(url):
    time.sleep(config.REQUEST_DELAY_SECONDS)
    response = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _slug_from_href(href):
    path = urlparse(href).path
    return path.strip("/").split("/")[0]


def parse_sections(html):
    """Pure parsing step for discover_sections; takes raw HTML, returns
    a list of (slug, section_name) or [] if none were found."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("div.desktopSubCategoryDiv") or soup

    sections = []
    seen_slugs = set()
    for link in container.select("a[href]"):
        href = link["href"]
        if "/tp-" not in href:
            continue
        slug = _slug_from_href(href)
        if not slug or slug in seen_slugs:
            continue
        name = _normalize(link.get("aria-label") or link.get_text(strip=True))
        if not name:
            continue
        seen_slugs.add(slug)
        sections.append((slug, name))

    return sections


def discover_sections():
    try:
        html = _get(TODAYS_PAPER_URL)
    except requests.RequestException:
        logger.warning("Could not reach %s, using fallback section list", TODAYS_PAPER_URL)
        return list(FALLBACK_SECTIONS)

    sections = parse_sections(html)
    if not sections:
        logger.warning("No sections discovered on %s, using fallback list", TODAYS_PAPER_URL)
        return list(FALLBACK_SECTIONS)

    return sections


def parse_articles(html):
    """Pure parsing step for list_articles; takes raw section-page HTML,
    returns a list of article listing dicts."""
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    for card in soup.select("div.media.positionRelative"):
        link_tag = card.select_one("a.linkOverlay[href]")
        title_tag = card.select_one(".title10")
        if not link_tag or not title_tag:
            continue

        summary_tag = card.select_one(".desktopSummary")
        time_tag = card.select_one(".desktopTime")
        img_tag = card.select_one("img")

        thumbnail = None
        if img_tag is not None:
            raw_thumbnail = img_tag.get("data-src") or img_tag.get("src")
            if raw_thumbnail:
                thumbnail = urljoin(BASE_URL, raw_thumbnail)

        articles.append(
            {
                "url": urljoin(BASE_URL, link_tag["href"]),
                "headline": _text(title_tag),
                "summary": _text(summary_tag),
                "listing_time": _text(time_tag),
                "thumbnail": thumbnail,
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

    metadata = {}
    ld_json_tag = soup.select_one('script[type="application/ld+json"]')
    if ld_json_tag is not None:
        try:
            # strict=False: some pages embed raw newlines inside JSON string
            # values (e.g. multi-line headlines), which strict JSON rejects.
            metadata = json.loads(ld_json_tag.string or "{}", strict=False)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse ld+json for %s", url)

    body_container = soup.select_one("div.desktopDetailBody")
    paragraphs = []
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
