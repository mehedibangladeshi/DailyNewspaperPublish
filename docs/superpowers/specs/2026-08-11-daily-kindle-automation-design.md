# Daily Kindle Automation — Design

## Context

The pipeline (`main.py`) already scrapes Jugantor's todays-paper edition and builds a Kindle-ready `.epub` on demand. Two pieces were explicitly deferred in the original build (see `README.md`'s "Not implemented yet" and `CLAUDE.md`'s "Deferred" section): daily scheduling and auto-email to a Kindle `@kindle.com` address. This design implements both together, since the natural way to run this schedule doesn't need a persistent machine at all.

The repo already has a GitHub remote (`origin` → `mehedibangladeshi/DailyNewspaperPublish`), which is what makes the chosen approach possible without any new hosting account.

## Goal

Every day at 8:00 AM Bangladesh time (UTC+6, no DST), automatically scrape the day's Jugantor edition, build the epub, and email it to the user's Kindle so it's waiting on-device without manual intervention.

## Decision: run location

**Chosen: GitHub Actions scheduled workflow**, over the alternatives considered:

- **macOS launchd (local machine):** free, no new accounts, but unreliable — only fires if the laptop is on and awake at the scheduled time. Rejected for a laptop that sleeps overnight.
- **AWS Lambda + EventBridge:** free tier is generous and permanent (not just 12 months) and timing is more exact than GitHub's, but requires packaging native dependencies (`Pillow`, `beautifulsoup4`, `ebooklib`) into a Lambda-compatible artifact — meaningfully more setup for no benefit at this scale.
- **PythonAnywhere free tier:** has a daily scheduled-task slot, but restricts outbound network requests to a whitelist on the free plan, which would likely block both the scrape (jugantor.com) and SMTP send. Not viable without a paid upgrade.
- **GitHub Actions (chosen):** free (2,000 min/month for private repos; this job uses ~100–150 min/month), no new account since the repo is already there, and its ephemeral-runner model fits naturally — the runner builds the epub *and* emails it in the same job, no persistent storage or server needed.

Trade-offs accepted: scheduled triggers are best-effort (can slip a few minutes under GitHub's load, not wall-clock exact), and GitHub auto-disables a scheduled workflow after 60 days with zero commits to the repo (mitigation: just re-enable it from the Actions tab if that ever happens — not worth building around for an actively-developed repo).

## Local vs. CI behavior (explicit)

This is one system with two entry points into the same `main.py`, distinguished only by the `SEND_TO_KINDLE` env var:

| | Local (`.venv/bin/python main.py`) | GitHub Actions (scheduled or manual dispatch) |
|---|---|---|
| `SEND_TO_KINDLE` | unset → `false` | set to `'true'` in the workflow's `env:` |
| Behavior | Builds `.epub`(s) into `output/`, exactly as documented today. No network send. | Builds `.epub`(s), then emails all of them to Kindle in one message. |
| Use case | Generate an edition anytime to inspect/read locally, without touching Kindle delivery at all. | The unattended daily run. |

No other code path differs between the two — same `main()`, same `build_source_edition()` per source, same scraper. This is why the env-var flag (not, say, a CLI argument) is the right switch: it needs zero developer action to preserve the local workflow as GitHub Actions is added.

## Multi-source growth (Jugantor today, more newspapers/magazines later)

`config.SOURCES` and `main.py`'s loop already make adding a new source purely additive — write a module under `jugantor_epub/sources/` with the same `discover_sections()` / `list_articles()` / `fetch_article()` / `SOURCE_NAME` shape, append its name to `config.SOURCES`. No part of this design changes that contract.

What this design decides is what "send to Kindle" means once `SOURCES` has more than one entry: **one combined email per day**, containing every source's `.epub` as a separate attachment, sent once after all sources have finished building — not one email per source as they complete. This means:

- `main.py` collects `(source_name, output_path)` for every source that builds successfully, across the whole `SOURCES` loop, before sending anything.
- If some sources fail to build and others succeed, the email still goes out with whichever epubs did build (existing per-source error isolation is preserved — a bad source degrades the digest, it doesn't block delivery of the rest).
- If every source fails to build, there is nothing to email, and the run exits non-zero (see exit-code fix below) — no partial email, no empty email.
- Adding a second source later requires no changes to `email_sender.py` or the email-sending call site in `main.py` — it already attaches "whatever built successfully," regardless of count.

### 1. `jugantor_epub/email_sender.py` (new)

Follows the existing parse/fetch split used in `sources/jugantor.py`:

- `build_message(epub_entries, edition_date, from_addr, to_addr) -> EmailMessage` — reads each `(source_name, epub_path)` entry's file bytes and constructs a single MIME message with one attachment per entry, each as `application/epub+zip`. Takes a list so it works identically whether there's 1 source or 5. This is what the test suite exercises directly against small fixture epub files.
- `send_to_kindle(epub_entries, edition_date)` — thin I/O wrapper. Reads `config.GMAIL_ADDRESS` / `config.GMAIL_APP_PASSWORD` / `config.KINDLE_EMAIL`, calls `build_message(...)`, and sends via `smtplib.SMTP_SSL("smtp.gmail.com", 465)`.

No subject/body requirements beyond something human-readable (e.g. `"Daily reading — {edition_date}"`) — Amazon's Send-to-Kindle has supported native `.epub` attachments (no forced MOBI conversion) since 2022, and supports multiple attachments per email (each becomes a separate document on-device), so no format-conversion or one-email-per-file constraint applies.

### 2. `jugantor_epub/config.py` (modified)

Replaces the existing placeholder `SEND_TO_KINDLE = False` with env-driven settings, so local manual runs (`.venv/bin/python main.py`) behave exactly as documented today — no email attempt — unless explicitly opted in:

```python
SEND_TO_KINDLE = os.environ.get("SEND_TO_KINDLE", "false").lower() == "true"
KINDLE_EMAIL = os.environ.get("KINDLE_EMAIL")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
```

### 3. `main.py` (modified)

- The `SOURCES` loop no longer sends email per-source. Instead it accumulates `(source_module.SOURCE_NAME, output_path)` into a `built` list for every source that builds successfully; a source that raises is still caught and logged, same as today, and simply doesn't contribute to `built`.
- After the loop finishes: if `built` is empty, nothing to send — log an error and exit non-zero (see below). Otherwise, if `config.SEND_TO_KINDLE` is true, call `email_sender.send_to_kindle(built, edition_date)` once, with everything that built successfully.
- **Exit-code fix:** today `main()` catches every per-source exception and logs it but always exits `0`, even when every source fails. Since failure detection relies on GitHub's built-in notification for a failed workflow run, `main()` now exits non-zero in two cases: (a) `built` is empty (no source produced an edition), or (b) `config.SEND_TO_KINDLE` is true and the single combined `send_to_kindle()` call raises. A run where some sources fail but at least one builds (and email sends, if enabled) still exits `0` — consistent with treating per-source failures as degraded-but-successful, not fatal.

### 4. `.github/workflows/daily-kindle.yml` (new)

```yaml
name: Daily Kindle edition
on:
  schedule:
    - cron: '0 2 * * *'   # 02:00 UTC = 08:00 BD time (UTC+6, no DST)
  workflow_dispatch:

jobs:
  build-and-send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          SEND_TO_KINDLE: 'true'
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: jugantor-epub-${{ github.run_id }}
          path: output/*.epub
          retention-days: 7
```

`if: always()` on the upload step means even a partially-failed run uploads whatever epub(s) did get built, for debugging.

**Required repo secrets** (Settings → Secrets and variables → Actions):
- `GMAIL_ADDRESS` — sender Gmail account.
- `GMAIL_APP_PASSWORD` — a Google App Password (requires 2FA on that account), not the regular account password.
- `KINDLE_EMAIL` — the `@kindle.com` Send-to-Kindle address, from Amazon's Manage Your Content and Devices → Preferences → Personal Document Settings.

**Manual one-time step (Amazon side, can't be automated):** add `GMAIL_ADDRESS` to Amazon's Approved Personal Document E-mail List — otherwise Amazon silently drops the email.

## Error handling / observability

- Failure detection relies entirely on GitHub's built-in notification for a failed scheduled workflow run (no custom failure-alert email) — made possible by the `main.py` exit-code fix above.
- The built epub(s) are always uploaded as a workflow artifact (7-day retention) regardless of overall success/failure, so a bad run — including one where the combined email failed to send after epubs built fine — can be inspected without re-scraping.
- Existing per-source and per-article error isolation in `main.py`/`build_source_edition()` is preserved unchanged; the only new fatal paths are "zero sources built anything" and "the combined send itself failed."

## Testing

- `tests/test_email_sender.py`: unit-tests `build_message()` directly against small fixture epub files — asserts one attachment per `(source_name, path)` entry, correct filenames, and MIME type (`application/epub+zip`) for each, including the single-entry and multi-entry (2+ sources) cases.
- `send_to_kindle()` itself is not unit tested — it's a thin I/O wrapper, consistent with how `_get()` in the scraper is treated (not tested directly; exercised only via the wrappers that call it).

## Documentation updates

- `README.md`: replace the "Not implemented yet" bullets for automation/Kindle-email with a "Daily Kindle delivery (GitHub Actions)" section covering the cron schedule, the three required secrets, the Amazon approved-sender step, and the 60-day inactivity auto-disable caveat.
- `CLAUDE.md`: update the "Deferred" section to reflect that both items are now implemented, pointing at `.github/workflows/daily-kindle.yml` and `jugantor_epub/email_sender.py`.

## Out of scope (YAGNI, not building now)

- Custom failure-alert emails (GitHub's built-in notification is sufficient per user decision).
- MOBI conversion fallback — not building proactively since native EPUB support on Kindle is assumed current; if this assumption proves wrong once tested against a real device, revisit then.
- A configurable per-source vs. combined-email toggle — combined is the only mode being built; if a future need for per-source delivery emerges, revisit then rather than building both now.
