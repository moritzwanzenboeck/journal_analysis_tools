#!/bin/bash
set -euo pipefail
# Resolve once before changing directories; quote paths containing spaces.
tools_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd /private/tmp
exec python3 -m notebook \
  --ServerApp.root_dir="$(dirname -- "$tools_dir")" \
  "$tools_dir/create_journal_analysis.ipynb" "$@"
