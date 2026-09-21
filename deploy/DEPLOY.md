# Deploying CricBet on a Hostinger VPS

**End result:** people open `https://yourdomain.com` (no port number) from anywhere.

```
Visitor ──HTTPS──▶ nginx (ports 80/443) ──unix socket──▶ uvicorn ▶ your FastAPI app
                    ▲                                     (no TCP port at all)
                    └─ free Let's Encrypt certificate, renews itself
```

- **nginx** is the only thing exposed to the internet. It handles HTTPS and forwards requests to the app.
- The app listens on a **unix socket** (`/run/cricbet/cricbet.sock`), not a port, so there is nothing like `:8000` to open, remember or attack.
- **systemd** keeps the app running, restarts it if it crashes, and starts it on reboot.

Tested on Python 3.12 with the versions pinned in `requirements.txt`.

---

## Before you start

- A Hostinger VPS running **Ubuntu 22.04 or 24.04** (or Debian 12) and its **IP address** (shown in hPanel → VPS).
- Root SSH access: `ssh root@YOUR_VPS_IP`
- Your domain (called `yourdomain.com` below).

---

## Step 1: Point the domain at the VPS

In the DNS settings for your domain (hPanel → Domains → your domain → DNS / Nameservers, or at whichever registrar holds the domain), create:

| Type | Name  | Value         |
|------|-------|---------------|
| A    | `@`   | your VPS IP   |
| A    | `www` | your VPS IP   |

Delete any **existing** `A`, `AAAA` or `CNAME` records for `@` and `www` that point elsewhere (Hostinger often pre-creates parking records). A leftover `AAAA` (IPv6) record is the most common reason HTTPS setup fails.

DNS can take from a few minutes to a few hours. Check from your own computer:

```
nslookup yourdomain.com
```

It should print your VPS IP.

## Step 2: Upload the project

From your own computer (Windows PowerShell, Mac or Linux terminal), in the folder containing the zip:

```
scp Cricbet3_deploy.zip root@YOUR_VPS_IP:/root/
```

Then on the server:

```
ssh root@YOUR_VPS_IP
apt-get update && apt-get install -y unzip
mkdir -p /opt/cricbet
unzip /root/Cricbet3_deploy.zip -d /opt/cricbet
```

> **About `crickbet.db`:** the zip contains your current database, including any users, wallets and bets in it. If you want the live site to start empty, delete it now (`rm /opt/cricbet/crickbet.db`); fresh tables are created automatically. Then create your admin in "After it is live" below.

## Step 3: Run the setup script

```
sudo bash /opt/cricbet/deploy/setup.sh yourdomain.com you@email.com
```

The email is only used by Let's Encrypt for certificate-expiry notices. The script:

1. installs Python, nginx, certbot and a firewall
2. creates a locked-down `cricbet` user to run the app
3. installs the dependencies and generates a **random session secret** in `/opt/cricbet/.env`
4. starts the app as a service (socket only, no port)
5. configures nginx for your domain
6. opens only SSH, 80 and 443 in the firewall
7. checks your DNS points here, then gets the HTTPS certificate and turns on HTTPS-only cookies

If DNS isn't ready yet, it stops before the certificate step and tells you. Wait, then run the same command again; it's safe to re-run and won't reset your secret or database.

When it finishes, open `https://yourdomain.com`.

> **Hostinger firewall:** if you have turned on a firewall in hPanel (in the VPS security/firewall settings), make sure it allows TCP **80** and **443** (and SSH), otherwise the site will time out from outside even though the server is fine.

---

## After it is live (please do these)

**1. Replace the default admin password.** `create_admin.py` contains the admin username and password in plain text, so anyone who has ever had the code knows it.

```
cd /opt/cricbet
sudo -u cricbet venv/bin/python deploy/set_admin_password.py
```

Enter the admin username (e.g. `Cricbet`) and a new long password (typed hidden). Consider also deleting the password line from `create_admin.py`.

**2. Ask ProExch about whitelisting the server.** A comment in `services/proexch_api.py` ("Leave empty when your server IP is whitelisted") suggests ProExch may restrict access by IP address. If the match list is empty or shows "Unable to load cricket data" on the live site but works on your own computer, ProExch is most likely refusing the VPS. Give them your **VPS IP** to whitelist.

**3. Back up the database.** All users, balances and bets live in one file, `/opt/cricbet/crickbet.db`. A daily safe copy:

```
apt-get install -y sqlite3
mkdir -p /var/backups/cricbet
crontab -e
```

Add this line (copies daily at 03:00):

```
0 3 * * * sqlite3 /opt/cricbet/crickbet.db ".backup '/var/backups/cricbet/crickbet-$(date +\%F).db'"
```

Also download a copy to your own computer or storage now and then; a backup on the same server doesn't protect you if the server is lost.

**4. Optional: force browsers to always use HTTPS** (only once you've confirmed the site loads correctly over HTTPS). Inside the `server { ... listen 443 ssl ... }` block in `/etc/nginx/sites-available/cricbet`, add:

```
add_header Strict-Transport-Security "max-age=31536000" always;
```

then `nginx -t && systemctl reload nginx`.

---

## Day-to-day

| I want to...                         | Command |
|--------------------------------------|---------|
| Update the site after changing files | upload the changed files to `/opt/cricbet/`, then `sudo chown -R cricbet:cricbet /opt/cricbet && sudo systemctl restart cricbet` |
| See app logs live                    | `journalctl -u cricbet -f` |
| See nginx errors                     | `tail -f /var/log/nginx/error.log` |
| Restart / stop the app               | `sudo systemctl restart cricbet` / `sudo systemctl stop cricbet` |
| Is everything running?               | `systemctl status cricbet nginx` |
| Change a setting (`.env`)            | `sudo nano /opt/cricbet/.env` then `sudo systemctl restart cricbet` |
| Check certificate auto-renewal       | `sudo certbot renew --dry-run` |

If you add new Python packages to `requirements.txt`: `/opt/cricbet/venv/bin/pip install -r /opt/cricbet/requirements.txt`, then restart.

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Browser can't connect / times out | DNS not pointing at the VPS yet, or a firewall (hPanel or `ufw status`) is blocking 80/443. |
| **502 Bad Gateway** | The app isn't running. `journalctl -u cricbet -n 50` shows why, then `sudo systemctl restart cricbet`. |
| **413 Request Entity Too Large** on deposit screenshots | Files over ~6 MB are rejected by design (the app's own limit is 5 MB). |
| Setup stops at the certificate step | Domain not pointing here yet, or a stale `AAAA` record. Fix DNS, re-run the same setup command. |
| Logged out immediately after login | `SESSION_HTTPS_ONLY=true` in `.env` but you're visiting over plain `http://`. Use `https://`. |
| Match list empty / "Unable to load cricket data" | ProExch may not have whitelisted the VPS IP (see above), or their API is down. Check `journalctl -u cricbet -f`. |
| Password-reset links point to the wrong address | Set `PUBLIC_BASE_URL=https://yourdomain.com` in `.env`, then restart. |
| Visiting the raw IP shows nothing | Intended. nginx only serves your domain. |

---

## What's in `deploy/`

| File | Purpose |
|---|---|
| `setup.sh` | One-shot server setup (steps above) |
| `cricbet.service` | systemd unit: runs the app on a unix socket, restarts on failure |
| `nginx-cricbet.conf` | nginx reverse-proxy template for your domain |
| `env.example` | The three settings the app reads from `.env` |
| `set_admin_password.py` | Safely set/create an admin login without storing the password in a file |
