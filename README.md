# Jugantor Todays-Paper → Kindle EPUB

Scrapes the Bengali daily newspaper [Jugantor](https://www.jugantor.com/todays-paper)'s
web edition and builds a Kindle-ready `.epub` of the day's paper — organized by
section (front page, sports, editorial, etc.), one article per page, with images
and a properly embedded Bengali font (Noto Sans Bengali, SIL OFL) so the text
renders correctly on-device.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```
.venv/bin/python main.py
```

This scrapes today's edition and writes `output/jugantor-YYYY-MM-DD.epub`.
Transfer that file to your Kindle (USB, or drag-and-drop into the Send-to-Kindle
app / kindle.com library).

## Project layout

- `jugantor_epub/sources/jugantor.py` — scraping logic for jugantor.com (section
  discovery, article listing, article detail + metadata).
- `jugantor_epub/images.py` — downloads and resizes article images.
- `jugantor_epub/cover.py` — renders the epub's cover image (masthead logo +
  edition date on a branded background), with a text-only fallback if the
  logo can't be fetched.
- `jugantor_epub/bengali_date.py` — formats an ISO date as Bengali digits +
  month name, used on the cover and title page.
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

## Adding another newspaper later

Add a new module under `jugantor_epub/sources/` exposing the same functions as
`jugantor.py` (`discover_sections()`, `list_articles(slug)`, `fetch_article(url)`,
`get_cover_logo_url()`, plus a `SOURCE_NAME` constant), then add its module name
to `config.SOURCES`. `main.py` already loops over that list, so no other code
changes are needed.

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
