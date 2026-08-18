# Newspapers → Kindle EPUB

Scrapes daily newspapers' web editions and builds a Kindle-ready `.epub` for
each — organized by section (front page, sports, editorial, etc.), one
article per page, with images and a properly embedded Bengali font (Noto
Sans Bengali, SIL OFL) so Bengali text renders correctly on-device. Currently
covers [Jugantor](https://www.jugantor.com/todays-paper),
[Prothom Alo](https://www.prothomalo.com), and
[Dhaka Tribune](https://www.dhakatribune.com) (English); each is a separate
epub built from its own source module.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```
.venv/bin/python main.py
```

This scrapes today's edition of every source in `config.SOURCES` and writes one
`output/{slug}-YYYY-MM-DD.epub` per source (e.g. `output/jugantor-YYYY-MM-DD.epub`,
`output/prothomalo-YYYY-MM-DD.epub`, `output/dhakatribune-YYYY-MM-DD.epub`).
Transfer those files to your Kindle (USB, or drag-and-drop into the
Send-to-Kindle app / kindle.com library).

## Project layout

- `jugantor_epub/sources/jugantor.py` — scraping logic for jugantor.com (section
  discovery, article listing, article detail + metadata).
- `jugantor_epub/sources/prothomalo.py` — scraping logic for prothomalo.com,
  independent from Jugantor's (different site architecture: category pages
  instead of a print-edition text site, listing data from an embedded JSON
  blob instead of DOM cards).
- `jugantor_epub/sources/dhakatribune.py` — scraping logic for
  dhakatribune.com, the first English-language source. DOM-card listings
  (closer to Jugantor's approach) but a curated section allowlist, since its
  nav is a full mega-menu rather than a flat category list.
- `jugantor_epub/sources/text_utils.py` — paper-agnostic NFC
  Unicode-normalization helpers, shared by every source module.
- `jugantor_epub/sources/ld_json.py` — selects a `<script
  type="application/ld+json">` block by its schema.org `@type`; several
  sites bury the useful block behind an unrelated one, so "take the first
  block" isn't safe in general.
- `jugantor_epub/images.py` — downloads and resizes article images.
- `jugantor_epub/cover.py` — renders the epub's cover image (masthead logo +
  edition date on a branded background), with a text-only fallback if the
  logo can't be fetched. Accent color, logo URL, an optional logo-cleanup
  hook, and the date formatter are all supplied per source.
- `jugantor_epub/bengali_date.py` / `jugantor_epub/english_date.py` — format
  an ISO date as a Bengali or English display string; each source module
  picks whichever matches its own language via `format_date()`.
- `jugantor_epub/epub_builder.py` — assembles the scraped content into an epub
  via `ebooklib`, embedding the Bengali font and the cover.
- `jugantor_epub/config.py` — tunables (output dir, request delay, image size,
  the list of enabled sources).
- `jugantor_epub/opds_catalog.py` — pure functions that build the OPDS
  catalog XML (per-newspaper retention, feed rendering) from filenames and
  dates, no I/O.
- `jugantor_epub/opds_publish.py` — reads/writes the `gh-pages` checkout,
  calling into `opds_catalog.py` to decide what to keep, evict, and render.
- `main.py` — CLI entrypoint; runs the full pipeline for every source listed in
  `config.SOURCES`.

## Adding another newspaper

Add a new module under `jugantor_epub/sources/` exposing the same functions as
the existing sources (`discover_sections()`, `list_articles(slug, edition_date)`,
`fetch_article(url)`, `get_cover_logo_url()`, `format_date(edition_date)`,
plus `SOURCE_NAME` and `COVER_ACCENT_COLOR` constants), then add its module
name to `config.SOURCES`. `main.py` already loops over that list, so no other
code changes are needed. Keep each newspaper's parsing logic in its own
module — only pull genuinely paper-agnostic code (like `text_utils.py`,
`ld_json.py`, the date formatters) into a shared file. See
`.claude/skills/add-news-source/` for the step-by-step process this project
uses to research and add a new source.

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

## OPDS catalog (for Boox / KOReader / other OPDS-capable readers)

The same daily workflow also publishes a static OPDS catalog to GitHub
Pages at `https://mehedibangladeshi.github.io/DailyNewspaperPublish/catalog.xml`.
Add that URL to any OPDS-capable reader app (KOReader, Moon+ Reader, etc.)
to browse and download editions directly — no email step needed. Each
configured newspaper gets its own feed holding its last 7 editions (by
count, not calendar days). This is independent of Kindle delivery above —
Kindle's stock firmware has no OPDS client, so email remains the way
editions reach a Kindle.

One-time manual step (can't be automated): enable GitHub Pages for this repo — Settings → Pages → Source: "Deploy from a branch" → select `gh-pages` / `/ (root)`. Until this is done, the catalog URL above will 404.

### Testing the catalog after a fresh push

Pushing to `main` doesn't publish anything by itself — it just updates the
workflow's code. To actually see the catalog live:

1. Trigger the workflow once by hand: Actions tab → "Daily Kindle edition" →
   "Run workflow" (or `gh workflow run daily-kindle.yml`). This is what
   builds the `gh-pages` branch for the first time — don't wait for the
   next 08:00 BD scheduled run.
2. Enable GitHub Pages (above), if you haven't already.
3. Open `https://mehedibangladeshi.github.io/DailyNewspaperPublish/catalog.xml`
   in a browser to see the raw feed, or add that same URL as an OPDS
   catalog in KOReader / Moon+ Reader.

Re-running the workflow again later the same day is safe to do repeatedly
while testing — `main.py` always rebuilds `output/{slug}-{date}.epub` from
a fresh scrape, and the OPDS publish step always replaces that day's
already-published copy with the latest rebuild (rather than keeping
whichever version was published first). Note this also re-sends the
Kindle email each time, since that's a separate, unrelated side effect of
the same run.
