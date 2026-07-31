#!/usr/bin/env bash
set -euo pipefail

package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$package_root"

pick_python() {
  local candidates=()
  [[ -n "${VOICE_TEXT_PYTHON:-}" ]] && candidates+=("$VOICE_TEXT_PYTHON")
  candidates+=(
    "$package_root/.venv/bin/python"
    "python3.13" "python3.12" "python3.11" "python3"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      if "$candidate" -c 'import sys, importlib.util; raise SystemExit(0 if sys.version_info >= (3, 11) and importlib.util.find_spec("pytest") else 1)' >/dev/null 2>&1; then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

python_bin="$(pick_python || true)"
if [[ -z "$python_bin" ]]; then
  echo "voice-text pytest needs Python 3.11+ with pytest." >&2
  exit 1
fi

if [[ "$#" -eq 0 ]]; then
  set -- "tests"
fi

exec env PYTHONPATH="$package_root${PYTHONPATH:+:$PYTHONPATH}" \
  "$python_bin" -m pytest "$@"
