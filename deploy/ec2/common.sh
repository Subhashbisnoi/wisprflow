# Shared settings and helpers for setup.sh and deploy.sh. Sourced, not executed.
# shellcheck shell=bash
# shellcheck disable=SC2034  # variables are used by the scripts that source this file

APP_USER="ledgerline"
APP_DIR="/opt/ledgerline"                 # git checkout (read-only to the service)
BACKEND_DIR="${APP_DIR}/backend"
VENV_DIR="${BACKEND_DIR}/.venv"
ENV_DIR="/etc/ledgerline"
ENV_FILE="${ENV_DIR}/ledgerline.env"
DATA_DIR="/var/lib/ledgerline"            # writable: uploaded documents
SERVICE_NAME="ledgerline-api"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
# Local port for Uvicorn. 8001 so it can share an instance with another app on 8000.
# Read from the env file when set there, so setup.sh and deploy.sh always agree. The file
# does not exist before the first setup run, and this file is sourced under `set -e`,
# so only read it when present.
API_PORT="${LEDGERLINE_PORT:-}"
if [[ -z "${API_PORT}" && -r "${ENV_FILE}" ]]; then
  API_PORT="$(sed -n 's/^LEDGERLINE_PORT=//p' "${ENV_FILE}" | tail -n1)"
fi
API_PORT="${API_PORT:-8001}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/api/v1/health"

# --- Operating system ------------------------------------------------------------------
# Ubuntu/Debian (apt, sites-available) and Amazon Linux 2023/RHEL family (dnf, conf.d).
# shellcheck source=/dev/null  # present on the target server, not on dev machines
OS_ID="$( { . /etc/os-release && echo "${ID:-unknown}"; } 2>/dev/null || echo unknown)"
case "${OS_ID}" in
  ubuntu|debian) OS_FAMILY="debian" ;;
  amzn|rhel|centos|rocky|almalinux|fedora) OS_FAMILY="rhel" ;;
  *) OS_FAMILY="unknown" ;;
esac

if [[ "${OS_FAMILY}" == "debian" ]]; then
  NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}"
  NGINX_ENABLED_LINK="/etc/nginx/sites-enabled/${SERVICE_NAME}"
else
  NGINX_SITE="/etc/nginx/conf.d/${SERVICE_NAME}.conf"
  NGINX_ENABLED_LINK=""
fi

# Python 3.12+ interpreter used to create the virtualenv. Amazon Linux 2023's default
# python3 is 3.9, so prefer an explicit python3.12/3.13 when present.
find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3; do
    if command -v "${candidate}" >/dev/null 2>&1 &&
       "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      command -v "${candidate}"
      return 0
    fi
  done
  return 1
}

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ ${EUID} -eq 0 ]] || die "Run with sudo: sudo $0 $*"
}

as_app() {
  sudo -u "${APP_USER}" -H -- "$@"
}

# Run a command as the service would: same user, environment file and working directory.
# systemd parses the env file, so values are handled exactly like the running service.
run_like_service() {
  systemd-run --quiet --wait --pipe --collect \
    --uid="${APP_USER}" --gid="${APP_USER}" \
    -p EnvironmentFile="${ENV_FILE}" \
    -p WorkingDirectory="${BACKEND_DIR}" \
    -- "$@"
}

# Render the systemd unit with this instance's port.
install_service_file() {
  # Also rewrites the hard-coded port of older revisions, so a rollback never lands on 8000.
  sed -e "s|__API_PORT__|${API_PORT}|g" -e "s|--port 8000 |--port ${API_PORT} |" \
    "${APP_DIR}/deploy/ec2/ledgerline-api.service" > "${SERVICE_FILE}"
  chmod 644 "${SERVICE_FILE}"
  systemctl daemon-reload
}

# Print the process listening on a TCP port (empty if free).
port_owner() {
  ss -ltnpH "sport = :$1" 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -n1
}

install_python_deps() {
  log "Installing Python dependencies (pinned, hash-checked)"
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    local python
    python="$(find_python)" || die "Python 3.12+ not found. Re-run setup.sh to install it."
    as_app "${python}" -m venv "${VENV_DIR}"
  fi
  as_app "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
  as_app "${VENV_DIR}/bin/pip" install --quiet --require-hashes --no-deps \
    -r "${BACKEND_DIR}/requirements.lock"
}

run_migrations() {
  log "Applying database migrations"
  run_like_service "${VENV_DIR}/bin/alembic" upgrade head
}

wait_for_health() {
  local attempts="${1:-30}"
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1; then
      log "API is healthy (${HEALTH_URL})"
      return 0
    fi
    sleep 2
  done
  return 1
}

env_value() {
  # Print the value of KEY from the env file (empty if missing).
  sed -n "s/^$1=//p" "${ENV_FILE}" | tail -n1
}

env_is_configured() {
  local db key
  db="$(env_value DB_URL)"
  key="$(env_value OPENAI_API_KEY)"
  [[ -n "${db}" && "${db}" != *"USER:PASSWORD@HOST"* && -n "${key}" && "${key}" != "sk-..." ]]
}
