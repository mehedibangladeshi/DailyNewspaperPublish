import pytest
import requests

from jugantor_epub.sources import dhakatribune


def test_parse_sections_finds_expected_slugs(load_fixture):
    html = load_fixture("dhakatribune_home.html")
    sections = dhakatribune.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "bangladesh" in slugs
    assert "sport" in slugs
    assert len(slugs) == len(set(slugs)), "sections should be deduplicated"

    names = dict(sections)
    assert names["bangladesh"] == "Bangladesh"
    assert names["feature"] == "D2"


def test_parse_sections_promotes_bangladesh_out_of_the_news_dropdown(load_fixture):
    """Regression: Bangladesh (the flagship section) is nested one level
    under a "News" dropdown in the real nav, not top-level itself."""
    html = load_fixture("dhakatribune_home.html")
    sections = dhakatribune.parse_sections(html)

    assert ("bangladesh", "Bangladesh") in sections


def test_parse_sections_excludes_non_core_nav_items(load_fixture):
    html = load_fixture("dhakatribune_home.html")
    sections = dhakatribune.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "latest-news" not in slugs, "the redundant News aggregate should be excluded"
    assert "others" not in slugs, "the vague More/Others catch-all should be excluded"
    assert "magazine-1" not in slugs
    assert "education" not in slugs, "Bangladesh's own siblings shouldn't be pulled in"


def test_parse_sections_returns_empty_list_on_unrelated_html():
    assert dhakatribune.parse_sections("<html><body>nothing here</body></html>") == []


def test_parse_sections_dedupes_repeated_slug():
    html = """
    <div id="main_menu">
      <a href="https://www.dhakatribune.com/world">World</a>
      <a href="https://www.dhakatribune.com/world">World (again)</a>
    </div>
    """
    sections = dhakatribune.parse_sections(html)

    assert len(sections) == 1


def test_parse_sections_skips_links_with_no_name():
    html = '<div id="main_menu"><a href="https://www.dhakatribune.com/world"></a></div>'
    assert dhakatribune.parse_sections(html) == []


def test_parse_sections_ignores_off_site_links_with_matching_path():
    html = """
    <div id="main_menu">
      <a href="https://not-dhakatribune.com/world">World</a>
    </div>
    """
    assert dhakatribune.parse_sections(html) == []


def test_get_performs_http_request_and_returns_body(monkeypatch):
    class _FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(dhakatribune.time, "sleep", lambda _: None)
    monkeypatch.setattr(dhakatribune._session, "get", lambda url, timeout: _FakeResponse())

    assert dhakatribune._get("https://www.dhakatribune.com/x") == "<html>ok</html>"


def test_discover_sections_falls_back_on_request_failure(monkeypatch):
    monkeypatch.setattr(
        dhakatribune, "_get", lambda url: (_ for _ in ()).throw(requests.RequestException("down"))
    )

    assert dhakatribune.discover_sections() == dhakatribune.FALLBACK_SECTIONS


def test_discover_sections_falls_back_when_nothing_parsed(monkeypatch):
    monkeypatch.setattr(dhakatribune, "_get", lambda url: "<html><body>empty</body></html>")

    assert dhakatribune.discover_sections() == dhakatribune.FALLBACK_SECTIONS


def test_discover_sections_returns_live_parsed_sections(monkeypatch, load_fixture):
    monkeypatch.setattr(dhakatribune, "_get", lambda url: load_fixture("dhakatribune_home.html"))

    sections = dhakatribune.discover_sections()

    assert ("bangladesh", "Bangladesh") in sections


def test_list_articles_fetches_then_parses(monkeypatch, load_fixture):
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        return load_fixture("dhakatribune_section_bangladesh.html")

    monkeypatch.setattr(dhakatribune, "_get", fake_get)

    articles = dhakatribune.list_articles("bangladesh")

    assert seen_urls == ["https://www.dhakatribune.com/bangladesh"]
    assert len(articles) > 0


def test_fetch_article_fetches_then_parses(monkeypatch, load_fixture):
    monkeypatch.setattr(dhakatribune, "_get", lambda url: load_fixture("dhakatribune_article_sample.html"))

    article = dhakatribune.fetch_article("https://www.dhakatribune.com/bangladesh/417636/earthquake-shakes-narsingdi")

    assert article["url"] == "https://www.dhakatribune.com/bangladesh/417636/earthquake-shakes-narsingdi"
    assert article["headline"]


def test_parse_articles_extracts_cards(load_fixture):
    html = load_fixture("dhakatribune_section_bangladesh.html")
    articles = dhakatribune.parse_articles(html)

    assert len(articles) > 0
    first = articles[0]
    assert first["url"].startswith("https://www.dhakatribune.com/bangladesh/")
    assert first["headline"]
    assert first["listing_time"], "expected an ISO data-published timestamp"


def test_parse_articles_resolves_protocol_relative_article_url():
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="//www.dhakatribune.com/world/123/headline">Headline</a></h2>
      <div class="summery">Summary text</div>
      <span class="time" data-published="2026-08-17T09:00:00+06:00">an hour ago</span>
    </div>
    """
    articles = dhakatribune.parse_articles(html)

    assert articles[0]["url"] == "https://www.dhakatribune.com/world/123/headline"
    assert articles[0]["listing_time"] == "2026-08-17T09:00:00+06:00"


def test_parse_articles_falls_back_to_display_text_when_no_data_published():
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="/world/123/headline">Headline</a></h2>
      <span class="time">an hour ago</span>
    </div>
    """
    articles = dhakatribune.parse_articles(html)

    assert articles[0]["listing_time"] == "an hour ago"


def test_parse_articles_skips_cards_with_no_headline_link():
    html = """
    <div class="each">
      <div class="summery">No headline link here</div>
    </div>
    """
    assert dhakatribune.parse_articles(html) == []


def test_parse_articles_leaves_thumbnail_none():
    """Thumbnails are lazy-loaded via a JS-resolved blob, not a plain <img
    src> - deliberately not scraped, see the comment in dhakatribune.py."""
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="/world/123/headline">Headline</a></h2>
    </div>
    """
    assert dhakatribune.parse_articles(html)[0]["thumbnail"] is None


def test_parse_article_extracts_metadata_and_body(load_fixture):
    html = load_fixture("dhakatribune_article_sample.html")
    article = dhakatribune.parse_article(html, "https://www.dhakatribune.com/bangladesh/417636/earthquake-shakes-narsingdi")

    assert article["headline"] == "Earthquake shakes Narsingdi"
    assert article["author"] == "UNB"
    assert article["date_published"] == "2026-08-17T09:57:16+06:00"
    assert article["image_url"].startswith("https://ecdn.dhakatribune.net/")
    assert len(article["paragraphs"]) == 4
    assert all(isinstance(p, str) and p for p in article["paragraphs"])


def test_parse_article_finds_newsarticle_block_even_though_organization_is_first(load_fixture):
    """Regression: the first ld+json block on a Dhaka Tribune article page
    is an Organization block, not the article metadata."""
    from bs4 import BeautifulSoup

    from jugantor_epub.sources import ld_json

    html = load_fixture("dhakatribune_article_sample.html")
    metadata = ld_json.select_by_type(BeautifulSoup(html, "html.parser"), "NewsArticle")

    assert metadata.get("@type") == "NewsArticle"
    assert metadata.get("headline")


def test_parse_article_handles_explicit_json_nulls():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": null, "author": null, "image": null}
      </script>
    </head><body>
      <article class="jw_detail_content_body"><p>Body text.</p></article>
    </body></html>
    """
    article = dhakatribune.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["image_url"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_handles_invalid_json_syntax():
    html = """
    <html><head>
      <script type="application/ld+json">{not valid json at all</script>
    </head><body>
      <article class="jw_detail_content_body"><p>Body text.</p></article>
    </body></html>
    """
    article = dhakatribune.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_accepts_plain_string_author_and_image():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": "H", "author": "Plain Author", "image": "https://example.com/i.jpg"}
      </script>
    </head><body>
      <article class="jw_detail_content_body"><p>Body.</p></article>
    </body></html>
    """
    article = dhakatribune.parse_article(html, "https://example.com/x")

    assert article["author"] == "Plain Author"
    assert article["image_url"] == "https://example.com/i.jpg"


def test_parse_article_missing_ldjson_still_returns_body():
    html = """
    <html><body>
      <article class="jw_detail_content_body"><p>Only body text, no ld+json.</p></article>
    </body></html>
    """
    article = dhakatribune.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["paragraphs"] == ["Only body text, no ld+json."]


def test_get_cover_logo_url_returns_dhakatribune_masthead_logo():
    assert dhakatribune.get_cover_logo_url() == dhakatribune.COVER_LOGO_URL


def test_format_date_uses_english_formatting():
    """Regression: unlike Jugantor/Prothom Alo, Dhaka Tribune is an
    English-language paper - its cover date must not render in Bengali."""
    assert dhakatribune.format_date("2026-08-17") == "17 August, 2026"
