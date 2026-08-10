import main
from jugantor_epub import epub_builder, images


class _FakeSourceOk:
    SOURCE_NAME = "Fake Paper"

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug):
        return [
            {"url": "https://x/1", "headline": "H1", "thumbnail": "https://img/shared.jpg"},
            {"url": "https://x/err", "headline": "H-err", "thumbnail": None},
            {"url": "https://x/3", "headline": "H3", "thumbnail": "https://img/shared.jpg"},
        ]

    @staticmethod
    def fetch_article(url):
        if url == "https://x/err":
            raise RuntimeError("boom")
        return {
            "headline": f"{url} detail",
            "author": "A",
            "date_published": "2026-08-10",
            "image_url": "https://img/shared.jpg",
            "paragraphs": ["p1"],
        }


class _FakeSourceAllFail:
    SOURCE_NAME = "Broken Paper"

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug):
        raise RuntimeError("site is down")

    @staticmethod
    def fetch_article(url):
        raise AssertionError("should never be called")


def test_build_source_edition_skips_failed_article_and_caches_image_downloads(monkeypatch):
    download_calls = []

    def fake_download_image(url, *args, **kwargs):
        download_calls.append(url)
        return ("shared.jpg", b"bytes")

    captured = {}

    def fake_build_epub(source_name, edition_date, sections_with_articles, output_path=None):
        captured["sections_with_articles"] = sections_with_articles
        return "/tmp/fake.epub"

    monkeypatch.setattr(images, "download_image", fake_download_image)
    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    output_path = main.build_source_edition(_FakeSourceOk, "2026-08-10")

    assert output_path == "/tmp/fake.epub"
    # the failing article is skipped, leaving 2 of the 3 listed
    articles = captured["sections_with_articles"][0][1]
    assert len(articles) == 2
    # both surviving articles share one image URL - should be downloaded once
    assert download_calls == ["https://img/shared.jpg"]


def test_build_source_edition_raises_when_nothing_scraped(monkeypatch):
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/unused.epub")

    try:
        main.build_source_edition(_FakeSourceAllFail, "2026-08-10")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Broken Paper" in str(exc)


def test_main_continues_to_next_source_after_one_fails(monkeypatch):
    built_for = []

    monkeypatch.setattr(main.config, "SOURCES", ["broken", "ok"])
    monkeypatch.setattr(
        main.importlib,
        "import_module",
        lambda name: {
            "jugantor_epub.sources.broken": _FakeSourceAllFail,
            "jugantor_epub.sources.ok": _FakeSourceOk,
        }[name],
    )
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(
        epub_builder, "build_epub", lambda *a, **k: built_for.append(a[0]) or "/tmp/x.epub"
    )

    main.main()

    assert built_for == ["Fake Paper"]
