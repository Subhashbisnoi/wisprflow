#!/usr/bin/env bash
# Deploy the latest code to an instance prepared with setup.sh.
#
#   sudo /opt/ledgerline/deploy/ec2/deploy.sh [--branch main] [--ref <commit-or-tag>]
#
# Steps: fetch -> install pinned dependencies -> migrate -> restart -> health check.
# If the new version fails its health check, the code is rolled back to the previous
# commit and restarted. Database migrations are NOT rolled back automatically; Ledgerline
# migrations are written to be additive, so the previous code keeps working.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The checkout below rewrites this very file; bash reads scripts lazily, so run from a copy.
if [[ -z "${LEDGERLINE_DEPLOY_COPY:-}" ]]; then
  copy_dir="$(mktemp -d)"
  cp "${SCRIPT_DIR}/deploy.sh" "${SCRIPT_DIR}/common.sh" "${copy_dir}/"
  LEDGERLINE_DEPLOY_COPY=1 exec bash "${copy_dir}/deploy.sh" "$@"
fi

# Never fail silently: report the failing line even if loading the helpers breaks.
trap 'printf "\033[1;31mxx\033[0m %s failed at line %s\n" "$(basename "$0")" "${LINENO}" >&2' ERR

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

BRANCH="main"
REF=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="${2:?}"; shift 2 ;;
    --ref)    REF="${2:?}"; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

require_root "$@"
[[ -d "${APP_DIR}/.git" && -f "${ENV_FILE}" ]] || die "Run setup.sh first."
cd "${APP_DIR}"

previous="$(as_app git rev-parse HEAD)"
log "Current version: ${previous:0:7}"

log "Fetching ${REF:-origin/${BRANCH}}"
as_app git fetch --quiet --prune --tags origin
target="$(as_app git rev-parse "${REF:-origin/${BRANCH}}^{commit}")"
if [[ "${target}" == "${previous}" ]]; then
  log "Already at ${target:0:7}; reinstalling and restarting anyway"
fi
as_app git checkout --quiet --force "${target}"
log "Deploying ${target:0:7}: $(as_app git log -1 --format=%s)"

rollback() {
  warn "Deploy failed; rolling the code back to ${previous:0:7}"
  as_app git checkout --quiet --force "${previous}"
  install_python_deps
  install_service_file
  systemctl restart "${SERVICE_NAME}"
  if wait_for_health 30; then
    warn "Rolled back to ${previous:0:7}; the API is serving the previous version."
  else
    journalctl -u "${SERVICE_NAME}" -n 50 --no-pager >&2
    die "Rollback also failed. Check the log above."
  fi
  exit 1
}
trap rollback ERR

install_python_deps
run_migrations
install_service_file
log "Restarting ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
if ! wait_for_health 30; then
  journalctl -u "${SERVICE_NAME}" -n 50 --no-pager >&2
  false   # triggers rollback
fi

trap - ERR
log "Deployed ${target:0:7}"
