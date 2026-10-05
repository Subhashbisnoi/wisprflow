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
NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"

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

install_python_deps() {
  log "Installing Python dependencies (pinned, hash-checked)"
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    as_app python3 -m venv "${VENV_DIR}"
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
