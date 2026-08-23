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

import base64
import json
import logging
import os

from . import config

logger = logging.getLogger(__name__)

STATUS_DIR_NAME = "send-status"
GITHUB_API_BASE = "https://api.github.com"

_session = config.make_session()


def _status_filename(edition_date):
    return f"{edition_date}.json"


def mark_sent(gh_pages_dir, source_slug, edition_date):
    _write_local(gh_pages_dir, source_slug, edition_date)
    _write_remote(source_slug, edition_date)


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


def _write_remote(source_slug, edition_date):
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repository = os.environ.get("GITHUB_REPOSITORY")
    if not github_token or not github_repository:
        return

    api_url = f"{GITHUB_API_BASE}/repos/{github_repository}/contents/{STATUS_DIR_NAME}/{_status_filename(edition_date)}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        existing = {}
        sha = None
        get_resp = _session.get(
            api_url, headers=headers, params={"ref": "gh-pages"}, timeout=config.REQUEST_TIMEOUT
        )
        if get_resp.status_code == 200:
            body = get_resp.json()
            existing = json.loads(base64.b64decode(body["content"]))
            sha = body["sha"]
        elif get_resp.status_code != 404:
            get_resp.raise_for_status()

        existing[source_slug] = True
        payload = {
            "message": f"mark {source_slug} sent for {edition_date}",
            "content": base64.b64encode(json.dumps(existing, sort_keys=True).encode("utf-8")).decode(
                "ascii"
            ),
            "branch": "gh-pages",
        }
        if sha:
            payload["sha"] = sha

        put_resp = _session.put(api_url, headers=headers, json=payload, timeout=config.REQUEST_TIMEOUT)
        put_resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to record remote send-status for %s: %s", source_slug, exc)
