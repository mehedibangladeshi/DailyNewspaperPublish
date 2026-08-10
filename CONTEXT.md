# Context

## Purpose

A personal tool that scrapes the Bengali daily newspaper [Jugantor](https://www.jugantor.com/todays-paper)'s web edition and packages it into a Kindle-ready `.epub`, organized the same way the print/web edition is — by section (front page, sports, editorial, etc.), one article per page.

## Why this exists

The newspaper publishes its daily edition as a set of article-listing pages rather than a downloadable format, so reading it comfortably on an e-ink Kindle (rather than a phone browser) requires converting it. This is a from-scratch personal project — not built on an existing codebase.

## Key decisions and why

- **Python, not Node.js** — good scraping/imaging/epub library support (`requests`+`BeautifulSoup`, `Pillow`, `ebooklib`).
- **Scrape HTML directly, no API** — the site is server-rendered with no anti-bot wall encountered during research; no API was found or needed. Article metadata comes from clean `<script type="application/ld+json">` blocks embedded in each article page, which is more reliable than parsing visible HTML for headline/author/date.
- **All sections, with images, today's date only** — chosen to match "the full daily edition" reading experience over a trimmed-down digest. Historical/back-issue support (the site supports a `?date=` query param) and a curated-subset mode were both explicitly deferred rather than built speculatively.
- **Embed a Bengali font in the epub** — Kindle devices have no built-in Bengali-capable font, so without embedding one, all Bengali text would render as blank boxes on-device. Noto Sans Bengali (SIL OFL) was chosen as a freely-redistributable open font.
- **Local file output only, manual run only, one newspaper only (for now)** — see "Deferred work" below. The code is structured to make each of these additive later rather than a rewrite.
- **Local git identity: `Mehedi Hasan <mehedipy@gmail.com>`, not the work email** — this repo pushes to a personal GitHub account (`git@personal.github.com:mehedibangladeshi/DailyNewspaperPublish.git`, matching the existing `personal.github.com` SSH host alias used by other personal repos like `ai-skills`), so the commit identity is scoped to match, distinct from the global work-email default used elsewhere on this machine.

## Architecture summary

See `CLAUDE.md` for the details future coding sessions need (commands, the parse/fetch split, error-isolation pattern, Unicode normalization gotcha, JSON-LD parsing quirks, font-embedding bug history). In short: `main.py` orchestrates a discover → scrape → build pipeline over source modules listed in `jugantor_epub/config.SOURCES`; each source module under `jugantor_epub/sources/` implements a small three-function contract so more newspapers can be added later without touching `main.py`.

## Known site quirks worth remembering

Found during initial scraping research and while fixing a code review pass — not obvious from reading the code alone:

- Some article pages embed a **raw literal newline inside a JSON string value** in their `ld+json` block (e.g. a multi-line headline), which breaks strict JSON parsing. Handled via `json.loads(..., strict=False)`.
- `ld+json` fields (headline, author, image) can be **present but explicitly `null`**, not merely absent — `dict.get(key, default)` doesn't catch that case; code must use `dict.get(key) or default`.
- The site **mixes NFC/NFD Unicode normalization** for Bengali nukta characters (e.g. "ড়") across different fields on the same page — text is normalized to NFC on extraction for consistent comparison/rendering.
- At least one observed image URL from the site's own data contained an unencoded `'` producing a broken CDN path — this fails gracefully (image skipped, article still included) rather than being treated as a code bug.

## Deferred work (explicitly out of scope for now)

Flagged by the user as follow-ups, structurally supported but not built:
- **More newspapers** — add a module under `jugantor_epub/sources/` with the same three-function shape, list it in `config.SOURCES`.
- **Daily automation** — `main.py` takes no arguments and does one complete run; needs only an OS-level cron/launchd entry, no code changes.
- **Auto-email to Kindle** — planned as an `email_sender.py` with `send_to_kindle(epub_path)` (SMTP to a `@kindle.com` Send-to-Kindle address), gated behind a `SEND_TO_KINDLE` flag in `config.py`, called from `main.py` right after a successful `build_epub()`.

## Reference

Original design/plan: `/Users/mehedihasan/.claude/plans/hey-i-want-to-prancy-sedgewick.md`.
