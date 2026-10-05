#!/usr/bin/env bash
# One-time (and safely re-runnable) setup of the Ledgerline API on Ubuntu 22.04/24.04 or
# Amazon Linux 2023.
#
#   sudo ./deploy/ec2/setup.sh [--domain api.example.com --email you@example.com]
#                              [--repo URL] [--branch main]
#
# First run: installs packages, creates the service user, clones the code, writes
# /etc/ledgerline/ledgerline.env and stops so you can fill in DB_URL and OPENAI_API_KEY.
# Second run: installs dependencies, migrates the database, starts the service behind
# Nginx and (with --domain and --email) gets a Let's Encrypt certificate.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Never fail silently: report the failing line even if loading the helpers breaks.
trap 'printf "\033[1;31mxx\033[0m %s failed at line %s\n" "$(basename "$0")" "${LINENO}" >&2' ERR

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

# Default to the repository this script was run from (works for forks), else upstream.
REPO_URL="$(git -C "${SCRIPT_DIR}" remote get-url origin 2>/dev/null || true)"
REPO_URL="${REPO_URL:-https://github.com/Subhashbisnoi/wisprflow.git}"
BRANCH="main"
DOMAIN=""
EMAIL=""

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --email)  EMAIL="${2:?}"; shift 2 ;;
    --repo)   REPO_URL="${2:?}"; shift 2 ;;
    --branch) BRANCH="${2:?}"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) warn "Unknown option: $1"; usage 1 ;;
  esac
done

require_root "$@"
trap 'die "setup failed at line ${LINENO}. Fix the error above and re-run; every step is idempotent."' ERR

# --- 1. System packages ----------------------------------------------------------------
log "Installing system packages (${OS_ID})"
case "${OS_FAMILY}" in
  debian)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip git nginx curl ca-certificates >/dev/null
    if [[ -n "${DOMAIN}" ]]; then
      apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
    fi
    ;;
  rhel)
    # Amazon Linux 2023 ships curl-minimal (which provides curl) and python3 3.9, so
    # install python3.12 explicitly and leave curl alone.
    dnf install -y -q python3.12 python3.12-pip git nginx tar >/dev/null
    ;;
  *)
    die "Unsupported OS '${OS_ID}'. Use Ubuntu 22.04/24.04 or Amazon Linux 2023."
    ;;
esac

find_python >/dev/null || die "Python 3.12+ is required and could not be installed."
log "Using $("$(find_python)" --version) at $(find_python)"

# --- 2. Service user and directories ---------------------------------------------------
if ! id "${APP_USER}" >/dev/null 2>&1; then
  log "Creating system user ${APP_USER}"
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi
install -d -o "${APP_USER}" -g "${APP_USER}" -m 755 "${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_USER}" -m 750 "${DATA_DIR}" "${DATA_DIR}/storage"
install -d -o root -g "${APP_USER}" -m 750 "${ENV_DIR}"

# --- 3. Code ---------------------------------------------------------------------------
if [[ -d "${APP_DIR}/.git" ]]; then
  log "Code already present in ${APP_DIR} (use deploy.sh to update)"
else
  log "Cloning ${REPO_URL} (${BRANCH}) into ${APP_DIR}"
  as_app git clone --quiet --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

# --- 4. Environment file ---------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  log "Writing ${ENV_FILE}"
  install -o root -g "${APP_USER}" -m 640 "${APP_DIR}/deploy/ec2/ledgerline.env.example" "${ENV_FILE}"
  secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${secret}|" "${ENV_FILE}"
fi

if ! env_is_configured; then
  trap - ERR
  warn "Fill in DB_URL and OPENAI_API_KEY (and check CORS_ORIGINS) in ${ENV_FILE}:"
  warn "    sudo nano ${ENV_FILE}"
  warn "then re-run this script with the same options."
  exit 0
fi

# --- 5. Python environment and database ------------------------------------------------
install_python_deps
run_migrations

# --- 6. systemd service ----------------------------------------------------------------
owner="$(port_owner "${API_PORT}")"
if [[ -n "${owner}" ]] && ! systemctl is-active --quiet "${SERVICE_NAME}"; then
  die "Port ${API_PORT} is already used by '${owner}'. Pick another: sudo LEDGERLINE_PORT=8002 $0 ..."
fi
log "Installing systemd service ${SERVICE_NAME} on 127.0.0.1:${API_PORT}"
install_service_file
systemctl enable --quiet "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
if ! wait_for_health 30; then
  journalctl -u "${SERVICE_NAME}" -n 50 --no-pager >&2
  die "The API did not become healthy. See the log above."
fi

# --- 7. Nginx --------------------------------------------------------------------------
log "Configuring Nginx"
# On a server that already hosts other sites, never claim the catch-all server name.
other_sites="$(grep -lsE '^[[:space:]]*server_name' /etc/nginx/conf.d/*.conf /etc/nginx/sites-enabled/* 2>/dev/null \
  | grep -v "${SERVICE_NAME}" || true)"
if [[ -z "${DOMAIN}" && -n "${other_sites}" ]]; then
  die "Nginx already serves other sites (${other_sites//$'\n'/, }). Re-run with --domain <your-domain>."
fi
server_name="${DOMAIN:-_}"
sed -e "s|__SERVER_NAME__|${server_name}|" -e "s|__API_PORT__|${API_PORT}|g" \
  "${APP_DIR}/deploy/ec2/nginx-ledgerline-api.conf" > "${NGINX_SITE}"
if [[ "${OS_FAMILY}" == "debian" ]]; then
  ln -sf "${NGINX_SITE}" "${NGINX_ENABLED_LINK}"
  rm -f /etc/nginx/sites-enabled/default
fi
# On Amazon Linux, conf.d is included before nginx.conf's own sample server, so this
# server is the default for port 80 (a harmless "conflicting server name" warning may show).
nginx -t -q 2>&1 | grep -v "conflicting server name" >&2 || true
nginx -t -q 2>/dev/null || die "Nginx configuration test failed: run 'sudo nginx -t'"
systemctl enable --quiet nginx
systemctl reload nginx 2>/dev/null || systemctl restart nginx

# --- 8. HTTPS --------------------------------------------------------------------------
install_certbot_rhel() {
  # Not packaged for Amazon Linux 2023: install the official pip package in its own venv,
  # plus a systemd timer for renewals (Ubuntu's package ships its own timer).
  if command -v certbot >/dev/null 2>&1; then
    log "Using the existing certbot ($(command -v certbot)) and its renewal schedule"
    return 0
  fi
  if [[ ! -x /opt/certbot/bin/certbot ]]; then
    log "Installing certbot"
    "$(find_python)" -m venv /opt/certbot
    /opt/certbot/bin/pip install --quiet --upgrade pip certbot certbot-nginx
  fi
  ln -sf /opt/certbot/bin/certbot /usr/local/bin/certbot
  cat > /etc/systemd/system/certbot-renew.service <<'UNIT'
[Unit]
Description=Renew Let's Encrypt certificates
[Service]
Type=oneshot
ExecStart=/opt/certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
UNIT
  cat > /etc/systemd/system/certbot-renew.timer <<'UNIT'
[Unit]
Description=Twice-daily certificate renewal check
[Timer]
OnCalendar=*-*-* 03,15:00:00
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now --quiet certbot-renew.timer
}

if [[ -n "${DOMAIN}" ]]; then
  if [[ -z "${EMAIL}" ]]; then
    warn "--domain given without --email: skipping the certificate. Re-run with --email."
  else
    [[ "${OS_FAMILY}" == "rhel" ]] && install_certbot_rhel
    log "Requesting a Let's Encrypt certificate for ${DOMAIN}"
    certbot --nginx --non-interactive --agree-tos --redirect -m "${EMAIL}" -d "${DOMAIN}"
  fi
fi

# --- 9. Done ---------------------------------------------------------------------------
curl -fsS --max-time 5 -H "Host: ${DOMAIN:-localhost}" http://127.0.0.1/api/v1/health >/dev/null \
  || warn "Nginx is up but did not proxy the health check; run: sudo nginx -t"

public="${DOMAIN:+https://${DOMAIN}}"
public="${public:-http://$(curl -fsS --max-time 2 http://checkip.amazonaws.com 2>/dev/null || echo SERVER_IP)}"
log "Ledgerline API is running"
cat <<EOF

  Health:   ${public}/api/v1/health
  API docs: ${public}/docs
  Logs:     sudo journalctl -u ${SERVICE_NAME} -f
  Update:   sudo ${APP_DIR}/deploy/ec2/deploy.sh

  Frontend: set VITE_API_BASE_URL=${public}/api/v1 and add the frontend's URL to
            CORS_ORIGINS in ${ENV_FILE} (then: sudo systemctl restart ${SERVICE_NAME}).
  Demo data (optional):
            sudo -u ${APP_USER} ${VENV_DIR}/bin/pip install -q fpdf2 &&
            sudo systemd-run --wait --pipe --collect --uid=${APP_USER} \\
              -p EnvironmentFile=${ENV_FILE} -p WorkingDirectory=${BACKEND_DIR} \\
              ${VENV_DIR}/bin/python -m scripts.seed_demo
EOF
