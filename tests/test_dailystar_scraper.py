import requests

from jugantor_epub.sources import dailystar


def setup_function(_):
    # Each test should see a clean per-run cache, same reasoning as
    # main.py running dailystar.discover_sections() once at the top of a
    # real build - never leak a fetch across two unrelated test cases.
    dailystar._listing_cache.clear()


def test_parse_todays_news_groups_articles_by_url_section(load_fixture):
    html = load_fixture("dailystar_todays_news.html")
    grouped = dailystar.parse_todays_news(html)

    assert "business" in grouped
    assert "sports" in grouped
    assert len(grouped["business"]) > 0

    article = grouped["business"][0]
    assert article["url"].startswith("https://www.thedailystar.net/business/")
    assert article["headline"]
    assert article["thumbnail"].startswith("https://www.thedailystar.net/")


def test_parse_todays_news_dedupes_by_url():
    html = """
    <div class="views-row">
      <img src="/img1.jpg" />
      <h3 class="card-title"><a href="/business/news/story-1">Story One</a></h3>
      <div class="card-intro">Summary</div>
      <div class="card-info"><span>18 August 2026</span></div>
    </div>
    <div class="views-row">
      <img src="/img1.jpg" />
      <h5 class="field-content card-title"><a href="/business/news/story-1">Story One (again)</a></h5>
      <div class="card-info"><span>18 August 2026</span></div>
    </div>
    """
    grouped = dailystar.parse_todays_news(html)

    assert sum(len(articles) for articles in grouped.values()) == 1


def test_parse_todays_news_excludes_star_multimedia_section():
    html = """
    <div class="views-row">
      <img src="/img1.jpg" />
      <h3 class="card-title"><a href="/star-multimedia/news/video-story">Video story</a></h3>
      <div class="card-info"><span>18 August 2026</span></div>
    </div>
    <div class="views-row">
      <img src="/img2.jpg" />
      <h3 class="card-title"><a href="/business/news/real-story">Real story</a></h3>
      <div class="card-info"><span>18 August 2026</span></div>
    </div>
    """
    grouped = dailystar.parse_todays_news(html)

    assert "star-multimedia" not in grouped
    assert list(grouped.keys()) == ["business"]


def test_parse_todays_news_skips_rows_without_card_title():
    html = """
    <div class="views-row"><div class="card-intro">No title here</div></div>
    """
    assert dailystar.parse_todays_news(html) == {}


def test_parse_todays_news_returns_empty_dict_on_unrelated_html():
    assert dailystar.parse_todays_news("<html><body>nothing here</body></html>") == {}


def test_parse_todays_news_handles_missing_thumbnail_and_summary():
    html = """
    <div class="views-row">
      <h3 class="card-title"><a href="/opinion/news/no-image">No image story</a></h3>
      <div class="card-info"><span>18 August 2026</span></div>
    </div>
    """
    grouped = dailystar.parse_todays_news(html)

    article = grouped["opinion"][0]
    assert article["thumbnail"] is None
    assert article["summary"] == ""


def test_get_performs_http_request_and_returns_body(monkeypatch):
    class _FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(dailystar.time, "sleep", lambda _: None)
    monkeypatch.setattr(dailystar._session, "get", lambda url, timeout: _FakeResponse())

    assert dailystar._get("https://www.thedailystar.net/todays-news") == "<html>ok</html>"


def test_discover_sections_falls_back_on_request_failure(monkeypatch):
    monkeypatch.setattr(
        dailystar, "_get", lambda url: (_ for _ in ()).throw(requests.RequestException("down"))
    )

    assert dailystar.discover_sections() == dailystar.FALLBACK_SECTIONS


def test_discover_sections_falls_back_when_nothing_parsed(monkeypatch):
    monkeypatch.setattr(dailystar, "_get", lambda url: "<html><body>empty</body></html>")

    assert dailystar.discover_sections() == dailystar.FALLBACK_SECTIONS


def test_fallback_sections_excludes_star_multimedia():
    slugs = [slug for slug, _ in dailystar.FALLBACK_SECTIONS]
    assert "star-multimedia" not in slugs


def test_discover_sections_returns_live_parsed_sections(monkeypatch, load_fixture):
    monkeypatch.setattr(dailystar, "_get", lambda url: load_fixture("dailystar_todays_news.html"))

    sections = dailystar.discover_sections()

    slugs = dict(sections)
    assert "business" in slugs
    assert slugs["business"] == "Business"


def test_discover_sections_and_list_articles_share_one_fetch(monkeypatch, load_fixture):
    """Regression: unlike every other source, all of Daily Star's sections
    live on one URL - discover_sections() and list_articles() must share a
    single fetch+parse per run instead of re-requesting /todays-news once
    per section."""
    fetch_count = 0

    def fake_get(url):
        nonlocal fetch_count
        fetch_count += 1
        return load_fixture("dailystar_todays_news.html")

    monkeypatch.setattr(dailystar, "_get", fake_get)

    sections = dailystar.discover_sections()
    for slug, _ in sections:
        dailystar.list_articles(slug, "2026-08-18")

    assert fetch_count == 1


def test_list_articles_returns_only_requested_section(load_fixture, monkeypatch):
    monkeypatch.setattr(dailystar, "_get", lambda url: load_fixture("dailystar_todays_news.html"))

    business_articles = dailystar.list_articles("business", "2026-08-18")
    sports_articles = dailystar.list_articles("sports", "2026-08-18")

    assert len(business_articles) > 0
    assert all(a["url"].startswith("https://www.thedailystar.net/business/") for a in business_articles)
    assert len(sports_articles) > 0


def test_list_articles_returns_empty_list_for_unknown_slug(load_fixture, monkeypatch):
    monkeypatch.setattr(dailystar, "_get", lambda url: load_fixture("dailystar_todays_news.html"))

    assert dailystar.list_articles("no-such-section", "2026-08-18") == []


def test_fetch_article_fetches_then_parses(monkeypatch, load_fixture):
    monkeypatch.setattr(dailystar, "_get", lambda url: load_fixture("dailystar_article_sample.html"))

    article = dailystar.fetch_article(
        "https://www.thedailystar.net/business/economy/news/bb-sets-54-higher-agri-rural-credit-target-4250126"
    )

    assert article["url"].endswith("4250126")
    assert article["headline"]


def test_parse_article_extracts_metadata_and_body(load_fixture):
    html = load_fixture("dailystar_article_sample.html")
    url = "https://www.thedailystar.net/business/economy/news/bb-sets-54-higher-agri-rural-credit-target-4250126"

    article = dailystar.parse_article(html, url)

    assert article["headline"] == "BB sets 54% higher agri, rural credit target"
    assert article["author"] == "Star Business Report"
    assert article["date_published"] == "18 August 2026"
    assert article["image_url"].startswith("https://www.thedailystar.net/sites/default/files/")
    assert len(article["paragraphs"]) > 0
    assert all(isinstance(p, str) and p for p in article["paragraphs"])


def test_parse_article_finds_newsarticle_block_inside_graph(load_fixture):
    """Regression: the whole page's ld+json metadata is bundled as one
    schema.org @graph array, not separate <script> blocks per type."""
    html = load_fixture("dailystar_article_sample.html")

    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["headline"] == "BB sets 54% higher agri, rural credit target"


def test_parse_article_handles_list_shaped_author_name():
    """Regression: wire-service pieces carry author.name as a list
    (["AFP", "Paris"]), unlike Jugantor/Dhaka Tribune/Prothom Alo's
    dict-or-string-only author shapes."""
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph": [{"@type": "NewsArticle", "headline": "H", "author": {"name": ["AFP", "Paris"]}}]}
      </script>
    </head><body>
      <div class="block-field-blocknodenewsbody"><p>Body text.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["author"] == "AFP, Paris"


def test_parse_article_handles_plain_string_author_name():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph": [{"@type": "NewsArticle", "headline": "H", "author": {"name": "The Daily Star"}}]}
      </script>
    </head><body>
      <div class="block-field-blocknodenewsbody"><p>Body text.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["author"] == "The Daily Star"


def test_parse_article_handles_plain_string_author_field():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph": [{"@type": "NewsArticle", "headline": "H", "author": "Plain Author"}]}
      </script>
    </head><body>
      <div class="block-field-blocknodenewsbody"><p>Body text.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["author"] == "Plain Author"


def test_parse_article_handles_explicit_json_nulls():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph": [{"@type": "NewsArticle", "headline": null, "author": null}]}
      </script>
    </head><body>
      <div class="block-field-blocknodenewsbody"><p>Body text.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["image_url"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_handles_invalid_json_syntax():
    html = """
    <html><head>
      <script type="application/ld+json">{not valid json at all</script>
    </head><body>
      <div class="block-field-blocknodenewsbody"><p>Body text.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["paragraphs"] == ["Body text."]


def test_parse_article_missing_ldjson_still_returns_body():
    html = """
    <html><body>
      <div class="block-field-blocknodenewsbody"><p>Only body text, no ld+json.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["headline"] == ""
    assert article["author"] == ""
    assert article["paragraphs"] == ["Only body text, no ld+json."]


def test_parse_article_missing_date_and_image_default_gracefully():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph": [{"@type": "NewsArticle", "headline": "H"}]}
      </script>
    </head><body>
      <div class="block-field-blocknodenewsbody"><p>Body.</p></div>
    </body></html>
    """
    article = dailystar.parse_article(html, "https://example.com/x")

    assert article["date_published"] == ""
    assert article["image_url"] == ""


def test_get_cover_logo_url_returns_bundled_local_asset_path():
    import os

    url = dailystar.get_cover_logo_url()

    assert url == dailystar.COVER_LOGO_URL
    assert not url.startswith("http")
    assert os.path.exists(url)


def test_format_date_uses_english_formatting():
    assert dailystar.format_date("2026-08-18") == "18 August, 2026"
