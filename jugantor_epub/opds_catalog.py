"""Pure functions for building the OPDS catalog served from the gh-pages
branch. No I/O here - jugantor_epub/opds_publish.py handles reading and
writing files; this module only transforms filenames and builds XML
strings from data it's handed.
"""

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
