import requests

from jugantor_epub.sources import jugantor


def test_parse_sections_finds_expected_slugs(load_fixture):
    html = load_fixture("todays_paper.html")
    sections = jugantor.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert "tp-firstpage" in slugs
    assert "tp-sports" in slugs
    assert len(slugs) == len(set(slugs)), "sections should be deduplicated"

    firstpage_name = dict(sections)["tp-firstpage"]
    assert firstpage_name == "প্রথম পাতা"


def test_parse_sections_returns_empty_list_on_unrelated_html():
    assert jugantor.parse_sections("<html><body>nothing here</body></html>") == []


def test_parse_sections_dedupes_repeated_slug():
    html = """
    <div class="desktopSubCategoryDiv">
      <a aria-label="প্রথম পাতা" href="/tp-firstpage">প্রথম পাতা</a>
      <a aria-label="প্রথম পাতা (again)" href="/tp-firstpage">প্রথম পাতা</a>
    </div>
    """
    sections = jugantor.parse_sections(html)

    assert len(sections) == 1


def test_get_performs_http_request_and_returns_body(monkeypatch):
    class _FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(jugantor.time, "sleep", lambda _: None)
    monkeypatch.setattr(jugantor._session, "get", lambda url, timeout: _FakeResponse())

    assert jugantor._get("https://www.jugantor.com/x") == "<html>ok</html>"


def test_parse_sections_skips_links_with_no_name():
    html = """
    <div class="desktopSubCategoryDiv">
      <a href="/tp-empty"></a>
    </div>
    """
    assert jugantor.parse_sections(html) == []


def test_discover_sections_falls_back_on_request_failure(monkeypatch):
    monkeypatch.setattr(
        jugantor, "_get", lambda url: (_ for _ in ()).throw(requests.RequestException("down"))
    )

    assert jugantor.discover_sections() == jugantor.FALLBACK_SECTIONS


def test_discover_sections_falls_back_when_nothing_parsed(monkeypatch):
    monkeypatch.setattr(jugantor, "_get", lambda url: "<html><body>empty</body></html>")

    assert jugantor.discover_sections() == jugantor.FALLBACK_SECTIONS


def test_discover_sections_returns_live_parsed_sections(monkeypatch, load_fixture):
    monkeypatch.setattr(jugantor, "_get", lambda url: load_fixture("todays_paper.html"))

    sections = jugantor.discover_sections()

    assert ("tp-firstpage", "প্রথম পাতা") in sections


def test_list_articles_fetches_then_parses(monkeypatch, load_fixture):
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        return load_fixture("section_firstpage.html")

    monkeypatch.setattr(jugantor, "_get", fake_get)

    articles = jugantor.list_articles("tp-firstpage")

    assert seen_urls == ["https://www.jugantor.com/tp-firstpage"]
    assert len(articles) > 0


def test_fetch_article_fetches_then_parses(monkeypatch, load_fixture):
    monkeypatch.setattr(jugantor, "_get", lambda url: load_fixture("article_sample.html"))

    article = jugantor.fetch_article("https://www.jugantor.com/tp-firstpage/1138370")

    assert article["url"] == "https://www.jugantor.com/tp-firstpage/1138370"
    assert article["headline"]


def test_parse_articles_extracts_cards(load_fixture):
    html = load_fixture("section_firstpage.html")
    articles = jugantor.parse_articles(html)

    assert len(articles) > 0
    first = articles[0]
    assert first["url"] == "https://www.jugantor.com/tp-firstpage/1138370"
    assert "বিশৃঙ্খল বাসে বাড়ছে যানজট" in first["headline"]
    assert first["thumbnail"].startswith("https://cdn.jugantor.com/")
    assert first["listing_time"]


def test_parse_article_extracts_metadata_and_body(load_fixture):
    html = load_fixture("article_sample.html")
    article = jugantor.parse_article(html, "https://www.jugantor.com/tp-firstpage/1138370")

    assert article["headline"] == "বিশৃঙ্খল বাসে বাড়ছে যানজট"
    assert article["author"] == "মতিন আব্দুল্লাহ"
    assert article["date_published"] == "2026-08-10T00:00:00+06:00"
    assert article["image_url"].startswith("https://cdn.jugantor.com/")
    assert len(article["paragraphs"]) > 0
    assert all(isinstance(p, str) and p for p in article["paragraphs"])


def test_parse_article_handles_raw_newline_in_ldjson(load_fixture):
    """Regression test: some pages embed a literal newline inside a JSON
    string value (e.g. multi-line headline), which strict json.loads
    rejects. parse_article must still recover title/body via strict=False."""
    html = load_fixture("article_raw_newline_ldjson.html")
    article = jugantor.parse_article(html, "https://www.jugantor.com/tp-city/1137912")

    assert article["headline"], "headline should be recovered despite the embedded newline"
    assert "\n" not in article["headline"]
    assert len(article["paragraphs"]) > 0


def test_parse_article_handles_explicit_json_nulls():
    """Regression test: ld+json fields present but set to JSON null (not
    merely absent) must not crash - metadata.get(key, default) only
    falls back when the key is missing, not when its value is null."""
    html = """
    <html><body>
      <script type="application/ld+json">
      {"headline": null, "author": {"name": null}, "image": null}
      </script>
      <div class="desktopDetailBody"><p>Body text.</p></div>
    </body></html>
    """
    article = jugantor.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["image_url"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_articles_resolves_relative_thumbnail_url():
    html = """
    <html><body>
      <div class="media positionRelative">
        <img data-src="/uploads/pic.jpg">
        <div class="title10">Headline</div>
        <a class="linkOverlay" href="/tp-firstpage/123"></a>
      </div>
    </body></html>
    """
    articles = jugantor.parse_articles(html)

    assert articles[0]["thumbnail"] == "https://www.jugantor.com/uploads/pic.jpg"


def test_parse_article_handles_invalid_json_syntax():
    html = """
    <html><body>
      <script type="application/ld+json">{not valid json at all</script>
      <div class="desktopDetailBody"><p>Body text.</p></div>
    </body></html>
    """
    article = jugantor.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_accepts_plain_string_author_and_image():
    html = """
    <html><body>
      <script type="application/ld+json">
      {"headline": "H", "author": "Plain Author", "image": "https://example.com/i.jpg"}
      </script>
      <div class="desktopDetailBody"><p>Body.</p></div>
    </body></html>
    """
    article = jugantor.parse_article(html, "https://example.com/x")

    assert article["author"] == "Plain Author"
    assert article["image_url"] == "https://example.com/i.jpg"


def test_parse_article_missing_ldjson_still_returns_body():
    html = """
    <html><body>
      <div class="desktopDetailBody"><p>Only body text, no ld+json.</p></div>
    </body></html>
    """
    article = jugantor.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["paragraphs"] == ["Only body text, no ld+json."]


def test_get_cover_logo_url_returns_jugantor_masthead_logo():
    assert jugantor.get_cover_logo_url() == "https://cdn.jugantor.com/uploads/settings/logo-black.png"
