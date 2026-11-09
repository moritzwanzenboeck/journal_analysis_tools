#!/bin/bash
# Shared implementation for the Finder notebook launchers.
set -euo pipefail

tools_dir="$1"
notebook_name="$2"
shift 2
cd /private/tmp

fail() {
  printf '%s\n' "$1" >&2
  if [[ "${JOURNAL_TOOLS_NO_DIALOG:-0}" != 1 && -x /usr/bin/osascript ]]; then
    /usr/bin/osascript - "$1" <<'APPLESCRIPT' || true
on run argv
  display alert "Could not open notebook" message (item 1 of argv) as critical
end run
APPLESCRIPT
  fi
  exit 1
}

[[ -f "$tools_dir/$notebook_name" ]] || fail "Notebook not found: $tools_dir/$notebook_name"
candidates=(
  "${JOURNAL_TOOLS_PYTHON:-}"
  "$tools_dir/.venv/bin/python3"
  "$tools_dir/.venv/bin/python"
  "$(command -v python3 || true)"
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.10/bin/python3
  /opt/homebrew/bin/python3
  /usr/local/bin/python3
)
selected_python=''
for candidate in "${candidates[@]}"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c \
      'import sys; assert sys.version_info >= (3, 10); import notebook, ipykernel, ipywidgets' >/dev/null 2>&1; then
    selected_python="$candidate"
    break
  fi
done
[[ -n "$selected_python" ]] || fail "This notebook needs Python 3.10 or newer with Jupyter Notebook, ipykernel and ipywidgets. Install the repository requirements into your Python environment, or use the standalone Journal Analysis Tools app."
if [[ "${1:-}" == '--check' ]]; then
  printf 'Python: %s\nNotebook: %s\nRoot: %s\n' "$selected_python" "$tools_dir/$notebook_name" "$(dirname -- "$tools_dir")"
  exit 0
fi
exec "$selected_python" -m notebook \
  --ServerApp.root_dir="$(dirname -- "$tools_dir")" \
  --ServerApp.open_browser=True \
  "$tools_dir/$notebook_name" "$@"
