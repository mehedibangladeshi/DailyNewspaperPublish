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
- `jugantor_epub/epub_builder.py` — assembles the scraped content into an epub
  via `ebooklib`, embedding the Bengali font.
- `jugantor_epub/config.py` — tunables (output dir, request delay, image size,
  the list of enabled sources).
- `main.py` — CLI entrypoint; runs the full pipeline for every source listed in
  `config.SOURCES`.

## Adding another newspaper later

Add a new module under `jugantor_epub/sources/` exposing the same three
functions as `jugantor.py` (`discover_sections()`, `list_articles(slug)`,
`fetch_article(url)`, plus a `SOURCE_NAME` constant), then add its module name
to `config.SOURCES`. `main.py` already loops over that list, so no other code
changes are needed.

## Not implemented yet (deferred)

- Daily automation (cron/launchd) — `main.py` takes no arguments and does one
  full run, so it's schedule-ready as-is; just needs an OS-level cron entry.
- Auto-email to a Kindle `@kindle.com` Send-to-Kindle address.
