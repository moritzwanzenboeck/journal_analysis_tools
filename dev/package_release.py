"""Build and ZIP a relocatable, precompiled launcher with its notebook tools.

Run on each target OS/architecture. Python/Jupyter are not bundled. Only an
explicit list of source files is packaged; no venv, settings or project data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev.build_notebook_launchers import APP_NAME, WINDOWS_APP_NAME, install, install_windows, validate_macos_app

TARGETS = ('windows-x86_64', 'macos-x86_64', 'macos-arm64')
SOURCE_FILES = (
    'README.md', 'requirements.txt', 'notebook_launcher.py', 'start_notebook.command',
    'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb',
    'app/__init__.py', 'app/launcher.py', 'app/notebook_services.py',
    'app/journal_tools.py', 'app/text_tools.py', 'app/paper_tools.py', 'app/launch_notebook.sh', 'app/assets/app.icns',
    'dev/SETUP.md', 'dev/analysis_reference.md', 'dev/README.md',
    'dev/build_notebook_launchers.py', 'dev/windows_launcher.cs',
)


def validate_version(version):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?', version):
        raise ValueError('Version must be a release tag such as v1.1.0.')
    return version


def native_target():
    machine = platform.machine().lower()
    if sys.platform == 'win32' and machine in ('amd64', 'x86_64'):
        return 'windows-x86_64'
    if sys.platform == 'darwin' and machine in ('x86_64', 'arm64'):
        return 'macos-' + machine
    raise RuntimeError('Build releases on Windows x86_64, Intel macOS or Apple Silicon macOS.')


def asset_name(version, target):
    validate_version(version)
    if target not in TARGETS:
        raise ValueError('Unsupported release target.')
    return f'Journal-Analysis-Tools-{version}-{target}.zip'


def copy_sources(root, package):
    package.mkdir(parents=True)
    for name in SOURCE_FILES:
        source = root / name
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f'Required release source is missing or is a symlink: {source}')
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == '.ipynb':
            notebook = json.loads(source.read_text(encoding='utf-8'))
            notebook.get('metadata', {}).pop('widgets', None)
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    cell['execution_count'] = None
                    cell['outputs'] = []
            destination.write_text(json.dumps(notebook, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
        else:
            shutil.copyfile(source, destination)
    # Source checkouts on shared drives can have their executable bits stripped.
    for name in ('start_notebook.command', 'app/launch_notebook.sh'):
        (package/name).chmod(0o755)


def write_archive(package, archive):
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        zipped.write(package, package.name + '/')
        for path in sorted(package.rglob('*')):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            if path.is_symlink():
                raise ValueError(f'Unexpected symlink in release payload: {path}')
            zipped.write(path, (Path(package.name)/path.relative_to(package)).as_posix())


def source_revision(root):
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def build_release(root, version, output):
    validate_version(version)
    root, output = Path(root).resolve(), Path(output).expanduser().resolve()
    target = native_target()
    archive = output/asset_name(version, target)
    checksum = archive.with_suffix('.zip.sha256')
    if archive.exists() or checksum.exists():
        raise FileExistsError(f'Release artifact already exists: {archive}')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='journal-release-') as temporary:
        package = Path(temporary)/archive.stem
        copy_sources(root, package)
        if target.startswith('macos-'):
            install(package, package, portable=True)
            app_name = APP_NAME
        else:
            install_windows(package, package, portable=True)
            app_name = WINDOWS_APP_NAME
        metadata = dict(version=version, target=target, source_commit=source_revision(root),
                        python_bundled=False, python_requirement='3.10+', app=app_name)
        (package/'RELEASE.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
        (package/'INSTALL.txt').write_text(
            'JOURNAL ANALYSIS TOOLS '+version+'\n\n'
            'This archive includes the compiled launcher. No compiler or build command is needed.\n'
            '1. Extract the complete folder onto a LOCAL disk. Keep all its files together.\n'
            '2. Install Python 3.10+ with Tk, then follow the one-time Python/Jupyter setup in dev/SETUP.md.\n'
            '3. Double-click '+app_name+'. Start a service, then choose Run All Cells in the notebook.\n\n'
            'Python/Jupyter are not bundled. Do not copy an existing .venv from another computer.\n'
            'Project output may be saved on a shared drive, while this tools folder remains local.\n', encoding='utf-8')
        try:
            write_archive(package, archive)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            checksum.write_text(f'{digest}  {archive.name}\n', encoding='ascii')
        except BaseException:
            archive.unlink(missing_ok=True)
            checksum.unlink(missing_ok=True)
            raise
    return archive


def verify_archive(archive):
    """Extract/move the download, then check its signature and native startup."""
    archive = Path(archive).resolve()
    checksum = archive.with_suffix('.zip.sha256').read_text(encoding='ascii').split()[0]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        raise ValueError('Release checksum mismatch.')
    with tempfile.TemporaryDirectory(prefix="journal's extracted release ä ") as temporary:
        destination = Path(temporary)
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(archive), str(destination)], check=True)
        else:
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(destination)
        original = destination/archive.stem
        package = destination/'Moved journal tools ä'
        original.rename(package)
        metadata = json.loads((package/'RELEASE.json').read_text())
        if metadata['target'] != native_target():
            raise ValueError('Cannot verify a release for another platform on this machine.')
        # A recipient creates a fresh local venv. Use the test machine's installed
        # packages for this offline check; no build-directory paths are available.
        subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', '--without-pip', str(package/'.venv')], check=True)
        environment = dict(os.environ, JOURNAL_TOOLS_NO_DIALOG='1')
        for key in ('JOURNAL_TOOLS_PYTHON', 'JOURNAL_TOOLS_BUILD_PYTHON'):
            environment.pop(key, None)
        if sys.platform == 'darwin':
            validate_macos_app(package/APP_NAME)
            script = subprocess.check_output(['/usr/bin/osadecompile', str(package/APP_NAME/'Contents/Resources/Scripts/main.scpt')], text=True)
            if 'set toolsFolder to ""' not in script or sys.executable in script:
                raise ValueError('Portable app contains a machine-specific path.')
            command = ['/bin/bash', str(package/'start_notebook.command'), '--check']
        else:
            command = [str(package/WINDOWS_APP_NAME), '--check']
        subprocess.run(command, cwd=package, env=environment, check=True, timeout=60)
    print('Verified extracted, relocated native release:', archive.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'dist')
    args = parser.parse_args()
    archive = build_release(Path(__file__).resolve().parents[1], args.version, args.output)
    verify_archive(archive)
    print('Ready for release:', archive)


if __name__ == '__main__':
    main()
