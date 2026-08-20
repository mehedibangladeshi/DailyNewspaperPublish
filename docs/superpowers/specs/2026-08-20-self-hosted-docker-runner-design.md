# Self-Hosted Docker Runner for Daily Kindle Automation — Design

## Context

`.github/workflows/daily-kindle.yml` runs the daily pipeline on GitHub's hosted `ubuntu-latest` runners. Two sources — Dhaka Tribune and Ittefaq — are Cloudflare-fronted and reliably 403 (Managed Challenge) when scraped from those runners' Azure-hosted datacenter IPs, while the identical request succeeds from a residential IP (confirmed by direct comparison during each source's initial research; see `CONTEXT.md`'s "Known, accepted limitation" entries for both). This was previously judged not worth fixing. The user is revisiting that call now that a spike (2026-08-20, this session) reconfirmed both sources scrape cleanly from a local/residential connection using the existing scraper code unmodified — the problem is the runner's IP, not the scraper logic.

## Decision: fix the IP, not the scraper

Alternatives considered and rejected:
- **Targeted residential/anti-bot proxy service for just the two blocked sources** — keeps GitHub-hosted runners for the other three sources (smaller blast radius), but is a recurring paid dependency for a personal project.
- **Public/free residential proxy lists** — rejected outright: unreliable, poorly (if at all) geo-targeted, and a meaningful share of "free residential proxy" networks are actually compromised consumer devices — a real security/privacy risk to route scraper traffic through, not just a reliability one.
- **Do nothing on CI, rely on manual local builds** — the `--source` flag (added this session, see `main.py`) already supports this as a fallback, but the user wants the two sources back on the daily automated path.

**Chosen: move the whole daily workflow to a self-hosted GitHub Actions runner** on the user's own always-on machine, so every request — including Dhaka Tribune's and Ittefaq's — originates from a genuine residential IP. Whole-workflow (not split GitHub-hosted/self-hosted) was chosen for simplicity: one job, one runner, no artifact handoff between two jobs.

**Accepted trade-off:** this makes the self-hosted machine's uptime/network a single point of failure for *all five* sources, where previously only the two Cloudflare-blocked sources could fail on a bad day. `workflow_dispatch` (already present in the workflow) remains available for a manual re-run if a scheduled run is missed. No new monitoring/alerting is being built beyond GitHub's existing failed-workflow notification — consistent with how the rest of this pipeline's error handling already works (see `CLAUDE.md`'s error-isolation section).

**Security note:** self-hosted runners are a real risk mainly for public repos with PR-triggered workflows (arbitrary fork code execution). This repo is private and the workflow only triggers on `schedule`/`workflow_dispatch`, so that risk model doesn't apply here.

## Decision: containerize, for host portability

The runner's first host is the user's current always-on machine (Linux, CachyOS, x86_64), but the user expects to migrate it to a different machine later (a Mac mini or a Raspberry Pi — a different OS and, for the Pi, a different CPU architecture). Docker does not change which network the traffic egresses from — a container on a given host still egresses through that host's own network interface, so it has no bearing on the Cloudflare-block fix itself, which comes entirely from running on the self-hosted machine's real IP. Its value here is purely environmental: the app's exact Python version and dependencies live in a `Dockerfile` instead of depending on whatever the host OS's package manager happens to ship — including CachyOS's PEP 668 "externally managed" restriction, which would otherwise reject a bare `pip install`. Migrating hosts later becomes "install Docker + re-register the runner," not "re-debug a Python/dependency setup on a new OS and architecture" (a Raspberry Pi's `docker build` on the same Dockerfile produces an ARM64 image automatically — nothing to prepare for that now).

## Workflow changes (`.github/workflows/daily-kindle.yml`)

- `runs-on: ubuntu-latest` → `runs-on: [self-hosted, Linux]` (the default labels GitHub assigns a newly-registered self-hosted runner).
- Drop the `actions/setup-python@v7` step — self-hosted runners use whatever's already on the box; with containerization, the host doesn't even need Python installed, only Docker.
- Replace the `pip install -r requirements.txt` / `python main.py` steps with:
  1. `docker build -t daily-newspaper .`
  2. `docker run --rm` with the existing `SEND_TO_KINDLE`/`GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`/`KINDLE_EMAIL`/`PUBLISH_OPDS` env vars passed through as `-e`, and volume mounts for `output/` and `${GH_PAGES_DIR}` so the built `.epub` files and the OPDS catalog land back on the host — unchanged inputs for the existing `actions/upload-artifact` and `peaceiris/actions-gh-pages` steps that follow.
- `actions/checkout@v7`, the `gh-pages` checkout/existence-check steps, `actions/upload-artifact@v7`, and `peaceiris/actions-gh-pages` are unaffected — they're git/artifact operations independent of which runner or container executes the build step.

## New: `Dockerfile` (repo root)

`python:3.x-slim` base image; `pip install -r requirements.txt`; copies the repo; `CMD ["python", "main.py"]`. Not used for local development (`.venv`-based local runs per `CLAUDE.md` are unaffected) — only for the containerized CI build step above.

## New: setup/runbook doc

A step-by-step instruction doc for provisioning a machine as the self-hosted runner (install Docker, download/register the GitHub Actions runner with a repo-generated registration token, install it as a systemd service via `svc.sh install && svc.sh start`) — written so the user can follow it unassisted whenever they're ready to actually provision the machine (explicitly deferred by the user to a later session; this branch only prepares the code/docs, no runner registration happens now).

## Scope note

All of the above lands on a dedicated branch (`self-hosted-docker-runner`), not `main` — the user does not want the daily automation's live behavior to change until they've provisioned the runner machine themselves and merged deliberately.

## Testing / verification (deferred to when the runner is actually provisioned)

Once the runner is registered and running: trigger `workflow_dispatch` manually and confirm all five sources build (including Dhaka Tribune and Ittefaq), Kindle emails send, and the OPDS catalog publishes — the same verification the existing automation already relies on. At that point, update `CONTEXT.md`'s Dhaka Tribune/Ittefaq "known, accepted limitation" entries to record the fix.
