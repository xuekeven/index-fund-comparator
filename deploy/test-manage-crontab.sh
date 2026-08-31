#!/usr/bin/env bash

set -euo pipefail

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
test_directory="$(mktemp -d)"
trap 'rm -rf "${test_directory}"' EXIT

fake_crontab="${test_directory}/crontab"
export FAKE_CRONTAB_STATE="${test_directory}/state"

printf '%s\n' \
  'SHELL=/bin/bash' \
  '15 2 * * * /usr/local/bin/unrelated-backup' \
  '0 9 * * 1 cd /old/backend && .venv/bin/python -m app.sync.sse_funds' \
  '0 20 * * 1-5 cd /old/backend && .venv/bin/python -m app.sync.sse_details' \
  '0 8 * * 1 cd /old/backend && .venv/bin/python -m app.sync.szse_funds' \
  '0 15 * * 1-5 cd /old/backend && .venv/bin/python -m app.sync.szse_quotes' \
  '0 7 * * 1 cd /old/backend && .venv/bin/python -m app.sync.csrc_funds' \
  '0 8 * * 1-5 cd /old/backend && .venv/bin/python -m app.sync.csrc_details' \
  > "${FAKE_CRONTAB_STATE}"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'if [[ "${1:-}" == "-l" ]]; then' \
  '  [[ -f "${FAKE_CRONTAB_STATE}" ]] || exit 1' \
  '  cat "${FAKE_CRONTAB_STATE}"' \
  'else' \
  '  cp "$1" "${FAKE_CRONTAB_STATE}"' \
  'fi' \
  > "${fake_crontab}"
chmod +x "${fake_crontab}"

run_manager() {
  IFC_CRONTAB_BIN="${fake_crontab}" \
  IFC_SYNC_LOG="${test_directory}/index-fund-sync.log" \
    "${script_directory}/manage-crontab.sh" "$1" >/dev/null
}

run_manager install
run_manager install

[[ "$(grep -c 'app\.sync\.sse_funds' "${FAKE_CRONTAB_STATE}")" == "1" ]]
[[ "$(grep -c 'app\.sync\.sse_details' "${FAKE_CRONTAB_STATE}")" == "1" ]]
[[ "$(grep -c 'app\.sync\.szse_funds' "${FAKE_CRONTAB_STATE}")" == "1" ]]
[[ "$(grep -c 'app\.sync\.szse_details' "${FAKE_CRONTAB_STATE}")" == "1" ]]
[[ "$(grep -c 'app\.sync\.csrc_funds' "${FAKE_CRONTAB_STATE}")" == "1" ]]
[[ "$(grep -c 'app\.sync\.csrc_details' "${FAKE_CRONTAB_STATE}")" == "1" ]]
if grep -q 'app\.sync\.szse_quotes' "${FAKE_CRONTAB_STATE}"; then
  echo "Legacy SZSE quote job was not removed" >&2
  exit 1
fi
grep -q '^0 16 \* \* 1-5 .*app\.sync\.sse_details' "${FAKE_CRONTAB_STATE}"
grep -q '^0 9 \* \* 1 .*app\.sync\.szse_funds' "${FAKE_CRONTAB_STATE}"
grep -q '^0 22 \* \* 1-5 .*app\.sync\.szse_details' "${FAKE_CRONTAB_STATE}"
grep -q '^0 9 1 \* \* .*app\.sync\.csrc_funds' "${FAKE_CRONTAB_STATE}"
grep -q '^0 22 \* \* 1-5 .*app\.sync\.csrc_details' "${FAKE_CRONTAB_STATE}"
[[ "$(grep -c 'flock -w 14400 .*backend/\.sync\.lock' "${FAKE_CRONTAB_STATE}")" == "6" ]]
[[ "$(grep -c 'IFC_SYNC_METHOD=scheduled' "${FAKE_CRONTAB_STATE}")" == "6" ]]
grep -q '/usr/local/bin/unrelated-backup' "${FAKE_CRONTAB_STATE}"

run_manager remove

if grep -Eq 'app\.sync\.(sse|szse|csrc)_' "${FAKE_CRONTAB_STATE}"; then
  echo "Managed jobs were not removed" >&2
  exit 1
fi
grep -q '/usr/local/bin/unrelated-backup' "${FAKE_CRONTAB_STATE}"
