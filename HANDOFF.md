# Handoff: Self-hosted Docker runner for dailyNewspaper

**Written:** 2026-08-23, by the Claude Code session that did the
design/implementation work (on a Mac with no Docker installed).
**For:** a fresh Claude Code session on the machine that will actually host
the self-hosted GitHub Actions runner.
**This file is transient** — see "Cleanup" at the bottom. It is not
documentation to keep; it exists only to hand this task to a new session.

## Where things stand

- `main` @ `c76dc6d` — up to date, includes the new `--source` CLI flag on
  `main.py` (build/send a single newspaper source without scraping all of
  `config.SOURCES`; see `main.py`'s `parse_args`/`main(sources=...)`).
- `self-hosted-docker-runner` (this branch) @ `d74583d` plus this file —
  **not yet merged to `main`, on purpose** (the user didn't want the live
  daily-automation workflow to change until the runner machine is actually
  provisioned and proven working).

## The task this branch prepares for

Two sources — Dhaka Tribune and Ittefaq — are Cloudflare-blocked (403) when
scraped from GitHub Actions' hosted (datacenter-IP) runners, but scrape fine
from a residential IP (confirmed both by prior research and a fresh spike
this session — see `CONTEXT.md`'s "Known, accepted limitation" entries under
Dhaka Tribune and Ittefaq for the full history). The fix decided on: move the
whole daily workflow to a **self-hosted GitHub Actions runner** on the user's
own always-on machine, containerized with Docker so the setup is portable if
the runner later moves to a different machine (Mac mini or Raspberry Pi were
mentioned).

**Read these two files first — they contain the full design rationale and
the exact setup steps; don't re-derive either from scratch:**
- `docs/superpowers/specs/2026-08-20-self-hosted-docker-runner-design.md` —
  why self-hosted+Docker was chosen over alternatives (targeted residential
  proxy, anti-bot API, free proxy lists, self-hosted without Docker), and the
  accepted trade-offs (whole-pipeline dependency on this machine's uptime).
- `docs/self-hosted-runner-setup.md` — the step-by-step runbook: install
  Docker, register the GitHub Actions runner, install it as a systemd
  service, test with a manual `workflow_dispatch`, and (later) how to migrate
  to a different machine.

Also on this branch (already implemented, not yet exercised for real):
`Dockerfile`, `.dockerignore`, `.github/workflows/daily-kindle.yml` (now
`runs-on: [self-hosted, Linux]`, builds/runs the Docker image with volume
mounts for `output/` and the OPDS `gh-pages` checkout dir),
`tests/test_dockerfile.py`, `tests/test_workflow.py`. Full test suite (270
tests) was passing as of the last commit on this branch.

## What's genuinely unverified — do this first

**`docker build` was never actually run** — the Mac used for this session had
no Docker installed, so the `Dockerfile` and the workflow's `docker run`
invocation are untested. Once on the target Linux machine with Docker
installed, sanity-check before registering the runner:
```
docker build -t daily-newspaper .
docker run --rm -v "$PWD/output:/app/output" daily-newspaper
```
Watch for anything distro-specific missing at `pip install` time (e.g.
Pillow's manylinux wheels normally need no extra system packages, but
confirm) and that the container can actually reach the internet/DNS from
this host's network.

## Suggested next steps (in order)

1. Sanity-check the Docker build/run as above.
2. Follow `docs/self-hosted-runner-setup.md` to install Docker properly (as a
   service) and register+start the GitHub Actions runner.
3. Trigger `workflow_dispatch` manually from the GitHub Actions UI and
   confirm all 5 sources build, Kindle emails send, and OPDS publishes.
4. Once verified, update `CONTEXT.md`'s Dhaka Tribune/Ittefaq "known,
   accepted limitation" entries to record the fix (the runbook's "Test it"
   section already says this — don't skip it).
5. Delete this file (see Cleanup below).
6. Merge `self-hosted-docker-runner` into `main` (the user wanted this held
   back until the runner was actually working — check with them before
   merging if that's still the plan).

## Suggested skills for the new session

- **`superpowers:systematic-debugging`** — if the Docker build or the runner
  registration hits an error, use this rather than guessing fixes ad hoc.
- **`superpowers:verification-before-completion`** — before telling the user
  "it works," actually run the manual `workflow_dispatch` and check the Run
  summary log line in the Actions output (`main.py`'s `main()` logs a
  one-line summary: built/sent/size-skipped/failure counts).
- **`superpowers:brainstorming`** — if anything about the design needs to
  change once real hardware constraints show up (e.g. Docker won't install
  cleanly, or the machine turns out not to have a stable residential IP),
  don't silently deviate — brainstorm the change the same way this design
  was reached.

## Things NOT to re-litigate

The design spec already settled these after explicit back-and-forth with the
user — don't reopen unless new information genuinely contradicts them:
- Self-hosted (not a proxy service, not "do nothing on CI").
- Whole workflow on one runner (not split GitHub-hosted/self-hosted).
- Docker (chosen specifically for future host-portability, not because it
  affects the IP-block fix itself — it doesn't).
- Changes stay on this branch until the runner is proven working; not merged
  to `main` preemptively.

## Cleanup

Once the runner setup is verified working (step 3 above has succeeded and
step 4's `CONTEXT.md` update is done), **delete this file** as part of that
same batch of commits:
```
git rm HANDOFF.md
git commit -m "chore: remove handoff doc, setup complete"
```
It's a one-time transfer document, not something to keep around — the
permanent record of *why* lives in the design spec, and the permanent
record of *how* lives in the runbook. Don't delete it before the setup is
actually confirmed working, in case the new session needs to be resumed
again.
