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
grep -q '^0 16 \* \* 1-5 .*app\.sync\.sse_details' "${FAKE_CRONTAB_STATE}"
grep -q '/usr/local/bin/unrelated-backup' "${FAKE_CRONTAB_STATE}"

run_manager remove

if grep -q 'app\.sync\.sse_' "${FAKE_CRONTAB_STATE}"; then
  echo "Managed jobs were not removed" >&2
  exit 1
fi
grep -q '/usr/local/bin/unrelated-backup' "${FAKE_CRONTAB_STATE}"
