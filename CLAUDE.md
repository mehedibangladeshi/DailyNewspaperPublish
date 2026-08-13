# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Setup:
```
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # includes runtime + test deps
```

Run the pipeline (scrapes today's edition, writes `output/jugantor-YYYY-MM-DD.epub`):
```
.venv/bin/python main.py
```

Run tests:
```
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m pytest tests/test_jugantor_scraper.py -v          # one file
.venv/bin/python -m pytest tests/test_jugantor_scraper.py::test_parse_article_extracts_metadata_and_body -v  # one test
.venv/bin/python -m pytest tests/ --cov=jugantor_epub --cov=main --cov-report=term-missing  # coverage
```

The `test_build_epub_passes_epubcheck` test skips itself if no Java runtime is on PATH.

## Architecture

Three-stage pipeline, wired together in `main.py`: **discover → scrape → build**. For each source module listed in `config.SOURCES` (currently just `"jugantor"`), `main.build_source_edition()` calls `discover_sections()` → `list_articles(slug)` per section → `fetch_article(url)` per listed article → `images.download_image()` for each article's image → `epub_builder.build_epub()`.

**Source module contract** (`jugantor_epub/sources/*.py`): each module exposes `discover_sections() -> [(slug, name), ...]`, `list_articles(slug) -> [dict, ...]`, `fetch_article(url) -> dict`, `get_cover_logo_url() -> str`, and a `SOURCE_NAME` string. `main.py` only depends on this shape, imported dynamically via `importlib.import_module(f"jugantor_epub.sources.{name}")` — adding a second newspaper means adding a new module with this same shape and appending its name to `config.SOURCES`; no changes to `main.py` are needed.

**Parsing vs. fetching split**: inside `jugantor_epub/sources/jugantor.py`, each public function (`discover_sections`, `list_articles`, `fetch_article`) is a thin wrapper that does an HTTP GET via the shared `_get()` helper and then delegates to a pure parsing function (`parse_sections(html)`, `parse_articles(html)`, `parse_article(html, url)`). The pure functions take raw HTML/strings and return plain dicts/tuples with no I/O — this is what the test suite exercises directly against saved fixture HTML in `tests/fixtures/`, without hitting the network. Keep this split when touching the scraper: put HTML-shape logic in the `parse_*` functions, keep `_get`/network concerns in the wrapper.

**Error isolation**: failures are contained at the smallest scope that makes sense — one failed article is skipped (`main.build_source_edition`'s per-article try/except), one failed section falls through to the next, one failed source (raises if it scraped zero articles) doesn't stop other sources in `main.main()`'s per-source try/except. Preserve this when adding new failure points; don't let one bad item abort the whole run.

**Bengali text normalization**: the live site mixes Unicode NFC/NFD forms for Bengali nukta characters (e.g. "ড়") across different fields on the same page. All extracted text goes through `_text()` / `_normalize()` helpers in `jugantor.py` which call `unicodedata.normalize("NFC", ...)` — do this for any new text extraction so headline/summary/body strings compare and render consistently.

**JSON-LD parsing quirks**: article pages embed metadata as `<script type="application/ld+json">` (first block on the page is the `NewsArticle` object; a `BreadcrumbList` block usually follows — `select_one` intentionally grabs the first). Two things to keep in mind: (1) it's parsed with `json.loads(..., strict=False)` because some headlines contain a raw literal newline inside a JSON string value, which strict JSON rejects; (2) fields can be *present but explicitly `null`* (not just absent), so code reads them as `metadata.get("headline") or ""` rather than `metadata.get("headline", "")` — the `, default` form only helps when the key is missing entirely.

**Kindle font embedding**: Kindle devices don't ship a Bengali-capable font. `epub_builder.py` embeds `fonts/NotoSansBengali-Regular.ttf` (SIL OFL license) as an `EpubItem` and references it from `style/main.css` via `@font-face`. Note the CSS `url()` path is relative to the stylesheet's own location (`EPUB/style/main.css`), not the epub root — it must be `../fonts/...`, not `fonts/...` (this was a real bug caught by `epubcheck`; the test suite validates the built epub with `epubcheck` when Java is available).

**Image handling**: `main.py` caches `images.download_image()` results by URL within a single source's build (`cached_download_image` closure in `build_source_edition`) since multiple articles often share the same photo — `epub_builder.py` separately dedupes by output filename when writing `EpubImage` items into the book. Both layers matter: the cache avoids redundant downloads/re-encodes, the epub_builder dedup avoids duplicate zip entries.

**Cover generation**: `jugantor_epub/cover.py` renders the epub's cover (fixing the "blank/no cover" look Kindle shows otherwise). `main.build_source_edition()` fetches each source's masthead logo via `source_module.get_cover_logo_url()`, formats the edition date in Bengali via `bengali_date.format_bengali_date()`, and calls `cover.render_cover(source_name, date_text, logo_url)` to composite them onto a 1600×2560 JPEG (white background, brand-red `#c40c13` accent rule under the logo) using `compose_cover()` — a pure function, so it's testable without hitting the network. If the logo fetch/decode fails, `compose_cover()` falls back to rendering `source_name` as text (via the already-embedded Bengali font) instead of aborting the build; the whole cover step is additionally wrapped in a try/except in `main.py` so a totally unexpected rendering failure still doesn't stop a source's build (same error-isolation principle as elsewhere). `epub_builder.build_epub()` takes the resulting bytes as `cover_image_bytes`: it sets them as the epub's library-thumbnail cover via `book.set_cover(..., create_page=False)` (metadata only, no extra full-page cover in the reading flow) and reuses the same image as `title.xhtml`'s content, so the two aren't duplicated in the zip.

## Daily automation & Kindle delivery

Implemented via a GitHub Actions scheduled workflow (`.github/workflows/daily-kindle.yml`, `cron: '0 2 * * *'` = 08:00 BD time) plus `jugantor_epub/email_sender.py`. `main.py` accumulates `(source_name, output_path)` for every source that builds successfully; when `config.SEND_TO_KINDLE` is true (set by the workflow, unset for local runs) it sends one combined email with every built epub attached via `email_sender.send_to_kindle()`. `main()` now exits non-zero when no source produced an edition or the combined send failed, since failure detection relies on GitHub's built-in failed-workflow notification. See `docs/superpowers/specs/2026-08-11-daily-kindle-automation-design.md` for the full design rationale.

**OPDS catalog for non-Kindle e-readers**: alongside the Kindle email, the same workflow run publishes a static OPDS catalog to the `gh-pages` branch (`jugantor_epub/opds_catalog.py` for the pure feed-building logic, `jugantor_epub/opds_publish.py` for the I/O side that reads/writes the `gh-pages` checkout), gated behind `config.PUBLISH_OPDS` the same way Kindle delivery is gated behind `config.SEND_TO_KINDLE`. The catalog is organized by newspaper, not by date: a root `catalog.xml` navigation feed lists one entry per `config.SOURCES` slug, each linking to that source's own `{slug}/feed.xml` acquisition feed holding its last 7 *successfully built* editions — a count, not a calendar window, so a source that skipped a day doesn't lose an entry, it just keeps older news a little longer. `opds_publish.publish_catalog()` copies forward whatever's still within that count from the existing `gh-pages` checkout, physically deletes anything falling out of it, and the workflow republishes the whole `gh-pages` branch from scratch each run (`keep_files: false`, `force_orphan: true`) — so eviction never needs a separate `git rm` step.
