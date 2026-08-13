# OPDS Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish every built newspaper edition as a static OPDS catalog on GitHub Pages, organized by newspaper (one navigation feed per source, each holding its last 7 editions by count), so OPDS-capable e-readers (KOReader, Moon+ Reader on the user's Boox device) can browse and pull editions directly, alongside the existing Kindle email delivery.

**Architecture:** A pure module (`opds_catalog.py`) builds Atom/OPDS XML strings from plain data (filenames, dates, source names) with zero I/O. A thin wrapper (`opds_publish.py`, same role as `email_sender.py`) reads/writes the `gh-pages` checkout on disk, calling into the pure module. `main.py` calls the wrapper once after its existing per-source build loop, gated behind a new `config.PUBLISH_OPDS` flag mirroring the existing `SEND_TO_KINDLE` pattern. The GitHub Actions workflow checks out `gh-pages`, runs `main.py`, then force-publishes the result back to `gh-pages` with `peaceiris/actions-gh-pages`.

**Tech Stack:** Python 3, stdlib only for the new code (`xml.etree.ElementTree`, `datetime`, `os`, `shutil`) — no new dependencies. GitHub Actions + `peaceiris/actions-gh-pages@v3` for hosting.

## Global Constraints

- Retention is **count-based**: each newspaper keeps its last 7 *successfully built* editions, not "editions from the last 7 days." A source that skipped days simply has fewer/older entries; nothing evicts except a genuine 8th successful build.
- Entry titles use the non-zero-padded format: `"Thursday, 3 Aug, 2026"`, never `"Thursday, 03 Aug, 2026"`.
- Epub filenames inside `gh-pages/{slug}/` stay exactly as `epub_builder.py` already writes them (`{slug}-{date}.epub`) — no renaming.
- No auth — the catalog is public, per the user's explicit choice.
- Catalog structure is two-level: root `catalog.xml` (nav, one entry per `config.SOURCES` slug, always — even a source with zero active editions still appears) → per-source `{slug}/feed.xml` (acquisition, ≤7 entries).
- Follow existing repo conventions: pure-function/I/O split (`opds_catalog.py` pure, `opds_publish.py` I/O, mirroring `sources/jugantor.py`'s parse/fetch split and `email_sender.py`'s role), per-source `try/except` error isolation (one source's feed failing must not block the others or the root catalog), env-driven config flags defaulting off (mirrors `SEND_TO_KINDLE`).
- Spec: `docs/superpowers/specs/2026-08-13-opds-catalog-design.md` — read it for the full rationale behind every decision above.

---

### Task 1: `jugantor_epub/config.py` — OPDS config flags

**Files:**
- Modify: `jugantor_epub/config.py` (append after the existing `GMAIL_APP_PASSWORD` block, currently ending at line 44)
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Produces: `config.PUBLISH_OPDS` (bool), `config.OPDS_BASE_URL` (str), `config.OPDS_RETENTION_COUNT` (int), `config.GH_PAGES_DIR` (str) — all consumed by Task 5 (`opds_publish.py`) and Task 6 (`main.py`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_publish_opds_defaults_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("PUBLISH_OPDS", raising=False)
    importlib.reload(config)
    assert config.PUBLISH_OPDS is False


def test_publish_opds_true_when_env_set_true(monkeypatch):
    monkeypatch.setenv("PUBLISH_OPDS", "true")
    importlib.reload(config)
    assert config.PUBLISH_OPDS is True


def test_publish_opds_case_insensitive(monkeypatch):
    monkeypatch.setenv("PUBLISH_OPDS", "TRUE")
    importlib.reload(config)
    assert config.PUBLISH_OPDS is True


def test_gh_pages_dir_defaults_to_gh_pages_checkout(monkeypatch):
    monkeypatch.delenv("GH_PAGES_DIR", raising=False)
    importlib.reload(config)
    assert config.GH_PAGES_DIR == "gh-pages-checkout"


def test_gh_pages_dir_read_from_env(monkeypatch):
    monkeypatch.setenv("GH_PAGES_DIR", "/custom/path")
    importlib.reload(config)
    assert config.GH_PAGES_DIR == "/custom/path"


def test_opds_base_url_and_retention_count_are_fixed():
    assert config.OPDS_BASE_URL == "https://mehedibangladeshi.github.io/DailyNewspaperPublish/"
    assert config.OPDS_RETENTION_COUNT == 7
```

This file already has a module-level `autouse=True` fixture (`_reload_config_after_test`) that reloads `config` after every test — no new fixture needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: the 6 new tests FAIL with `AttributeError: module 'jugantor_epub.config' has no attribute 'PUBLISH_OPDS'` (or `GH_PAGES_DIR`/`OPDS_BASE_URL`/`OPDS_RETENTION_COUNT`).

- [ ] **Step 3: Implement**

Append to `jugantor_epub/config.py`, after the existing `if GMAIL_APP_PASSWORD:` block:

```python
PUBLISH_OPDS = os.environ.get("PUBLISH_OPDS", "false").lower() == "true"
OPDS_BASE_URL = "https://mehedibangladeshi.github.io/DailyNewspaperPublish/"
OPDS_RETENTION_COUNT = 7
GH_PAGES_DIR = os.environ.get("GH_PAGES_DIR", "gh-pages-checkout")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: all tests PASS (existing + 6 new).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/config.py tests/test_config.py
git commit -m "feat: add OPDS config flags (PUBLISH_OPDS, GH_PAGES_DIR, retention/base URL)"
```

---

### Task 2: `jugantor_epub/opds_catalog.py` — filename parsing and count-based retention

**Files:**
- Create: `jugantor_epub/opds_catalog.py`
- Test: `tests/test_opds_catalog.py` (new)

**Interfaces:**
- Produces: `parse_edition_filename(filename) -> (slug: str, edition_date: date) | None`, `keep_latest_n(filenames: list[str], n: int) -> (kept: list[str], evicted: list[str])`, both consumed by Task 3, Task 4, and Task 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_opds_catalog.py`:

```python
from datetime import date

from jugantor_epub import opds_catalog


def test_parse_edition_filename_extracts_slug_and_date():
    assert opds_catalog.parse_edition_filename("jugantor-2026-08-13.epub") == (
        "jugantor",
        date(2026, 8, 13),
    )


def test_parse_edition_filename_handles_hyphenated_slug():
    assert opds_catalog.parse_edition_filename("prothom-alo-2026-08-13.epub") == (
        "prothom-alo",
        date(2026, 8, 13),
    )


def test_parse_edition_filename_rejects_non_epub():
    assert opds_catalog.parse_edition_filename("jugantor-2026-08-13.txt") is None


def test_parse_edition_filename_rejects_malformed_date():
    assert opds_catalog.parse_edition_filename("jugantor-notadate.epub") is None


def test_parse_edition_filename_rejects_missing_slug():
    assert opds_catalog.parse_edition_filename("2026-08-13.epub") is None


def test_keep_latest_n_keeps_newest_first_within_limit():
    filenames = [
        "jugantor-2026-08-10.epub",
        "jugantor-2026-08-13.epub",
        "jugantor-2026-08-11.epub",
    ]
    kept, evicted = opds_catalog.keep_latest_n(filenames, 7)
    assert kept == [
        "jugantor-2026-08-13.epub",
        "jugantor-2026-08-11.epub",
        "jugantor-2026-08-10.epub",
    ]
    assert evicted == []


def test_keep_latest_n_evicts_oldest_beyond_limit():
    filenames = [f"jugantor-2026-08-{day:02d}.epub" for day in range(1, 9)]  # 8 editions
    kept, evicted = opds_catalog.keep_latest_n(filenames, 7)
    assert len(kept) == 7
    assert evicted == ["jugantor-2026-08-01.epub"]
    assert "jugantor-2026-08-01.epub" not in kept


def test_keep_latest_n_ignores_unparseable_filenames():
    filenames = ["jugantor-2026-08-13.epub", "feed.xml"]
    kept, evicted = opds_catalog.keep_latest_n(filenames, 7)
    assert kept == ["jugantor-2026-08-13.epub"]
    assert evicted == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_opds_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jugantor_epub.opds_catalog'`.

- [ ] **Step 3: Implement**

Create `jugantor_epub/opds_catalog.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_opds_catalog.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/opds_catalog.py tests/test_opds_catalog.py
git commit -m "feat: add OPDS filename parsing and count-based retention"
```

---

### Task 3: `jugantor_epub/opds_catalog.py` — entry title formatting

**Files:**
- Modify: `jugantor_epub/opds_catalog.py` (append)
- Test: `tests/test_opds_catalog.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces: `format_entry_title(edition_date: date) -> str`, consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_opds_catalog.py`:

```python
def test_format_entry_title_two_digit_day():
    assert opds_catalog.format_entry_title(date(2026, 8, 13)) == "Thursday, 13 Aug, 2026"


def test_format_entry_title_single_digit_day_not_zero_padded():
    assert opds_catalog.format_entry_title(date(2026, 8, 3)) == "Monday, 3 Aug, 2026"


def test_format_entry_title_single_digit_day_one():
    assert opds_catalog.format_entry_title(date(2026, 8, 1)) == "Saturday, 1 Aug, 2026"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_opds_catalog.py -v`
Expected: the 3 new tests FAIL with `AttributeError: module 'jugantor_epub.opds_catalog' has no attribute 'format_entry_title'`.

- [ ] **Step 3: Implement**

Append to `jugantor_epub/opds_catalog.py`:

```python
def format_entry_title(edition_date):
    """'Thursday, 3 Aug, 2026' - day is never zero-padded (the user's
    explicit choice over "Thursday, 03 Aug, 2026").
    """
    weekday = edition_date.strftime("%A")
    month = edition_date.strftime("%b")
    return f"{weekday}, {edition_date.day} {month}, {edition_date.year}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_opds_catalog.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/opds_catalog.py tests/test_opds_catalog.py
git commit -m "feat: add non-zero-padded OPDS entry title formatting"
```

---

### Task 4: `jugantor_epub/opds_catalog.py` — feed XML rendering

**Files:**
- Modify: `jugantor_epub/opds_catalog.py` (append)
- Test: `tests/test_opds_catalog.py` (append)

**Interfaces:**
- Consumes: `parse_edition_filename` and `format_entry_title` from Tasks 2–3 (same module, called internally).
- Produces: `render_source_feed_xml(slug: str, source_name: str, kept_filenames: list[str], updated_date: date) -> str`, `render_root_feed_xml(sources: list[(str, str)], updated_date: date) -> str` — both consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_opds_catalog.py`:

```python
import xml.etree.ElementTree as ET

ATOM_NS = "{http://www.w3.org/2005/Atom}"


def test_render_source_feed_xml_is_well_formed_and_has_one_entry_per_kept_file():
    xml_text = opds_catalog.render_source_feed_xml(
        "jugantor",
        "যুগান্তর",
        ["jugantor-2026-08-13.epub", "jugantor-2026-08-12.epub"],
        date(2026, 8, 13),
    )
    root = ET.fromstring(xml_text)
    assert root.tag == f"{ATOM_NS}feed"
    entries = root.findall(f"{ATOM_NS}entry")
    assert len(entries) == 2
    titles = [entry.find(f"{ATOM_NS}title").text for entry in entries]
    assert titles == ["Thursday, 13 Aug, 2026", "Wednesday, 12 Aug, 2026"]
    acquisition_links = [entry.find(f"{ATOM_NS}link").get("href") for entry in entries]
    assert acquisition_links == ["jugantor-2026-08-13.epub", "jugantor-2026-08-12.epub"]


def test_render_source_feed_xml_empty_when_no_kept_files():
    xml_text = opds_catalog.render_source_feed_xml("jugantor", "যুগান্তর", [], date(2026, 8, 13))
    root = ET.fromstring(xml_text)
    assert root.findall(f"{ATOM_NS}entry") == []


def test_render_root_feed_xml_is_well_formed_and_lists_every_source():
    xml_text = opds_catalog.render_root_feed_xml(
        [("jugantor", "যুগান্তর"), ("prothomalo", "প্রথম আলো")],
        date(2026, 8, 13),
    )
    root = ET.fromstring(xml_text)
    assert root.tag == f"{ATOM_NS}feed"
    entries = root.findall(f"{ATOM_NS}entry")
    assert len(entries) == 2
    hrefs = [entry.find(f"{ATOM_NS}link").get("href") for entry in entries]
    assert hrefs == ["jugantor/feed.xml", "prothomalo/feed.xml"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_opds_catalog.py -v`
Expected: the 3 new tests FAIL with `AttributeError: module 'jugantor_epub.opds_catalog' has no attribute 'render_source_feed_xml'`.

- [ ] **Step 3: Implement**

Append to `jugantor_epub/opds_catalog.py` (add `import xml.etree.ElementTree as ET` to the top of the file, alongside the existing `from datetime import date`):

```python
import xml.etree.ElementTree as ET

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_opds_catalog.py -v`
Expected: all tests PASS (14 total in this file).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/opds_catalog.py tests/test_opds_catalog.py
git commit -m "feat: render OPDS root navigation and per-source acquisition feeds"
```

---

### Task 5: `jugantor_epub/opds_publish.py` — I/O wrapper

**Files:**
- Create: `jugantor_epub/opds_publish.py`

**Interfaces:**
- Consumes: `config.SOURCES`, `config.OPDS_RETENTION_COUNT` (Task 1); `opds_catalog.keep_latest_n`, `opds_catalog.render_source_feed_xml`, `opds_catalog.render_root_feed_xml` (Tasks 2 & 4); `source_module.SOURCE_NAME` (existing contract in `jugantor_epub/sources/*.py`).
- Produces: `publish_catalog(gh_pages_dir: str, output_dir: str, edition_date: str) -> None`, consumed by Task 6 (`main.py`).

Per the spec, this is a thin I/O wrapper and is **not unit tested directly** — same treatment as `email_sender.send_to_kindle()` and the scraper's `_get()`. Its deliverable is verified with a one-off manual check (Step 2 below), not a permanent test file.

- [ ] **Step 1: Implement**

Create `jugantor_epub/opds_publish.py`:

```python
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
```

- [ ] **Step 2: Manually verify end-to-end, including eviction**

Run this from the repo root (uses real temp directories, no network, no config mutation survives since `config.SOURCES` is monkeypatched only for this one-off process):

```bash
.venv/bin/python -c "
import os, tempfile
from jugantor_epub import opds_publish, config

config.SOURCES = ['jugantor']

with tempfile.TemporaryDirectory() as gh_pages, tempfile.TemporaryDirectory() as output:
    source_dir = os.path.join(gh_pages, 'jugantor')
    os.makedirs(source_dir)
    # seed 7 pre-existing editions (2026-08-01 .. 2026-08-07)
    for day in range(1, 8):
        open(os.path.join(source_dir, f'jugantor-2026-08-{day:02d}.epub'), 'wb').write(b'old')

    # today (08-08) is an 8th successful build
    open(os.path.join(output, 'jugantor-2026-08-08.epub'), 'wb').write(b'new')

    opds_publish.publish_catalog(gh_pages, output, '2026-08-08')

    files = sorted(os.listdir(source_dir))
    print('files after publish:', files)
    assert 'jugantor-2026-08-01.epub' not in files, 'oldest should have been evicted'
    assert 'jugantor-2026-08-08.epub' in files, 'new build should have been copied in'
    assert len([f for f in files if f.endswith('.epub')]) == 7, 'exactly 7 epubs should remain'
    assert os.path.exists(os.path.join(gh_pages, 'catalog.xml'))
    print('catalog.xml:')
    print(open(os.path.join(gh_pages, 'catalog.xml')).read())
    print('OK')
"
```

Expected output ends with `OK` and no `AssertionError`; `catalog.xml` printed should contain a `jugantor/feed.xml` link.

- [ ] **Step 3: Commit**

```bash
git add jugantor_epub/opds_publish.py
git commit -m "feat: add OPDS catalog publish wrapper (copy-forward + evict)"
```

---

### Task 6: `main.py` — wire up OPDS publishing

**Files:**
- Modify: `main.py` (import line 6; insert new block before the final `return 0`, currently around line 116)
- Test: `tests/test_main.py` (append)

**Interfaces:**
- Consumes: `config.PUBLISH_OPDS`, `config.GH_PAGES_DIR`, `config.OUTPUT_DIR` (Task 1); `opds_publish.publish_catalog(gh_pages_dir, output_dir, edition_date)` (Task 5).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_main.py`. First, add a second autouse guard fixture right after the existing `_no_real_kindle_email` fixture (same file, same pattern):

```python
@pytest.fixture(autouse=True)
def _no_real_opds_publish(monkeypatch):
    """Same guard as _no_real_kindle_email, for the OPDS publish path."""
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", False)

    def _unexpected_publish(*args, **kwargs):
        raise AssertionError("unexpected publish")

    monkeypatch.setattr(main.opds_publish, "publish_catalog", _unexpected_publish)
```

Then append these tests at the end of the file:

```python
def test_main_does_not_publish_opds_when_disabled(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", False)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    exit_code = main.main()

    assert exit_code == 0


def test_main_publishes_opds_catalog_when_enabled(monkeypatch):
    published = []

    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", True)
    monkeypatch.setattr(main.config, "GH_PAGES_DIR", "/tmp/gh-pages")
    monkeypatch.setattr(main.config, "OUTPUT_DIR", "/tmp/output")
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")
    monkeypatch.setattr(
        main.opds_publish, "publish_catalog", lambda *a, **k: published.append(a)
    )

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 10)

    monkeypatch.setattr(main, "date", _FixedDate)

    exit_code = main.main()

    assert exit_code == 0
    assert published == [("/tmp/gh-pages", "/tmp/output", "2026-08-10")]


def test_main_returns_nonzero_when_opds_publish_fails(monkeypatch):
    monkeypatch.setattr(main.config, "SOURCES", ["ok"])
    monkeypatch.setattr(main.config, "PUBLISH_OPDS", True)
    monkeypatch.setattr(main.importlib, "import_module", lambda name: _FakeSourceOk)
    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))
    monkeypatch.setattr(epub_builder, "build_epub", lambda *a, **k: "/tmp/x.epub")

    def _boom(*a, **k):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(main.opds_publish, "publish_catalog", _boom)

    exit_code = main.main()

    assert exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: the new tests FAIL — `_no_real_opds_publish` fixture errors with `AttributeError: <module 'main'> does not have the attribute 'opds_publish'` (main.py doesn't import it yet), which also breaks every other test in the file since the fixture is autouse. This is expected and resolves once Step 3 lands.

- [ ] **Step 3: Implement**

In `main.py`, change line 6 from:

```python
from jugantor_epub import bengali_date, config, cover, email_sender, epub_builder, images
```

to:

```python
from jugantor_epub import bengali_date, config, cover, email_sender, epub_builder, images, opds_publish
```

Then, in `main()`, insert a new block after the existing `SEND_TO_KINDLE` block and before the final `return 0` — i.e. change:

```python
    if config.SEND_TO_KINDLE:
        try:
            email_sender.send_to_kindle(built, edition_date)
        except Exception as exc:
            logger.error("Failed to send combined edition to Kindle: %s", exc)
            return 1
        logger.info("Sent %d edition(s) to Kindle.", len(built))

    return 0
```

to:

```python
    if config.SEND_TO_KINDLE:
        try:
            email_sender.send_to_kindle(built, edition_date)
        except Exception as exc:
            logger.error("Failed to send combined edition to Kindle: %s", exc)
            return 1
        logger.info("Sent %d edition(s) to Kindle.", len(built))

    if config.PUBLISH_OPDS:
        try:
            opds_publish.publish_catalog(config.GH_PAGES_DIR, config.OUTPUT_DIR, edition_date)
        except Exception as exc:
            logger.error("Failed to publish OPDS catalog: %s", exc)
            return 1
        logger.info("Published OPDS catalog to %s", config.GH_PAGES_DIR)

    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: all tests PASS (existing + 3 new).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS (no regressions in other files).

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: publish OPDS catalog from main() when PUBLISH_OPDS is set"
```

---

### Task 7: `.github/workflows/daily-kindle.yml` — CI wiring

**Files:**
- Modify: `.github/workflows/daily-kindle.yml` (full file, shown below)
- Test: `tests/test_workflow.py` (append)

**Interfaces:**
- Consumes: `config.PUBLISH_OPDS` / `config.GH_PAGES_DIR` env var names (Task 1) — must match exactly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workflow.py`:

```python
def test_workflow_has_write_permission_for_gh_pages_publish():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "contents: write" in content


def test_workflow_checks_out_gh_pages_branch_with_continue_on_error():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "ref: gh-pages" in content
    assert "continue-on-error: true" in content
    assert "path: gh-pages-checkout" in content


def test_workflow_runs_main_with_opds_env_vars():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "PUBLISH_OPDS: 'true'" in content
    assert "GH_PAGES_DIR: gh-pages-checkout" in content


def test_workflow_publishes_to_gh_pages_with_keep_files_false_and_force_orphan():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "uses: peaceiris/actions-gh-pages@v3" in content
    assert "keep_files: false" in content
    assert "force_orphan: true" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`
Expected: the 4 new tests FAIL (none of these strings exist in the workflow file yet).

- [ ] **Step 3: Implement**

Replace the full contents of `.github/workflows/daily-kindle.yml` with:

```yaml
name: Daily Kindle edition
on:
  schedule:
    - cron: '0 2 * * *'   # 02:00 UTC = 08:00 BD time (UTC+6, no DST)
  workflow_dispatch:

jobs:
  build-and-send:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        continue-on-error: true
        with:
          ref: gh-pages
          path: gh-pages-checkout
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
          PUBLISH_OPDS: 'true'
          GH_PAGES_DIR: gh-pages-checkout
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: jugantor-epub-${{ github.run_id }}
          path: output/*.epub
          retention-days: 7
      - uses: peaceiris/actions-gh-pages@v3
        if: always()
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: gh-pages-checkout
          keep_files: false
          force_orphan: true
```

Notes for the engineer applying this:
- The second `actions/checkout@v4` has `continue-on-error: true` because the `gh-pages` branch won't exist on the very first run — a missing/empty `gh-pages-checkout` directory is exactly "zero existing editions" to `opds_publish.publish_catalog` (it calls `os.makedirs(..., exist_ok=True)` per source, so it creates whatever's missing).
- `if: always()` on the `peaceiris/actions-gh-pages` step (same reasoning as the existing `upload-artifact` step): the OPDS catalog and the Kindle email are independent delivery paths, so a Kindle-send failure shouldn't prevent an otherwise-successful OPDS publish, or vice versa.
- No new repo secret is required — `secrets.GITHUB_TOKEN` is automatically provided by GitHub Actions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`
Expected: all tests PASS (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily-kindle.yml tests/test_workflow.py
git commit -m "ci: publish OPDS catalog to gh-pages after each daily run"
```

---

### Task 8: Cleanup — delete prototype, update docs, full suite

**Files:**
- Delete: `prototypes/opds_catalog/logic.py`, `prototypes/opds_catalog/tui.py`, `prototypes/opds_catalog/NOTES.md` (and the now-empty `prototypes/opds_catalog/` and `prototypes/` directories)
- Modify: `README.md` (add a section; add two bullets to "Project layout")
- Modify: `CLAUDE.md` (extend the "Daily automation & Kindle delivery" section)

**Interfaces:** none — documentation and repo hygiene only.

- [ ] **Step 1: Delete the prototype**

```bash
git rm -r prototypes/
```

Its pure logic (`logic.py`) has already been absorbed into `jugantor_epub/opds_catalog.py` (Tasks 2–4) with count-based retention instead of the prototype's calendar-window retention, and per-source instead of the flat-feed structure the prototype validated — the prototype's job (deciding the shape) is done.

- [ ] **Step 2: Update `README.md`**

Add two bullets to the "Project layout" list (after the `jugantor_epub/config.py` bullet, before the `main.py` bullet):

```markdown
- `jugantor_epub/opds_catalog.py` — pure functions that build the OPDS
  catalog XML (per-newspaper retention, feed rendering) from filenames and
  dates, no I/O.
- `jugantor_epub/opds_publish.py` — reads/writes the `gh-pages` checkout,
  calling into `opds_catalog.py` to decide what to keep, evict, and render.
```

Add a new section after the existing "Daily Kindle delivery (GitHub Actions)" section:

```markdown
## OPDS catalog (for Boox / KOReader / other OPDS-capable readers)

The same daily workflow also publishes a static OPDS catalog to GitHub
Pages at `https://mehedibangladeshi.github.io/DailyNewspaperPublish/catalog.xml`.
Add that URL to any OPDS-capable reader app (KOReader, Moon+ Reader, etc.)
to browse and download editions directly — no email step needed. Each
configured newspaper gets its own feed holding its last 7 editions (by
count, not calendar days). This is independent of Kindle delivery above —
Kindle's stock firmware has no OPDS client, so email remains the way
editions reach a Kindle.
```

- [ ] **Step 3: Update `CLAUDE.md`**

Append a new paragraph at the end of the existing "Daily automation & Kindle delivery" section:

```markdown

**OPDS catalog for non-Kindle e-readers**: alongside the Kindle email, the same workflow run publishes a static OPDS catalog to the `gh-pages` branch (`jugantor_epub/opds_catalog.py` for the pure feed-building logic, `jugantor_epub/opds_publish.py` for the I/O side that reads/writes the `gh-pages` checkout), gated behind `config.PUBLISH_OPDS` the same way Kindle delivery is gated behind `config.SEND_TO_KINDLE`. The catalog is organized by newspaper, not by date: a root `catalog.xml` navigation feed lists one entry per `config.SOURCES` slug, each linking to that source's own `{slug}/feed.xml` acquisition feed holding its last 7 *successfully built* editions — a count, not a calendar window, so a source that skipped a day doesn't lose an entry, it just keeps older news a little longer. `opds_publish.publish_catalog()` copies forward whatever's still within that count from the existing `gh-pages` checkout, physically deletes anything falling out of it, and the workflow republishes the whole `gh-pages` branch from scratch each run (`keep_files: false`, `force_orphan: true`) — so eviction never needs a separate `git rm` step.
```

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS, zero regressions.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: document OPDS catalog delivery, remove absorbed prototype"
```

---

## Self-Review Notes

- **Spec coverage:** every decision in `docs/superpowers/specs/2026-08-13-opds-catalog-design.md` maps to a task — config flags (Task 1), `parse_edition_filename`/`keep_latest_n` (Task 2), title formatting (Task 3), both feed renderers (Task 4), the publish wrapper including physical eviction (Task 5), `main.py` gating (Task 6), workflow permissions/checkout/publish (Task 7), prototype deletion + doc updates (Task 8).
- **Type/signature consistency check:** `keep_latest_n` returns `(kept, evicted)` in Task 2 and is called that way in Task 5; `render_source_feed_xml(slug, source_name, kept_filenames, updated_date)` and `render_root_feed_xml(sources, updated_date)` signatures from Task 4 match exactly how Task 5 calls them; `publish_catalog(gh_pages_dir, output_dir, edition_date)` from Task 5 matches the call in Task 6's `main.py` edit and the test assertion `published == [("/tmp/gh-pages", "/tmp/output", "2026-08-10")]`.
- **No placeholders:** every step has literal code, not a description of code.
