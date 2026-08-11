# Daily Kindle Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically build the daily Jugantor epub on a schedule and email it to the user's Kindle, without changing local manual-run behavior.

**Architecture:** A new `jugantor_epub/email_sender.py` module (parse/fetch-split style, matching `sources/jugantor.py`) builds a MIME message with one epub attachment per successfully-built source and sends it via Gmail SMTP. `main.py` accumulates `(source_name, output_path)` across its existing per-source loop, calls the sender once after the loop when `config.SEND_TO_KINDLE` is true, and now returns a real exit code. A new GitHub Actions workflow runs `main.py` daily with `SEND_TO_KINDLE=true` and the Gmail/Kindle secrets set; local runs are untouched because the env var defaults off.

**Tech Stack:** Python 3, `smtplib`/`email.message.EmailMessage` (stdlib, no new dependency), `ebooklib` (existing), GitHub Actions.

## Global Constraints

- `SEND_TO_KINDLE` env var (via `config.py`) is the *only* switch between local and CI behavior; default `false`; local runs never attempt to send email.
- Cron schedule: `'0 2 * * *'` (02:00 UTC = 08:00 Bangladesh time, UTC+6, no DST).
- Exactly **one combined email per day** with every successfully-built source's `.epub` as a separate attachment — never one email per source.
- If zero sources build, no email is sent and the run exits non-zero. If the combined send itself fails, the run also exits non-zero. A run where some (not all) sources fail but the rest build (and any enabled send succeeds) still exits `0`.
- Required GitHub Actions secrets, exact names: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `KINDLE_EMAIL`.
- Built epub(s) are uploaded as a workflow artifact on every run (`if: always()`), 7-day retention, regardless of success/failure.
- New EPUB metadata fields are fixed personal-branding constants shared across every source, not derived from `source_name`: Publisher = `"MHB"`, Description = `"Mehedi's personal news digest"`. Title/Author/Language/Identifier stay unchanged.
- No MOBI conversion, no custom failure-alert email, no per-source-vs-combined toggle — explicitly out of scope (YAGNI); do not add them.

---

## File Structure

- `jugantor_epub/epub_builder.py` (modify) — add two `book.add_metadata('DC', ...)` calls.
- `jugantor_epub/config.py` (modify) — replace the `SEND_TO_KINDLE = False` placeholder with env-driven settings.
- `jugantor_epub/email_sender.py` (new) — `build_message()` pure function + `send_to_kindle()` I/O wrapper.
- `main.py` (modify) — accumulate built sources, call the sender once, real exit code.
- `.github/workflows/daily-kindle.yml` (new) — scheduled workflow.
- `README.md`, `CLAUDE.md` (modify) — replace deferred/not-implemented notes with what's actually built.
- Tests: `tests/test_epub_builder.py` (extend), `tests/test_config.py` (new), `tests/test_email_sender.py` (new), `tests/test_main.py` (extend), `tests/test_workflow.py` (new), `tests/test_docs.py` (new).

---

### Task 1: EPUB Publisher/Description metadata

**Files:**
- Modify: `jugantor_epub/epub_builder.py:67-71` (inside `build_epub`, right after `book.add_author(source_name)`)
- Test: `tests/test_epub_builder.py`

**Interfaces:**
- Produces: no new public function — `build_epub()`'s signature and return value are unchanged. Only the metadata written into the built epub changes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_epub_builder.py`:

```python
def test_build_epub_sets_publisher_and_description_metadata(tmp_path):
    output_path = tmp_path / "metadata.epub"

    epub_builder.build_epub(
        "টেস্ট পত্রিকা", "2026-08-10", _sample_sections(), output_path=str(output_path)
    )

    book = epub.read_epub(str(output_path))
    publisher = book.get_metadata("DC", "publisher")
    description = book.get_metadata("DC", "description")

    assert publisher == [("MHB", {})]
    assert description == [("Mehedi's personal news digest", {})]
```

Add `from ebooklib import epub` to the top of `tests/test_epub_builder.py` (it currently only imports `epub_builder`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_epub_builder.py::test_build_epub_sets_publisher_and_description_metadata -v`
Expected: FAIL — `publisher == []` (metadata not set yet).

- [ ] **Step 3: Write minimal implementation**

In `jugantor_epub/epub_builder.py`, right after the existing `book.add_author(source_name)` line:

```python
    book.add_author(source_name)
    book.add_metadata("DC", "publisher", "MHB")
    book.add_metadata("DC", "description", "Mehedi's personal news digest")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_epub_builder.py -v`
Expected: all tests in the file PASS (including the new one and the existing four).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/epub_builder.py tests/test_epub_builder.py
git commit -m "feat: add Publisher/Description metadata to built epubs"
```

---

### Task 2: Env-driven Kindle settings in config.py

**Files:**
- Modify: `jugantor_epub/config.py:27-28`
- Test: `tests/test_config.py` (new)

**Interfaces:**
- Produces: `config.SEND_TO_KINDLE` (bool), `config.KINDLE_EMAIL` (str or `None`), `config.GMAIL_ADDRESS` (str or `None`), `config.GMAIL_APP_PASSWORD` (str or `None`) — all read from the process environment at import time. Task 3 (`email_sender.py`) and Task 4 (`main.py`) read these directly off the `config` module.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import importlib

import pytest

from jugantor_epub import config


@pytest.fixture(autouse=True)
def _reload_config_after_test():
    yield
    importlib.reload(config)


def test_send_to_kindle_defaults_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("SEND_TO_KINDLE", raising=False)
    importlib.reload(config)
    assert config.SEND_TO_KINDLE is False


def test_send_to_kindle_true_when_env_set_true(monkeypatch):
    monkeypatch.setenv("SEND_TO_KINDLE", "true")
    importlib.reload(config)
    assert config.SEND_TO_KINDLE is True


def test_send_to_kindle_case_insensitive(monkeypatch):
    monkeypatch.setenv("SEND_TO_KINDLE", "TRUE")
    importlib.reload(config)
    assert config.SEND_TO_KINDLE is True


def test_kindle_credentials_read_from_env(monkeypatch):
    monkeypatch.setenv("KINDLE_EMAIL", "me@kindle.com")
    monkeypatch.setenv("GMAIL_ADDRESS", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    importlib.reload(config)
    assert config.KINDLE_EMAIL == "me@kindle.com"
    assert config.GMAIL_ADDRESS == "sender@gmail.com"
    assert config.GMAIL_APP_PASSWORD == "app-password"


def test_kindle_credentials_default_none_when_unset(monkeypatch):
    monkeypatch.delenv("KINDLE_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    importlib.reload(config)
    assert config.KINDLE_EMAIL is None
    assert config.GMAIL_ADDRESS is None
    assert config.GMAIL_APP_PASSWORD is None
```

The `autouse` fixture reloads `config` from the real (unpatched) environment after every test in this file, so no test in this module leaks a patched `SEND_TO_KINDLE`/credentials value into other test files that import `config` later in the same run (e.g. `tests/test_main.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `config.SEND_TO_KINDLE` is currently the hardcoded `False` placeholder (so the "defaults false" test passes by coincidence, but "true when env set" and the credential tests FAIL with `AttributeError: module 'jugantor_epub.config' has no attribute 'KINDLE_EMAIL'`).

- [ ] **Step 3: Write minimal implementation**

In `jugantor_epub/config.py`, replace:

```python
# Not implemented yet - see plan's "Deferred For Later" section.
SEND_TO_KINDLE = False
```

with:

```python
SEND_TO_KINDLE = os.environ.get("SEND_TO_KINDLE", "false").lower() == "true"
KINDLE_EMAIL = os.environ.get("KINDLE_EMAIL")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
```

`os` is already imported at the top of `config.py` — no new import needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: all 5 tests PASS.

Then run the full suite to confirm no leakage into other files:

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS (in particular `tests/test_main.py`'s existing tests, which assume `config.SEND_TO_KINDLE` is `False` by default).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/config.py tests/test_config.py
git commit -m "feat: read Kindle-delivery settings from environment variables"
```

---

### Task 3: `email_sender.py` — build and send the combined message

**Files:**
- Create: `jugantor_epub/email_sender.py`
- Test: `tests/test_email_sender.py` (new)

**Interfaces:**
- Consumes: `config.GMAIL_ADDRESS`, `config.GMAIL_APP_PASSWORD`, `config.KINDLE_EMAIL` (all from Task 2).
- Produces: `build_message(epub_entries, edition_date, from_addr, to_addr) -> EmailMessage`, where `epub_entries` is a list of `(source_name: str, epub_path: str)` tuples. `send_to_kindle(epub_entries, edition_date) -> None`, raises on SMTP failure. Task 4 (`main.py`) calls `email_sender.send_to_kindle(built, edition_date)` where `built` is exactly this `(source_name, output_path)` list shape.

- [ ] **Step 1: Write the failing test**

Create `tests/test_email_sender.py`:

```python
from jugantor_epub import email_sender


def test_build_message_single_entry_attachment(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-11.epub"
    epub_path.write_bytes(b"fake epub bytes")

    message = email_sender.build_message(
        [("যুগান্তর", str(epub_path))],
        "2026-08-11",
        "sender@gmail.com",
        "kindle@kindle.com",
    )

    assert message["From"] == "sender@gmail.com"
    assert message["To"] == "kindle@kindle.com"
    assert "2026-08-11" in message["Subject"]

    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/epub+zip"
    assert attachments[0].get_filename() == "jugantor-2026-08-11.epub"
    assert attachments[0].get_payload(decode=True) == b"fake epub bytes"


def test_build_message_multi_entry_attachments(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-11.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "other-2026-08-11.epub"
    epub_b.write_bytes(b"paper B bytes")

    message = email_sender.build_message(
        [("যুগান্তর", str(epub_a)), ("Other Paper", str(epub_b))],
        "2026-08-11",
        "sender@gmail.com",
        "kindle@kindle.com",
    )

    attachments = list(message.iter_attachments())
    assert len(attachments) == 2
    filenames = {a.get_filename() for a in attachments}
    assert filenames == {"jugantor-2026-08-11.epub", "other-2026-08-11.epub"}
    for attachment in attachments:
        assert attachment.get_content_type() == "application/epub+zip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_email_sender.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jugantor_epub.email_sender'`.

- [ ] **Step 3: Write minimal implementation**

Create `jugantor_epub/email_sender.py`:

```python
import os
import smtplib
from email.message import EmailMessage

from . import config


def build_message(epub_entries, edition_date, from_addr, to_addr):
    """Build a MIME message with one epub attachment per (source_name, epub_path) entry."""
    message = EmailMessage()
    message["Subject"] = f"Daily reading — {edition_date}"
    message["From"] = from_addr
    message["To"] = to_addr
    message.set_content(f"Attached: {len(epub_entries)} edition(s) for {edition_date}.")

    for _source_name, epub_path in epub_entries:
        with open(epub_path, "rb") as epub_file:
            data = epub_file.read()
        message.add_attachment(
            data,
            maintype="application",
            subtype="epub+zip",
            filename=os.path.basename(epub_path),
        )

    return message


def send_to_kindle(epub_entries, edition_date):
    """Send every built epub as one combined message to the configured Kindle address."""
    message = build_message(
        epub_entries, edition_date, config.GMAIL_ADDRESS, config.KINDLE_EMAIL
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        smtp.send_message(message)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_email_sender.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/email_sender.py tests/test_email_sender.py
git commit -m "feat: add email_sender module for combined Kindle delivery"
```

---

### Task 4: Wire sending + exit code into main.py

**Files:**
- Modify: `main.py` (whole file — imports, `main()`, `if __name__ == "__main__":` block; `build_source_edition()` is unchanged)
- Test: `tests/test_main.py` (extend)

**Interfaces:**
- Consumes: `email_sender.send_to_kindle(epub_entries, edition_date)` (Task 3), `config.SEND_TO_KINDLE` (Task 2). `build_source_edition(source_module, edition_date) -> output_path` is unchanged (existing function, unchanged signature/return).
- Produces: `main() -> int` (0 on success/degraded-success, 1 when nothing built or the combined send failed). This is a behavior change from today's `main() -> None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_main.py`, add a second fake source (distinct `SOURCE_NAME`, needed for the multi-source combined-email test) right after `_FakeSourceOk`:

```python
class _FakeSourceOk2:
    SOURCE_NAME = "Fake Paper 2"

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug):
        return [{"url": "https://x/2", "headline": "H2", "thumbnail": None}]

    @staticmethod
    def fetch_article(url):
        return {
            "headline": "H2 detail",
            "author": "B",
            "date_published": "2026-08-10",
            "image_url": None,
            "paragraphs": ["p2"],
        }
```

Then update the existing `test_main_continues_to_next_source_after_one_fails` to assert the new return value, and add three new tests, at the end of the file:

```python
def test_main_continues_to_next_source_after_one_fails(monkeypatch):
    built_for = []

    monkeypatch.setattr(main.config, "SOURCES", ["broken", "ok"])
    monkeypatch.setattr(
        main.importlib,
        "import_module",
        lambda name: {
            "jugantor_epub.sources.broken": _FakeSourceAllFail,
            "jugantor_epub.sources.ok": _FakeSourceOk,
        }[name],
    )
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(
        epub_builder, "build_epub", lambda *a, **k: built_for.append(a[0]) or "/tmp/x.epub"
    )

    exit_code = main.main()

    assert built_for == ["Fake Paper"]
    assert exit_code == 0


def test_main_returns_nonzero_when_all_sources_fail(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["broken"])
    monkeypatch.setattr(
        main.importlib, "import_module", lambda name: _FakeSourceAllFail
    )

    exit_code = main.main()

    assert exit_code == 1


def test_main_does_not_send_when_send_to_kindle_disabled(monkeypatch):
    sent = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", False)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")
    monkeypatch.setattr(
        main.email_sender, "send_to_kindle", lambda *a, **k: sent.append(a)
    )

    exit_code = main.main()

    assert sent == []
    assert exit_code == 0


def test_main_sends_combined_email_with_every_built_source(monkeypatch):
    sent = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok1", "ok2"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(
        main.importlib,
        "import_module",
        lambda name: {
            "jugantor_epub.sources.ok1": _FakeSourceOk,
            "jugantor_epub.sources.ok2": _FakeSourceOk2,
        }[name],
    )
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(
        epub_builder,
        "build_epub",
        lambda source_name, *a, **k: f"/tmp/{source_name}.epub",
    )
    monkeypatch.setattr(
        main.email_sender, "send_to_kindle", lambda *a, **k: sent.append(a)
    )

    exit_code = main.main()

    assert exit_code == 0
    assert len(sent) == 1
    epub_entries, edition_date = sent[0]
    assert epub_entries == [
        ("Fake Paper", "/tmp/Fake Paper.epub"),
        ("Fake Paper 2", "/tmp/Fake Paper 2.epub"),
    ]
    assert edition_date == "2026-08-10"


def test_main_returns_nonzero_when_send_to_kindle_fails(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(*a, **k):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.email_sender, "send_to_kindle", _boom)

    exit_code = main.main()

    assert exit_code == 1
```

Note: `main.main()` currently derives `edition_date` from `date.today()`, not a fixed string — the assertion `edition_date == "2026-08-10"` above requires patching `date` too. Add this to `test_main_sends_combined_email_with_every_built_source` right before calling `main.main()`:

```python
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 10)

    monkeypatch.setattr(main, "date", _FixedDate)
```

And add `from datetime import date` to the top of `tests/test_main.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'email_sender'` (and the return-value assertions fail since `main()` currently returns `None`).

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `main.py` from the `main()` function to the end with:

```python
import importlib
import logging
import sys
from datetime import date

from jugantor_epub import config, email_sender, epub_builder, images

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def build_source_edition(source_module, edition_date):
    sections_with_articles = []
    total_articles = 0
    skipped = 0
    image_cache = {}

    def cached_download_image(image_url):
        if image_url not in image_cache:
            image_cache[image_url] = images.download_image(image_url)
        return image_cache[image_url]

    for slug, section_name in source_module.discover_sections():
        try:
            listing = source_module.list_articles(slug)
        except Exception as exc:
            logger.warning("Skipping section %s (%s): %s", slug, section_name, exc)
            continue

        articles = []
        for item in listing:
            try:
                detail = source_module.fetch_article(item["url"])
            except Exception as exc:
                logger.warning("Skipping article %s: %s", item.get("url"), exc)
                skipped += 1
                continue

            image_url = detail.get("image_url") or item.get("thumbnail")
            image_result = cached_download_image(image_url) if image_url else None

            articles.append(
                {
                    "section_slug": slug,
                    "headline": detail.get("headline") or item.get("headline", ""),
                    "author": detail.get("author", ""),
                    "display_time": item.get("listing_time") or detail.get("date_published", ""),
                    "paragraphs": detail.get("paragraphs") or [],
                    "summary": item.get("summary", ""),
                    "image_filename": image_result[0] if image_result else None,
                    "image_bytes": image_result[1] if image_result else None,
                }
            )

        if articles:
            sections_with_articles.append((section_name, articles))
            total_articles += len(articles)
        logger.info("Section %s: %d article(s)", section_name, len(articles))

    if total_articles == 0:
        raise RuntimeError(f"No articles were scraped for source {source_module.SOURCE_NAME!r}")

    output_path = epub_builder.build_epub(
        source_module.SOURCE_NAME, edition_date, sections_with_articles
    )

    logger.info(
        "Built %s: %d section(s), %d article(s), %d skipped -> %s",
        source_module.SOURCE_NAME,
        len(sections_with_articles),
        total_articles,
        skipped,
        output_path,
    )
    return output_path


def main():
    edition_date = date.today().isoformat()
    built = []
    for source_name in config.SOURCES:
        source_module = importlib.import_module(f"jugantor_epub.sources.{source_name}")
        try:
            output_path = build_source_edition(source_module, edition_date)
        except Exception as exc:
            logger.error("Skipping source %s: %s", source_name, exc)
            continue
        built.append((source_module.SOURCE_NAME, output_path))

    if not built:
        logger.error("No source produced an edition; nothing to send.")
        return 1

    if config.SEND_TO_KINDLE:
        try:
            email_sender.send_to_kindle(built, edition_date)
        except Exception as exc:
            logger.error("Failed to send combined edition to Kindle: %s", exc)
            return 1
        logger.info("Sent %d edition(s) to Kindle.", len(built))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

(Only the `import` block, `main()`, and the `__main__` guard changed; `build_source_edition` is reproduced above unchanged so the file stays internally consistent — do not re-derive it from memory, copy it as shown.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: all tests PASS (6 existing/updated + new ones).

Then run the full suite:

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: send combined Kindle email from main.py and exit non-zero on failure"
```

---

### Task 5: GitHub Actions scheduled workflow

**Files:**
- Create: `.github/workflows/daily-kindle.yml`
- Test: `tests/test_workflow.py` (new)

**Interfaces:**
- Consumes: `main.py` as the entrypoint (Task 4), `SEND_TO_KINDLE`/`GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`/`KINDLE_EMAIL` env var names (Task 2) — must match exactly, since GitHub Actions secrets are wired to these names.
- Produces: nothing consumed by later Python tasks — this is the last task with a functional dependency; Task 6 (docs) refers to this file's schedule/secrets textually.

- [ ] **Step 1: Write the failing test**

Create `tests/test_workflow.py`:

```python
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "daily-kindle.yml"


def test_workflow_file_exists():
    assert WORKFLOW_PATH.exists()


def test_workflow_has_daily_schedule_and_manual_dispatch():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "cron: '0 2 * * *'" in content
    assert "workflow_dispatch:" in content


def test_workflow_runs_main_with_send_to_kindle_and_required_secrets():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "run: python main.py" in content
    assert "SEND_TO_KINDLE: 'true'" in content
    assert "GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}" in content
    assert "GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}" in content
    assert "KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}" in content


def test_workflow_uploads_epub_artifact_always():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "if: always()" in content
    assert "path: output/*.epub" in content
    assert "retention-days: 7" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`
Expected: FAIL — `test_workflow_file_exists` fails (file doesn't exist yet), rest error/fail on missing file too.

- [ ] **Step 3: Write minimal implementation**

Create `.github/workflows/daily-kindle.yml`:

```yaml
name: Daily Kindle edition
on:
  schedule:
    - cron: '0 2 * * *'   # 02:00 UTC = 08:00 BD time (UTC+6, no DST)
  workflow_dispatch:

jobs:
  build-and-send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          SEND_TO_KINDLE: 'true'
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: jugantor-epub-${{ github.run_id }}
          path: output/*.epub
          retention-days: 7
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily-kindle.yml tests/test_workflow.py
git commit -m "feat: add GitHub Actions scheduled workflow for daily Kindle delivery"
```

**Manual step (not part of this commit, cannot be automated):** after this is merged and secrets are added in Settings → Secrets and variables → Actions, the user must add `GMAIL_ADDRESS`'s value to Amazon's Approved Personal Document E-mail List (Manage Your Content and Devices → Preferences → Personal Document Settings), or Amazon silently drops the email.

---

### Task 6: Update README.md and CLAUDE.md

**Files:**
- Modify: `README.md:46-50` (the "Not implemented yet (deferred)" section)
- Modify: `CLAUDE.md:46-48` (the "Deferred (not implemented)" section)
- Test: `tests/test_docs.py` (new)

**Interfaces:**
- Consumes: nothing (documentation only, no code dependency).
- Produces: nothing consumed by other tasks — this is the final task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs.py`:

```python
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_readme_documents_kindle_delivery_not_deferred():
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Daily Kindle delivery" in content
    assert "Not implemented yet" not in content


def test_claude_md_deferred_section_reflects_implemented_automation():
    content = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "daily-kindle.yml" in content
    assert "email_sender.py" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_docs.py -v`
Expected: FAIL — `README.md` still contains `"Not implemented yet"` and doesn't mention `"Daily Kindle delivery"`; `CLAUDE.md` doesn't mention `daily-kindle.yml` or `email_sender.py`.

- [ ] **Step 3: Write minimal implementation**

In `README.md`, replace the final section (from `## Not implemented yet (deferred)` to the end of the file) with:

```markdown
## Daily Kindle delivery (GitHub Actions)

A scheduled GitHub Actions workflow (`.github/workflows/daily-kindle.yml`) runs
`main.py` every day at 08:00 Bangladesh time (`cron: '0 2 * * *'` UTC), builds
the day's edition(s), and emails every built `.epub` as an attachment to your
Kindle in one combined message. Local runs (`.venv/bin/python main.py`) are
unaffected — they only build the epub into `output/`, no email is attempted.

Required repo secrets (Settings → Secrets and variables → Actions):
- `GMAIL_ADDRESS` — sender Gmail account.
- `GMAIL_APP_PASSWORD` — a Google App Password (requires 2FA on that account).
- `KINDLE_EMAIL` — your `@kindle.com` Send-to-Kindle address (Amazon → Manage
  Your Content and Devices → Preferences → Personal Document Settings).

One manual one-time step on Amazon's side (can't be automated): add
`GMAIL_ADDRESS` to Amazon's Approved Personal Document E-mail List, or Amazon
silently drops the email.

GitHub auto-disables a scheduled workflow after 60 days with zero commits to
the repo — re-enable it from the Actions tab if that ever happens.
```

In `CLAUDE.md`, replace the `## Deferred (not implemented)` section with:

```markdown
## Daily automation & Kindle delivery

Implemented via a GitHub Actions scheduled workflow (`.github/workflows/daily-kindle.yml`, `cron: '0 2 * * *'` = 08:00 BD time) plus `jugantor_epub/email_sender.py`. `main.py` accumulates `(source_name, output_path)` for every source that builds successfully; when `config.SEND_TO_KINDLE` is true (set by the workflow, unset for local runs) it sends one combined email with every built epub attached via `email_sender.send_to_kindle()`. `main()` now exits non-zero when no source produced an edition or the combined send failed, since failure detection relies on GitHub's built-in failed-workflow notification. See `docs/superpowers/specs/2026-08-11-daily-kindle-automation-design.md` for the full design rationale.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_docs.py -v`
Expected: both tests PASS.

Then run the entire suite one final time:

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS, including `tests/test_build_epub_passes_epubcheck` if Java is on PATH (it self-skips otherwise).

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md tests/test_docs.py
git commit -m "docs: replace deferred Kindle-automation notes with what's implemented"
```

---

## Post-plan manual steps (cannot be done by an agent)

1. Add the three secrets (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `KINDLE_EMAIL`) in the GitHub repo's Settings → Secrets and variables → Actions.
2. Generate a Google App Password for the sending Gmail account (requires 2FA enabled on that account first).
3. Add the sending Gmail address to Amazon's Approved Personal Document E-mail List.
4. Optionally trigger the workflow once manually via `workflow_dispatch` (Actions tab → "Daily Kindle edition" → "Run workflow") to confirm end-to-end delivery before relying on the schedule.
