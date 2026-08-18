from bs4 import BeautifulSoup

from jugantor_epub.sources import ld_json


def test_select_by_type_returns_matching_block():
    html = """
    <script type="application/ld+json">{"@type": "BreadcrumbList", "x": 1}</script>
    <script type="application/ld+json">{"@type": "NewsArticle", "headline": "H"}</script>
    """
    soup = BeautifulSoup(html, "html.parser")

    result = ld_json.select_by_type(soup, "NewsArticle")

    assert result == {"@type": "NewsArticle", "headline": "H"}


def test_select_by_type_returns_empty_dict_when_no_block_matches():
    html = '<script type="application/ld+json">{"@type": "BreadcrumbList"}</script>'
    soup = BeautifulSoup(html, "html.parser")

    assert ld_json.select_by_type(soup, "NewsArticle") == {}


def test_select_by_type_returns_empty_dict_when_no_ldjson_present():
    soup = BeautifulSoup("<html><body>nothing here</body></html>", "html.parser")

    assert ld_json.select_by_type(soup, "NewsArticle") == {}


def test_select_by_type_skips_blocks_with_invalid_json_syntax():
    html = """
    <script type="application/ld+json">{not valid json at all</script>
    <script type="application/ld+json">{"@type": "NewsArticle", "headline": "H"}</script>
    """
    soup = BeautifulSoup(html, "html.parser")

    result = ld_json.select_by_type(soup, "NewsArticle")

    assert result.get("headline") == "H"


def test_select_by_type_handles_raw_newline_in_string_value():
    """Regression: some sites embed a literal newline inside a JSON string
    value (e.g. a multi-line headline), which strict json.loads rejects."""
    html = (
        '<script type="application/ld+json">'
        '{"@type": "NewsArticle", "headline": "line one\nline two"}'
        "</script>"
    )
    soup = BeautifulSoup(html, "html.parser")

    result = ld_json.select_by_type(soup, "NewsArticle")

    assert result.get("headline") == "line one\nline two"


def test_select_by_type_skips_non_dict_json_values():
    html = '<script type="application/ld+json">["not", "a", "dict"]</script>'
    soup = BeautifulSoup(html, "html.parser")

    assert ld_json.select_by_type(soup, "NewsArticle") == {}


def test_select_by_type_finds_block_inside_graph_array():
    """Regression: Daily Star's Drupal setup bundles every entity for the
    page into one block via a schema.org "@graph" array instead of emitting
    separate <script> blocks per type."""
    html = """
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
      {"@type": "NewsArticle", "headline": "H"},
      {"@type": "Organization", "name": "Publisher"}
    ]}
    </script>
    """
    soup = BeautifulSoup(html, "html.parser")

    result = ld_json.select_by_type(soup, "NewsArticle")

    assert result == {"@type": "NewsArticle", "headline": "H"}


def test_select_by_type_prefers_top_level_type_over_graph():
    html = """
    <script type="application/ld+json">
    {"@type": "NewsArticle", "headline": "Top level", "@graph": [
      {"@type": "NewsArticle", "headline": "Nested"}
    ]}
    </script>
    """
    soup = BeautifulSoup(html, "html.parser")

    result = ld_json.select_by_type(soup, "NewsArticle")

    assert result.get("headline") == "Top level"
