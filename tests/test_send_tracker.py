import json
import os

from jugantor_epub import send_tracker


def _read_status(gh_pages_dir, edition_date):
    path = os.path.join(gh_pages_dir, send_tracker.STATUS_DIR_NAME, f"{edition_date}.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_mark_sent_creates_local_status_file_with_source_marked_true(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")

    assert _read_status(tmp_path, "2026-08-23") == {"jugantor": True}


def test_mark_sent_merges_with_existing_local_status_same_day(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")
    send_tracker.mark_sent(str(tmp_path), "prothomalo", "2026-08-23")

    assert _read_status(tmp_path, "2026-08-23") == {"jugantor": True, "prothomalo": True}


def test_mark_sent_deletes_non_today_local_status_files(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    status_dir = tmp_path / send_tracker.STATUS_DIR_NAME
    status_dir.mkdir()
    (status_dir / "2026-08-22.json").write_text('{"jugantor": true}', encoding="utf-8")

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")

    assert sorted(os.listdir(status_dir)) == ["2026-08-23.json"]


def test_mark_sent_local_write_failure_is_logged_not_raised(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    # Point at a path that can't be a directory (a file already sits there),
    # so os.makedirs raises inside _write_local.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")

    send_tracker.mark_sent(str(blocked), "jugantor", "2026-08-23")  # must not raise
