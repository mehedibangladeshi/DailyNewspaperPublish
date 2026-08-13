"""Pure functions for building the OPDS catalog served from the gh-pages
branch. No I/O here - jugantor_epub/opds_publish.py handles reading and
writing files; this module only transforms filenames and builds XML
strings from data it's handed.
"""

import xml.etree.ElementTree as ET
from datetime import date

_DATE_LEN = len("YYYY-MM-DD")


def parse_edition_filename(filename):
    """Parse '{slug}-{date}.epub' -> (slug, date) or None if it doesn't match.

    Splits from the right rather than using a slug-matching regex so that
    a slug containing its own hyphens (e.g. "prothom-alo") still parses
    correctly.
    """
    if not filename.endswith(".epub"):
        return None
    stem = filename[: -len(".epub")]
    if len(stem) < _DATE_LEN + 1 or stem[-_DATE_LEN - 1] != "-":
        return None
    slug, date_str = stem[: -_DATE_LEN - 1], stem[-_DATE_LEN:]
    if not slug:
        return None
    try:
        parsed_date = date.fromisoformat(date_str)
    except ValueError:
        return None
    return slug, parsed_date


def keep_latest_n(filenames, n):
    """Split filenames into (kept, evicted) by embedded date, newest first.

    Retention is count-based: always keep the n most recent successfully-
    built editions, however many calendar days they span. Filenames that
    don't match the '{slug}-{date}.epub' shape (e.g. "feed.xml") are
    ignored entirely - neither kept nor evicted.
    """
    dated = []
    for name in filenames:
        parsed = parse_edition_filename(name)
        if parsed is not None:
            dated.append((parsed[1], name))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    kept = [name for _, name in dated[:n]]
    evicted = [name for _, name in dated[n:]]
    return kept, evicted


def format_entry_title(edition_date):
    """'Thursday, 3 Aug, 2026' - day is never zero-padded (the user's
    explicit choice over "Thursday, 03 Aug, 2026").
    """
    weekday = edition_date.strftime("%A")
    month = edition_date.strftime("%b")
    return f"{weekday}, {edition_date.day} {month}, {edition_date.year}"


ATOM_NS = "http://www.w3.org/2005/Atom"


def _atom_tag(tag):
    return f"{{{ATOM_NS}}}{tag}"


def _add_child(parent, tag, text=None, **attrib):
    child = ET.SubElement(parent, _atom_tag(tag), attrib)
    if text is not None:
        child.text = text
    return child


def render_source_feed_xml(slug, source_name, kept_filenames, updated_date):
    """kept_filenames: '{slug}-{date}.epub' names, already in display order
    (newest first - the order keep_latest_n() returns them in).
    """
    ET.register_namespace("", ATOM_NS)
    feed = ET.Element(_atom_tag("feed"))
    _add_child(feed, "id", text=f"urn:daily-newspaper-opds:source:{slug}")
    _add_child(feed, "title", text=source_name)
    _add_child(feed, "updated", text=f"{updated_date.isoformat()}T00:00:00Z")
    _add_child(
        feed, "link", rel="self", href="feed.xml",
        type="application/atom+xml;profile=opds-catalog;kind=acquisition",
    )
    _add_child(
        feed, "link", rel="up", href="../catalog.xml",
        type="application/atom+xml;profile=opds-catalog;kind=navigation",
    )

    for filename in kept_filenames:
        parsed = parse_edition_filename(filename)
        if parsed is None:
            continue
        _, edition_date = parsed
        entry = _add_child(feed, "entry")
        _add_child(entry, "title", text=format_entry_title(edition_date))
        _add_child(entry, "id", text=f"urn:daily-newspaper-opds:{slug}:{edition_date.isoformat()}")
        _add_child(entry, "updated", text=f"{edition_date.isoformat()}T00:00:00Z")
        _add_child(
            entry, "link", rel="http://opds-spec.org/acquisition", href=filename,
            type="application/epub+zip",
        )

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(feed, encoding="unicode")


def render_root_feed_xml(sources, updated_date):
    """sources: list of (slug, source_name), one per config.SOURCES entry -
    every configured newspaper gets a nav entry regardless of whether it
    currently has any active editions.
    """
    ET.register_namespace("", ATOM_NS)
    feed = ET.Element(_atom_tag("feed"))
    _add_child(feed, "id", text="urn:daily-newspaper-opds:catalog")
    _add_child(feed, "title", text="Daily Newspaper — Catalog")
    _add_child(feed, "updated", text=f"{updated_date.isoformat()}T00:00:00Z")
    _add_child(
        feed, "link", rel="self", href="catalog.xml",
        type="application/atom+xml;profile=opds-catalog;kind=navigation",
    )

    for slug, source_name in sources:
        entry = _add_child(feed, "entry")
        _add_child(entry, "title", text=source_name)
        _add_child(entry, "id", text=f"urn:daily-newspaper-opds:source:{slug}")
        _add_child(entry, "updated", text=f"{updated_date.isoformat()}T00:00:00Z")
        _add_child(
            entry, "link", rel="subsection", href=f"{slug}/feed.xml",
            type="application/atom+xml;profile=opds-catalog;kind=acquisition",
        )

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(feed, encoding="unicode")
