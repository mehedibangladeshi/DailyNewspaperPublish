# Reference: adding a news source

Concrete techniques from adding Prothom Alo alongside Jugantor. Adapt, don't
copy blindly - every site is a little different.

## 1. Research commands

Use the scratchpad directory for fetched HTML, never the repo. A plain
`curl` (no headless browser) is enough for almost every Bangladeshi news
site seen so far; add `-A "Mozilla/5.0 ..."` and `--compressed`.

```bash
SP=<your scratchpad dir>
curl -s --compressed -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "https://example-newspaper.com/" -o "$SP/home.html" -w "HTTP %{http_code}, size %{size_download}\n"
```

If `curl` returns `size 0` with a 200, retry with `--compressed` explicitly
or check for a Cloudflare challenge in the headers (`curl -sv ... -o /dev/null`).

**Is there a real print-edition text site, or only web categories, or an
unusable image e-paper?** Check the homepage nav for an "epaper"/"e-paper"
link; fetch it and grep for `.jpg`/`iframe`/`flipbook` - if those dominate,
it's a scanned-image flipbook, not usable for text extraction, and you
should scrape the regular web category pages instead (discovered from the
homepage's nav container, same pattern as Jugantor's `/todays-paper` vs
Prothom Alo's plain `/bangladesh`, `/sports`, etc.).

**DOM cards vs embedded JSON listing** - grep the fetched section/category
page for real per-article `<a href>` links matching an article URL pattern.
If none show up in the raw HTML (only nav links), the site is a JS-hydrated
SPA and the actual listing lives in an embedded JSON blob instead:

```bash
grep -oE '<script[^>]*id="[^"]*"' "$SP/section.html" | sort -u
grep -oE 'window\.__[A-Za-z_]+' "$SP/section.html" | sort -u
```

Common CMS fingerprints: a `<script type="application/json" id="static-page">`
or similar blob (Quintype CMS - Bengali/Indian papers including Prothom Alo
use this), a Next.js `__NEXT_DATA__` script, or a `window.__INITIAL_STATE__`
global. Once found, extract and `json.loads()` it, then write a small
recursive walker to collect the real per-article nodes (dedupe by URL - the
same story commonly appears under more than one listing widget in these
trees).

**Article detail page** - check every `<script type="application/ld+json">`
block's `@type`, don't assume the first one is the useful one:

```python
import re, json
blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
for b in blocks:
    d = json.loads(b, strict=False)
    print(d.get("@type"), list(d.keys()))
```

Jugantor's first block is always `NewsArticle`. Prothom Alo's first block
is `BreadcrumbList` - the real metadata is a later block, found by checking
`@type == "NewsArticle"` explicitly. Also check the shape of `author` (a
dict, a list of dicts, or a bare string - handle all three defensively) and
whether fields can be explicitly JSON `null` (not just absent - use
`metadata.get(key) or default`, never `metadata.get(key, default)`).

For the body, prefer a stable DOM selector over unescaping `articleBody`
out of the JSON-LD (double-unescaping HTML-in-JSON is messier); verify the
selector by counting matches against the ld+json `articleBody`'s paragraph
count.

**Masthead logo** - fetch the candidate URL and open it with PIL:

```python
from PIL import Image
im = Image.open(io.BytesIO(fetched_bytes))
print(im.size, im.mode)
```

If the only asset is `.svg`, PIL can't decode it - look for `og:image`,
`apple-touch-icon`, or a favicon PNG instead, and verify it actually opens
before using it. If the found asset is a banner with baked-in extra text
(a subtitle, a big decorative graphic) rather than a tight wordmark, crop
it down (see "Cover cleanup hook" below) rather than pasting it as-is.

**Accent color** - if the paper's brand color isn't already known, sample a
pixel from its logo:

```python
im.convert("RGB").getpixel((x, y))
```

**Premium/paywall detection** - look for an `isAccessibleForFree` (or
similar) field in the ld+json metadata, or an `access`/`subscription` field
in the listing JSON. If found, ask the user (Phase 2) whether to skip such
articles (raise from `fetch_article`, letting `main.py`'s existing
per-article `try/except` skip them) or include them best-effort.

## 2. Source module contract

Every module under `jugantor_epub/sources/` must expose:

```python
SOURCE_NAME = "..."              # display name (e.g. Bengali paper name)
COVER_ACCENT_COLOR = (r, g, b)   # used for the cover's accent rule
FALLBACK_SECTIONS = [(slug, name), ...]  # defensive fallback list

def discover_sections() -> list[(slug, name)]: ...
def list_articles(slug) -> list[dict]: ...        # keys: url, headline, summary, listing_time, thumbnail
def fetch_article(url) -> dict: ...               # keys: url, headline, author, date_published, image_url, paragraphs
def get_cover_logo_url() -> str: ...
```

Optional: `def prepare_logo_image(image: PIL.Image) -> PIL.Image` - called
by `cover.render_cover` on the freshly-fetched logo before compositing, if
the source's own logo asset needs cropping/background-cleanup (see Prothom
Alo's implementation for the pattern: crop to a fixed box, then make a
near-white background transparent by per-pixel threshold).

Keep the same **parse/fetch split** as the existing modules: a thin
`fetch_article(url)`/`list_articles(slug)`/`discover_sections()` wrapper
that does the HTTP GET via a shared `_get()` helper, delegating to a pure
`parse_article(html, url)`/`parse_articles(html)`/`parse_sections(html)`
function that takes raw HTML/JSON and returns plain dicts - this is what
the test suite exercises directly against fixtures, without network access.

Use `from .text_utils import extract_text as _text, normalize_text as
_normalize` for NFC Unicode normalization - don't redefine these per module.

Add the new module's slug to `jugantor_epub/config.SOURCES`.

## 3. Cover design picker

Render variants with the real renderer, not a reimplementation:

```python
from jugantor_epub import cover
img_bytes = cover.render_cover(source_name, date_text, logo_url, accent_color, prepare_logo=...)
```

or call `cover.compose_cover(logo_image, source_name, date_text, accent_color)`
directly against a locally-fetched/prepared logo image for faster iteration
without a network round trip per render.

Base64-embed each JPEG into a single self-contained HTML file (no external
image URLs - the Artifact CSP blocks them), load the `artifact-design` skill
before writing it, then publish with the `Artifact` tool and share the link.
A simple grid of thumbnails with a click-to-enlarge lightbox has worked well
here - no need for anything fancier for a one-off design comparison.

Wait for the user's choice via a follow-up message or `AskUserQuestion`
before touching `cover.py`/the source module for real.

If the chosen design needs `cover.py` changes shared by *all* sources
(e.g. dynamic logo/rule/date layout instead of fixed pixel offsets), verify
the change is calibrated to produce **pixel-identical output for existing
sources** - add a regression test asserting this using each existing
source's real logo dimensions, the same way Jugantor's 500x109 logo was
checked after the layout became dynamic for Prothom Alo's taller logo.

## 4. Test taxonomy to mirror

From `tests/test_jugantor_scraper.py` / `tests/test_prothomalo_scraper.py`:

- `parse_sections`: finds expected slugs, dedupes, skips nameless links, returns `[]` on unrelated HTML, excludes non-category links (multi-segment paths, off-site links, etc. - whatever this site's nav includes beyond real categories).
- `discover_sections`: falls back to `FALLBACK_SECTIONS` on request failure and on empty parse; returns live-parsed sections against a fixture.
- `_get`: performs the HTTP request via the shared session with the rate-limit sleep.
- `list_articles`/`parse_articles`: fetches then parses; extracts real fields from a fixture; dedupes (if the site's listing structure can repeat entries); handles missing thumbnail/hero-image; handles malformed/missing listing data gracefully (`[]`, not a crash).
- `fetch_article`/`parse_article`: fetches then parses; extracts full metadata + body from a fixture; regression tests for every JSON-LD quirk found in Phase 1 (explicit nulls, invalid JSON syntax, plain-string vs dict vs list author/image, missing ld+json entirely, wrong-block-is-first); premium-article skip if applicable.
- `get_cover_logo_url`: returns the expected constant.
- If you added `prepare_logo_image`: crops to the expected box, makes the expected background transparent, leaves non-background pixels opaque.

Fixtures: trim real fetched pages/JSON down to ~10-250KB (strip ad/analytics
scripts and unrelated JSON fields, keep the exact structures the parser
depends on) rather than committing multi-MB raw responses.

## 5. Docs to update

- `CONTEXT.md`: add a "### <Paper>" subsection under "Known site quirks worth remembering" documenting what Phase 1 found; update the "Purpose" line and any "one newspaper only" / deferred-work wording that's no longer accurate.
- `README.md`: project layout list (new module + one-line description of what's structurally different from existing sources), and the "Adding another newspaper" section if the contract gained a new optional piece (like `prepare_logo_image`).

## 6. End-to-end verification

```bash
.venv/bin/python -m pytest tests/ --cov=jugantor_epub --cov=main --cov-report=term-missing -q
```

Then a real build. For a faster smoke test before committing to a full run,
monkeypatch `discover_sections` down to one section:

```python
from datetime import date
import main
from jugantor_epub.sources import <slug> as mod
mod.discover_sections = lambda: [mod.FALLBACK_SECTIONS[0]]
main.build_source_edition(mod, date.today().isoformat(), source_slug="<slug>")
```

Run `epubcheck` against the real output if Java is available (`shutil.which("java")`):

```python
from epubcheck import EpubCheck
result = EpubCheck("output/<slug>-<date>.epub")
print(result.valid, result.messages)
```

Once satisfied, run the full (unrestricted) `main.py` for the real daily
build and deliver the epub to the user.
