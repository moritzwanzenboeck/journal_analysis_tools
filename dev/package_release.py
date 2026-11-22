"""Build and ZIP a self-contained launcher, Python and notebook tools.

Run on each target OS/architecture. Download and install dependencies at build
time only. Include runtime licenses; exclude local venvs, settings and projects.
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
from dev.bundle_python import bundle_python, isolated_environment, runtime_python

TARGETS = ('windows-x86_64', 'macos-x86_64', 'macos-arm64')
SOURCE_FILES = (
    'README.md', 'requirements.txt', 'notebook_launcher.py', 'start_notebook.command',
    'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb',
    'app/__init__.py', 'app/launcher.py', 'app/notebook_services.py', 'app/voila_app.py',
    'app/assets/dashboard.html', 'app/assets/journal_notebook.html.j2',
    'app/journal_tools.py', 'app/text_tools.py', 'app/paper_tools.py', 'app/macos_bootstrap.py', 'app/launch_notebook.sh', 'app/assets/app.icns',
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
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
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


def build_release(root, version, output, *, runtime_cache=None):
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
        runtime_metadata = bundle_python(package, target, runtime_cache or root/'dist/runtime-cache')
        if target.startswith('macos-'):
            install(package, package, portable=True)
            app_name = APP_NAME
            shutil.rmtree(package/'app/python')
            (package/'app/runtime-packages.json').unlink()
        else:
            install_windows(package, package, portable=True)
            app_name = WINDOWS_APP_NAME
        metadata = dict(version=version, target=target, source_commit=source_revision(root),
                        app=app_name, **runtime_metadata)
        (package/'RELEASE.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
        (package/'INSTALL.txt').write_text(
            'JOURNAL ANALYSIS TOOLS '+version+'\n\n'
            'Python, Voilà, Jupyter and the compiled launcher are included. No setup commands are needed.\n'
            '1. Extract the complete folder onto a LOCAL disk. Keep all its files together.\n'
            '2. Double-click '+app_name+'.\n'
            '3. Choose a tool in the local web app that opens in your browser.\n\n' +
            ('On Mac the app contains its Python and tools; editable notebooks are kept in your user account.\n'
             if target.startswith('macos-') else 'Keep app/python with the tools.\n') +
            'No packages or runtime are downloaded or installed on startup.\n'
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
        metadata = json.loads((package/'RELEASE.json').read_text(encoding='utf-8'))
        if metadata['target'] != native_target() or metadata.get('python_bundled') is not True:
            raise ValueError('Cannot verify a release for another platform on this machine.')
        environment = dict(isolated_environment(), JOURNAL_TOOLS_NO_DIALOG='1',
                           JOURNAL_TOOLS_WORKSPACE=str(destination/'Notebook workspace'))
        # No Python or package manager from PATH, user site or the build venv.
        environment['PATH'] = str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'System32') if os.name == 'nt' else '/usr/bin:/bin'
        # A user's unrelated Python settings must not break native app startup.
        native_environment = dict(environment, PYTHONHOME=str(destination/'missing-python'),
                                  PYTHONPATH=str(destination/'missing-packages'))
        if sys.platform == 'darwin':
            validate_macos_app(package/APP_NAME)
            script = subprocess.check_output(['/usr/bin/osadecompile', str(package/APP_NAME/'Contents/Resources/Scripts/main.scpt')], text=True)
            if 'set toolsFolder to ""' not in script or sys.executable in script:
                raise ValueError('Portable app contains a machine-specific path.')
            # Exercise the compiled Finder entry point, not just its shell shortcut.
            native_environment['JOURNAL_TOOLS_APP_CHECK'] = '1'
            command = [str(package/APP_NAME/'Contents/MacOS/applet')]
        else:
            command = [str(package/WINDOWS_APP_NAME), '--check']
        subprocess.run(command, cwd=destination, env=native_environment, check=True, timeout=60)
        subprocess.run([str(runtime_python(package, native_target())), '-I', '-B',
                        str(Path(__file__).with_name('check_bundled_runtime.py')), str(package)],
                       cwd=destination, env=environment, check=True, timeout=240)
        if sys.platform == 'darwin':
            validate_macos_app(package/APP_NAME)
    print('Verified extracted, relocated native release:', archive.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'dist')
    parser.add_argument('--runtime-cache', type=Path, help='Reuse verified runtime downloads between builds')
    args = parser.parse_args()
    archive = build_release(Path(__file__).resolve().parents[1], args.version, args.output, runtime_cache=args.runtime_cache)
    verify_archive(archive)
    print('Ready for release:', archive)


if __name__ == '__main__':
    main()
