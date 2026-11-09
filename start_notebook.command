#!/bin/bash
# Open the shared launcher for both notebook services.
set -euo pipefail
script_path="${BASH_SOURCE[0]}"
[[ "$script_path" = /* ]] || script_path="$PWD/$script_path"
tools_dir="$(dirname -- "$script_path")"
exec /bin/bash "$tools_dir/app/launch_notebook.sh" "$tools_dir" "$@"
