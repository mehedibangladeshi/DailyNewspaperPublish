# Setting up the self-hosted runner

Follow this once, on whichever always-on machine will run the daily Kindle
automation. See `docs/superpowers/specs/2026-08-20-self-hosted-docker-runner-design.md`
for why this exists (Cloudflare blocks Dhaka Tribune/Ittefaq scraping from
GitHub-hosted runners, but not from a residential IP like this machine's).

The workflow itself doesn't need Python installed on this machine — it builds
and runs a Docker image (see the repo's `Dockerfile`), so the only host
dependency is Docker.

## 1. Install Docker

**Arch-based (CachyOS, Arch Linux, Manjaro, ...):**
```
sudo pacman -S docker
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```
Log out and back in (or `newgrp docker`) for the group change to take effect.

**Debian-based (Raspberry Pi OS, Ubuntu, ...):**
```
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```
Log out and back in for the group change to take effect.

Verify with `docker run hello-world`.

**Check the real path MTU before registering the runner.** Docker's default
bridge network MTU is 1500, but many residential/PPPoE connections have a
lower real path MTU. If Docker's MTU is set too high, small requests (page
scraping, SMTP login) work fine, but sustained large transfers **from inside
a container** (e.g. emailing a multi-MB epub attachment) can silently stall
or drop mid-transfer — this bit us on 2026-08-23: Kindle sends kept failing
with smtplib's "Server not connected" / "read operation timed out" only
during the actual DATA transfer, never during login, and only when run
through Docker (a bare host script sending the same size never reproduced
it). Diagnosed with:
```
ping -M do -s 1472 -c 3 smtp.gmail.com
```
If that reports `Frag needed and DF set (mtu = N)`, the real path MTU is
`N`. Set Docker's bridge MTU comfortably below that (we used `N - 80`, i.e.
1400 for a reported 1480, since email_sender.py's own retry logic already
tolerates the rare transient failure - the margin doesn't need to be exact):
```
sudo mkdir -p /etc/docker
echo '{"mtu": 1400}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```
Verify a fresh container picks it up: `docker run --rm alpine sh -c "cat /sys/class/net/eth0/mtu"`.

## 2. Register the GitHub Actions runner

1. On GitHub: open this repo → **Settings → Actions → Runners → New self-hosted runner**.
2. Pick **Linux** and the matching architecture (**x64** for CachyOS/most PCs,
   **ARM64** for a Raspberry Pi). GitHub shows a set of commands with a
   registration token baked in — run those on the machine, e.g.:
   ```
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-linux-x64-<version>.tar.gz -L <url-from-github-ui>
   tar xzf ./actions-runner-linux-x64-<version>.tar.gz
   ./config.sh --url https://github.com/<owner>/<repo> --token <token-from-github-ui>
   ```
   (Copy the exact URL/token from the GitHub UI — they're one-time and
   repo-specific, not reproduced here.) Accept the default name/labels when
   prompted (`self-hosted`, `Linux`, `X64`/`ARM64`) — the workflow targets
   `runs-on: [self-hosted, Linux]`.
3. Install it as a service so it survives reboots and restarts if it crashes:
   ```
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```
4. Confirm it shows **Idle** under Settings → Actions → Runners in GitHub.

## 3. Test it

Trigger a manual run: repo → **Actions → Daily Kindle edition → Run workflow**.
Confirm all five sources build (including Dhaka Tribune and Ittefaq — the
whole point of this move), the Kindle emails send, and the OPDS catalog
publishes to `gh-pages`.

Once confirmed, update `CONTEXT.md`'s Dhaka Tribune/Ittefaq "known, accepted
limitation" entries to record the fix.

## Migrating to a different machine later

Repeat steps 1–3 on the new machine (Docker + a freshly-registered runner —
registration tokens are one-time, so generate a new one from the GitHub UI).
Once the new runner shows **Idle** and a manual run succeeds on it, remove
the old runner entry from Settings → Actions → Runners. No repo changes are
needed — the `Dockerfile` already declares the whole application environment,
independent of host OS/architecture.

## Troubleshooting

- **Runner never goes Idle**: check `sudo ./svc.sh status` in the
  `actions-runner` directory, and `journalctl -u actions.runner.* -f` for logs.
- **`docker` commands need `sudo`**: the `usermod -aG docker` group change
  didn't take effect — log out/in fully (a new terminal isn't enough) or
  reboot.
- **Workflow can't reach github.com**: self-hosted runners only need
  *outbound* HTTPS access (they poll GitHub, nothing inbound is required) —
  check the machine's firewall/router isn't blocking outbound 443.
