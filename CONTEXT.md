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
- **One newspaper only (for now)** — see "Deferred work" below; the source-module contract is structured to make adding a second newspaper additive rather than a rewrite.
- **Daily automation via scheduled GitHub Actions, not local cron/launchd** — `.github/workflows/daily-kindle.yml` runs `main.py` on a daily schedule (plus manual `workflow_dispatch`), so the pipeline runs even when the personal machine is off. Local runs (`.venv/bin/python main.py`) still work unchanged and just build into `output/` without emailing anything.
- **One combined Kindle email per day, not one email per source** — `jugantor_epub/email_sender.py`'s `send_to_kindle(epub_entries, edition_date)` is called once from `main.py` after *all* sources have finished building, attaching every successfully-built `.epub` to a single message. This was a deliberate rejection of an earlier per-source design (`send_to_kindle(epub_path)` called right after each `build_epub()`) — see the design doc — because Send-to-Kindle delivery is naturally a once-a-day event, and one combined email avoids spamming the Kindle inbox when `config.SOURCES` grows. Sending is gated behind the `config.SEND_TO_KINDLE` env-driven switch (defaults off; the GitHub Actions workflow sets `SEND_TO_KINDLE=true`), and `main.py` exits non-zero if every source fails to build or the send itself fails, so a scheduled run failure is visible in the Actions tab.
- **OPDS catalog as a second, independent delivery path (GitHub Pages)** — added alongside Kindle email so the user's Boox e-ink device (via KOReader/Moon+ Reader, which support OPDS; stock Kindle firmware does not) can browse and pull editions directly. Organized by newspaper, not by date: a root navigation feed lists one entry per configured source, each linking to that source's own feed holding its last 7 *successfully built* editions by count (not a calendar window). No auth — an explicit, informed choice for simplicity over content protection. See `docs/superpowers/specs/2026-08-13-opds-catalog-design.md` for the full design rationale.
- **Local git identity: `Mehedi Hasan <mehedipy@gmail.com>`, not the work email** — this repo pushes to a personal GitHub account (`git@personal.github.com:mehedibangladeshi/DailyNewspaperPublish.git`, matching the existing `personal.github.com` SSH host alias used by other personal repos like `ai-skills`), so the commit identity is scoped to match, distinct from the global work-email default used elsewhere on this machine.

## Architecture summary

See `CLAUDE.md` for the details future coding sessions need (commands, the parse/fetch split, error-isolation pattern, Unicode normalization gotcha, JSON-LD parsing quirks, font-embedding bug history, cover generation). In short: `main.py` orchestrates a discover → scrape → build pipeline over source modules listed in `jugantor_epub/config.SOURCES`; each source module under `jugantor_epub/sources/` implements a small contract (section/article scraping plus a masthead-logo URL for the cover) so more newspapers can be added later without touching `main.py`.

## Known site quirks worth remembering

Found during initial scraping research and while fixing a code review pass — not obvious from reading the code alone:

- Some article pages embed a **raw literal newline inside a JSON string value** in their `ld+json` block (e.g. a multi-line headline), which breaks strict JSON parsing. Handled via `json.loads(..., strict=False)`.
- `ld+json` fields (headline, author, image) can be **present but explicitly `null`**, not merely absent — `dict.get(key, default)` doesn't catch that case; code must use `dict.get(key) or default`.
- The site **mixes NFC/NFD Unicode normalization** for Bengali nukta characters (e.g. "ড়") across different fields on the same page — text is normalized to NFC on extraction for consistent comparison/rendering.
- At least one observed image URL from the site's own data contained an unencoded `'` producing a broken CDN path — this fails gracefully (image skipped, article still included) rather than being treated as a code bug.

## Deferred work (explicitly out of scope for now)

Daily automation and auto-email to Kindle have shipped (see above and
`CLAUDE.md`). Still flagged by the user as a follow-up, structurally
supported but not built:
- **More newspapers** — add a module under `jugantor_epub/sources/` with the same contract shape (including `get_cover_logo_url()`), list it in `config.SOURCES`.

## Reference

Original design/plan: `/Users/mehedihasan/.claude/plans/hey-i-want-to-prancy-sedgewick.md`.
