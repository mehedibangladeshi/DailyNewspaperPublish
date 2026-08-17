import json

import pytest
import requests
from bs4 import BeautifulSoup

from jugantor_epub.sources import ld_json, prothomalo


def test_parse_sections_finds_expected_slugs(load_fixture):
    html = load_fixture("prothomalo_home.html")
    sections = prothomalo.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "bangladesh" in slugs
    assert "sports" in slugs
    assert len(slugs) == len(set(slugs)), "sections should be deduplicated"

    names = dict(sections)
    assert names["bangladesh"] == "বাংলাদেশ"


def test_parse_sections_excludes_multi_segment_and_off_site_links(load_fixture):
    html = load_fixture("prothomalo_home.html")
    sections = prothomalo.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "collection" not in slugs
    assert "collection/latest" not in slugs
    assert all(not slug.startswith("api/") for slug in slugs)


def test_parse_sections_returns_empty_list_on_unrelated_html():
    assert prothomalo.parse_sections("<html><body>nothing here</body></html>") == []


def test_parse_sections_dedupes_repeated_slug():
    html = """
    <div id="navbar">
      <a aria-label="বাংলাদেশ" href="https://www.prothomalo.com/bangladesh">বাংলাদেশ</a>
      <a aria-label="বাংলাদেশ (again)" href="https://www.prothomalo.com/bangladesh">বাংলাদেশ</a>
    </div>
    """
    sections = prothomalo.parse_sections(html)

    assert len(sections) == 1


def test_parse_sections_skips_links_with_no_name():
    html = """
    <div id="navbar">
      <a href="https://www.prothomalo.com/empty"></a>
    </div>
    """
    assert prothomalo.parse_sections(html) == []


def test_get_performs_http_request_and_returns_body(monkeypatch):
    class _FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(prothomalo.time, "sleep", lambda _: None)
    monkeypatch.setattr(prothomalo._session, "get", lambda url, timeout: _FakeResponse())

    assert prothomalo._get("https://www.prothomalo.com/x") == "<html>ok</html>"


def test_discover_sections_falls_back_on_request_failure(monkeypatch):
    monkeypatch.setattr(
        prothomalo, "_get", lambda url: (_ for _ in ()).throw(requests.RequestException("down"))
    )

    assert prothomalo.discover_sections() == prothomalo.FALLBACK_SECTIONS


def test_discover_sections_falls_back_when_nothing_parsed(monkeypatch):
    monkeypatch.setattr(prothomalo, "_get", lambda url: "<html><body>empty</body></html>")

    assert prothomalo.discover_sections() == prothomalo.FALLBACK_SECTIONS


def test_discover_sections_returns_live_parsed_sections(monkeypatch, load_fixture):
    monkeypatch.setattr(prothomalo, "_get", lambda url: load_fixture("prothomalo_home.html"))

    sections = prothomalo.discover_sections()

    assert ("bangladesh", "বাংলাদেশ") in sections


def test_list_articles_fetches_then_parses(monkeypatch, load_fixture):
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        return load_fixture("prothomalo_section_bangladesh.html")

    monkeypatch.setattr(prothomalo, "_get", fake_get)

    articles = prothomalo.list_articles("bangladesh")

    assert seen_urls == ["https://www.prothomalo.com/bangladesh"]
    assert len(articles) > 0


def test_fetch_article_fetches_then_parses(monkeypatch, load_fixture):
    monkeypatch.setattr(prothomalo, "_get", lambda url: load_fixture("prothomalo_article_sample.html"))

    article = prothomalo.fetch_article("https://www.prothomalo.com/bangladesh/6suuafru01")

    assert article["url"] == "https://www.prothomalo.com/bangladesh/6suuafru01"
    assert article["headline"]


def test_parse_articles_extracts_stories_and_dedupes_from_nested_collection_json(load_fixture):
    """Regression: listing data isn't in DOM cards - it's a deeply nested,
    recursive Quintype collection tree embedded as JSON, where the same
    story commonly appears under more than one widget."""
    html = load_fixture("prothomalo_section_bangladesh.html")
    articles = prothomalo.parse_articles(html)

    assert len(articles) > 0
    urls = [a["url"] for a in articles]
    assert len(urls) == len(set(urls)), "articles should be deduplicated by url"

    first = articles[0]
    assert first["url"] == "https://www.prothomalo.com/bangladesh/6suuafru01"
    assert "ভূমধ্যসাগরে" in first["headline"]
    assert first["thumbnail"].startswith("https://media.prothomalo.com/")


def test_parse_articles_returns_empty_list_when_static_page_script_missing():
    assert prothomalo.parse_articles("<html><body>no static-page script here</body></html>") == []


def test_parse_articles_handles_invalid_json_syntax():
    html = """
    <html><body>
      <script type="application/json" id="static-page">{not valid json at all</script>
    </body></html>
    """
    assert prothomalo.parse_articles(html) == []


def test_parse_articles_handles_missing_hero_image():
    payload = {
        "qt": {
            "data": {
                "collection": {
                    "items": [
                        {
                            "type": "story",
                            "story": {
                                "headline": "No image here",
                                "subheadline": "sub",
                                "url": "https://www.prothomalo.com/world/abc123",
                            },
                        }
                    ]
                }
            }
        }
    }
    html = f"""
    <html><body>
      <script type="application/json" id="static-page">{json.dumps(payload)}</script>
    </body></html>
    """
    articles = prothomalo.parse_articles(html)

    assert len(articles) == 1
    assert articles[0]["thumbnail"] is None


def test_parse_article_extracts_metadata_and_body(load_fixture):
    html = load_fixture("prothomalo_article_sample.html")
    article = prothomalo.parse_article(html, "https://www.prothomalo.com/bangladesh/6suuafru01")

    assert article["headline"] == "ভূমধ্যসাগরে ১০ দিন ভাসছিল নৌকাটি, মারা যান ১০ জন"
    assert article["author"] == "নিজস্ব প্রতিবেদক"
    assert article["date_published"] == "2026-08-17T12:14:01+06:00"
    assert article["image_url"].startswith("https://media.prothomalo.com/")
    assert len(article["paragraphs"]) > 0
    assert all(isinstance(p, str) and p for p in article["paragraphs"])


def test_parse_article_finds_newsarticle_block_even_though_breadcrumblist_is_first(load_fixture):
    """Regression: unlike Jugantor, the first ld+json block on a Prothom Alo
    article page is a BreadcrumbList, not the article metadata."""
    html = load_fixture("prothomalo_article_sample.html")
    soup_metadata = ld_json.select_by_type(BeautifulSoup(html, "html.parser"), "NewsArticle")

    assert soup_metadata.get("@type") == "NewsArticle"
    assert soup_metadata.get("headline")


def test_parse_article_handles_list_shaped_author():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": "H", "author": [{"name": "First Author"}, {"name": "Second"}]}
      </script>
    </head><body>
      <div class="story-element"><div class="story-element-text"><p>Body text.</p></div></div>
    </body></html>
    """
    article = prothomalo.parse_article(html, "https://example.com/x")

    assert article["author"] == "First Author"


def test_parse_article_handles_explicit_json_nulls():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": null, "author": null, "image": null}
      </script>
    </head><body>
      <div class="story-element"><div class="story-element-text"><p>Body text.</p></div></div>
    </body></html>
    """
    article = prothomalo.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["image_url"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_handles_invalid_json_syntax():
    html = """
    <html><head>
      <script type="application/ld+json">{not valid json at all</script>
    </head><body>
      <div class="story-element"><div class="story-element-text"><p>Body text.</p></div></div>
    </body></html>
    """
    article = prothomalo.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_accepts_plain_string_author_and_image():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": "H", "author": "Plain Author", "image": "https://example.com/i.jpg"}
      </script>
    </head><body>
      <div class="story-element"><div class="story-element-text"><p>Body.</p></div></div>
    </body></html>
    """
    article = prothomalo.parse_article(html, "https://example.com/x")

    assert article["author"] == "Plain Author"
    assert article["image_url"] == "https://example.com/i.jpg"


def test_parse_article_missing_ldjson_still_returns_body():
    html = """
    <html><body>
      <div class="story-element"><div class="story-element-text"><p>Only body text, no ld+json.</p></div></div>
    </body></html>
    """
    article = prothomalo.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["paragraphs"] == ["Only body text, no ld+json."]


def test_parse_article_raises_for_subscriber_only_articles():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": "Premium", "isAccessibleForFree": false}
      </script>
    </head><body>
      <div class="story-element"><div class="story-element-text"><p>Teaser only...</p></div></div>
    </body></html>
    """
    with pytest.raises(ValueError):
        prothomalo.parse_article(html, "https://example.com/premium")


def test_fetch_article_propagates_subscriber_only_error(monkeypatch):
    """main.py's per-article try/except relies on fetch_article raising for
    premium articles so they're skipped rather than included as teasers."""
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": "Premium", "isAccessibleForFree": false}
      </script>
    </head><body>
      <div class="story-element"><div class="story-element-text"><p>Teaser only...</p></div></div>
    </body></html>
    """
    monkeypatch.setattr(prothomalo, "_get", lambda url: html)

    with pytest.raises(ValueError):
        prothomalo.fetch_article("https://example.com/premium")


def test_get_cover_logo_url_returns_prothomalo_masthead_logo():
    assert prothomalo.get_cover_logo_url() == prothomalo.COVER_LOGO_URL


def test_prepare_logo_image_crops_to_wordmark_region():
    from PIL import Image

    source = Image.new("RGB", (1200, 630), prothomalo.LOGO_BACKGROUND_RGB)

    result = prothomalo.prepare_logo_image(source)

    left, top, right, bottom = prothomalo.LOGO_CROP_BOX
    assert result.size == (right - left, bottom - top)


def test_prepare_logo_image_makes_near_white_background_transparent():
    from PIL import Image

    source = Image.new("RGB", (1200, 630), prothomalo.LOGO_BACKGROUND_RGB)

    result = prothomalo.prepare_logo_image(source)

    assert result.mode == "RGBA"
    assert result.getpixel((5, 5))[3] == 0, "near-white background should be transparent"


def test_prepare_logo_image_keeps_non_background_pixels_opaque():
    from PIL import Image, ImageDraw

    source = Image.new("RGB", (1200, 630), prothomalo.LOGO_BACKGROUND_RGB)
    draw = ImageDraw.Draw(source)
    left, top, right, bottom = prothomalo.LOGO_CROP_BOX
    # paint a dark wordmark-like blob well inside the crop box
    draw.rectangle([left + 20, top + 20, left + 60, top + 60], fill=(10, 10, 10))

    result = prothomalo.prepare_logo_image(source)

    assert result.getpixel((25, 25)) == (10, 10, 10, 255)


def test_format_date_uses_bengali_formatting():
    assert prothomalo.format_date("2026-08-17") == "১৭ আগস্ট, ২০২৬"
