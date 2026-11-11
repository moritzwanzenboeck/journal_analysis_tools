"""Publish release assets only after all three native packages pass validation.

Called by the tag workflow with GITHUB_TOKEN, GITHUB_REPOSITORY and GITHUB_SHA.
Tokens stay in memory; release files are uploaded from the verified CI artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dev.package_release import TARGETS, asset_name, validate_version


def validate_assets(version, directory, revision):
    validate_version(version)
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Release commit SHA is required.')
    directory = Path(directory)
    expected = {asset_name(version, target) for target in TARGETS}
    actual = {path.name for path in directory.glob('*.zip')}
    if actual != expected:
        raise ValueError(f'Expected all three native release ZIPs; found {sorted(actual)}')
    files = []
    for target in TARGETS:
        archive = directory/asset_name(version, target)
        checksum = archive.with_suffix('.zip.sha256')
        data = archive.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        expected_line = f'{digest}  {archive.name}'
        if checksum.read_text(encoding='ascii').strip() != expected_line:
            raise ValueError(f'Invalid checksum for {archive.name}')
        with zipfile.ZipFile(archive) as zipped:
            metadata = json.loads(zipped.read(archive.stem+'/RELEASE.json'))
            if (metadata.get('version') != version or metadata.get('target') != target
                    or metadata.get('source_commit') != revision or metadata.get('python_bundled') is not False):
                raise ValueError(f'Invalid release metadata for {archive.name}')
            required = ['notebook_launcher.py', 'requirements.txt', 'app/launcher.py', 'app/paper_tools.py',
                        'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb', 'INSTALL.txt']
            required += ['Journal Notebook Launcher.exe'] if target.startswith('windows-') else ['Journal Notebook Launcher.app/Contents/MacOS/applet']
            for name in required:
                if archive.stem+'/'+name not in zipped.namelist():
                    raise ValueError(f'Release is missing {name}')
        files.extend([archive, checksum])
    return files


class GitHub:
    def __init__(self, token):
        if not token:
            raise ValueError('GITHUB_TOKEN is required.')
        self.token = token

    def request(self, url, method='GET', body=None, content_type='application/json'):
        if not url.startswith(('https://api.github.com/', 'https://uploads.github.com/')):
            raise ValueError('Unexpected GitHub API host.')
        headers = {'Authorization': 'Bearer '+self.token, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'JournalToolsRelease'}
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        if data is not None:
            headers['Content-Type'] = content_type
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method),
                         context=ssl.create_default_context(), timeout=120) as response:
                data = response.read()
                return json.loads(data) if data else None
        except HTTPError as error:
            if method == 'GET' and error.code == 404:
                return None
            try:
                message = json.load(error).get('message', error.reason)
            except (ValueError, AttributeError):
                message = error.reason
            raise RuntimeError(f'GitHub API HTTP {error.code}: {message}') from None


def publish(version, directory, revision, repository, notes, client):
    # Complete local validation before making a single API request.
    files = validate_assets(version, directory, revision)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository.')
    if not notes.strip():
        raise ValueError('Release notes are required.')
    base = 'https://api.github.com/repos/'+repository
    release = client.request(base+'/releases/tags/'+version)
    if release and not release['draft']:
        raise ValueError('This version is already published. Use a new tag; published releases are not replaced.')
    if release is None:
        release = client.request(base+'/releases', 'POST', dict(
            tag_name=version, target_commitish=revision, name='Journal Analysis Tools '+version,
            body=notes, draft=True, prerelease='-' in version))
    assets_url = base+f"/releases/{release['id']}/assets"
    existing = {asset['name']: asset for asset in client.request(assets_url)}
    if set(existing) - {path.name for path in files}:
        raise ValueError('Draft release has unexpected assets; review it before publishing.')
    for path in files:
        data = path.read_bytes()
        digest = 'sha256:'+hashlib.sha256(data).hexdigest()
        asset = existing.get(path.name)
        if asset and asset.get('digest') == digest and asset['size'] == len(data):
            continue
        if asset:
            client.request(base+f"/releases/assets/{asset['id']}", 'DELETE')
        url = f"https://uploads.github.com/repos/{repository}/releases/{release['id']}/assets?"+urlencode({'name': path.name})
        result = client.request(url, 'POST', data, 'application/zip' if path.suffix == '.zip' else 'text/plain')
        if result['state'] != 'uploaded' or result['size'] != len(data) or (result.get('digest') and result['digest'] != digest):
            raise RuntimeError(f'Upload verification failed for {path.name}; release remains a draft.')
        print('Uploaded:', path.name)
    release = client.request(base+f"/releases/{release['id']}", 'PATCH', dict(
        body=notes, draft=False, prerelease='-' in version, make_latest='false' if '-' in version else 'true'))
    print('Published:', release['html_url'])
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    validate_version(args.version)
    notes_path = Path(__file__).resolve().parent/'releases'/(args.version+'.md')
    publish(args.version, args.assets, os.environ['GITHUB_SHA'], os.environ['GITHUB_REPOSITORY'],
            notes_path.read_text(encoding='utf-8'), GitHub(os.environ['GITHUB_TOKEN']))


if __name__ == '__main__':
    main()
