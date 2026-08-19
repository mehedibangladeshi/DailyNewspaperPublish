# Per-Source Interleaved Kindle Send Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send each source's Kindle email as soon as that source's epub is built, instead of building every source first and sending all emails at the end.

**Architecture:** `main.py`'s per-source loop currently does `build → (continue loop) → ... → send-all-at-once`. It changes to `build → send → (continue loop)`. A new `email_sender.KindleSender` context manager (lazy-connecting, reused across sources, self-healing via `smtp.noop()`) replaces the direct call to the existing batch `send_to_kindle()` for the live path. OPDS publishing stays a single batch step after the loop. The existing batch `send_to_kindle()` / `NoEditionsSentError` / `build_message()` in `email_sender.py` are untouched — `build_message()` is reused internally by `KindleSender.send()`, the rest is kept as unused code (deliberately, per user decision) and its tests are left alone.

**Tech Stack:** Python 3, `smtplib`, `pytest`, `unittest.mock`.

## Global Constraints

- Non-zero exit code from `main()` if ANY source's build fails or ANY source's send fails (real SMTP error) — but the loop must always continue to the next source regardless of what failed.
- An oversized epub (over `GMAIL_MAX_ATTACHMENT_BYTES`) is a **non-fatal** skip — logged as a warning, does not flip the run's exit code, does not count as a "failure" in the summary.
- OPDS catalog publishing (`opds_publish.publish_catalog`) stays exactly as it is today: one call after the whole per-source loop finishes, unaffected by this change.
- `KindleSender` connects lazily (nothing happens in `__enter__`); the first call to `.send()` triggers `smtplib.SMTP_SSL` connect + login. Subsequent calls check liveness via `smtp.noop()` and reconnect if stale.
- `config.SEND_TO_KINDLE` continues to gate whether any sending is attempted at all — when `False`, `main()` must not construct a `KindleSender` or touch SMTP in any way.
- Do not modify `email_sender.build_message()`, `email_sender.send_to_kindle()`, or `email_sender.NoEditionsSentError` — they stay as-is, and their existing tests in `tests/test_email_sender.py` stay as-is, untouched and still passing.

---

## File Structure

- **Modify:** `jugantor_epub/email_sender.py` — add `KindleSender` class (new code, appended after the existing `send_to_kindle` function). Reuses the existing `build_message()` helper and `GMAIL_MAX_ATTACHMENT_BYTES` constant.
- **Modify:** `main.py` — restructure `main()`'s per-source loop to build then immediately send (via a `KindleSender` instance shared across the loop), track aggregate counters, and log one summary line at the end. `build_source_edition()` is unchanged.
- **Modify:** `tests/test_email_sender.py` — append new tests for `KindleSender` (do not touch the existing tests).
- **Modify:** `tests/test_main.py` — update the `_no_real_kindle_email` autouse fixture and the send-related tests to reflect the new `KindleSender`-based flow.

---

## Task 1: `KindleSender` class in `email_sender.py`

**Files:**
- Modify: `jugantor_epub/email_sender.py` (append after `send_to_kindle`, ~line 83)
- Test: `tests/test_email_sender.py` (append new tests)

**Interfaces:**
- Consumes: `email_sender.build_message(epub_entries, edition_date, from_addr, to_addr)` (existing, unchanged), `email_sender.GMAIL_MAX_ATTACHMENT_BYTES` (existing, unchanged), `config.GMAIL_ADDRESS`, `config.GMAIL_APP_PASSWORD`, `config.KINDLE_EMAIL` (existing config values).
- Produces: `email_sender.KindleSender` — a context manager class.
  - `KindleSender()` — constructor, takes no args.
  - `__enter__(self) -> KindleSender` — does nothing but return `self` (lazy connect).
  - `__exit__(self, exc_type, exc, tb)` — closes the SMTP connection if one was opened; never raises.
  - `send(self, source_name: str, epub_path: str, edition_date: str) -> bool` — returns `True` if the email was sent, `False` if skipped for being oversized. Raises on a real SMTP send failure (does not swallow it — `main.py` catches it).

- [ ] **Step 1: Write the failing tests for `KindleSender`**

Append to `tests/test_email_sender.py`:

```python
import smtplib as _smtplib


def test_kindle_sender_does_not_connect_until_first_send(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL") as smtp_ssl_cls:
        with email_sender.KindleSender():
            pass  # never called .send()

    smtp_ssl_cls.assert_not_called()


def test_kindle_sender_connects_and_sends_on_first_send(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    smtp_instance = MagicMock()
    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sent = sender.send("যুগান্তর", str(epub_path), "2026-08-19")

    assert sent is True
    smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465)
    smtp_instance.login.assert_called_once()
    assert smtp_instance.send_message.call_count == 1
    message = smtp_instance.send_message.call_args.args[0]
    attachments = list(message.iter_attachments())
    assert attachments[0].get_filename() == "jugantor-2026-08-19.epub"


def test_kindle_sender_reuses_connection_across_multiple_sends(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-19.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-19.epub"
    epub_b.write_bytes(b"paper B bytes")

    smtp_instance = MagicMock()
    smtp_instance.noop.return_value = (250, b"OK")
    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sender.send("যুগান্তর", str(epub_a), "2026-08-19")
            sender.send("প্রথম আলো", str(epub_b), "2026-08-19")

    smtp_ssl_cls.assert_called_once()
    assert smtp_instance.login.call_count == 1
    assert smtp_instance.send_message.call_count == 2


def test_kindle_sender_reconnects_when_noop_fails(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-19.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-19.epub"
    epub_b.write_bytes(b"paper B bytes")

    first_conn = MagicMock()
    first_conn.noop.side_effect = _smtplib.SMTPServerDisconnected("gone")
    second_conn = MagicMock()
    second_conn.noop.return_value = (250, b"OK")

    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL",
        side_effect=[first_conn, second_conn],
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sender.send("যুগান্তর", str(epub_a), "2026-08-19")
            sender.send("প্রথম আলো", str(epub_b), "2026-08-19")

    assert smtp_ssl_cls.call_count == 2
    assert first_conn.send_message.call_count == 1
    assert second_conn.send_message.call_count == 1


def test_kindle_sender_skips_oversized_epub_without_connecting_or_raising(tmp_path):
    huge_epub = tmp_path / "prothomalo-2026-08-19.epub"
    huge_epub.write_bytes(b"x" * (26 * 1024 * 1024))

    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL") as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sent = sender.send("প্রথম আলো", str(huge_epub), "2026-08-19")

    assert sent is False
    smtp_ssl_cls.assert_not_called()


def test_kindle_sender_raises_on_send_failure(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    smtp_instance = MagicMock()
    smtp_instance.send_message.side_effect = _smtplib.SMTPException("boom")
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        with email_sender.KindleSender() as sender:
            try:
                sender.send("যুগান্তর", str(epub_path), "2026-08-19")
            except _smtplib.SMTPException:
                pass
            else:
                raise AssertionError("expected SMTPException")


def test_kindle_sender_closes_connection_on_exit(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    smtp_instance = MagicMock()
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        with email_sender.KindleSender() as sender:
            sender.send("যুগান্তর", str(epub_path), "2026-08-19")

    smtp_instance.quit.assert_called_once()


def test_kindle_sender_exit_does_not_raise_if_never_connected():
    with email_sender.KindleSender():
        pass  # no assertion needed - just must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_email_sender.py -v -k KindleSender or kindle_sender`

Expected: FAIL with `AttributeError: module 'jugantor_epub.email_sender' has no attribute 'KindleSender'`

- [ ] **Step 3: Implement `KindleSender`**

Append to `jugantor_epub/email_sender.py` (after the existing `send_to_kindle` function, keeping everything above it untouched):

```python
class KindleSender:
    """Sends one Kindle email per source, reusing a single SMTP connection
    across the whole run instead of reconnecting per source.

    Connects lazily: no SMTP traffic happens until the first .send() call.
    Later calls verify the connection is still alive via smtp.noop() and
    transparently reconnect if it has gone stale, since a run's sources can
    be minutes apart while each one scrapes and builds.
    """

    def __init__(self):
        self._smtp = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception:
                pass
            self._smtp = None
        return False

    def _ensure_connected(self):
        if self._smtp is not None:
            try:
                status, _ = self._smtp.noop()
                if status == 250:
                    return
            except Exception:
                pass
            self._smtp = None

        smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        self._smtp = smtp

    def send(self, source_name, epub_path, edition_date):
        """Send one source's epub as its own Kindle email.

        Returns True if sent, False if skipped for being over Gmail's
        attachment size limit. Raises on a real send failure so the caller
        can count it as a failed source.
        """
        file_size = os.path.getsize(epub_path)
        if file_size > GMAIL_MAX_ATTACHMENT_BYTES:
            logger.warning(
                "Skipping Kindle email for %s: %s is %d bytes, over Gmail's send limit",
                source_name,
                epub_path,
                file_size,
            )
            return False

        self._ensure_connected()
        message = build_message(
            [(source_name, epub_path)],
            edition_date,
            config.GMAIL_ADDRESS,
            config.KINDLE_EMAIL,
        )
        self._smtp.send_message(message)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_email_sender.py -v`

Expected: All tests PASS, including the pre-existing `send_to_kindle` tests (untouched, must still pass).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/email_sender.py tests/test_email_sender.py
git commit -m "feat: add KindleSender for reusable, self-healing SMTP connections"
```

---

## Task 2: Wire `main()` to build-then-send per source

**Files:**
- Modify: `main.py:97-132` (the `main()` function)
- Modify: `tests/test_main.py` (fixture + send-related tests)

**Interfaces:**
- Consumes: `email_sender.KindleSender` (from Task 1) — `with email_sender.KindleSender() as sender: sender.send(source_name, output_path, edition_date) -> bool`, raises on real failure.
- Produces: `main()` still returns an `int` exit code (`0` or `1`), same contract as today.

- [ ] **Step 1: Update the `_no_real_kindle_email` fixture and rewrite the send-related tests in `tests/test_main.py`**

Replace the fixture (currently `tests/test_main.py:9-24`):

```python
@pytest.fixture(autouse=True)
def _no_real_kindle_email(monkeypatch):
    """Guard against any test in this file accidentally dialing out to real

    Gmail SMTP: default sending off and make an unstubbed KindleSender.send
    call fail loudly instead of silently reaching smtplib. Tests that
    deliberately exercise sending override this via monkeypatch later in
    their own body; since they share this fixture's monkeypatch instance,
    their explicit setattr calls run after this default and take precedence.
    """
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", False)

    def _unexpected_send(self, *args, **kwargs):
        raise AssertionError("unexpected send")

    monkeypatch.setattr(main.email_sender.KindleSender, "send", _unexpected_send)
```

Replace `test_main_does_not_send_when_send_to_kindle_disabled` (currently `tests/test_main.py:264-279`):

```python
def test_main_does_not_send_when_send_to_kindle_disabled(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", False)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    exit_code = main.main()

    assert exit_code == 0
    # the autouse fixture's KindleSender.send would raise AssertionError if called
```

Replace `test_main_sends_combined_email_with_every_built_source` (currently `tests/test_main.py:282-321`) with a per-source version:

```python
def test_main_sends_one_email_per_built_source_as_soon_as_it_builds(monkeypatch):
    sent = []
    build_order = []

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

    def fake_build_epub(source_name, *a, **k):
        build_order.append(source_name)
        return f"/tmp/{source_name}.epub"

    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    def fake_send(self, source_name, epub_path, edition_date):
        sent.append((source_name, epub_path, edition_date))
        return True

    monkeypatch.setattr(main.email_sender.KindleSender, "send", fake_send)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 10, 12, 0, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(main, "datetime", _FixedDatetime)

    exit_code = main.main()

    assert exit_code == 0
    assert build_order == ["Fake Paper", "Fake Paper 2"]
    assert sent == [
        ("Fake Paper", "/tmp/Fake Paper.epub", "2026-08-10"),
        ("Fake Paper 2", "/tmp/Fake Paper 2.epub", "2026-08-10"),
    ]
```

Replace `test_main_returns_nonzero_when_send_to_kindle_fails` (currently `tests/test_main.py:324-338`):

```python
def test_main_returns_nonzero_when_send_to_kindle_fails(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(self, *a, **k):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.email_sender.KindleSender, "send", _boom)

    exit_code = main.main()

    assert exit_code == 1
```

Add a new test for the non-fatal size-skip behavior (append near the other send tests):

```python
def test_main_returns_zero_when_send_is_only_size_skipped(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")
    monkeypatch.setattr(
        main.email_sender.KindleSender, "send", lambda self, *a, **k: False
    )

    exit_code = main.main()

    assert exit_code == 0
```

Replace `test_main_still_publishes_opds_when_kindle_send_fails` (currently `tests/test_main.py:397-418`):

```python
def test_main_still_publishes_opds_when_kindle_send_fails(monkeypatch):
    published = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "SEND_TO_KINDLE", True)
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(self, *a, **k):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(main.email_sender.KindleSender, "send", _boom)
    monkeypatch.setattr(
        main.opds_publish, "publish_catalog", lambda *a, **k: published.append(a)
    )

    exit_code = main.main()

    assert exit_code == 1  # Kindle failure still surfaces as a failed run
    assert len(published) == 1  # but OPDS still got published
```

- [ ] **Step 2: Run the updated tests to verify they fail against current `main.py`**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`

Expected: FAIL — `AttributeError: type object 'config' has no attribute ...` is not it; rather the send-related tests fail because `main.email_sender.KindleSender` doesn't exist yet as an attribute used the way the test expects, or because `main.py` still calls the old `send_to_kindle` path. (`build_order`/`sent` assertions will fail since `main.py` hasn't changed yet.)

- [ ] **Step 3: Rewrite `main()` in `main.py`**

Replace `main.py:97-132`:

```python
def main():
    edition_date = datetime.now(DHAKA_TZ).date().isoformat()

    built_count = 0
    sent_count = 0
    size_skipped_count = 0
    build_failures = 0
    send_failures = 0

    sender = email_sender.KindleSender() if config.SEND_TO_KINDLE else None

    with sender if sender is not None else _null_context():
        for source_slug in config.SOURCES:
            source_module = importlib.import_module(f"jugantor_epub.sources.{source_slug}")
            try:
                output_path = build_source_edition(source_module, edition_date, source_slug)
            except Exception as exc:
                logger.error("Skipping source %s: %s", source_slug, exc)
                build_failures += 1
                continue
            built_count += 1

            if sender is not None:
                try:
                    sent = sender.send(source_module.SOURCE_NAME, output_path, edition_date)
                except Exception as exc:
                    logger.error("Failed to send Kindle email for %s: %s", source_module.SOURCE_NAME, exc)
                    send_failures += 1
                    continue
                if sent:
                    sent_count += 1
                else:
                    size_skipped_count += 1

    if built_count == 0:
        logger.error("No source produced an edition; nothing to send.")
        return 1

    logger.info(
        "Run summary: %d built, %d sent, %d size-skipped, %d build failure(s), %d send failure(s)",
        built_count,
        sent_count,
        size_skipped_count,
        build_failures,
        send_failures,
    )

    exit_code = 1 if (build_failures or send_failures) else 0

    if config.PUBLISH_OPDS:
        try:
            opds_publish.publish_catalog(config.GH_PAGES_DIR, config.OUTPUT_DIR, edition_date)
        except Exception as exc:
            logger.error("Failed to publish OPDS catalog: %s", exc)
            exit_code = 1
        else:
            logger.info("Published OPDS catalog to %s", config.GH_PAGES_DIR)

    return exit_code
```

Add a tiny local no-op context manager helper above `main()` (needed since `KindleSender()` is only constructed when `SEND_TO_KINDLE` is on, but the `for` loop must run either way):

```python
from contextlib import contextmanager


@contextmanager
def _null_context():
    yield None
```

Place this `_null_context` helper and its `from contextlib import contextmanager` import near the top of `main.py`, alongside the other imports (after the existing `from zoneinfo import ZoneInfo` line).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`

Expected: All tests PASS, including the untouched build-related tests (`test_build_source_edition_*`) and the untouched OPDS-only tests (`test_main_does_not_publish_opds_when_disabled`, `test_main_publishes_opds_catalog_when_enabled`, `test_main_returns_nonzero_when_opds_publish_fails`, `test_main_continues_to_next_source_after_one_fails`, `test_main_returns_nonzero_when_all_sources_fail`).

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All tests PASS (including `tests/test_email_sender.py` from Task 1, unaffected by this task).

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: send each source's Kindle email as soon as it builds"
```

---

## Self-Review Notes

- **Spec coverage:** exit-code semantics (Global Constraints + Task 2 Step 3's `exit_code` logic), size-skip non-fatal behavior (`test_main_returns_zero_when_send_is_only_size_skipped`), lazy connect (`test_kindle_sender_does_not_connect_until_first_send`), connection reuse + noop-based reconnect (`test_kindle_sender_reuses_connection_across_multiple_sends`, `test_kindle_sender_reconnects_when_noop_fails`), OPDS staying batched and unaffected (existing OPDS tests untouched, `KindleSender` only wraps the per-source loop) — all covered.
- **Placeholder scan:** no TBD/TODO markers; all steps have literal code.
- **Type consistency:** `KindleSender.send(source_name: str, epub_path: str, edition_date: str) -> bool` is used identically in Task 1's tests and Task 2's `main.py` wiring. `build_message()` signature is reused unchanged from the existing code.
