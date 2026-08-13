import xml.etree.ElementTree as ET
from datetime import date

from jugantor_epub import opds_catalog

ATOM_NS = "{http://www.w3.org/2005/Atom}"


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


def test_format_entry_title_two_digit_day():
    assert opds_catalog.format_entry_title(date(2026, 8, 13)) == "Thursday, 13 Aug, 2026"


def test_format_entry_title_single_digit_day_not_zero_padded():
    assert opds_catalog.format_entry_title(date(2026, 8, 3)) == "Monday, 3 Aug, 2026"


def test_format_entry_title_single_digit_day_one():
    assert opds_catalog.format_entry_title(date(2026, 8, 1)) == "Saturday, 1 Aug, 2026"


def test_render_source_feed_xml_is_well_formed_and_has_one_entry_per_kept_file():
    xml_text = opds_catalog.render_source_feed_xml(
        "jugantor",
        "যুগান্তর",
        ["jugantor-2026-08-13.epub", "jugantor-2026-08-12.epub"],
        date(2026, 8, 13),
    )
    root = ET.fromstring(xml_text)
    assert root.tag == f"{ATOM_NS}feed"
    entries = root.findall(f"{ATOM_NS}entry")
    assert len(entries) == 2
    titles = [entry.find(f"{ATOM_NS}title").text for entry in entries]
    assert titles == ["Thursday, 13 Aug, 2026", "Wednesday, 12 Aug, 2026"]
    acquisition_links = [entry.find(f"{ATOM_NS}link").get("href") for entry in entries]
    assert acquisition_links == ["jugantor-2026-08-13.epub", "jugantor-2026-08-12.epub"]


def test_render_source_feed_xml_empty_when_no_kept_files():
    xml_text = opds_catalog.render_source_feed_xml("jugantor", "যুগান্তর", [], date(2026, 8, 13))
    root = ET.fromstring(xml_text)
    assert root.findall(f"{ATOM_NS}entry") == []


def test_render_root_feed_xml_is_well_formed_and_lists_every_source():
    xml_text = opds_catalog.render_root_feed_xml(
        [("jugantor", "যুগান্তর"), ("prothomalo", "প্রথম আলো")],
        date(2026, 8, 13),
    )
    root = ET.fromstring(xml_text)
    assert root.tag == f"{ATOM_NS}feed"
    entries = root.findall(f"{ATOM_NS}entry")
    assert len(entries) == 2
    hrefs = [entry.find(f"{ATOM_NS}link").get("href") for entry in entries]
    assert hrefs == ["jugantor/feed.xml", "prothomalo/feed.xml"]
