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

## Components

### 1. `jugantor_epub/email_sender.py` (new)

Follows the existing parse/fetch split used in `sources/jugantor.py`:

- `build_message(epub_path, source_name, edition_date, from_addr, to_addr) -> EmailMessage` — **pure**, no I/O. Reads the epub file's bytes and constructs a MIME message with the epub attached as `application/epub+zip`. This is what the test suite exercises directly against a small fixture epub.
- `send_to_kindle(epub_path, source_name, edition_date)` — thin I/O wrapper. Reads `config.GMAIL_ADDRESS` / `config.GMAIL_APP_PASSWORD` / `config.KINDLE_EMAIL`, calls `build_message(...)`, and sends via `smtplib.SMTP_SSL("smtp.gmail.com", 465)`.

No subject/body requirements beyond something human-readable — Amazon's Send-to-Kindle has supported native `.epub` attachments (no forced MOBI conversion) since 2022, so no format-conversion step is needed.

### 2. `jugantor_epub/config.py` (modified)

Replaces the existing placeholder `SEND_TO_KINDLE = False` with env-driven settings, so local manual runs (`.venv/bin/python main.py`) behave exactly as documented today — no email attempt — unless explicitly opted in:

```python
SEND_TO_KINDLE = os.environ.get("SEND_TO_KINDLE", "false").lower() == "true"
KINDLE_EMAIL = os.environ.get("KINDLE_EMAIL")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
```

### 3. `main.py` (modified)

- After `build_source_edition()` succeeds for a source, if `config.SEND_TO_KINDLE` is true, call `email_sender.send_to_kindle(output_path, source_module.SOURCE_NAME, edition_date)`. A send failure is caught and logged per-source — same error-isolation pattern as scraping failures — and doesn't stop other sources.
- **Exit-code fix:** today `main()` catches every per-source exception and logs it but always exits `0`, even when every source fails. Since failure detection relies on GitHub's built-in notification for a failed workflow run, `main()` now tracks whether at least one source fully succeeded (built, and — when enabled — sent) across the `SOURCES` loop, and calls `sys.exit(1)` if none did. This only changes the final exit code; the existing per-source isolation in the loop is unchanged.

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
- The built epub is always uploaded as a workflow artifact (7-day retention) regardless of overall success/failure, so a bad run can be inspected without re-scraping.
- Existing per-source and per-article error isolation in `main.py`/`build_source_edition()` is preserved unchanged.

## Testing

- `tests/test_email_sender.py`: unit-tests `build_message()` directly against a small fixture epub file — asserts `From`/`To` headers, attachment filename, and MIME type (`application/epub+zip`). No network/SMTP involved.
- `send_to_kindle()` itself is not unit tested — it's a thin I/O wrapper, consistent with how `_get()` in the scraper is treated (not tested directly; exercised only via the wrappers that call it).

## Documentation updates

- `README.md`: replace the "Not implemented yet" bullets for automation/Kindle-email with a "Daily Kindle delivery (GitHub Actions)" section covering the cron schedule, the three required secrets, the Amazon approved-sender step, and the 60-day inactivity auto-disable caveat.
- `CLAUDE.md`: update the "Deferred" section to reflect that both items are now implemented, pointing at `.github/workflows/daily-kindle.yml` and `jugantor_epub/email_sender.py`.

## Out of scope (YAGNI, not building now)

- Custom failure-alert emails (GitHub's built-in notification is sufficient per user decision).
- MOBI conversion fallback — not building proactively since native EPUB support on Kindle is assumed current; if this assumption proves wrong once tested against a real device, revisit then.
- Handling multiple `SOURCES` with separate email sends beyond what the existing per-source loop already does — today there's only one source (`jugantor`), and the design doesn't need to special-case a future second source.
