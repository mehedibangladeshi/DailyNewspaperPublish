# Prothom Alo Trim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Prothom Alo's scrape to actually match "today's edition" — filtering listings to stories published on the run's `edition_date`, and excluding two non-editorial nav sections — so its epub stops growing unboundedly (410 articles / ~24MB observed 2026-08-17) and stays proportionate to Jugantor's and Dhaka Tribune's per-day sizes.

**Architecture:** Prothom Alo's category-listing JSON already carries a `published-at` epoch-ms timestamp per story (verified against `tests/fixtures/prothomalo_section_bangladesh.html`). `parse_articles()` converts each story's timestamp to its Asia/Dhaka calendar date and drops anything not matching `edition_date`, before any per-article detail fetch or image download happens. This requires threading `edition_date` through the shared source-module contract (`list_articles(slug, edition_date)`), which Jugantor and Dhaka Tribune accept-and-ignore since their listings are inherently single-day already. Separately, `video` and `chakri` (jobs) are dropped from Prothom Alo's section list entirely — a content-fit decision, not a date one.

**Tech Stack:** Python 3, `zoneinfo` (stdlib, Python ≥3.9) for the Asia/Dhaka conversion — no new dependency.

## Global Constraints

- Follow the existing parse/fetch split (`CLAUDE.md`): HTML/JSON-shape logic goes in `parse_*` functions (pure, tested against fixtures); `_get`/network concerns stay in the thin wrapper.
- Preserve error isolation: a per-section/per-article failure must not abort the whole run (see `CLAUDE.md`'s error-isolation principle).
- All extracted text still goes through `_normalize()` — unaffected by this change, but don't remove it while editing nearby code.
- Run the full suite (`.venv/bin/python -m pytest tests/ -v`) after every task — it must stay green throughout.

---

### Task 1: Thread `edition_date` through the source-module contract

**Files:**
- Modify: `jugantor_epub/sources/jugantor.py:128-131` (`list_articles`)
- Modify: `jugantor_epub/sources/dhakatribune.py:139-142` (`list_articles`)
- Modify: `jugantor_epub/sources/prothomalo.py:124-168` (`parse_articles`, `list_articles`)
- Modify: `main.py` (the `source_module.list_articles(slug)` call site inside `build_source_edition`)
- Modify: `CLAUDE.md:32` (source module contract description)
- Test: `tests/test_jugantor_scraper.py`, `tests/test_dhakatribune_scraper.py`, `tests/test_prothomalo_scraper.py`, `tests/test_main.py`

**Interfaces:**
- Produces: `list_articles(slug, edition_date) -> [dict, ...]` — new required second positional parameter on every source module. Jugantor/Dhaka Tribune ignore it (default `edition_date=None` in their signature so any existing single-arg caller still works). Prothom Alo requires it and passes it straight through to `parse_articles(html, edition_date)`.
- Produces (Prothom Alo only): `parse_articles(html, edition_date) -> [dict, ...]` — `edition_date` is an ISO date string (`"YYYY-MM-DD"`), matching what `main.py` already computes via `date.today().isoformat()`.

This task is pure plumbing — no filtering behavior yet. Task 2 adds the actual date logic on top of this signature.

- [ ] **Step 1: Update Jugantor and Dhaka Tribune's `list_articles` to accept-and-ignore `edition_date`**

In `jugantor_epub/sources/jugantor.py`, change:

```python
def list_articles(slug):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html)
```

to:

```python
def list_articles(slug, edition_date=None):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html)
```

In `jugantor_epub/sources/dhakatribune.py`, change:

```python
def list_articles(slug):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html)
```

to:

```python
def list_articles(slug, edition_date=None):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html)
```

Both modules' listing pages are already inherently single-day (Jugantor's print-edition pages, Dhaka Tribune's single-page-no-pagination category listing), so `edition_date` is accepted only to keep the contract uniform across sources — nothing reads it here.

- [ ] **Step 2: Update Prothom Alo's `parse_articles` and `list_articles` signatures (no filtering yet)**

In `jugantor_epub/sources/prothomalo.py`, change:

```python
def parse_articles(html):
    """Pure parsing step for list_articles; takes raw section-page HTML.
    Unlike Jugantor, the listing data isn't in scrapeable DOM cards - it's
    embedded as a <script type="application/json" id="static-page"> blob
    (Quintype CMS's hydration state), so this parses that JSON instead of
    selecting HTML cards."""
```

to:

```python
def parse_articles(html, edition_date):
    """Pure parsing step for list_articles; takes raw section-page HTML and
    the run's edition_date (ISO "YYYY-MM-DD" string). Unlike Jugantor, the
    listing data isn't in scrapeable DOM cards - it's embedded as a
    <script type="application/json" id="static-page"> blob (Quintype CMS's
    hydration state), so this parses that JSON instead of selecting HTML
    cards."""
```

(Leave the body unchanged for this step — Task 2 adds the filtering logic.)

Change:

```python
def list_articles(slug):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html)
```

to:

```python
def list_articles(slug, edition_date):
    section_url = f"{BASE_URL}/{slug}"
    html = _get(section_url)
    return parse_articles(html, edition_date)
```

- [ ] **Step 3: Update every existing call site of `prothomalo.parse_articles`/`list_articles` in tests to pass `edition_date`**

In `tests/test_prothomalo_scraper.py`, update these four call sites (the fixture's stories span 2026-08-16 and 2026-08-17 — verified via `datetime.fromtimestamp(published_at/1000, tz=ZoneInfo("Asia/Dhaka"))`; use `"2026-08-17"` throughout so `test_parse_articles_extracts_stories_and_dedupes_from_nested_collection_json`'s existing assertions about the first story keep passing unchanged):

```python
def test_parse_articles_extracts_stories_and_dedupes_from_nested_collection_json(load_fixture):
    """Regression: listing data isn't in DOM cards - it's a deeply nested,
    recursive Quintype collection tree embedded as JSON, where the same
    story commonly appears under more than one widget."""
    html = load_fixture("prothomalo_section_bangladesh.html")
    articles = prothomalo.parse_articles(html, "2026-08-17")
```

```python
def test_parse_articles_returns_empty_list_when_static_page_script_missing():
    assert prothomalo.parse_articles("<html><body>no static-page script here</body></html>", "2026-08-17") == []
```

```python
def test_parse_articles_handles_invalid_json_syntax():
    html = """
    <html><body>
      <script type="application/json" id="static-page">{not valid json at all</script>
    </body></html>
    """
    assert prothomalo.parse_articles(html, "2026-08-17") == []
```

```python
def test_parse_articles_handles_missing_hero_image():
    payload = {
        "qt": {
            "data": {
                "collection": {
                    "items": [
                        {
                            "type": "story",
                            "story": {
                                "headline": "No image here",
                                "subheadline": "sub",
                                "url": "https://www.prothomalo.com/world/abc123",
                            },
                        }
                    ]
                }
            }
        }
    }
    html = f"""
    <html><body>
      <script type="application/json" id="static-page">{json.dumps(payload)}</script>
    </body></html>
    """
    articles = prothomalo.parse_articles(html, "2026-08-17")

    assert len(articles) == 1
    assert articles[0]["thumbnail"] is None
```

And the `list_articles` wrapper test:

```python
def test_list_articles_fetches_then_parses(monkeypatch, load_fixture):
    seen_urls = []

    def fake_get(url):
        seen_urls.append(url)
        return load_fixture("prothomalo_section_bangladesh.html")

    monkeypatch.setattr(prothomalo, "_get", fake_get)

    articles = prothomalo.list_articles("bangladesh", "2026-08-17")

    assert seen_urls == ["https://www.prothomalo.com/bangladesh"]
    assert len(articles) > 0
```

- [ ] **Step 4: Run the Prothom Alo test file to confirm nothing is broken by the signature change**

Run: `.venv/bin/python -m pytest tests/test_prothomalo_scraper.py -v`
Expected: all PASS (Task 2 hasn't added filtering yet, so counts are unchanged from before).

- [ ] **Step 5: Wire `main.py`'s call site to pass `edition_date`**

In `main.py`, inside `build_source_edition`, change:

```python
    for slug, section_name in source_module.discover_sections():
        try:
            listing = source_module.list_articles(slug)
        except Exception as exc:
```

to:

```python
    for slug, section_name in source_module.discover_sections():
        try:
            listing = source_module.list_articles(slug, edition_date)
        except Exception as exc:
```

- [ ] **Step 6: Update the three fake source classes in `tests/test_main.py` to accept the new parameter**

Each of `_FakeSourceOk`, `_FakeSourceOk2`, and `_FakeSourceAllFail` has a `list_articles(slug)` static method (lines 47, 84, 114). Change each to `list_articles(slug, edition_date)`, e.g.:

```python
class _FakeSourceOk:
    SOURCE_NAME = "Fake Paper"
    COVER_ACCENT_COLOR = (10, 20, 30)

    @staticmethod
    def discover_sections():
        return [("sec1", "Section One")]

    @staticmethod
    def list_articles(slug, edition_date):
        return [
            {"url": "https://x/1", "headline": "H1", "thumbnail": "https://img/shared.jpg"},
            {"url": "https://x/err", "headline": "H-err", "thumbnail": None},
            {"url": "https://x/3", "headline": "H3", "thumbnail": "https://img/shared.jpg"},
        ]
```

Apply the same `slug, edition_date` signature change to `_FakeSourceOk2.list_articles` (line 84) and `_FakeSourceAllFail.list_articles` (line 114) — leave their bodies unchanged.

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS (190 tests before this task; still 190, none added yet).

- [ ] **Step 8: Update `CLAUDE.md`'s source-module contract description**

In `CLAUDE.md:32`, change:

```
**Source module contract** (`jugantor_epub/sources/*.py`): each module exposes `discover_sections() -> [(slug, name), ...]`, `list_articles(slug) -> [dict, ...]`, `fetch_article(url) -> dict`, `get_cover_logo_url() -> str`, and a `SOURCE_NAME` string. `main.py` only depends on this shape, imported dynamically via `importlib.import_module(f"jugantor_epub.sources.{name}")` — adding a second newspaper means adding a new module with this same shape and appending its name to `config.SOURCES`; no changes to `main.py` are needed.
```

to:

```
**Source module contract** (`jugantor_epub/sources/*.py`): each module exposes `discover_sections() -> [(slug, name), ...]`, `list_articles(slug, edition_date) -> [dict, ...]`, `fetch_article(url) -> dict`, `get_cover_logo_url() -> str`, and a `SOURCE_NAME` string. `edition_date` is the same ISO `"YYYY-MM-DD"` string `main.py` computes once per run; Jugantor and Dhaka Tribune accept it via `edition_date=None` and ignore it (their listings are inherently single-day already), while Prothom Alo uses it to filter listings to stories actually published that day (see the Prothom Alo scraper notes below) — necessary because its category pages are a rolling recent-stories feed, not a bounded single-day listing like the other two. `main.py` only depends on this shape, imported dynamically via `importlib.import_module(f"jugantor_epub.sources.{name}")` — adding a second newspaper means adding a new module with this same shape and appending its name to `config.SOURCES`; no changes to `main.py` are needed.
```

- [ ] **Step 9: Commit**

```bash
git add jugantor_epub/sources/jugantor.py jugantor_epub/sources/dhakatribune.py jugantor_epub/sources/prothomalo.py main.py CLAUDE.md tests/test_prothomalo_scraper.py tests/test_main.py
git commit -m "refactor: thread edition_date through the source-module list_articles contract"
```

---

### Task 2: Filter Prothom Alo listings to stories published on `edition_date`

**Files:**
- Modify: `jugantor_epub/sources/prothomalo.py` (add `_story_date` helper, filtering logic in `parse_articles`)
- Test: `tests/test_prothomalo_scraper.py`

**Interfaces:**
- Consumes: `parse_articles(html, edition_date)` signature from Task 1.
- Produces: `_story_date(published_at) -> date | None` — converts a Quintype `published-at` epoch-ms value to its Asia/Dhaka calendar `datetime.date`, or `None` if the value is missing/malformed. Not part of the public contract, but Task 4's manual verification may reference it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_prothomalo_scraper.py` (near the other `parse_articles` tests):

```python
def test_parse_articles_filters_to_stories_published_on_edition_date(load_fixture):
    """The bangladesh fixture's 35 stories split 27/8 across 2026-08-17 and
    2026-08-16 (Asia/Dhaka calendar dates, verified against published-at)."""
    html = load_fixture("prothomalo_section_bangladesh.html")

    articles_17 = prothomalo.parse_articles(html, "2026-08-17")
    articles_16 = prothomalo.parse_articles(html, "2026-08-16")

    assert len(articles_17) == 27
    assert len(articles_16) == 8


def test_parse_articles_keeps_story_with_missing_published_at():
    payload = {
        "qt": {
            "data": {
                "collection": {
                    "items": [
                        {
                            "type": "story",
                            "story": {
                                "headline": "No timestamp here",
                                "subheadline": "sub",
                                "url": "https://www.prothomalo.com/world/no-date",
                            },
                        }
                    ]
                }
            }
        }
    }
    html = f"""
    <html><body>
      <script type="application/json" id="static-page">{json.dumps(payload)}</script>
    </body></html>
    """

    articles = prothomalo.parse_articles(html, "2026-08-17")

    assert len(articles) == 1
    assert articles[0]["url"] == "https://www.prothomalo.com/world/no-date"


def test_story_date_converts_epoch_ms_to_asia_dhaka_date():
    # 1786947241293 ms -> 2026-08-17 05:14:01 in Asia/Dhaka (UTC+6)
    assert prothomalo._story_date(1786947241293) == date(2026, 8, 17)


def test_story_date_returns_none_for_missing_or_invalid_value():
    assert prothomalo._story_date(None) is None
    assert prothomalo._story_date("not-a-timestamp") is None
```

Add `from datetime import date` to the top of `tests/test_prothomalo_scraper.py` if not already imported (check first — it currently imports only `json`, `pytest`, `requests`, `BeautifulSoup`, and the source modules).

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_prothomalo_scraper.py -k "filters_to_stories or missing_published_at or story_date" -v`
Expected: FAIL — `test_parse_articles_filters_to_stories_published_on_edition_date` fails because both counts equal 35 (no filtering yet); `test_story_date_converts...` and `test_story_date_returns_none...` fail with `AttributeError: module 'prothomalo' has no attribute '_story_date'`.

- [ ] **Step 3: Implement `_story_date` and wire filtering into `parse_articles`**

Add near the top of `jugantor_epub/sources/prothomalo.py`, after the existing imports:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo
```

Add a module-level constant near `MEDIA_BASE_URL`:

```python
# Prothom Alo is Bangladesh's paper, so "today" for date-filtering purposes
# means the Asia/Dhaka calendar day, regardless of what timezone this
# process happens to run in (main.py's edition_date is computed once, in
# whatever local time the run has, and is compared against here).
DHAKA_TZ = ZoneInfo("Asia/Dhaka")
```

Add the helper function just above `parse_articles`:

```python
def _story_date(published_at):
    """Convert a Quintype `published-at` epoch-ms timestamp to its
    Asia/Dhaka calendar date. Returns None if the value is missing or
    malformed - callers should fail open (keep the story) rather than drop
    it, since this is a newly-relied-on field with no track record yet of
    being reliably present across every section's JSON shape."""
    if not isinstance(published_at, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(published_at / 1000, tz=DHAKA_TZ).date()
    except (OverflowError, OSError, ValueError):
        return None
```

Update `parse_articles` to filter using it. Change:

```python
def parse_articles(html, edition_date):
    """Pure parsing step for list_articles; takes raw section-page HTML and
    the run's edition_date (ISO "YYYY-MM-DD" string). Unlike Jugantor, the
    listing data isn't in scrapeable DOM cards - it's embedded as a
    <script type="application/json" id="static-page"> blob (Quintype CMS's
    hydration state), so this parses that JSON instead of selecting HTML
    cards."""
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.select_one("script#static-page")
    if script_tag is None:
        return []

    try:
        data = json.loads(script_tag.string or "{}", strict=False)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse static-page JSON")
        return []

    collection = ((data.get("qt") or {}).get("data") or {}).get("collection") or {}
    stories = []
    _find_stories(collection.get("items") or [], set(), stories)

    articles = []
    for story in stories:
        thumbnail = None
        s3_key = story.get("hero-image-s3-key")
        if s3_key:
            thumbnail = f"{MEDIA_BASE_URL}/{s3_key}?w=400&auto=format,compress&fit=max"

        articles.append(
            {
                "url": story["url"],
                "headline": _normalize(story.get("headline") or ""),
                "summary": _normalize(story.get("subheadline") or ""),
                "listing_time": "",
                "thumbnail": thumbnail,
            }
        )

    return articles
```

to:

```python
def parse_articles(html, edition_date):
    """Pure parsing step for list_articles; takes raw section-page HTML and
    the run's edition_date (ISO "YYYY-MM-DD" string). Unlike Jugantor, the
    listing data isn't in scrapeable DOM cards - it's embedded as a
    <script type="application/json" id="static-page"> blob (Quintype CMS's
    hydration state), so this parses that JSON instead of selecting HTML
    cards.

    Unlike Jugantor's print-edition pages, a category page has no natural
    "today only" bound - it's a rolling feed of recent stories regardless of
    date. Each story carries its own published-at epoch-ms timestamp, so
    this filters to stories whose Asia/Dhaka calendar date matches
    edition_date, dropping the rest before any per-article fetch happens."""
    soup = BeautifulSoup(html, "html.parser")
    script_tag = soup.select_one("script#static-page")
    if script_tag is None:
        return []

    try:
        data = json.loads(script_tag.string or "{}", strict=False)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Could not parse static-page JSON")
        return []

    collection = ((data.get("qt") or {}).get("data") or {}).get("collection") or {}
    stories = []
    _find_stories(collection.get("items") or [], set(), stories)

    target_date = date.fromisoformat(edition_date)
    warned_missing_date = False

    articles = []
    for story in stories:
        story_date = _story_date(story.get("published-at"))
        if story_date is not None and story_date != target_date:
            continue
        if story_date is None and not warned_missing_date:
            logger.warning(
                "Story listing missing/invalid published-at, keeping it: %s",
                story.get("url"),
            )
            warned_missing_date = True

        thumbnail = None
        s3_key = story.get("hero-image-s3-key")
        if s3_key:
            thumbnail = f"{MEDIA_BASE_URL}/{s3_key}?w=400&auto=format,compress&fit=max"

        articles.append(
            {
                "url": story["url"],
                "headline": _normalize(story.get("headline") or ""),
                "summary": _normalize(story.get("subheadline") or ""),
                "listing_time": "",
                "thumbnail": thumbnail,
            }
        )

    return articles
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_prothomalo_scraper.py -k "filters_to_stories or missing_published_at or story_date" -v`
Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS (194 tests: 190 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add jugantor_epub/sources/prothomalo.py tests/test_prothomalo_scraper.py
git commit -m "feat: filter Prothom Alo listings to stories published on edition_date"
```

---

### Task 3: Exclude `video` and `chakri` sections from Prothom Alo

**Files:**
- Modify: `jugantor_epub/sources/prothomalo.py` (`FALLBACK_SECTIONS`, `parse_sections`)
- Test: `tests/test_prothomalo_scraper.py`

**Interfaces:**
- Consumes: none from earlier tasks (independent of the date-filtering change).
- Produces: `EXCLUDED_SECTION_SLUGS` module-level constant — a `set` of slugs Task 4's docs may reference.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_prothomalo_scraper.py`:

```python
def test_parse_sections_excludes_video_and_chakri():
    html = """
    <div id="navbar">
      <a aria-label="বাংলাদেশ" href="https://www.prothomalo.com/bangladesh">বাংলাদেশ</a>
      <a aria-label="ভিডিও" href="https://www.prothomalo.com/video">ভিডিও</a>
      <a aria-label="চাকরি" href="https://www.prothomalo.com/chakri">চাকরি</a>
    </div>
    """
    sections = prothomalo.parse_sections(html)

    slugs = [slug for slug, _ in sections]
    assert slugs == ["bangladesh"]


def test_fallback_sections_excludes_video_and_chakri():
    slugs = [slug for slug, _ in prothomalo.FALLBACK_SECTIONS]
    assert "video" not in slugs
    assert "chakri" not in slugs
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_prothomalo_scraper.py -k "excludes_video_and_chakri" -v`
Expected: FAIL — `test_parse_sections_excludes_video_and_chakri` fails because `slugs` includes `"video"` and `"chakri"`; `test_fallback_sections_excludes_video_and_chakri` fails because `FALLBACK_SECTIONS` still lists both.

- [ ] **Step 3: Remove `video` and `chakri` from `FALLBACK_SECTIONS` and add the exclusion set**

Change:

```python
# Used only if live discovery finds nothing (defensive fallback). Unlike
# Jugantor, Prothom Alo has no separate print-edition site - these are its
# regular web nav categories, discovered from the homepage's #navbar.
FALLBACK_SECTIONS = [
    ("bangladesh", "বাংলাদেশ"),
    ("politics", "রাজনীতি"),
    ("world", "বিশ্ব"),
    ("business", "বাণিজ্য"),
    ("opinion", "মতামত"),
    ("sports", "খেলা"),
    ("entertainment", "বিনোদন"),
    ("chakri", "চাকরি"),
    ("lifestyle", "জীবনযাপন"),
    ("video", "ভিডিও"),
]
```

to:

```python
# Used only if live discovery finds nothing (defensive fallback). Unlike
# Jugantor, Prothom Alo has no separate print-edition site - these are its
# regular web nav categories, discovered from the homepage's #navbar.
# "video" and "chakri" are deliberately excluded here (see
# EXCLUDED_SECTION_SLUGS below) - Kindle can't play video, and job listings
# aren't news narrative the way the rest of the paper is.
FALLBACK_SECTIONS = [
    ("bangladesh", "বাংলাদেশ"),
    ("politics", "রাজনীতি"),
    ("world", "বিশ্ব"),
    ("business", "বাণিজ্য"),
    ("opinion", "মতামত"),
    ("sports", "খেলা"),
    ("entertainment", "বিনোদন"),
    ("lifestyle", "জীবনযাপন"),
]

# Nav categories that are discovered live (via parse_sections) or would
# otherwise appear in FALLBACK_SECTIONS, but don't fit a daily reading
# digest: "video" is a format Kindle can't play (a video-story page's body
# is a player + caption, not prose), and "chakri" (jobs/classifieds) isn't
# news narrative. Same "curated allowlist over generic filter" spirit as
# Dhaka Tribune's CORE_SECTION_SLUGS, expressed as a denylist since only
# two of Prothom Alo's ~10 nav categories need excluding.
EXCLUDED_SECTION_SLUGS = {"video", "chakri"}
```

Update `parse_sections` to apply the exclusion. Change:

```python
    sections = []
    seen_slugs = set()
    for link in container.select("a[href]"):
        href = link["href"]
        if not href.startswith(BASE_URL):
            continue
        path = urlparse(href).path.strip("/")
        # Only single-segment paths are real nav categories; this also
        # naturally excludes /collection/latest, /search, oauth links, etc.
        if not path or "/" in path:
            continue
        if path in seen_slugs:
            continue
        name = _normalize(link.get("aria-label") or link.get_text(strip=True))
        if not name:
            continue
        seen_slugs.add(path)
        sections.append((path, name))

    return sections
```

to:

```python
    sections = []
    seen_slugs = set()
    for link in container.select("a[href]"):
        href = link["href"]
        if not href.startswith(BASE_URL):
            continue
        path = urlparse(href).path.strip("/")
        # Only single-segment paths are real nav categories; this also
        # naturally excludes /collection/latest, /search, oauth links, etc.
        if not path or "/" in path:
            continue
        if path in seen_slugs or path in EXCLUDED_SECTION_SLUGS:
            continue
        name = _normalize(link.get("aria-label") or link.get_text(strip=True))
        if not name:
            continue
        seen_slugs.add(path)
        sections.append((path, name))

    return sections
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_prothomalo_scraper.py -k "excludes_video_and_chakri" -v`
Expected: both PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS (196 tests: 194 + 2 new). Watch especially `test_parse_sections_finds_expected_slugs` and `test_discover_sections_returns_live_parsed_sections` in the same file — they assert `"bangladesh"`/`"sports"` are present, not that `video`/`chakri` are absent, so they should be unaffected, but confirm.

- [ ] **Step 6: Commit**

```bash
git add jugantor_epub/sources/prothomalo.py tests/test_prothomalo_scraper.py
git commit -m "feat: exclude video and chakri sections from Prothom Alo"
```

---

### Task 4: Verify the real-world size reduction

**Files:** none modified — this is a manual verification task, no code changes.

**Interfaces:** none.

- [ ] **Step 1: Run a real local build**

Run: `.venv/bin/python main.py`

This builds all three sources' epubs into `output/` using today's real date, without touching Kindle email or OPDS (both env vars default off locally).

- [ ] **Step 2: Compare Prothom Alo's new epub size and article count against the 2026-08-17 baseline**

Run:
```bash
ls -la output/prothomalo-*.epub
```

Baseline from the failed run (2026-08-17): 410 articles across 10 sections, ~24.5MB. Expected after this plan: 8 sections (video/chakri excluded), each holding only stories published that calendar day — a substantially smaller count and file size. There's no fixed target number (it depends on how much Prothom Alo actually published that day), but it should be in the same rough order of magnitude as Jugantor's ~170 articles / ~3.6MB, not 400+/24MB.

If the size is still disproportionately large, re-check whether `_story_date`'s Asia/Dhaka conversion is being hit for most stories (i.e., the "keep on missing timestamp" fail-open path isn't silently keeping everything) by checking the run's log output for how many `"Story listing missing/invalid published-at, keeping it"` warnings appear per section — one per section is expected/harmless, dozens would indicate the field isn't as reliably present as the fixture suggested, and is worth a follow-up investigation rather than silently living with a partially-effective filter.

- [ ] **Step 3: Confirm the built epub opens correctly**

If `epubcheck` (Java) is available, it already runs as part of `tests/test_epub_builder.py`'s `test_build_epub_passes_epubcheck`, which was included in the Task 1-3 full-suite runs. No separate action needed here beyond noting that test passed.

- [ ] **Step 4: No commit for this task** — it's verification only, not a code change. If Step 2 reveals a problem, stop and re-open Task 2 or Task 3 rather than proceeding.
