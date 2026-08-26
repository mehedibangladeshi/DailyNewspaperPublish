import pytest
import requests

from jugantor_epub.sources import ittefaq


def test_parse_sections_finds_expected_slugs(load_fixture):
    html = load_fixture("ittefaq_home.html")
    sections = ittefaq.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "national" in slugs
    assert "sports" in slugs
    assert "editorial" in slugs
    assert len(slugs) == len(set(slugs)), "sections should be deduplicated"

    names = dict(sections)
    assert names["national"] == "জাতীয়"
    assert names["sports"] == "খেলা"


def test_parse_sections_excludes_non_core_nav_items(load_fixture):
    html = load_fixture("ittefaq_home.html")
    sections = ittefaq.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "video" not in slugs, "video pages have no usable text body"
    assert "photo" not in slugs, "photo galleries have no prose"
    assert "jobs" not in slugs, "classifieds aren't news narrative"
    assert "latest-news" not in slugs, "redundant aggregate of every other section"


def test_parse_sections_returns_empty_list_on_unrelated_html():
    assert ittefaq.parse_sections("<html><body>nothing here</body></html>") == []


def test_parse_sections_dedupes_repeated_slug():
    html = """
    <div>
      <a href="https://www.ittefaq.com.bd/sports">খেলা</a>
      <a href="https://www.ittefaq.com.bd/sports">খেলা (again)</a>
    </div>
    """
    sections = ittefaq.parse_sections(html)

    assert len(sections) == 1


def test_parse_sections_skips_links_with_no_name():
    html = '<a href="https://www.ittefaq.com.bd/sports"></a>'
    assert ittefaq.parse_sections(html) == []


def test_parse_sections_ignores_off_site_links_with_matching_path():
    html = '<a href="https://not-ittefaq.com.bd/sports">খেলা</a>'
    assert ittefaq.parse_sections(html) == []


def test_get_performs_http_request_and_returns_body(monkeypatch):
    class _FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(ittefaq.time, "sleep", lambda _: None)
    monkeypatch.setattr(ittefaq._session, "get", lambda url, timeout: _FakeResponse())

    assert ittefaq._get("https://www.ittefaq.com.bd/x") == "<html>ok</html>"


def test_discover_sections_falls_back_on_request_failure(monkeypatch):
    monkeypatch.setattr(
        ittefaq, "_get", lambda url: (_ for _ in ()).throw(requests.RequestException("down"))
    )

    assert ittefaq.discover_sections() == ittefaq.FALLBACK_SECTIONS


def test_discover_sections_falls_back_when_nothing_parsed(monkeypatch):
    monkeypatch.setattr(ittefaq, "_get", lambda url: "<html><body>empty</body></html>")

    assert ittefaq.discover_sections() == ittefaq.FALLBACK_SECTIONS


def test_discover_sections_returns_live_parsed_sections(monkeypatch, load_fixture):
    monkeypatch.setattr(ittefaq, "_get", lambda url: load_fixture("ittefaq_home.html"))

    sections = ittefaq.discover_sections()

    assert ("sports", "খেলা") in sections


def test_discover_sections_moves_editorial_off_the_front(monkeypatch, load_fixture):
    monkeypatch.setattr(ittefaq, "_get", lambda url: load_fixture("ittefaq_home.html"))

    sections = ittefaq.discover_sections()

    assert sections[0][0] != "editorial"
    slugs = [slug for slug, _ in sections]
    assert len(slugs) - slugs.index("editorial") - 1 == ittefaq.EDITORIAL_SECTIONS_AFTER


def test_reorder_editorial_moves_it_to_fixed_offset_from_end():
    sections = [("editorial", "সম্পাদকীয়"), ("a", "A"), ("b", "B"), ("c", "C")]

    reordered = ittefaq._reorder_editorial(sections)

    assert reordered == [("a", "A"), ("editorial", "সম্পাদকীয়"), ("b", "B"), ("c", "C")]


def test_reorder_editorial_is_noop_when_editorial_absent():
    sections = [("a", "A"), ("b", "B")]

    assert ittefaq._reorder_editorial(sections) == sections


def test_reorder_editorial_appends_at_end_when_too_few_sections_remain():
    sections = [("editorial", "সম্পাদকীয়"), ("a", "A")]

    reordered = ittefaq._reorder_editorial(sections)

    assert reordered == [("a", "A"), ("editorial", "সম্পাদকীয়")]


def test_reorder_editorial_preserves_relative_order_of_other_sections():
    sections = [("editorial", "সম্পাদকীয়"), ("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]

    reordered = ittefaq._reorder_editorial(sections)

    slugs = [slug for slug, _ in reordered]
    assert slugs == ["a", "b", "editorial", "c", "d"]


def test_list_articles_fetches_then_parses(monkeypatch, load_fixture):
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        return load_fixture("ittefaq_section_sports.html")

    monkeypatch.setattr(ittefaq, "_get", fake_get)

    articles = ittefaq.list_articles("sports")

    assert seen_urls == ["https://www.ittefaq.com.bd/sports"]
    assert len(articles) > 0


def test_fetch_article_fetches_then_parses(monkeypatch, load_fixture):
    monkeypatch.setattr(ittefaq, "_get", lambda url: load_fixture("ittefaq_article_sample.html"))

    article = ittefaq.fetch_article("https://www.ittefaq.com.bd/804943/x")

    assert article["url"] == "https://www.ittefaq.com.bd/804943/x"
    assert article["headline"]


def test_parse_articles_extracts_cards(load_fixture):
    html = load_fixture("ittefaq_section_sports.html")
    articles = ittefaq.parse_articles(html)

    assert len(articles) > 0
    first = articles[0]
    assert first["url"].startswith("https://www.ittefaq.com.bd/")
    assert first["headline"]
    assert first["summary"]
    assert first["listing_time"], "expected an ISO data-published timestamp"
    assert first["thumbnail"] is None


def test_parse_articles_resolves_protocol_relative_article_url():
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="//www.ittefaq.com.bd/123/headline">Headline</a></h2>
      <div class="summery">Summary text</div>
      <span class="time" data-published="2026-08-19T09:00:00+06:00">an hour ago</span>
    </div>
    """
    articles = ittefaq.parse_articles(html)

    assert articles[0]["url"] == "https://www.ittefaq.com.bd/123/headline"
    assert articles[0]["listing_time"] == "2026-08-19T09:00:00+06:00"


def test_parse_articles_falls_back_to_display_text_when_no_data_published():
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="/123/headline">Headline</a></h2>
      <span class="time">an hour ago</span>
    </div>
    """
    articles = ittefaq.parse_articles(html)

    assert articles[0]["listing_time"] == "an hour ago"


def test_parse_articles_skips_cards_with_no_headline_link():
    html = """
    <div class="each">
      <div class="summery">No headline link here</div>
    </div>
    """
    assert ittefaq.parse_articles(html) == []


def test_parse_articles_dedupes_repeated_url():
    """The same story can appear in more than one listing widget on a page."""
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="/123/headline">Headline</a></h2>
    </div>
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="/123/headline">Headline</a></h2>
    </div>
    """
    assert len(ittefaq.parse_articles(html)) == 1


def test_parse_articles_leaves_thumbnail_none():
    """Thumbnails are lazy-loaded via a JS-resolved data-ari blob, not a
    plain <img src> - deliberately not scraped, see ittefaq.py."""
    html = """
    <div class="each">
      <h2 class="title"><a class="link_overlay" href="/123/headline">Headline</a></h2>
    </div>
    """
    assert ittefaq.parse_articles(html)[0]["thumbnail"] is None


def test_parse_article_extracts_metadata_and_body(load_fixture):
    html = load_fixture("ittefaq_article_sample.html")
    article = ittefaq.parse_article(html, "https://www.ittefaq.com.bd/804943/x")

    assert article["headline"] == "ব্রাজিল কিংবদন্তি রবার্তো কার্লোসের ইসলাম গ্রহণের গুঞ্জন"
    assert article["author"] == "ইত্তেফাক ডিজিটাল ডেস্ক"
    assert article["date_published"] == "2026-08-19T09:31:56+06:00"
    assert article["image_url"].startswith("https://cdn.ittefaqbd.com/")
    assert len(article["paragraphs"]) == 9
    assert all(isinstance(p, str) and p for p in article["paragraphs"])


def test_parse_article_finds_newsarticle_block_even_though_organization_is_first(load_fixture):
    """Regression: the first ld+json block on an Ittefaq article page is an
    Organization block (a Website block follows) - the article metadata is
    the third block."""
    from bs4 import BeautifulSoup

    from jugantor_epub.sources import ld_json

    html = load_fixture("ittefaq_article_sample.html")
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
      <div class="jw_article_body"><p>Body text.</p></div>
    </body></html>
    """
    article = ittefaq.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["image_url"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_handles_invalid_json_syntax():
    html = """
    <html><head>
      <script type="application/ld+json">{not valid json at all</script>
    </head><body>
      <div class="jw_article_body"><p>Body text.</p></div>
    </body></html>
    """
    article = ittefaq.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_accepts_plain_string_author_and_image():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@type": "NewsArticle", "headline": "H", "author": "Plain Author", "image": "https://example.com/i.jpg"}
      </script>
    </head><body>
      <div class="jw_article_body"><p>Body.</p></div>
    </body></html>
    """
    article = ittefaq.parse_article(html, "https://example.com/x")

    assert article["author"] == "Plain Author"
    assert article["image_url"] == "https://example.com/i.jpg"


def test_parse_article_missing_ldjson_still_returns_body():
    html = """
    <html><body>
      <div class="jw_article_body"><p>Only body text, no ld+json.</p></div>
    </body></html>
    """
    article = ittefaq.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["paragraphs"] == ["Only body text, no ld+json."]


def test_get_cover_logo_url_returns_ittefaq_masthead_logo():
    assert ittefaq.get_cover_logo_url() == ittefaq.COVER_LOGO_URL


def test_format_date_uses_bengali_formatting():
    from jugantor_epub import bengali_date

    assert ittefaq.format_date("2026-08-19") == bengali_date.format_bengali_date("2026-08-19")
