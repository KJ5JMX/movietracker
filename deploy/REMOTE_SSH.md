# Remote shell to the Ubuntu box (deploy from anywhere)

Goal: run `deploy.sh` and tail logs on the box from work, with no open ports.
This reuses the Cloudflare Tunnel + Zero Trust Access you already run for the
backend. SSH never touches the public internet; it rides the tunnel, gated by
the same email one-time-PIN as the admin panel.

There are two ways to connect once it's set up:
- **Browser terminal** — nothing to install at work, just a browser + your
  email for the PIN. Preferred for locked-down work machines. Availability can
  depend on your Zero Trust plan; if you don't see the option, use the client
  method below (it always works).
- **Native SSH via `cloudflared`** — install one small binary on the machine
  you connect from. Guaranteed to work.

---

## 1. On the Ubuntu box (one time)

Make sure an SSH server is running locally (the tunnel connects to it over
loopback):

```bash
sudo apt update && sudo apt install -y openssh-server
sudo systemctl enable --now ssh
sudo systemctl status ssh      # confirm "active (running)"
```

Add an SSH route to the existing tunnel.

**If your tunnel is dashboard-managed** (Zero Trust → Networks → Tunnels):
- Open your tunnel → Public Hostname → Add a public hostname:
  - Subdomain: `ssh`
  - Domain: `thenobodyprojects.com`
  - Type: `SSH`
  - URL: `localhost:22`

**If your tunnel uses a local `config.yml`** (e.g. `/etc/cloudflared/config.yml`):
add an ingress rule (above the catch-all `service: http_status:404`):

```yaml
  - hostname: ssh.thenobodyprojects.com
    service: ssh://localhost:22
```

then `sudo systemctl restart cloudflared`.

---

## 2. In Cloudflare Zero Trust (one time)

Access → Applications → Add an application → **Self-hosted**:
- Application domain: subdomain `ssh`, domain `thenobodyprojects.com`.
- Policy: **Allow**, Include → Emails → your admin email (same as the admin
  panel). Login method: One-time PIN.
- (For the browser terminal) In the app's settings, set **Browser rendering**
  to **SSH**. If that option isn't present on your plan, skip it and use the
  client method.

This is the exact same pattern as the `/admin` Access app, just on the `ssh`
hostname instead of a path.

---

## 3a. Connect from work — browser terminal (no install)

1. Visit `https://ssh.thenobodyprojects.com`.
2. Authenticate via Access (enter your email, paste the one-time PIN it sends).
3. A terminal opens in the browser. Log in with your box's Linux user.

## 3b. Connect from work — native SSH client (`cloudflared`)

Install `cloudflared` on the machine you connect from, then add to
`~/.ssh/config`:

```
Host cuedup-box
  HostName ssh.thenobodyprojects.com
  User YOUR_LINUX_USER
  ProxyCommand cloudflared access ssh --hostname %h
```

Then `ssh cuedup-box` — a browser pops once for the Access PIN, then you're in.

---

## 4. Deploy + watch logs (the actual day-to-day)

Once you have a shell on the box:

```bash
cd ~/movie_tracker
bash deploy/deploy.sh            # pulls git, rebuilds, restarts; migrations auto-run
docker compose logs -f api       # live logs (Ctrl-C to stop)
```

`deploy.sh` already prints status + the last 20 log lines at the end, so for a
routine deploy you may not need the `logs -f` at all.

Note: the deploy pulls from git, so you still push your changes first (from
wherever you committed them). This box only ever *pulls*.

---

## Hardening (optional but recommended)

Because Access already gates the hostname by your email, you're in good shape.
To tighten the box's own SSH:
- Use key-based auth and disable password login: in `/etc/ssh/sshd_config` set
  `PasswordAuthentication no` (after confirming your key works), then
  `sudo systemctl restart ssh`.
- Keep the box awake (sleep kills the backend for everyone — SQLite lives here).
