---
name: add-news-source
description: Add a new Bengali (or other) newspaper as an independent scraper source in this epub pipeline - researches the target site, asks clarifying questions, writes the source module + tests + fixtures, offers a few epub-cover design options via a published Artifact, updates docs, and verifies with a real build. Use when the user says "/add-news-source <newspaper>", "add another newspaper", "add <name> as a new source", or wants to extend jugantor_epub/sources/ with a new paper.
---

# Add News Source

Args: `<newspaper name or slug>` and optional free-text context (a URL, known quirks, "it has a paywall", etc). If the newspaper's official site URL isn't given, find it yourself before starting Phase 1.

This retraces how Prothom Alo was added alongside Jugantor. Read
[REFERENCE.md](REFERENCE.md) for the concrete techniques (curl/python
snippets for detecting CMS shape, the exact source-module contract, the
existing test taxonomy) before starting - don't rediscover them from scratch.

## Principles (apply throughout)

- **Each newspaper is a fully separate module and a fully separate epub.** Only pull code into a shared file (like `jugantor_epub/sources/text_utils.py`) when it is genuinely paper-agnostic (Unicode normalization, generic HTTP helpers) - never share parsing/selector logic between papers.
- **Ask, don't assume**, whenever there's a real tradeoff with no obviously-correct answer (section scope, premium-article handling, accent color, cover style). Use `AskUserQuestion` with a recommended option first. Don't ask about things you can just determine from research.
- Read the existing `jugantor_epub/sources/*.py` modules and `CONTEXT.md`/`CLAUDE.md` first - they document the contract and the project's accumulated quirks.

## Phases

### 1. Research the live site

Explore the target site's real HTML/JSON (curl + python, not guesswork) to answer, concretely, before writing any code:
- Is there a real text-based "print edition" / section-listing site, or only regular web categories, or (worse) an image/PDF-scan e-paper that's unusable for text extraction?
- How is the article *listing* rendered: server-rendered DOM cards (scrape with BeautifulSoup selectors), or client-hydrated JSON embedded in a `<script>` tag (parse that JSON instead - see REFERENCE.md for how to spot this)?
- How is the article *detail* page structured: `ld+json` blocks (which `@type` holds the real metadata - is it really the first block?), DOM body selectors, any JSON quirks (raw newlines, explicit nulls, author as list vs dict vs string)?
- Is there a paywall/premium flag to detect and skip?
- What masthead logo asset is available - is it a plain raster image PIL can open, or only SVG (PIL can't decode SVGs - find a PNG/JPEG alternative, e.g. `og:image`, and verify it actually decodes)?

See [REFERENCE.md](REFERENCE.md) for the exact probing commands.

### 2. Resolve open design decisions

Ask via `AskUserQuestion`, one question at a time, only for things Phase 1 couldn't settle on its own - typically: which sections/categories to include, how to handle premium articles, and (if the logo needs cleanup) how much of a redesign the cover deserves. Give a recommendation, not just options.

### 3. Implement the source module

Create `jugantor_epub/sources/<slug>.py` implementing the full contract (see REFERENCE.md): `discover_sections`, `list_articles`, `fetch_article`, `get_cover_logo_url`, `SOURCE_NAME`, `COVER_ACCENT_COLOR`, `FALLBACK_SECTIONS`, plus `prepare_logo_image` if the logo asset needs cropping/cleanup before compositing. Add the new slug to `jugantor_epub/config.SOURCES`.

### 4. Offer cover design options

Render 2-3 structurally different cover variants using the real `jugantor_epub.cover.compose_cover` (don't hand-roll a duplicate renderer), embed them as a self-contained HTML page (base64 images, favicon emoji, see the artifact-design skill), publish it with the `Artifact` tool, and ask which direction to implement for real before touching `cover.py`.

### 5. Tests and fixtures

Mirror the existing test taxonomy exactly (`tests/test_jugantor_scraper.py` / `tests/test_prothomalo_scraper.py`): happy-path tests against small, trimmed *real* fixtures under `tests/fixtures/`, plus hand-crafted inline HTML/JSON for every edge case found in Phase 1. Update `tests/test_main.py` fakes and `tests/test_cover.py` if the shared contract changed. Run the full suite with coverage; the new module should land at ~100%.

### 6. Update docs

Update `CONTEXT.md` (a new "Known site quirks" subsection for this paper, and the Purpose/deferred-work framing if it's no longer accurate) and `README.md` (project layout, "Adding another newspaper" section) the same way the Prothom Alo diff did.

### 7. Verify end-to-end

Run the real pipeline for just the new source against the live site (temporarily limit to one section first if it's slow), confirm the epub builds, run `epubcheck` if Java is available, and hand the built epub to the user.
