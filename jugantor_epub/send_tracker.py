"""Tracks which sources' Kindle emails have already gone out today, so the
hosted-runner fallback workflow (daily-kindle-fallback.yml) can skip
sources the self-hosted runner already delivered before going dark.

mark_sent() writes to two places, both needed: a local file inside the
already-mounted gh-pages checkout (survives into the primary workflow's own
end-of-job publish step), and a live GitHub Contents API write (survives the
machine dying before that publish step ever runs). See
docs/superpowers/specs/2026-08-23-hosted-runner-fallback-design.md for why
neither one alone is sufficient.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

STATUS_DIR_NAME = "send-status"


def _status_filename(edition_date):
    return f"{edition_date}.json"


def mark_sent(gh_pages_dir, source_slug, edition_date):
    _write_local(gh_pages_dir, source_slug, edition_date)


def _write_local(gh_pages_dir, source_slug, edition_date):
    try:
        status_dir = os.path.join(gh_pages_dir, STATUS_DIR_NAME)
        os.makedirs(status_dir, exist_ok=True)

        today_filename = _status_filename(edition_date)
        for name in os.listdir(status_dir):
            if name != today_filename:
                os.remove(os.path.join(status_dir, name))

        today_path = os.path.join(status_dir, today_filename)
        existing = {}
        if os.path.exists(today_path):
            with open(today_path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        existing[source_slug] = True
        with open(today_path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, sort_keys=True)
    except Exception as exc:
        logger.warning("Failed to record local send-status for %s: %s", source_slug, exc)
