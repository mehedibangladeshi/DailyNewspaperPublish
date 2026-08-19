from datetime import datetime, timezone

import pytest

import main
from jugantor_epub import epub_builder, images


@pytest.fixture(autouse=True)
def _no_real_kindle_email(monkeypatch):
    """Guard against any test in this file accidentally dialing out to real

    Gmail SMTP: default sending off and make an unstubbed KindleSender.send
    call fail loudly instead of silently reaching smtplib. Tests that
    deliberately exercise sending override this via monkeypatch later in
    their own body; since they share this fixture's monkeypatch instance,
    their explicit setattr calls run after this default and take precedence.
    """
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", False)

    def _unexpected_send(self, *args, **kwargs):
        raise AssertionError("unexpected send")

    monkeypatch.setattr(main.email_sender.KindleSender, "send", _unexpected_send)


@pytest.fixture(autouse=True)
def _no_real_opds_publish(monkeypatch):
    """Same guard as _no_real_kindle_email, for the OPDS publish path."""
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", False)

    def _unexpected_publish(*args, **kwargs):
        raise AssertionError("unexpected publish")

    monkeypatch.setattr(main.opds_publish, "publish_catalog", _unexpected_publish)


class _FakeSourceOk:
    SOURCE_NAME = "Fake Paper"
    COVER_ACCENT_COLOR = (10, 20, 30)

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug, edition_date):
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

    @staticmethod
    def get_cover_logo_url():
        return "https://x/logo.png"

    @staticmethod
    def format_date(edition_date):
        return f"formatted-{edition_date}"


class _FakeSourceOk2:
    SOURCE_NAME = "Fake Paper 2"
    COVER_ACCENT_COLOR = (40, 50, 60)

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug, edition_date):
        return [{"url": "https://x/2", "headline": "H2", "thumbnail": None}]

    @staticmethod
    def fetch_article(url):
        return {
            "headline": "H2 detail",
            "author": "B",
            "date_published": "2026-08-10",
            "image_url": None,
            "paragraphs": ["p2"],
        }

    @staticmethod
    def get_cover_logo_url():
        return "https://x/logo2.png"

    @staticmethod
    def format_date(edition_date):
        return f"formatted-{edition_date}"


class _FakeSourceAllFail:
    SOURCE_NAME = "Broken Paper"

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug, edition_date):
        raise RuntimeError("site is down")

    @staticmethod
    def fetch_article(url):
        raise AssertionError("should never be called")

    @staticmethod
    def get_cover_logo_url():
        return "https://x/logo.png"


def test_build_source_edition_skips_failed_article_and_caches_image_downloads(monkeypatch):
    download_calls = []

    def fake_download_image(url, *args, **kwargs):
        download_calls.append(url)
        return ("shared.jpg", b"bytes")

    captured = {}

    def fake_build_epub(source_name, edition_date, sections_with_articles, **kwargs):
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


def test_build_source_edition_passes_rendered_cover_to_build_epub(monkeypatch):
    render_calls = []

    def fake_render_cover(source_name, date_text, logo_url, accent_color, prepare_logo=None):
        render_calls.append((source_name, date_text, logo_url, accent_color, prepare_logo))
        return b"COVERBYTES"

    captured = {}

    def fake_build_epub(source_name, edition_date, sections_with_articles, **kwargs):
        captured["cover_image_bytes"] = kwargs.get("cover_image_bytes")
        return "/tmp/fake.epub"

    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(main.cover, "render_cover", fake_render_cover)
    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    main.build_source_edition(_FakeSourceOk, "2026-08-10")

    assert render_calls == [("Fake Paper", "formatted-2026-08-10", "https://x/logo.png", (10, 20, 30), None)]
    assert captured["cover_image_bytes"] == b"COVERBYTES"


def test_build_source_edition_forwards_a_sources_prepare_logo_image_when_defined(monkeypatch):
    """Sources that don't define prepare_logo_image (like Jugantor) pass
    None, verified above; a source that does define one (like Prothom Alo)
    must have it forwarded to cover.render_cover."""
    render_calls = []

    def fake_render_cover(source_name, date_text, logo_url, accent_color, prepare_logo=None):
        render_calls.append(prepare_logo)
        return b"COVERBYTES"

    def fake_prepare_logo_image(image):
        return image

    class _FakeSourceWithLogoPrep(_FakeSourceOk):
        prepare_logo_image = staticmethod(fake_prepare_logo_image)

    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(main.cover, "render_cover", fake_render_cover)
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/fake.epub")

    main.build_source_edition(_FakeSourceWithLogoPrep, "2026-08-10")

    assert render_calls == [fake_prepare_logo_image]


def test_build_source_edition_builds_without_cover_when_render_cover_fails(monkeypatch):
    captured = {}

    def fake_build_epub(source_name, edition_date, sections_with_articles, **kwargs):
        captured["cover_image_bytes"] = kwargs.get("cover_image_bytes")
        return "/tmp/fake.epub"

    def _boom(*a, **k):
        raise RuntimeError("PIL exploded")

    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(main.cover, "render_cover", _boom)
    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    output_path = main.build_source_edition(_FakeSourceOk, "2026-08-10")

    assert output_path == "/tmp/fake.epub"
    assert captured["cover_image_bytes"] is None


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

    exit_code = main.main()

    assert built_for == ["Fake Paper"]
    # Per the plan's Global Constraints, a build failure now flips the exit
    # code non-zero even though the run continues to the next source and
    # the successful source still gets built.
    assert exit_code == 1


def test_main_returns_nonzero_when_all_sources_fail(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["broken"])
    monkeypatch.setattr(
        main.importlib, "import_module", lambda name: _FakeSourceAllFail
    )

    exit_code = main.main()

    assert exit_code == 1


def test_main_does_not_send_when_send_to_kindle_disabled(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", False)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    exit_code = main.main()

    assert exit_code == 0
    # the autouse fixture's KindleSender.send would raise AssertionError if called


def test_main_sends_one_email_per_built_source_as_soon_as_it_builds(monkeypatch):
    sent = []
    build_order = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok1", "ok2"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(
        main.importlib,
        "import_module",
        lambda name: {
            "jugantor_epub.sources.ok1": _FakeSourceOk,
            "jugantor_epub.sources.ok2": _FakeSourceOk2,
        }[name],
    )
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))

    def fake_build_epub(source_name, *a, **k):
        build_order.append(source_name)
        return f"/tmp/{source_name}.epub"

    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    def fake_send(self, source_name, epub_path, edition_date):
        sent.append((source_name, epub_path, edition_date))
        return True

    monkeypatch.setattr(main.email_sender.KindleSender, "send", fake_send)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 10, 12, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(main, "datetime", _FixedDatetime)

    exit_code = main.main()

    assert exit_code == 0
    assert build_order == ["Fake Paper", "Fake Paper 2"]
    assert sent == [
        ("Fake Paper", "/tmp/Fake Paper.epub", "2026-08-10"),
        ("Fake Paper 2", "/tmp/Fake Paper 2.epub", "2026-08-10"),
    ]


def test_main_returns_nonzero_when_send_to_kindle_fails(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(self, *a, **k):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.email_sender.KindleSender, "send", _boom)

    exit_code = main.main()

    assert exit_code == 1


def test_main_returns_zero_when_send_is_only_size_skipped(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")
    monkeypatch.setattr(
        main.email_sender.KindleSender, "send", lambda self, *a, **k: False
    )

    exit_code = main.main()

    assert exit_code == 0


def test_main_does_not_publish_opds_when_disabled(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", False)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    exit_code = main.main()

    assert exit_code == 0


def test_main_publishes_opds_catalog_when_enabled(monkeypatch):
    published = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", True)
    monkeypatch.setattr(main.config, "GH_PAGES_DIR", "/tmp/gh-pages")
    monkeypatch.setattr(main.config, "OUTPUT_DIR", "/tmp/output")
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")
    monkeypatch.setattr(
        main.opds_publish, "publish_catalog", lambda *a, **k: published.append(a)
    )

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 10, 12, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(main, "datetime", _FixedDatetime)

    exit_code = main.main()

    assert exit_code == 0
    assert published == [("/tmp/gh-pages", "/tmp/output", "2026-08-10")]


def test_main_returns_nonzero_when_opds_publish_fails(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(*a, **k):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(main.opds_publish, "publish_catalog", _boom)

    exit_code = main.main()

    assert exit_code == 1


def test_main_still_publishes_opds_when_kindle_send_fails(monkeypatch):
    published = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(self, *a, **k):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.email_sender.KindleSender, "send", _boom)
    monkeypatch.setattr(
        main.opds_publish, "publish_catalog", lambda *a, **k: published.append(a)
    )

    exit_code = main.main()

    assert exit_code == 1  # Kindle failure still surfaces as a failed run
    assert len(published) == 1  # but OPDS still got published
