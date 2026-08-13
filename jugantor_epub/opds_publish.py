"""I/O wrapper around opds_catalog.py's pure functions - reads/writes the
gh-pages checkout. Mirrors email_sender.py's role as the thin I/O layer
next to a pure module. Not unit tested directly, same treatment as
send_to_kindle() and _get() elsewhere in this codebase.
"""

import importlib
import logging
import os
import shutil
from datetime import date

from . import config
from .opds_catalog import keep_latest_n, render_root_feed_xml, render_source_feed_xml

logger = logging.getLogger(__name__)


def publish_catalog(gh_pages_dir, output_dir, edition_date):
    """edition_date: ISO string ('2026-08-13'), matching main.py's existing
    convention. Writes catalog.xml plus one {slug}/feed.xml per configured
    source into gh_pages_dir, ready to be published as-is (e.g. via
    peaceiris/actions-gh-pages with keep_files: false).
    """
    today = date.fromisoformat(edition_date)
    sources = []

    for slug in config.SOURCES:
        source_module = importlib.import_module(f"jugantor_epub.sources.{slug}")
        source_name = source_module.SOURCE_NAME
        sources.append((slug, source_name))

        try:
            _publish_source(gh_pages_dir, output_dir, slug, source_name, edition_date, today)
        except Exception as exc:
            logger.warning("Skipping OPDS publish for %s: %s", slug, exc)

    root_xml = render_root_feed_xml(sources, today)
    with open(os.path.join(gh_pages_dir, "catalog.xml"), "w", encoding="utf-8") as fh:
        fh.write(root_xml)


def _publish_source(gh_pages_dir, output_dir, slug, source_name, edition_date, today):
    source_dir = os.path.join(gh_pages_dir, slug)
    os.makedirs(source_dir, exist_ok=True)

    existing = [name for name in os.listdir(source_dir) if name != "feed.xml"]

    todays_filename = f"{slug}-{edition_date}.epub"
    todays_output_path = os.path.join(output_dir, todays_filename)
    candidates = list(existing)
    if os.path.exists(todays_output_path) and todays_filename not in candidates:
        candidates.append(todays_filename)

    kept, evicted = keep_latest_n(candidates, config.OPDS_RETENTION_COUNT)

    for filename in evicted:
        evicted_path = os.path.join(source_dir, filename)
        if os.path.exists(evicted_path):
            os.remove(evicted_path)

    if todays_filename in kept:
        dest_path = os.path.join(source_dir, todays_filename)
        if not os.path.exists(dest_path):
            shutil.copyfile(todays_output_path, dest_path)

    feed_xml = render_source_feed_xml(slug, source_name, kept, today)
    with open(os.path.join(source_dir, "feed.xml"), "w", encoding="utf-8") as fh:
        fh.write(feed_xml)
