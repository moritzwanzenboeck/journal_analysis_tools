"""Build-time only: install a checksum-pinned, relocatable Python distribution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

MANIFEST = Path(__file__).with_name('python_runtime.json')


def runtime_python(package, target, *, windowed=False):
    package = Path(package)
    embedded = package/'Journal Notebook Launcher.app/Contents/Resources/JournalTools/app/python'
    runtime = embedded if target.startswith('macos-') and embedded.is_dir() else package/'app/python'
    return runtime/('pythonw.exe' if windowed else 'python.exe') if target.startswith('windows-') else runtime/'bin/python3'


def isolated_environment():
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'TCL_LIBRARY', 'TK_LIBRARY',
                'JOURNAL_TOOLS_PYTHON', 'JOURNAL_TOOLS_BUILD_PYTHON'):
        environment.pop(key, None)
    return environment


def download_runtime(target, cache):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    entry = manifest['targets'][target]
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    url = manifest['provider']+'/releases/download/'+manifest['release']+'/'+entry['archive']
    archive = verified_download(cache/entry['archive'], url, entry['sha256'])
    return archive, manifest


def verified_download(archive, url, digest):
    if not archive.is_file():
        # A failed or interrupted download never becomes a reusable cache entry.
        with tempfile.TemporaryDirectory(prefix='download-', dir=archive.parent) as temporary:
            partial = Path(temporary)/'runtime.tar.gz'
            with urlopen(url, timeout=120) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
                raise ValueError('Python runtime checksum mismatch.')
            partial.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError(f'Python runtime checksum mismatch: {archive}')
    return archive


def extract_runtime(archive, destination):
    """Materialize archive links as files so ZIPs need no symlink privileges.

    Never extract devices, absolute paths or traversal paths. Python 3.10's
    tarfile has no extraction filter, so all paths and link targets are checked.
    """
    destination = Path(destination)
    destination.mkdir(parents=True)
    with tarfile.open(archive, 'r:gz') as tar:
        members = {member.name.rstrip('/'): member for member in tar.getmembers()}

        def checked(name):
            path = PurePosixPath(name)
            if ('\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
                    or not path.parts or path.parts[0] != 'python'):
                raise ValueError(f'Unsafe Python archive path: {name}')
            return path

        def resolve(member, seen):
            if member.name in seen:
                raise ValueError('Cyclic Python archive link.')
            if member.isreg():
                return member
            if not (member.issym() or member.islnk()):
                raise ValueError(f'Unsupported Python archive entry: {member.name}')
            link = member.linkname
            if PurePosixPath(link).is_absolute() or '\\' in link or ':' in link:
                raise ValueError(f'Unsafe Python archive link: {link}')
            name = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), link)
                                     if member.issym() else link)
            checked(name)
            return resolve(members[name], seen | {member.name})

        # Check the complete archive before writing payload files.
        for member in members.values():
            checked(member.name)
            if not member.isdir():
                resolve(member, set())
        for member in members.values():
            relative = checked(member.name).relative_to('python')
            output = destination.joinpath(*relative.parts)
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            source = resolve(member, set())
            with tar.extractfile(source) as reader, output.open('xb') as writer:
                shutil.copyfileobj(reader, writer)
            output.chmod(0o755 if source.mode & 0o111 else 0o644)


def bundle_python(package, target, cache):
    archive, manifest = download_runtime(target, cache)
    runtime = Path(package)/'app/python'
    extract_runtime(archive, runtime)
    licenses = verified_download(Path(cache)/('python-licenses-'+manifest['release']+'.rst'),
        'https://raw.githubusercontent.com/astral-sh/python-build-standalone/'+manifest['release']+'/python-licenses.rst',
        manifest['licenses_sha256'])
    shutil.copyfile(licenses, runtime/'THIRD_PARTY_LICENSES.rst')
    python = runtime_python(package, target)
    environment = isolated_environment()
    # Install wheels into the bundled interpreter, never the developer's venv.
    subprocess.run([str(python), '-m', 'pip', '--isolated', 'install', '--no-compile', '--no-warn-script-location',
                    '--only-binary=:all:', '-r', str(Path(package)/'requirements.txt')],
                   cwd=runtime, env=environment, check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], env=environment, check=True)
    packages = subprocess.check_output([str(python), '-m', 'pip', 'list', '--format=json'], env=environment)
    (Path(package)/'app/runtime-packages.json').write_text(
        json.dumps(json.loads(packages), indent=2)+'\n', encoding='utf-8')
    # Debug symbols and script entry points are unnecessary; the app uses -m.
    # Keep all library resources and third-party license files intact.
    for path in runtime.rglob('*.pdb'):
        path.unlink()
    scripts = runtime/('Scripts' if target.startswith('windows-') else 'bin')
    if scripts.is_dir():
        for path in scripts.iterdir():
            if path.is_file() and not path.name.startswith('python'):
                path.unlink()
    return dict(python_bundled=True, python_version=manifest['python_version'],
                runtime_provider=manifest['provider'], runtime_release=manifest['release'],
                runtime_sha256=manifest['targets'][target]['sha256'])
