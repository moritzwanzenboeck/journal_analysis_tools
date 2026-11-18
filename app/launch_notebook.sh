#!/bin/bash
# Shared entry point for the Finder app and .command shortcuts.
set -euo pipefail

tools_dir="$1"
shift
# Finder/VS Code may inherit a stale working directory on a mounted drive.
# Resolve a relative checkout before leaving it, then start Python locally.
[[ "$tools_dir" = /* ]] || tools_dir="$PWD/$tools_dir"
cd /tmp
# Preserve the old notebook-specific script interface as a service shortcut.
# Use positional arguments: macOS Bash 3.2 treats empty arrays as unset with -u.
case "${1:-}" in
  create_journal_analysis.ipynb) shift; set -- --service project "$@" ;;
  clean_and_count_text.ipynb) shift; set -- --service text "$@" ;;
  *.ipynb) printf 'Unknown notebook: %s\n' "$1" >&2; exit 1 ;;
esac

fail() {
  printf '%s\n' "$1" >&2
  if [[ "${JOURNAL_TOOLS_NO_DIALOG:-0}" != 1 && -x /usr/bin/osascript ]]; then
    /usr/bin/osascript - "$1" <<'APPLESCRIPT' || true
on run argv
  display alert "Could not open notebook launcher" message (item 1 of argv) as critical
end run
APPLESCRIPT
  fi
  exit 1
}

[[ -f "$tools_dir/notebook_launcher.py" ]] || fail "Launcher not found: $tools_dir/notebook_launcher.py"
# Packaged Macs keep executable code inside the signed app bundle.
embedded_tools="$tools_dir/Journal Notebook Launcher.app/Contents/Resources/JournalTools"
if [[ -z "${JOURNAL_TOOLS_PYTHON:-}" && -f "$embedded_tools/app/macos_bootstrap.py" && -x "$embedded_tools/app/python/bin/python3" ]]; then
  exec "$embedded_tools/app/python/bin/python3" -I -B "$embedded_tools/app/macos_bootstrap.py" "$embedded_tools" "$@"
fi
candidates=(
  "${JOURNAL_TOOLS_BUILD_PYTHON:-}"
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
# An explicit environment choice takes precedence on both Windows and macOS.
if [[ -n "${JOURNAL_TOOLS_PYTHON:-}" ]]; then
  candidates=("$JOURNAL_TOOLS_PYTHON")
elif [[ -d "$tools_dir/app/python" ]]; then
  candidates=("$tools_dir/app/python/bin/python3")
  unset PYTHONHOME PYTHONPATH VIRTUAL_ENV TCL_LIBRARY TK_LIBRARY
  export PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
elif [[ -x "$tools_dir/.venv/bin/python3" ]]; then
  candidates=("$tools_dir/.venv/bin/python3")
elif [[ -x "$tools_dir/.venv/bin/python" ]]; then
  candidates=("$tools_dir/.venv/bin/python")
fi
selected_python=''
for candidate in "${candidates[@]}"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c \
      'import sys; assert sys.version_info >= (3, 10); import tkinter, notebook, ipykernel, ipywidgets, anywidget, psutil' >/dev/null 2>&1; then
    selected_python="$candidate"
    break
  fi
done
if [[ -z "$selected_python" ]]; then
  if [[ -d "$tools_dir/app/python" && -z "${JOURNAL_TOOLS_PYTHON:-}" ]]; then
    fail "The bundled runtime could not start. Extract the complete platform ZIP again onto a local disk."
  fi
  fail "The launcher needs Python 3.10 or newer with Tk and the packages in requirements.txt. For source checkouts, follow dev/SETUP.md or set JOURNAL_TOOLS_PYTHON."
fi
exec "$selected_python" "$tools_dir/notebook_launcher.py" "$@"
