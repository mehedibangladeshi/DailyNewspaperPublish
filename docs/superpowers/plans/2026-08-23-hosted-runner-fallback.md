# Hosted-Runner Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** If the self-hosted runner (`thespace`) doesn't produce a successful daily edition by 10:00 BD time, a new GitHub-hosted-runner workflow automatically rebuilds and sends only the sources that weren't already delivered that day.

**Architecture:** A new module (`jugantor_epub/send_tracker.py`) records each successful Kindle send to two places — a local file inside the already-mounted `gh-pages` checkout, and a live GitHub Contents API write — so the record survives even if the machine goes dark mid-run. A new workflow (`daily-kindle-fallback.yml`), scheduled 2 hours after the primary, checks via the GitHub Actions API whether today's primary run already succeeded; if not, it reads back the send-status file and rebuilds only the missing sources using `main.py`'s existing `--source` flag.

**Tech Stack:** Python 3.12, `requests` (already a dependency), GitHub Actions (`gh` CLI, GitHub REST Contents API and Actions API), pytest + `unittest.mock.monkeypatch`.

Full design rationale: `docs/superpowers/specs/2026-08-23-hosted-runner-fallback-design.md`.

## Global Constraints

- No new GitHub Actions permission scopes beyond the `permissions: contents: write` both workflows' jobs already declare (or, for the fallback, will declare identically).
- `send_tracker.py`'s writes must never raise — a tracking failure must never cause an otherwise-successful Kindle send to be reported as failed (same error-isolation principle as the rest of the codebase, per `CLAUDE.md`).
- Exactly one `send-status/*.json` file exists in the `gh-pages` checkout at a time — any file not for today's `edition_date` is deleted before writing today's.
- The fallback reuses `main.py`'s existing `--source` flag (added in `c6da154`) — no changes to `main.py`'s argument parsing.
- The fallback runs on `ubuntu-latest` using the same native `pip install` + `python main.py` approach as the pre-migration workflow (see `git show main:.github/workflows/daily-kindle.yml`), not Docker — the hosted runner doesn't need Docker for anything else, so there's no reason to add that overhead here.

---

### Task 1: `send_tracker.py` — local status-file write

**Files:**
- Create: `jugantor_epub/send_tracker.py`
- Test: `tests/test_send_tracker.py`

**Interfaces:**
- Produces: `send_tracker.mark_sent(gh_pages_dir: str, source_slug: str, edition_date: str) -> None` (this task implements only the local half of it; Task 2 adds the remote half inside the same function).
- Produces (internal, used by Task 2 too): `send_tracker.STATUS_DIR_NAME = "send-status"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_send_tracker.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_send_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jugantor_epub.send_tracker'`

- [ ] **Step 3: Write the implementation**

Create `jugantor_epub/send_tracker.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_send_tracker.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/send_tracker.py tests/test_send_tracker.py
git commit -m "feat: track sent sources locally in the gh-pages checkout"
```

---

### Task 2: `send_tracker.py` — remote GitHub Contents API write

**Files:**
- Modify: `jugantor_epub/send_tracker.py`
- Modify: `tests/test_send_tracker.py`

**Interfaces:**
- Consumes: `config.make_session()` (from `jugantor_epub/config.py`, already used by `images.py`/`opds_publish.py`'s siblings — returns a `requests.Session` with the project's `User-Agent` header set), `config.REQUEST_TIMEOUT`.
- Produces: `send_tracker._session` (module-level `requests.Session`, monkeypatched in tests the same way `images._session` is).
- `mark_sent()`'s public signature is unchanged from Task 1; this task adds the second write inside it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_send_tracker.py` (below the existing tests, same file):

```python
import base64

import requests

from jugantor_epub import config


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


def test_write_remote_swallows_put_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someuser/somerepo")

    monkeypatch.setattr(send_tracker._session, "get", lambda *a, **k: _FakeResponse(404))

    def _raise(*a, **k):
        raise requests.RequestException("network down")

    monkeypatch.setattr(send_tracker._session, "put", _raise)

    send_tracker.mark_sent(str(tmp_path), "jugantor", "2026-08-23")  # must not raise
```

Also add `import base64` and `import requests` and `from jugantor_epub import config` near the top of `tests/test_send_tracker.py` alongside the existing `import json`/`import os`/`from jugantor_epub import send_tracker`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_send_tracker.py -v`
Expected: the 5 new tests FAIL (`AttributeError: module 'jugantor_epub.send_tracker' has no attribute '_session'`); the 4 Task 1 tests still PASS.

- [ ] **Step 3: Write the implementation**

Replace the full contents of `jugantor_epub/send_tracker.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_send_tracker.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/send_tracker.py tests/test_send_tracker.py
git commit -m "feat: push send-status live to gh-pages via the Contents API"
```

---

### Task 3: Wire `mark_sent()` into `main.py`

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: `send_tracker.mark_sent(gh_pages_dir, source_slug, edition_date)` from Task 2, `config.GH_PAGES_DIR` (existing).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_main.py`, near the other two autouse fixtures (`_no_real_kindle_email`, `_no_real_opds_publish`):

```python
@pytest.fixture(autouse=True)
def _no_real_send_tracking(monkeypatch):
    """Same guard pattern as the other two autouse fixtures above - default
    to a no-op so tests that merely exercise sending don't need a real
    gh-pages checkout or network access."""
    monkeypatch.setattr(main.send_tracker, "mark_sent", lambda *a, **k: None)
```

Add near the other `test_main_*send*` tests (after `test_main_sends_one_email_per_built_source_as_soon_as_it_builds`):

```python
def test_main_marks_sent_after_each_successful_send(monkeypatch, tmp_path):
    marked = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok1", "ok2"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.config, "GH_PAGES_DIR", str(tmp_path))
    monkeypatch.setattr(
        main.importlib,
        "import_module",
        lambda name: {
            "jugantor_epub.sources.ok1": _FakeSourceOk,
            "jugantor_epub.sources.ok2": _FakeSourceOk2,
        }[name],
    )
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda source_name, *a, **k: f"/tmp/{source_name}.epub")
    monkeypatch.setattr(main.email_sender.KindleSender, "send", lambda self, *a, **k: True)
    monkeypatch.setattr(
        main.send_tracker,
        "mark_sent",
        lambda gh_pages_dir, source_slug, edition_date: marked.append(
            (gh_pages_dir, source_slug, edition_date)
        ),
    )

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 10, 12, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(main, "datetime", _FixedDatetime)

    exit_code = main.main()

    assert exit_code == 0
    assert marked == [
        (str(tmp_path), "ok1", "2026-08-10"),
        (str(tmp_path), "ok2", "2026-08-10"),
    ]


def test_main_does_not_mark_sent_for_a_size_skipped_send(monkeypatch, tmp_path):
    marked = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.config, "GH_PAGES_DIR", str(tmp_path))
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")
    monkeypatch.setattr(main.email_sender.KindleSender, "send", lambda self, *a, **k: False)
    monkeypatch.setattr(
        main.send_tracker,
        "mark_sent",
        lambda gh_pages_dir, source_slug, edition_date: marked.append(
            (gh_pages_dir, source_slug, edition_date)
        ),
    )

    exit_code = main.main()

    assert exit_code == 0
    assert marked == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_main.py -v -k "marks_sent or size_skipped_send"`
Expected: FAIL — `test_main_marks_sent_after_each_successful_send` fails with `marked == []` (nothing recorded, since `main.py` doesn't call `mark_sent` yet); `test_main_does_not_mark_sent_for_a_size_skipped_send` passes vacuously right now but will be a real assertion once Step 3 is done. Also expect an `AttributeError: module 'main' has no attribute 'send_tracker'` from the autouse fixture, since `main.py` doesn't import `send_tracker` yet — this is the actual failure signal to fix.

- [ ] **Step 3: Wire in the implementation**

In `main.py`, add `send_tracker` to the existing import line:

```python
from jugantor_epub import config, cover, email_sender, epub_builder, images, opds_publish, send_tracker
```

Then in `main()`, inside the `if sender is not None:` block, change:

```python
                if sent:
                    sent_count += 1
                else:
                    size_skipped_count += 1
```

to:

```python
                if sent:
                    sent_count += 1
                    send_tracker.mark_sent(config.GH_PAGES_DIR, source_slug, edition_date)
                else:
                    size_skipped_count += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: all tests in the file PASS (the full file, not just the `-k` filter, since the autouse fixture change affects every test in it).

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: record each successful Kindle send via send_tracker"
```

---

### Task 4: Forward `GITHUB_TOKEN`/`GITHUB_REPOSITORY` into the primary workflow's container

**Files:**
- Modify: `.github/workflows/daily-kindle.yml`
- Modify: `tests/test_workflow.py`

**Interfaces:** None (pure workflow YAML + env passthrough; no Python interfaces).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_workflow.py`:

```python
def test_workflow_forwards_github_token_and_repository_for_send_tracking():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert 'GITHUB_TOKEN="$GITHUB_TOKEN"' in content
    assert 'GITHUB_REPOSITORY="$GITHUB_REPOSITORY"' in content
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workflow.py::test_workflow_forwards_github_token_and_repository_for_send_tracking -v`
Expected: FAIL (none of the three strings are in the file yet)

- [ ] **Step 3: Edit the workflow**

In `.github/workflows/daily-kindle.yml`, change:

```yaml
          docker run --rm \
            -e SEND_TO_KINDLE=true \
            -e PUBLISH_OPDS=true \
            -e GH_PAGES_DIR="$GH_PAGES_DIR" \
            -e GMAIL_ADDRESS="$GMAIL_ADDRESS" \
            -e GMAIL_APP_PASSWORD="$GMAIL_APP_PASSWORD" \
            -e KINDLE_EMAIL="$KINDLE_EMAIL" \
            -v "$PWD/output:/app/output" \
            -v "$PWD/$GH_PAGES_DIR:/app/$GH_PAGES_DIR" \
            daily-newspaper
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}
```

to:

```yaml
          docker run --rm \
            -e SEND_TO_KINDLE=true \
            -e PUBLISH_OPDS=true \
            -e GH_PAGES_DIR="$GH_PAGES_DIR" \
            -e GMAIL_ADDRESS="$GMAIL_ADDRESS" \
            -e GMAIL_APP_PASSWORD="$GMAIL_APP_PASSWORD" \
            -e KINDLE_EMAIL="$KINDLE_EMAIL" \
            -e GITHUB_TOKEN="$GITHUB_TOKEN" \
            -e GITHUB_REPOSITORY="$GITHUB_REPOSITORY" \
            -v "$PWD/output:/app/output" \
            -v "$PWD/$GH_PAGES_DIR:/app/$GH_PAGES_DIR" \
            daily-newspaper
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

(`GITHUB_REPOSITORY` is one of Actions' automatically-provided environment variables in every job/step — it doesn't need a `secrets.*`/`env:` entry, only the `-e GITHUB_REPOSITORY="$GITHUB_REPOSITORY"` docker forward, which reads it from the runner's already-ambient shell environment.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`
Expected: all pass (the whole file, to confirm nothing else broke)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily-kindle.yml tests/test_workflow.py
git commit -m "feat: forward GITHUB_TOKEN/GITHUB_REPOSITORY into the daily-kindle container"
```

---

### Task 5: New `daily-kindle-fallback.yml` workflow

**Files:**
- Create: `.github/workflows/daily-kindle-fallback.yml`
- Create: `tests/test_workflow_fallback.py`

**Interfaces:**
- Consumes: `send_tracker.STATUS_DIR_NAME` naming convention (`send-status/{date}.json`, read via `gh api`), `config.SOURCES` (imported directly in an inline Python snippet), `main.py --source` (existing flag).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workflow_fallback.py`:

```python
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "daily-kindle-fallback.yml"


def test_fallback_workflow_file_exists():
    assert WORKFLOW_PATH.exists()


def test_fallback_workflow_runs_on_hosted_runner_with_buffer_schedule():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in content
    assert "cron: '0 4 * * *'" in content
    assert "workflow_dispatch:" in content


def test_fallback_workflow_shares_concurrency_group_with_primary():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "group: daily-kindle" in content


def test_fallback_workflow_guard_checks_todays_primary_run_success():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "gh run list" in content
    assert "--workflow daily-kindle.yml" in content
    # the jq filter is embedded inside a bash double-quoted string, so the
    # literal file content has escaped quotes around "success", not bare ones
    assert '.conclusion == \\"success\\"' in content
    assert "already_succeeded=true" in content
    assert "already_succeeded=false" in content


def test_fallback_workflow_dedups_via_send_status_and_source_flag():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "send-status/$TODAY.json?ref=gh-pages" in content
    assert "from jugantor_epub import config" in content
    assert "missing_sources" in content
    assert "python main.py ${{ steps.dedup.outputs.missing_sources }}" in content


def test_fallback_workflow_forwards_required_secrets_and_env():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}" in content
    assert "GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}" in content
    assert "KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}" in content
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in content
    assert "SEND_TO_KINDLE: 'true'" in content
    assert "PUBLISH_OPDS: 'true'" in content


def test_fallback_workflow_publishes_gh_pages_same_as_primary():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "uses: peaceiris/actions-gh-pages@" in content
    assert "keep_files: false" in content
    assert "force_orphan: true" in content


def test_fallback_workflow_gates_build_steps_on_the_guard():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert content.count("steps.guard.outputs.already_succeeded == 'false'") >= 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workflow_fallback.py -v`
Expected: `test_fallback_workflow_file_exists` FAILS (file doesn't exist); every other test in the file errors/fails the same way since they all read the same missing file.

- [ ] **Step 3: Create the workflow**

Create `.github/workflows/daily-kindle-fallback.yml`:

```yaml
name: Daily Kindle edition (hosted-runner fallback)
on:
  schedule:
    - cron: '0 4 * * *'   # 04:00 UTC = 10:00 BD time (UTC+6, no DST) - 2h after the primary self-hosted schedule
  workflow_dispatch:

concurrency:
  group: daily-kindle
  cancel-in-progress: false

jobs:
  fallback-build-and-send:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: write
    env:
      GH_PAGES_DIR: gh-pages-checkout
    steps:
      - id: guard
        run: |
          TODAY_UTC=$(date -u +%Y-%m-%dT00:00:00Z)
          COUNT=$(gh run list --repo "$REPO" --workflow daily-kindle.yml --json conclusion,createdAt --limit 20 \
            --jq "[.[] | select(.createdAt >= \"$TODAY_UTC\") | select(.conclusion == \"success\")] | length")
          if [ "$COUNT" -gt 0 ]; then
            echo "already_succeeded=true" >> "$GITHUB_OUTPUT"
          else
            echo "already_succeeded=false" >> "$GITHUB_OUTPUT"
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
      - uses: actions/checkout@v7
        if: steps.guard.outputs.already_succeeded == 'false'
      - id: gh_pages_exists
        if: steps.guard.outputs.already_succeeded == 'false'
        run: |
          set +e
          git ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1
          code=$?
          set -e
          if [ "$code" -eq 0 ]; then
            echo "exists=true" >> "$GITHUB_OUTPUT"
          elif [ "$code" -eq 2 ]; then
            echo "exists=false" >> "$GITHUB_OUTPUT"
          else
            echo "exists=unknown" >> "$GITHUB_OUTPUT"
          fi
      - id: gh_pages_checkout
        if: steps.guard.outputs.already_succeeded == 'false' && steps.gh_pages_exists.outputs.exists == 'true'
        continue-on-error: true
        uses: actions/checkout@v7
        with:
          ref: gh-pages
          path: ${{ env.GH_PAGES_DIR }}
      - uses: actions/setup-python@v7
        if: steps.guard.outputs.already_succeeded == 'false'
        with:
          python-version: '3.x'
      - if: steps.guard.outputs.already_succeeded == 'false'
        run: pip install -r requirements.txt
      - id: dedup
        if: steps.guard.outputs.already_succeeded == 'false'
        run: |
          TODAY=$(date -u +%Y-%m-%d)
          set +e
          RAW=$(gh api "repos/$REPO/contents/send-status/$TODAY.json?ref=gh-pages" --jq '.content' 2>/dev/null | tr -d '\n' | base64 -d 2>/dev/null)
          set -e
          if [ -z "$RAW" ]; then
            RAW='{}'
          fi
          echo "$RAW" > /tmp/send-status.json
          MISSING=$(python3 -c "
          import json
          from jugantor_epub import config
          with open('/tmp/send-status.json') as f:
              sent = json.load(f)
          missing = [s for s in config.SOURCES if not sent.get(s)]
          print(' '.join(f'--source {s}' for s in missing))
          ")
          echo "missing_sources=$MISSING" >> "$GITHUB_OUTPUT"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
      - if: steps.guard.outputs.already_succeeded == 'false' && steps.dedup.outputs.missing_sources != ''
        run: python main.py ${{ steps.dedup.outputs.missing_sources }}
        env:
          SEND_TO_KINDLE: 'true'
          PUBLISH_OPDS: 'true'
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/upload-artifact@v7
        if: always() && steps.guard.outputs.already_succeeded == 'false'
        with:
          name: jugantor-epub-fallback-${{ github.run_id }}
          path: output/*.epub
          retention-days: 7
          if-no-files-found: ignore
      - uses: peaceiris/actions-gh-pages@84c30a85c19949d7eee79c4ff27748b70285e453 # v4.1.0
        if: always() && steps.guard.outputs.already_succeeded == 'false' && (steps.gh_pages_exists.outputs.exists == 'false' || steps.gh_pages_checkout.outcome == 'success')
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ${{ env.GH_PAGES_DIR }}
          keep_files: false
          force_orphan: true
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workflow_fallback.py -v`
Expected: 8 passed

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests pass (confirms nothing in earlier tasks regressed)

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/daily-kindle-fallback.yml tests/test_workflow_fallback.py
git commit -m "feat: add hosted-runner fallback workflow for missed self-hosted runs"
```

---

### Task 6: Document the fallback in `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Add a new paragraph**

In `CLAUDE.md`, under the `## Daily automation & Kindle delivery` section, immediately after the existing paragraph that ends "...even though `config.SOURCES` includes a source (Dhaka Tribune) with a known, permanent, accepted build failure in CI (see `CONTEXT.md`)." (the paragraph right before the "**Per-source emails...**" bolded one), add:

```markdown
**Hosted-runner fallback for a missed self-hosted run (`daily-kindle-fallback.yml`, added 2026-08-23)** — the primary workflow above runs on a self-hosted runner (see `docs/superpowers/specs/2026-08-20-self-hosted-docker-runner-design.md`), whose uptime/network is otherwise a single point of failure for all five sources. `daily-kindle-fallback.yml` runs the same pipeline on GitHub's own `ubuntu-latest` runners, scheduled 2 hours after the primary (04:00 UTC / 10:00 BD). Its first step queries the GitHub Actions API for today's runs of the primary workflow; if none succeeded (covers a self-hosted job stuck queued forever with no runner online, one that hung mid-run, and one that genuinely failed), it fetches `send-status/{today}.json` from the `gh-pages` branch — a live per-source record `jugantor_epub/send_tracker.py` writes immediately after each successful send, specifically so it survives the self-hosted machine dying mid-run before the primary workflow's own end-of-job publish step ever runs — and rebuilds only the sources not already marked sent, via `main.py`'s existing `--source` flag. Full design: `docs/superpowers/specs/2026-08-23-hosted-runner-fallback-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document the hosted-runner fallback workflow"
```
