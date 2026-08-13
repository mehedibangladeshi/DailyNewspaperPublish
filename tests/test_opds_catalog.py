from datetime import date

from jugantor_epub import opds_catalog


def test_parse_edition_filename_extracts_slug_and_date():
    assert opds_catalog.parse_edition_filename("jugantor-2026-08-13.epub") == (
        "jugantor",
        date(2026, 8, 13),
    )


def test_parse_edition_filename_handles_hyphenated_slug():
    assert opds_catalog.parse_edition_filename("prothom-alo-2026-08-13.epub") == (
        "prothom-alo",
        date(2026, 8, 13),
    )


def test_parse_edition_filename_rejects_non_epub():
    assert opds_catalog.parse_edition_filename("jugantor-2026-08-13.txt") is None


def test_parse_edition_filename_rejects_malformed_date():
    assert opds_catalog.parse_edition_filename("jugantor-notadate.epub") is None


def test_parse_edition_filename_rejects_missing_slug():
    assert opds_catalog.parse_edition_filename("2026-08-13.epub") is None


def test_keep_latest_n_keeps_newest_first_within_limit():
    filenames = [
        "jugantor-2026-08-10.epub",
        "jugantor-2026-08-13.epub",
        "jugantor-2026-08-11.epub",
    ]
    kept, evicted = opds_catalog.keep_latest_n(filenames, 7)
    assert kept == [
        "jugantor-2026-08-13.epub",
        "jugantor-2026-08-11.epub",
        "jugantor-2026-08-10.epub",
    ]
    assert evicted == []


def test_keep_latest_n_evicts_oldest_beyond_limit():
    filenames = [f"jugantor-2026-08-{day:02d}.epub" for day in range(1, 9)]  # 8 editions
    kept, evicted = opds_catalog.keep_latest_n(filenames, 7)
    assert len(kept) == 7
    assert evicted == ["jugantor-2026-08-01.epub"]
    assert "jugantor-2026-08-01.epub" not in kept


def test_keep_latest_n_ignores_unparseable_filenames():
    filenames = ["jugantor-2026-08-13.epub", "feed.xml"]
    kept, evicted = opds_catalog.keep_latest_n(filenames, 7)
    assert kept == ["jugantor-2026-08-13.epub"]
    assert evicted == []
