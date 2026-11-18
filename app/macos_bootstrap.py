"""Launch the embedded Mac tools with editable, per-user notebook copies."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

NOTEBOOKS = ('create_journal_analysis.ipynb', 'clean_and_count_text.ipynb')


def prepare_workspace(tools, base):
    """Retain edited notebooks; updated bundled templates get their own workspace."""
    tools, base = Path(tools).resolve(), Path(base).expanduser().resolve()
    digest = hashlib.sha256()
    for name in NOTEBOOKS:
        digest.update(name.encode('utf-8'))
        digest.update((tools / name).read_bytes())
    workspace = base / digest.hexdigest()[:16]
    base.mkdir(parents=True, exist_ok=True)
    if workspace.is_dir():
        # Recover an accidentally deleted notebook without replacing any existing one.
        for name in NOTEBOOKS:
            if not (workspace / name).exists():
                with (workspace / name).open('xb') as target:
                    target.write((tools / name).read_bytes())
        return workspace
    with tempfile.TemporaryDirectory(prefix='.notebooks-', dir=base) as temporary:
        staged = Path(temporary) / 'workspace'
        staged.mkdir()
        for name in NOTEBOOKS:
            shutil.copyfile(tools / name, staged / name)
        try:
            staged.rename(workspace)
        except OSError:
            if not workspace.is_dir():
                raise
    return workspace


def main():
    sys.dont_write_bytecode = True
    tools = Path(sys.argv.pop(1)).resolve()
    base = Path(os.environ.get('JOURNAL_TOOLS_WORKSPACE',
                Path.home() / 'Library/Application Support/Journal Analysis Tools/Notebooks'))
    workspace = prepare_workspace(tools, base)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY'):
        os.environ.pop(key, None)
    os.environ.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
                      JOURNAL_TOOLS_NOTEBOOK_ROOT=str(workspace))
    documents = Path.home() / 'Documents'
    os.environ.setdefault('JOURNAL_TOOLS_PROJECTS_ROOT', str(documents if documents.is_dir() else Path.home()))
    sys.path.insert(0, str(tools))
    from app.launcher import main as launch
    launch()


if __name__ == '__main__':
    main()
