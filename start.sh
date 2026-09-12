#!/usr/bin/env bash
#
# Start Cerebrum from Git Bash / WSL-style shells.
#
#     ./start.sh              bridge + web console, opens the browser
#     ./start.sh --check      verify keys, then exit
#     ./start.sh --no-web     bridge only
#     ./start.sh --force      start even though the checks failed
#     ./start.sh --no-browser do not open a tab
#
# This hands off to start.ps1 rather than reimplementing it. Stopping two
# services cleanly on Windows means killing process trees - npm spawns the
# Next server as a child, and killing only npm leaves node holding port 3000 -
# and that is already solved once, in PowerShell. Two copies of that logic
# would drift, and the copy you were not using would be the broken one.
#
# -ExecutionPolicy Bypass because the default policy on Windows is Restricted,
# which blocks local .ps1 files outright.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$root/start.ps1"

# PowerShell wants a Windows path; Git Bash hands us /c/Users/...
if command -v cygpath >/dev/null 2>&1; then
  script="$(cygpath -w "$script")"
fi

args=()
for arg in "$@"; do
  case "$arg" in
    --check|-c)     args+=("-Check") ;;
    --no-web|-n)    args+=("-NoWeb") ;;
    --force|-f)     args+=("-Force") ;;
    --no-browser)   args+=("-NoBrowser") ;;
    --help|-h)
      sed -n '3,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "start.sh: unknown option '$arg' (try --help)" >&2
      exit 2
      ;;
  esac
done

if ! command -v powershell.exe >/dev/null 2>&1; then
  echo "start.sh: powershell.exe not found on PATH." >&2
  echo "Run the services yourself:" >&2
  echo "  PYTHONPATH=backend .venv/Scripts/python.exe -m interview_agent.bridge" >&2
  echo "  (cd web && npm run dev)" >&2
  exit 1
fi

# Branching on the count rather than "${args[@]:-}": that expansion sends an
# empty string when there are no flags, and PowerShell rejects it as a
# positional argument to a script that only takes switches.
if [ ${#args[@]} -gt 0 ]; then
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$script" "${args[@]}"
else
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$script"
fi
