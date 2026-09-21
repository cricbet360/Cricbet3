#!/usr/bin/env bash
#
# CricBet - one-shot setup for a fresh Ubuntu/Debian VPS (e.g. Hostinger).
#
#   1. Upload the project to /opt/cricbet   (see deploy/DEPLOY.md)
#   2. Point your domain's DNS A record at this server's IP
#   3. sudo bash /opt/cricbet/deploy/setup.sh yourdomain.com you@email.com
#
# Safe to re-run: it will not overwrite your .env (so nobody gets logged out)
# or your database.

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"

APP_DIR="/opt/cricbet"
APP_USER="cricbet"
SOCKET="/run/cricbet/cricbet.sock"

say()  { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx  %s\033[0m\n' "$*"; exit 1; }

# set_env KEY VALUE  -> update KEY in .env, or add it if missing
set_env() {
    local key="$1" value="$2" file="$APP_DIR/.env"
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

# ---------------------------------------------------------------- checks

[[ $EUID -eq 0 ]] || die "Run as root:  sudo bash $0 yourdomain.com you@email.com"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
    die "Usage: sudo bash $0 yourdomain.com you@email.com"
fi

DOMAIN="${DOMAIN,,}"
DOMAIN="${DOMAIN#www.}"

[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$ ]] \
    || die "'$DOMAIN' does not look like a domain name (example: cricbet.com)"

[[ -f "$APP_DIR/main.py" ]] \
    || die "$APP_DIR/main.py not found. Upload the project to $APP_DIR first."

[[ -f "$APP_DIR/deploy/cricbet.service" && -f "$APP_DIR/deploy/nginx-cricbet.conf" ]] \
    || die "$APP_DIR/deploy/ is missing - upload the whole project folder."

# -------------------------------------------------------------- packages

say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip nginx certbot \
    python3-certbot-nginx ufw curl

# ------------------------------------------------------------------ user

say "Creating service user '$APP_USER'"
if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

# ---------------------------------------------------------------- python

say "Installing Python dependencies"
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# ------------------------------------------------------------------- env

if [[ ! -f "$APP_DIR/.env" ]]; then
    say "Creating $APP_DIR/.env with a fresh random session secret"
    SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    cat > "$APP_DIR/.env" <<EOF
SESSION_SECRET=$SECRET
SESSION_HTTPS_ONLY=false
PUBLIC_BASE_URL=http://$DOMAIN
EOF
else
    say "$APP_DIR/.env already exists - leaving it alone"
fi

# ----------------------------------------------------- folders / permissions

mkdir -p "$APP_DIR/static/uploads/payment_screenshots"

# Cached bytecode from another machine/Python version is useless here.
find "$APP_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env"
if [[ -f "$APP_DIR/crickbet.db" ]]; then
    chmod 640 "$APP_DIR/crickbet.db"
fi

# Create any missing database tables once, up front, so the two worker
# processes don't race to do it on first start.
say "Preparing database tables"
( cd "$APP_DIR" && runuser -u "$APP_USER" -- "$APP_DIR/venv/bin/python" -c "import main" )

# --------------------------------------------------------------- service

say "Installing and starting the cricbet service"
cp "$APP_DIR/deploy/cricbet.service" /etc/systemd/system/cricbet.service
systemctl daemon-reload
systemctl enable cricbet >/dev/null
systemctl restart cricbet

for _ in $(seq 1 30); do
    [[ -S "$SOCKET" ]] && break
    sleep 1
done

if [[ ! -S "$SOCKET" ]] || \
   ! curl -fsS --unix-socket "$SOCKET" -o /dev/null http://localhost/; then
    journalctl -u cricbet -n 40 --no-pager || true
    die "The app did not start. Read the log above (journalctl -u cricbet -n 100)."
fi
echo "App is answering on $SOCKET"

# ----------------------------------------------------------------- nginx

say "Configuring nginx for $DOMAIN"
sed "s/__DOMAIN__/$DOMAIN/g" "$APP_DIR/deploy/nginx-cricbet.conf" \
    > /etc/nginx/sites-available/cricbet

# Some VPS images have IPv6 switched off; nginx refuses to start if told to
# listen on [::]. Drop those lines in that case.
if [[ ! -e /proc/net/if_inet6 ]]; then
    warn "IPv6 is not available on this server - using IPv4 only."
    sed -i '/listen \[::\]/d' /etc/nginx/sites-available/cricbet
fi

ln -sf /etc/nginx/sites-available/cricbet /etc/nginx/sites-enabled/cricbet
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx || systemctl restart nginx

# -------------------------------------------------------------- firewall

say "Configuring firewall (ufw)"
SSH_PORT="$(ss -tlnp 2>/dev/null | awk '/sshd/ {n=split($4,a,":"); print a[n]; exit}')"
SSH_PORT="${SSH_PORT:-22}"
ufw allow "${SSH_PORT}/tcp" >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
echo "Open ports: SSH ($SSH_PORT), 80, 443. Everything else is blocked."

# ------------------------------------------------------------------- DNS

say "Checking DNS"
SERVER_IP="$(curl -4fsS --max-time 8 https://api.ipify.org || true)"
DOMAIN_IP="$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)"
WWW_IP="$(getent ahostsv4 "www.$DOMAIN" | awk '{print $1; exit}' || true)"

echo "This server:      ${SERVER_IP:-unknown}"
echo "$DOMAIN:  ${DOMAIN_IP:-not found}"
echo "www.$DOMAIN:  ${WWW_IP:-not found}"

if [[ -n "$(getent ahostsv6 "$DOMAIN" | awk '{print $1}' | grep -v '^::ffff:' || true)" ]]; then
    warn "$DOMAIN has an IPv6 (AAAA) record. Unless it points to THIS server,"
    warn "delete it in your DNS settings or HTTPS certificate issuance will fail."
fi

if [[ -z "$DOMAIN_IP" || ( -n "$SERVER_IP" && "$DOMAIN_IP" != "$SERVER_IP" ) ]]; then
    warn "$DOMAIN does not point at this server yet, so HTTPS was NOT set up."
    warn "Add an A record  $DOMAIN -> ${SERVER_IP:-your VPS IP}  (DNS can take a few minutes to hours),"
    warn "then run this script again."
    echo
    echo "The site is already running over plain HTTP at http://$DOMAIN once DNS resolves."
    exit 0
fi

CERT_DOMAINS=(-d "$DOMAIN")
if [[ -n "$WWW_IP" && ( -z "$SERVER_IP" || "$WWW_IP" == "$SERVER_IP" ) ]]; then
    CERT_DOMAINS+=(-d "www.$DOMAIN")
else
    warn "www.$DOMAIN does not point here - issuing a certificate for $DOMAIN only."
    warn "Add an A record for 'www' later if you want it, then re-run this script."
fi

# ------------------------------------------------------------------ HTTPS

say "Getting a free HTTPS certificate (Let's Encrypt)"
if certbot --nginx "${CERT_DOMAINS[@]}" \
        -m "$EMAIL" --agree-tos --no-eff-email --redirect --non-interactive; then

    set_env SESSION_HTTPS_ONLY true
    set_env PUBLIC_BASE_URL "https://$DOMAIN"
    systemctl restart cricbet

    say "Done"
    echo "Your site is live:  https://$DOMAIN"
    echo "Certificates renew automatically (check: systemctl list-timers | grep certbot)."
else
    warn "Certificate request failed - the site still works over http://$DOMAIN."
    warn "Fix the cause shown above (usually DNS), then re-run this script."
    exit 1
fi

echo
warn "IMPORTANT before real users arrive - see deploy/DEPLOY.md, 'After it is live':"
warn "  1. Change the default admin password (deploy/set_admin_password.py)"
warn "  2. Ask ProExch to whitelist this server's IP: ${SERVER_IP:-<your VPS IP>}"
