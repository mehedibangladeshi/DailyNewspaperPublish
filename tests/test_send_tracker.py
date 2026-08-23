import base64
import json
import os

import requests

from jugantor_epub import config, send_tracker


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


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _b64(obj):
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode("ascii")


def test_write_remote_noop_without_github_token_or_repository(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    def _unexpected_get(*a, **k):
        raise AssertionError("should not make a network call without env vars")

    monkeypatch.setattr(send_tracker._session, "get", _unexpected_get)

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")  # must not raise


def test_write_remote_creates_new_file_on_404(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someuser/somerepo")

    put_calls = []
    monkeypatch.setattr(send_tracker._session, "get", lambda *a, **k: _FakeResponse(404))
    monkeypatch.setattr(
        send_tracker._session,
        "put",
        lambda url, **k: put_calls.append((url, k)) or _FakeResponse(201),
    )

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")

    assert len(put_calls) == 1
    url, kwargs = put_calls[0]
    assert url == "https://api.github.com/repos/someuser/somerepo/contents/send-status/2026-08-23.json"
    payload = kwargs["json"]
    assert "sha" not in payload
    assert payload["branch"] == "gh-pages"
    assert json.loads(base64.b64decode(payload["content"])) == {"jugantor": True}


def test_write_remote_merges_with_existing_remote_content(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someuser/somerepo")

    put_calls = []
    monkeypatch.setattr(
        send_tracker._session,
        "get",
        lambda *a, **k: _FakeResponse(200, {"content": _b64({"prothomalo": True}), "sha": "abc123"}),
    )
    monkeypatch.setattr(
        send_tracker._session,
        "put",
        lambda url, **k: put_calls.append((url, k)) or _FakeResponse(200),
    )

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")

    payload = put_calls[0][1]["json"]
    assert payload["sha"] == "abc123"
    assert json.loads(base64.b64decode(payload["content"])) == {
        "prothomalo": True,
        "jugantor": True,
    }


def test_write_remote_swallows_get_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someuser/somerepo")

    def _raise(*a, **k):
        raise requests.RequestException("network down")

    monkeypatch.setattr(send_tracker._session, "get", _raise)

    def _unexpected_put(*a, **k):
        raise AssertionError("should not PUT after a failed GET")

    monkeypatch.setattr(send_tracker._session, "put", _unexpected_put)

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")  # must not raise


def test_missing_source_args_returns_all_sources_for_empty_mapping():
    result = send_tracker.missing_source_args({}, sources=["jugantor", "prothomalo"])
    assert result == "--source jugantor --source prothomalo"


def test_missing_source_args_returns_only_missing_sources():
    result = send_tracker.missing_source_args(
        {"jugantor": True}, sources=["jugantor", "prothomalo", "dhakatribune"]
    )
    assert result == "--source prothomalo --source dhakatribune"


def test_missing_source_args_returns_empty_string_when_all_sent():
    result = send_tracker.missing_source_args(
        {"jugantor": True, "prothomalo": True}, sources=["jugantor", "prothomalo"]
    )
    assert result == ""


def test_missing_source_args_defaults_to_config_sources(monkeypatch):
    monkeypatch.setattr(config, "SOURCES", ["jugantor", "prothomalo"])
    result = send_tracker.missing_source_args({"jugantor": True})
    assert result == "--source prothomalo"


def test_write_remote_swallows_put_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someuser/somerepo")

    monkeypatch.setattr(send_tracker._session, "get", lambda *a, **k: _FakeResponse(404))

    def _raise(*a, **k):
        raise requests.RequestException("network down")

    monkeypatch.setattr(send_tracker._session, "put", _raise)

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")  # must not raise
