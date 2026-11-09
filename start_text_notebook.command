#!/bin/bash
# Double-click in Finder to open the text-cleaning notebook.
set -euo pipefail
script_path="${BASH_SOURCE[0]}"
[[ "$script_path" = /* ]] || script_path="$PWD/$script_path"
tools_dir="$(dirname -- "$script_path")"
exec /bin/bash "$tools_dir/launch_notebook.sh" "$tools_dir" clean_and_count_text.ipynb "$@"
