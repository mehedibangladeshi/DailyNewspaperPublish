# OPDS catalog prototype — notes

## Question

Would a "rolling 7-day window of built editions, rendered as one flat OPDS
acquisition feed" model hold up for real use — across a build that fails
(no edition produced), a second newspaper source appearing later, entries
aging out and needing their epub files deleted from storage, and re-running
the same day twice?

Decisions already made going in (asked the user up front, since they change
the whole architecture):
- **Hosting**: static feed, no long-running server.
- **Exposure**: public, no auth.
- **Retention**: rolling 7 days.

## Answer

The flat-feed-with-`<category>` shape holds up. Ran it through:
registering a second hypothetical source (`prothomalo`) alongside `jugantor`,
building both on the same simulated day, viewing the rendered XML (entries
from both sources interleaved, each tagged with its own `<category
term=... label=.../>`, still readable), then ticking the simulated clock
forward 7 days. Both editions aged out on the same tick, both got listed in
"expired this tick" (the exact set of `.epub` files a real implementation
would need to delete from storage), and the re-rendered feed came back
empty and still well-formed. A failed build (`f`) is correctly a no-op —
no entry, no crash — matching `main.py`'s existing per-source skip.

**Verdict: no need for a navigation-feed-per-source layer.** One flat
acquisition feed, newest-first, with entries tagged by source, is enough
for the foreseeable number of sources (1-3). Revisit only if the source
count grows enough that the category tags stop being useful for
navigation.

## What this surfaced that wasn't obvious going in

**State persistence is not optional for the real version**, even though
this prototype deliberately kept it in-memory (per the prototype skill's
own "no persistence by default" rule). The daily build is a GitHub Actions
cron run with no long-running process — there is no Python object sitting
around between runs to call `add_edition`/`expire` on. The real
implementation needs the catalog state (which editions are currently
active, per source) persisted *somewhere* the next day's run can read it
back from — most likely a small `catalog_state.json` committed alongside
`catalog.xml` in the published output, rather than re-deriving it by
listing bucket/directory contents each run. This is the one design
question the prototype didn't answer and the next pass should.

## Recommended shape for the real feature (not yet implemented)

- New module `jugantor_epub/opds_catalog.py`, adapting `logic.py`'s pure
  functions but with `initial_state`/state loaded from and saved back to a
  JSON file each run instead of living in memory.
- `main.py` integration point: after all sources finish building (where it
  already accumulates `(source_name, output_path)` for the Kindle email),
  add each successfully-built edition to the catalog state, run `expire`,
  write the updated `catalog.xml` + `catalog_state.json`, and physically
  delete the epub files `expire` returned.
- Hosting: GitHub Pages via a dedicated branch (e.g. `peaceiris/actions-gh-pages`
  with `keep_files: false` so the branch is fully replaced each run,
  not accumulated) — avoids needing a new cloud account, and the daily
  full-replace keeps the branch small since old epubs are dropped every run
  anyway (7-day cap × ~1-3 sources is a handful of files at a time).
- Since exposure is "public, no auth" (user's explicit choice, not mine —
  I'd flagged the tradeoff that this makes scraped content openly
  downloadable to anyone with the URL, and they opted for simplicity
  anyway), no Basic Auth wiring needed in the feed generator itself.
- Kindle: stock firmware has no OPDS client, so email delivery
  (`email_sender.py`) stays as-is for Kindle. OPDS is additive, for the
  Boox/e-ink reader's OPDS-capable app (KOReader, Moon+ Reader, etc.) to
  pull from directly instead of waiting on email.

## Files

- `logic.py` — pure state/transitions, portable, worth lifting into
  `jugantor_epub/opds_catalog.py` (with persistence added) if this feature
  moves forward.
- `tui.py` — throwaway shell, delete when done.
