# Ittefaq Kindle-Delivery Size Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ittefaq's Kindle email actually ship, by trimming 4 lower-priority sections and adding a general "retry with more aggressive image compression if the built epub is oversized" tier that applies to any source.

**Architecture:** `jugantor_epub/images.py`'s single `download_image()` (network fetch + JPEG encode in one call) is split into `fetch_raw_image()` (network fetch/decode only) and `encode_image()` (resize/encode only, given explicit `max_width`/`quality`). `main.py`'s `build_source_edition()` caches raw fetched images by URL (as it already did for the old combined result), encodes them once at normal settings, builds the epub, and — only if the output file exceeds `email_sender.GMAIL_MAX_ATTACHMENT_BYTES` — re-encodes the same cached raw images at fallback settings and rebuilds the epub once (no network re-fetch, no loop). Separately, `jugantor_epub/sources/ittefaq.py` drops 4 section slugs from its allowlist.

**Tech Stack:** Python 3, pytest, Pillow (PIL), ebooklib. No new dependencies.

## Global Constraints

- Reuse `email_sender.GMAIL_MAX_ATTACHMENT_BYTES` as the oversized-trigger threshold — do not introduce a second, independently-tunable threshold constant (spec: "the same constant `email_sender.py` already gates sending on, so the trigger and the actual send-skip threshold can't drift apart").
- The retry is a single fallback tier, not a loop — if the rebuilt epub is still oversized, leave it as-is and let `email_sender.py`'s existing size gate skip the send (unchanged behavior).
- A failure during the retry (re-encode or rebuild) must not raise out of `build_source_edition` — catch it, log a warning, and return the original (oversized) epub path, per this codebase's existing error-isolation principle.
- `download_image(url, max_width=..., quality=...)` must keep working as a public function with its existing behavior (used directly by `tests/test_images.py`) — implement it as `fetch_raw_image()` + `encode_image()` composed together, not removed.

---

### Task 1: Trim Ittefaq's section allowlist

**Files:**
- Modify: `jugantor_epub/sources/ittefaq.py:26-78` (`CORE_SECTION_SLUGS`, `FALLBACK_SECTIONS`)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — same `CORE_SECTION_SLUGS: set[str]` and `FALLBACK_SECTIONS: list[tuple[str, str]]` shape, just 4 fewer entries in each.

- [ ] **Step 1: Confirm no existing test pins the removed slugs or a total count**

Run: `grep -n "projonmo\|probash\|campus\|social-media\|len(slugs)" tests/test_ittefaq_scraper.py`
Expected: only the unrelated `len(slugs) == len(set(slugs))` dedup-check line matches; no test asserts these 4 slugs are present or asserts a specific total section count. (Already verified during design — this step is a safety check before editing.)

- [ ] **Step 2: Remove the 4 slugs from `CORE_SECTION_SLUGS`**

In `jugantor_epub/sources/ittefaq.py`, edit the set so it reads:

```python
CORE_SECTION_SLUGS = {
    "national",
    "capital",
    "country",
    "politics",
    "world-news",
    "sports",
    "entertainment",
    "business",
    "tech",
    "education",
    "health",
    "literature",
    "religion",
    "lifestyle",
    "opinion",
    "news",
    "editorial",
    "law-and-court",
    "environment",
}
```

(Removed: `"social-media"`, `"projonmo"`, `"probash"`, `"campus"`.)

- [ ] **Step 3: Remove the matching 4 entries from `FALLBACK_SECTIONS`**

Edit the list so it reads:

```python
FALLBACK_SECTIONS = [
    ("national", "জাতীয়"),
    ("capital", "রাজধানী"),
    ("country", "সারাদেশ"),
    ("politics", "রাজনীতি"),
    ("world-news", "বিশ্ব সংবাদ"),
    ("sports", "খেলা"),
    ("entertainment", "বিনোদন"),
    ("business", "অর্থনীতি"),
    ("tech", "টেক"),
    ("education", "শিক্ষা"),
    ("health", "স্বাস্থ্য"),
    ("literature", "সাহিত্য"),
    ("religion", "ধর্ম"),
    ("lifestyle", "লাইফস্টাইল"),
    ("opinion", "মতামত"),
    ("news", "অন্যান্য"),
    ("editorial", "সম্পাদকীয়"),
    ("law-and-court", "আইন-আদালত"),
    ("environment", "পরিবেশ"),
]
```

(Removed the entries for `social-media`/`projonmo`/`probash`/`campus`, keeping every other tuple in its original order.)

- [ ] **Step 4: Run the Ittefaq test file to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/test_ittefaq_scraper.py -v`
Expected: all tests PASS (they only assert presence of `national`/`sports`/`editorial` and dedup behavior, not the full list or count).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/sources/ittefaq.py
git commit -m "feat: drop 4 lower-priority sections from Ittefaq's allowlist

social-media, projonmo, probash, and campus are dropped to reduce
Ittefaq's article/image count toward fitting Gmail's attachment
limit for Kindle delivery."
```

---

### Task 2: Split `images.py` into raw-fetch and encode steps

**Files:**
- Modify: `jugantor_epub/images.py`
- Test: `tests/test_images.py`

**Interfaces:**
- Consumes: `PIL.Image`, `requests`, `config.REQUEST_TIMEOUT`, `config.IMAGE_MAX_WIDTH`, `config.IMAGE_JPEG_QUALITY` (all already used in this file).
- Produces (for Task 3 to consume):
  - `fetch_raw_image(url: str | None) -> PIL.Image.Image | None` — network fetch + decode + `.convert("RGB")` only, no resize/encode. Returns `None` for a falsy `url`, a request failure, or undecodable content (logs a warning in the latter two cases, same as today).
  - `encode_image(image: PIL.Image.Image, url: str, max_width: int, quality: int) -> tuple[str, bytes]` — resizes if `image.width > max_width` (preserving aspect ratio, `LANCZOS`), encodes as JPEG at `quality`, returns `(filename, jpeg_bytes)` where `filename` is `sha1(url).hexdigest() + ".jpg"`. Does not mutate the passed-in `image` (uses `image.resize(...)`, which returns a new image, not `image.thumbnail(...)`, which would mutate in place) — this matters because the same cached `image` gets encoded twice (normal settings, then fallback settings on retry).
  - `download_image(url, max_width=config.IMAGE_MAX_WIDTH, quality=config.IMAGE_JPEG_QUALITY) -> tuple[str, bytes] | None` — unchanged public behavior, now implemented as `fetch_raw_image` + `encode_image` composed together.

- [ ] **Step 1: Write the failing tests for the new split**

Add to `tests/test_images.py` (after the existing imports/helpers, before the `download_image` tests):

```python
def test_fetch_raw_image_returns_decoded_image(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(_png_bytes(300, 200))
    )

    image = images.fetch_raw_image("https://example.com/pic.png")

    assert image is not None
    assert image.size == (300, 200)


def test_fetch_raw_image_returns_none_for_empty_url():
    assert images.fetch_raw_image("") is None
    assert images.fetch_raw_image(None) is None


def test_fetch_raw_image_returns_none_on_undecodable_content(monkeypatch):
    monkeypatch.setattr(
        images._session, "get", lambda *a, **k: _FakeResponse(b"not an image")
    )

    assert images.fetch_raw_image("https://example.com/broken.jpg") is None


def test_fetch_raw_image_returns_none_on_request_failure(monkeypatch):
    import requests

    def _raise(*a, **k):
        raise requests.RequestException("boom")

    monkeypatch.setattr(images._session, "get", _raise)

    assert images.fetch_raw_image("https://example.com/unreachable.jpg") is None


def test_encode_image_resizes_when_wider_than_max_width():
    image = Image.new("RGB", (1600, 800), color=(200, 50, 50))

    filename, data = images.encode_image(image, "https://example.com/pic.png", max_width=800, quality=75)

    assert filename.endswith(".jpg")
    resized = Image.open(io.BytesIO(data))
    assert resized.width == 800
    assert resized.height == 400


def test_encode_image_leaves_smaller_images_untouched():
    image = Image.new("RGB", (300, 200), color=(200, 50, 50))

    _filename, data = images.encode_image(image, "https://example.com/small.png", max_width=800, quality=75)

    resized = Image.open(io.BytesIO(data))
    assert resized.size == (300, 200)


def test_encode_image_at_lower_quality_produces_smaller_output():
    image = Image.new("RGB", (800, 800), color=(120, 60, 200))

    _f1, high_quality_bytes = images.encode_image(image, "https://x/a.jpg", max_width=800, quality=90)
    _f2, low_quality_bytes = images.encode_image(image, "https://x/a.jpg", max_width=500, quality=40)

    assert len(low_quality_bytes) < len(high_quality_bytes)


def test_encode_image_does_not_mutate_the_passed_in_image():
    image = Image.new("RGB", (1600, 800), color=(200, 50, 50))

    images.encode_image(image, "https://x/a.jpg", max_width=800, quality=75)

    assert image.size == (1600, 800)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_images.py -v`
Expected: FAIL — `AttributeError: module 'jugantor_epub.images' has no attribute 'fetch_raw_image'` (and similarly for `encode_image`).

- [ ] **Step 3: Implement the split in `jugantor_epub/images.py`**

Replace the body of the file from `def download_image(...)` onward with:

```python
def fetch_raw_image(url):
    """Fetch and decode an image, without resizing or re-encoding it.

    Returns a PIL Image, or None if the URL is empty or the image
    couldn't be fetched or decoded.
    """
    if not url:
        return None

    try:
        response = _session.get(url, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        image = image.convert("RGB")
    except (requests.RequestException, OSError) as exc:
        logger.warning("Skipping image %s: %s", url, exc)
        return None

    return image


def encode_image(image, url, max_width, quality):
    """Re-encode an already-decoded image as a size-capped JPEG.

    Does not mutate `image` - callers may encode the same decoded image
    more than once (e.g. at a fallback size/quality on retry).

    Returns (filename, jpeg_bytes).
    """
    if image.width > max_width:
        new_height = round(image.height * (max_width / image.width))
        image = image.resize((max_width, new_height), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)

    filename = f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"
    return filename, buffer.getvalue()


def download_image(url, max_width=config.IMAGE_MAX_WIDTH, quality=config.IMAGE_JPEG_QUALITY):
    """Fetch an image and re-encode it as a size-capped JPEG.

    Returns (filename, jpeg_bytes), or None if the image couldn't be
    fetched or decoded.
    """
    image = fetch_raw_image(url)
    if image is None:
        return None
    return encode_image(image, url, max_width, quality)
```

- [ ] **Step 4: Run all image tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_images.py -v`
Expected: all PASS, including the pre-existing `test_download_image_*` tests (unchanged, still exercising the composed `download_image`).

- [ ] **Step 5: Commit**

```bash
git add jugantor_epub/images.py tests/test_images.py
git commit -m "refactor: split images.download_image into fetch_raw_image + encode_image

Lets a caller re-encode the same already-downloaded image at
different settings without a second network round-trip - needed for
the upcoming oversized-epub retry in main.py."
```

---

### Task 3: Add fallback image config constants

**Files:**
- Modify: `jugantor_epub/config.py:16-17`

**Interfaces:**
- Produces: `config.IMAGE_MAX_WIDTH_FALLBACK: int`, `config.IMAGE_JPEG_QUALITY_FALLBACK: int` — consumed by Task 4.

- [ ] **Step 1: Add the constants**

In `jugantor_epub/config.py`, right after the existing `IMAGE_MAX_WIDTH`/`IMAGE_JPEG_QUALITY` lines:

```python
IMAGE_MAX_WIDTH = 800
IMAGE_JPEG_QUALITY = 75

# Used only as a one-time fallback when a built epub comes in over Gmail's
# attachment limit (see main.py's build_source_edition) - not the default
# for every build.
IMAGE_MAX_WIDTH_FALLBACK = 500
IMAGE_JPEG_QUALITY_FALLBACK = 50
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `.venv/bin/python -c "from jugantor_epub import config; print(config.IMAGE_MAX_WIDTH_FALLBACK, config.IMAGE_JPEG_QUALITY_FALLBACK)"`
Expected: `500 50`

- [ ] **Step 3: Commit**

```bash
git add jugantor_epub/config.py
git commit -m "feat: add fallback image compression settings for oversized epubs"
```

---

### Task 4: Rework `build_source_edition` for raw-image caching and oversized retry

**Files:**
- Modify: `main.py:1-100` (imports, `build_source_edition`)
- Modify: `tests/test_main.py` (existing `images.download_image` mocks, one existing test rewritten, one new test added)

**Interfaces:**
- Consumes: `images.fetch_raw_image(url)`, `images.encode_image(image, url, max_width, quality)` (Task 2), `config.IMAGE_MAX_WIDTH_FALLBACK`/`config.IMAGE_JPEG_QUALITY_FALLBACK` (Task 3), `email_sender.GMAIL_MAX_ATTACHMENT_BYTES` (existing).
- Produces: `build_source_edition(source_module, edition_date, source_slug=None) -> str` — same public signature and return type as today (a file path); internal behavior now includes the retry.

- [ ] **Step 1: Update the 16 simple `images.download_image` mocks in `tests/test_main.py`**

These are call sites that don't care about caching specifics — just that *some* image result comes back. Run this once from the repo root:

```bash
python3 - <<'EOF'
path = "tests/test_main.py"
text = open(path).read()
old = '    monkeypatch.setattr(images, "download_image", lambda *a, **k: ("x.jpg", b"bytes"))\n'
new = (
    '    monkeypatch.setattr(images, "fetch_raw_image", lambda url: "raw")\n'
    '    monkeypatch.setattr(\n'
    '        images, "encode_image", lambda image, url, max_width, quality: ("x.jpg", b"bytes")\n'
    '    )\n'
)
count = text.count(old)
assert count == 16, f"expected 16 occurrences, found {count}"
text = text.replace(old, new)
open(path, "w").write(text)
print("replaced", count)
EOF
```

Expected output: `replaced 16`

- [ ] **Step 2: Rewrite the one existing test that tracks download calls directly**

In `tests/test_main.py`, replace `test_build_source_edition_skips_failed_article_and_caches_image_downloads` (currently defines `fake_download_image` and patches `images.download_image`) with:

```python
def test_build_source_edition_skips_failed_article_and_caches_image_downloads(monkeypatch):
    fetch_calls = []
    encode_calls = []

    def fake_fetch_raw_image(url):
        fetch_calls.append(url)
        return "raw-image"

    def fake_encode_image(image, url, max_width, quality):
        encode_calls.append((image, url, max_width, quality))
        return ("shared.jpg", b"bytes")

    captured = {}

    def fake_build_epub(source_name, edition_date, sections_with_articles, **kwargs):
        captured["sections_with_articles"] = sections_with_articles
        return "/tmp/fake.epub"

    monkeypatch.setattr(images, "fetch_raw_image", fake_fetch_raw_image)
    monkeypatch.setattr(images, "encode_image", fake_encode_image)
    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    output_path = main.build_source_edition(_FakeSourceOk, "2026-08-10")

    assert output_path == "/tmp/fake.epub"
    # the failing article is skipped, leaving 2 of the 3 listed
    articles = captured["sections_with_articles"][0][1]
    assert len(articles) == 2
    # both surviving articles share one image URL - fetched once...
    assert fetch_calls == ["https://img/shared.jpg"]
    # ...but each article is still encoded from the shared cached image
    assert len(encode_calls) == 2
```

- [ ] **Step 3: Run the full main test file to verify it fails only where expected**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `main.build_source_edition` and other code still call `images.download_image`, which the tests no longer patch (they'd either hit `AttributeError` on the now-nonexistent mock target being unused, or, if `images.download_image` still exists as a real function per Task 2, real tests will fail because the code path calls the *real* `fetch_raw_image`/network path since `download_image` itself isn't patched). This is expected at this point — Step 4 fixes `main.py` itself.

- [ ] **Step 4: Implement the raw-cache-and-encode split in `main.py`**

Add `import os` to the top imports if not already present, then replace `build_source_edition` in `main.py` with:

```python
def build_source_edition(source_module, edition_date, source_slug=None):
    sections_with_articles = []
    total_articles = 0
    skipped = 0
    raw_image_cache = {}

    def cached_fetch_raw_image(image_url):
        if image_url not in raw_image_cache:
            raw_image_cache[image_url] = images.fetch_raw_image(image_url)
        return raw_image_cache[image_url]

    for slug, section_name in source_module.discover_sections():
        try:
            listing = source_module.list_articles(slug, edition_date)
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
            raw_image = cached_fetch_raw_image(image_url) if image_url else None

            articles.append(
                {
                    "section_slug": slug,
                    "headline": detail.get("headline") or item.get("headline", ""),
                    "author": detail.get("author", ""),
                    "display_time": item.get("listing_time") or detail.get("date_published", ""),
                    "paragraphs": detail.get("paragraphs") or [],
                    "summary": item.get("summary", ""),
                    "image_url": image_url,
                    "_raw_image": raw_image,
                }
            )

        if articles:
            sections_with_articles.append((section_name, articles))
            total_articles += len(articles)
        logger.info("Section %s: %d article(s)", section_name, len(articles))

    if total_articles == 0:
        raise RuntimeError(f"No articles were scraped for source {source_module.SOURCE_NAME!r}")

    all_articles = [article for _, articles in sections_with_articles for article in articles]
    _encode_article_images(all_articles, config.IMAGE_MAX_WIDTH, config.IMAGE_JPEG_QUALITY)

    try:
        cover_image_bytes = cover.render_cover(
            source_module.SOURCE_NAME,
            source_module.format_date(edition_date),
            source_module.get_cover_logo_url(),
            source_module.COVER_ACCENT_COLOR,
            prepare_logo=getattr(source_module, "prepare_logo_image", None),
        )
    except Exception as exc:
        logger.warning("Could not render cover for %s: %s", source_module.SOURCE_NAME, exc)
        cover_image_bytes = None

    output_path = epub_builder.build_epub(
        source_module.SOURCE_NAME,
        edition_date,
        sections_with_articles,
        source_slug=source_slug,
        cover_image_bytes=cover_image_bytes,
    )

    output_path = _rebuild_if_oversized(
        source_module,
        edition_date,
        sections_with_articles,
        all_articles,
        source_slug,
        cover_image_bytes,
        output_path,
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


def _encode_article_images(articles, max_width, quality):
    for article in articles:
        raw_image = article["_raw_image"]
        if raw_image is not None:
            filename, data = images.encode_image(raw_image, article["image_url"], max_width, quality)
            article["image_filename"] = filename
            article["image_bytes"] = data
        else:
            article["image_filename"] = None
            article["image_bytes"] = None


def _rebuild_if_oversized(
    source_module, edition_date, sections_with_articles, all_articles, source_slug, cover_image_bytes, output_path
):
    try:
        size = os.path.getsize(output_path)
    except OSError:
        return output_path

    if size <= email_sender.GMAIL_MAX_ATTACHMENT_BYTES:
        return output_path

    logger.info(
        "%s built oversized (%d bytes over %d); re-encoding images at fallback settings and rebuilding",
        source_module.SOURCE_NAME,
        size,
        email_sender.GMAIL_MAX_ATTACHMENT_BYTES,
    )
    try:
        _encode_article_images(all_articles, config.IMAGE_MAX_WIDTH_FALLBACK, config.IMAGE_JPEG_QUALITY_FALLBACK)
        output_path = epub_builder.build_epub(
            source_module.SOURCE_NAME,
            edition_date,
            sections_with_articles,
            source_slug=source_slug,
            cover_image_bytes=cover_image_bytes,
        )
    except Exception as exc:
        logger.warning(
            "Could not rebuild %s with fallback image settings, keeping oversized build: %s",
            source_module.SOURCE_NAME,
            exc,
        )

    return output_path
```

Note `_encode_article_images` mutates the same article dicts already referenced inside `sections_with_articles` (via the `all_articles` list built from it), so the retry's `epub_builder.build_epub()` call automatically picks up the newly-encoded `image_filename`/`image_bytes` without needing to reconstruct `sections_with_articles`.

- [ ] **Step 5: Run the full main test file to verify the existing suite passes**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: all PASS. (The fake `epub_builder.build_epub` mocks in most tests return non-existent paths like `"/tmp/x.epub"`; `os.path.getsize` raises `FileNotFoundError`, caught by `_rebuild_if_oversized`'s `except OSError`, so no retry fires and behavior is unchanged from before this task.)

- [ ] **Step 6: Write the failing test for the retry path itself**

Add to `tests/test_main.py`:

```python
def test_build_source_edition_rebuilds_with_fallback_settings_when_oversized(monkeypatch, tmp_path):
    monkeypatch.setattr(main.email_sender, "GMAIL_MAX_ATTACHMENT_BYTES", 5)

    build_settings = []
    fetch_calls = []

    def fake_build_epub(source_name, edition_date, sections_with_articles, **kwargs):
        path = tmp_path / "fake.epub"
        path.write_bytes(b"x" * 100)  # always "oversized" against the 5-byte threshold
        build_settings.append(sections_with_articles[0][1][0]["image_bytes"])
        return str(path)

    def fake_fetch_raw_image(url):
        fetch_calls.append(url)
        return "raw-image"

    def fake_encode_image(image, url, max_width, quality):
        return ("shared.jpg", f"{max_width}-{quality}".encode())

    monkeypatch.setattr(images, "fetch_raw_image", fake_fetch_raw_image)
    monkeypatch.setattr(images, "encode_image", fake_encode_image)
    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    output_path = main.build_source_edition(_FakeSourceOk, "2026-08-10")

    assert output_path == str(tmp_path / "fake.epub")
    # the shared image URL is fetched once total, including across the retry -
    # no second network round-trip for the fallback-settings rebuild
    assert fetch_calls == ["https://img/shared.jpg"]
    assert build_settings == [
        f"{main.config.IMAGE_MAX_WIDTH}-{main.config.IMAGE_JPEG_QUALITY}".encode(),
        f"{main.config.IMAGE_MAX_WIDTH_FALLBACK}-{main.config.IMAGE_JPEG_QUALITY_FALLBACK}".encode(),
    ]


def test_build_source_edition_keeps_oversized_build_if_retry_rebuild_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(main.email_sender, "GMAIL_MAX_ATTACHMENT_BYTES", 5)

    build_calls = {"n": 0}
    encode_calls = {"n": 0}

    def fake_build_epub(source_name, edition_date, sections_with_articles, **kwargs):
        build_calls["n"] += 1
        path = tmp_path / "fake.epub"
        path.write_bytes(b"x" * 100)  # always "oversized" against the 5-byte threshold
        return str(path)

    def _encode_image(image, url, max_width, quality):
        # first call is the normal-settings pass inside build_source_edition
        # itself, which must succeed so there's an oversized build to retry;
        # the retry's fallback-settings pass is what fails.
        encode_calls["n"] += 1
        if encode_calls["n"] == 1:
            return ("shared.jpg", b"bytes")
        raise RuntimeError("encode exploded")

    monkeypatch.setattr(images, "fetch_raw_image", lambda url: "raw-image")
    monkeypatch.setattr(images, "encode_image", _encode_image)
    monkeypatch.setattr(epub_builder, "build_epub", fake_build_epub)

    output_path = main.build_source_edition(_FakeSourceOk, "2026-08-10")

    assert output_path == str(tmp_path / "fake.epub")
    assert build_calls["n"] == 1  # the retry's rebuild never happened - encode blew up first
```

- [ ] **Step 7: Run the two new tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_main.py -k "oversized" -v`
Expected: both PASS — Step 4 already implemented `build_source_edition`/`_rebuild_if_oversized`, so these tests exercise existing code rather than driving new code.

- [ ] **Step 8: Run the entire test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: retry with fallback image compression when a built epub is oversized

build_source_edition now caches raw (undecoded-into-JPEG) images per
URL, encodes them once at normal settings, and - only if the result
exceeds email_sender.GMAIL_MAX_ATTACHMENT_BYTES - re-encodes the same
cached images at config.IMAGE_MAX_WIDTH_FALLBACK/
IMAGE_JPEG_QUALITY_FALLBACK and rebuilds once. Applies to any source,
not just Ittefaq. A failure during the retry keeps the original build
rather than aborting."
```

---

### Task 5: Update documentation and clean up the investigation handoff

**Files:**
- Modify: `CLAUDE.md` (Image handling section)
- Modify: `CONTEXT.md` (Ittefaq entry)
- Delete: `HANDOFF.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `CLAUDE.md`'s "Image handling" paragraph**

Find the existing paragraph (search for `**Image handling**:`) and replace it with:

```markdown
**Image handling**: `jugantor_epub/images.py` splits fetching from encoding: `fetch_raw_image(url)` does the network GET + decode only, `encode_image(image, url, max_width, quality)` does the resize/JPEG-encode only, and `download_image(url, max_width=..., quality=...)` composes both for the common case. `main.py` caches `fetch_raw_image()` results by URL within a single source's build (`cached_fetch_raw_image` closure in `build_source_edition`) since multiple articles often share the same photo; `epub_builder.py` separately dedupes by output filename when writing `EpubImage` items into the book. Both layers matter: the cache avoids redundant downloads, the epub_builder dedup avoids duplicate zip entries. If the built epub exceeds `email_sender.GMAIL_MAX_ATTACHMENT_BYTES`, `build_source_edition` re-encodes every article's already-cached raw image at `config.IMAGE_MAX_WIDTH_FALLBACK`/`IMAGE_JPEG_QUALITY_FALLBACK` and rebuilds the epub once (no second network fetch, no loop) — this is what makes it possible for a source like Ittefaq (22 sections, ~440 articles) to still fit under Gmail's attachment limit most days.
```

- [ ] **Step 2: Update `CONTEXT.md`'s Ittefaq entry**

Find the line (search for `A full day's edition (22 sections`) and replace the bullet with:

```markdown
- **A full day's edition (18 sections after trimming `social-media`/`projonmo`/`probash`/`campus`, previously 22) built ~20MB locally with default image settings**, over `email_sender.py`'s effective Gmail-safe attachment threshold (`GMAIL_MAX_ATTACHMENT_BYTES` ≈ 17.5MB). Fixed 2026-08-24 by trimming those 4 lower-priority sections and adding a general oversized-epub retry in `main.py` that re-encodes images at `config.IMAGE_MAX_WIDTH_FALLBACK`/`IMAGE_JPEG_QUALITY_FALLBACK` and rebuilds once (see `docs/superpowers/specs/2026-08-24-ittefaq-size-reduction-design.md`) — applies to any source that comes in oversized, not just Ittefaq. Not skipped by OPDS publishing, which has no size gate and never was.
```

- [ ] **Step 3: Delete the transient handoff doc**

```bash
rm HANDOFF.md
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md CONTEXT.md
git rm HANDOFF.md
git commit -m "docs: update image-handling and Ittefaq docs for the size-reduction fix

Also removes the transient investigation handoff now that the
decision it was written for has shipped."
```

---

## Final verification

- [ ] Run `.venv/bin/python -m pytest tests/ -v` once more at the end and confirm a fully green suite.
- [ ] Run `.venv/bin/python main.py --source ittefaq` locally (requires network) and check the logged line for `Built ইত্তেফাক: ...` plus the resulting `output/ittefaq-YYYY-MM-DD.epub` file size — confirm it's now comfortably under ~17.5MB, or that a "re-encoding images at fallback settings" log line appeared and the rebuilt file is.
