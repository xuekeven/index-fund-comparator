#!/usr/bin/env bash

set -euo pipefail

managed_block_start="# BEGIN index-fund-comparator managed jobs"
managed_block_end="# END index-fund-comparator managed jobs"
script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
project_directory="$(CDPATH= cd -- "${script_directory}/.." && pwd)"
backend_directory="${project_directory}/backend"
python_binary="${backend_directory}/.venv/bin/python"
schedule_file="${script_directory}/schedules.conf"
crontab_binary="${IFC_CRONTAB_BIN:-crontab}"

if [[ ! -f "${schedule_file}" ]]; then
  echo "Schedule configuration is missing: ${schedule_file}" >&2
  exit 1
fi

source "${schedule_file}"
: "${SSE_FUNDS_SCHEDULE:?SSE_FUNDS_SCHEDULE is required}"
: "${SSE_DETAILS_SCHEDULE:?SSE_DETAILS_SCHEDULE is required}"
: "${SZSE_FUNDS_SCHEDULE:?SZSE_FUNDS_SCHEDULE is required}"
: "${SZSE_DETAILS_SCHEDULE:?SZSE_DETAILS_SCHEDULE is required}"

account_directory=""
if command -v getent >/dev/null 2>&1; then
  account_directory="$(getent passwd "$(id -un)" | cut -d: -f6)"
fi
if [[ -z "${account_directory}" ]]; then
  account_directory="$(CDPATH= cd -- && pwd)"
fi

sync_log="${IFC_SYNC_LOG:-${account_directory}/logs/index-fund-sync.log}"
log_directory="$(dirname -- "${sync_log}")"
if [[ "${sync_log}" != /* ]]; then
  echo "IFC_SYNC_LOG must be an absolute path: ${sync_log}" >&2
  exit 1
fi

printf -v quoted_backend '%q' "${backend_directory}"
printf -v quoted_python '%q' "${python_binary}"
printf -v quoted_log '%q' "${sync_log}"

sse_funds_runner="${quoted_python}"
sse_details_runner="${quoted_python}"
szse_funds_runner="${quoted_python}"
szse_details_runner="${quoted_python}"
if flock_binary="$(command -v flock 2>/dev/null)" && [[ -n "${flock_binary}" ]]; then
  printf -v quoted_flock '%q' "${flock_binary}"
  printf -v quoted_sse_funds_lock '%q' "${log_directory}/index-fund-sse-funds.lock"
  printf -v quoted_sse_details_lock '%q' "${log_directory}/index-fund-sse-details.lock"
  printf -v quoted_szse_funds_lock '%q' "${log_directory}/index-fund-szse-funds.lock"
  printf -v quoted_szse_details_lock '%q' "${log_directory}/index-fund-szse-details.lock"
  sse_funds_runner="${quoted_flock} -n ${quoted_sse_funds_lock} ${quoted_python}"
  sse_details_runner="${quoted_flock} -n ${quoted_sse_details_lock} ${quoted_python}"
  szse_funds_runner="${quoted_flock} -n ${quoted_szse_funds_lock} ${quoted_python}"
  szse_details_runner="${quoted_flock} -n ${quoted_szse_details_lock} ${quoted_python}"
fi

current_crontab="$(mktemp)"
cleaned_crontab="$(mktemp)"
generated_crontab="$(mktemp)"
trap 'rm -f "${current_crontab}" "${cleaned_crontab}" "${generated_crontab}"' EXIT

if ! "${crontab_binary}" -l > "${current_crontab}" 2>/dev/null; then
  : > "${current_crontab}"
fi

awk \
  -v block_start="${managed_block_start}" \
  -v block_end="${managed_block_end}" '
    $0 == block_start { in_managed_block = 1; next }
    $0 == block_end { in_managed_block = 0; next }
    in_managed_block { next }
    /app\.sync\.sse_funds/ { next }
    /app\.sync\.sse_details/ { next }
    /app\.sync\.szse_funds/ { next }
    /app\.sync\.szse_quotes/ { next }
    /app\.sync\.szse_details/ { next }
    { print }
    END { if (in_managed_block) exit 42 }
  ' "${current_crontab}" > "${cleaned_crontab}"

cp "${cleaned_crontab}" "${generated_crontab}"
if [[ -s "${generated_crontab}" ]]; then
  printf '\n' >> "${generated_crontab}"
fi
{
  printf '%s\n' "${managed_block_start}"
  printf '%s\n' "SHELL=/bin/bash"
  printf '%s\n' "CRON_TZ=Asia/Shanghai"
  printf '%s cd %s && %s -m app.sync.sse_funds >> %s 2>&1\n' \
    "${SSE_FUNDS_SCHEDULE}" "${quoted_backend}" "${sse_funds_runner}" "${quoted_log}"
  printf '%s cd %s && %s -m app.sync.sse_details >> %s 2>&1\n' \
    "${SSE_DETAILS_SCHEDULE}" "${quoted_backend}" "${sse_details_runner}" "${quoted_log}"
  printf '%s cd %s && %s -m app.sync.szse_funds >> %s 2>&1\n' \
    "${SZSE_FUNDS_SCHEDULE}" "${quoted_backend}" "${szse_funds_runner}" "${quoted_log}"
  printf '%s cd %s && %s -m app.sync.szse_details >> %s 2>&1\n' \
    "${SZSE_DETAILS_SCHEDULE}" "${quoted_backend}" "${szse_details_runner}" "${quoted_log}"
  printf '%s\n' "${managed_block_end}"
} >> "${generated_crontab}"

action="${1:-install}"
case "${action}" in
  install)
    if [[ ! -x "${python_binary}" ]]; then
      echo "Python environment is missing: run 'uv sync --locked' in backend first." >&2
      exit 1
    fi
    mkdir -p "${log_directory}"
    "${crontab_binary}" "${generated_crontab}"
    echo "Installed index-fund-comparator cron jobs from ${schedule_file}"
    ;;
  print)
    cat "${generated_crontab}"
    ;;
  remove)
    "${crontab_binary}" "${cleaned_crontab}"
    echo "Removed index-fund-comparator cron jobs"
    ;;
  *)
    echo "Usage: $0 [install|print|remove]" >&2
    exit 2
    ;;
esac
