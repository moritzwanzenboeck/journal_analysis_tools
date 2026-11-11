"""Native release relocation, privacy and all-platform publication gates."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

from dev.build_notebook_launchers import launcher_source
from dev.package_release import SOURCE_FILES, TARGETS, asset_name, build_release, copy_sources, verify_archive
from dev.publish_release import publish, validate_assets

ROOT = Path(__file__).resolve().parents[2]
REVISION = 'a'*40


def make_assets(directory):
    for target in TARGETS:
        archive = directory/asset_name('v1.1.0', target)
        with zipfile.ZipFile(archive, 'w') as zipped:
            metadata = dict(version='v1.1.0', target=target, source_commit=REVISION, python_bundled=False)
            zipped.writestr(archive.stem+'/RELEASE.json', json.dumps(metadata))
            files = ['notebook_launcher.py', 'requirements.txt', 'app/launcher.py',
                     'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb', 'INSTALL.txt']
            files += ['Journal Notebook Launcher.exe'] if target.startswith('windows-') else ['Journal Notebook Launcher.app/Contents/MacOS/applet']
            for name in files:
                zipped.writestr(archive.stem+'/'+name, b'test fixture')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n')


class PackagingTests(unittest.TestCase):
    def test_only_runtime_sources_are_copied_and_saved_notebook_text_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, package = Path(temporary)/'source', Path(temporary)/'package'
            root.mkdir()
            for name in SOURCE_FILES:
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/name, target)
            private = root/'clean_and_count_text.ipynb'
            notebook = json.loads(private.read_text())
            notebook['metadata']['widgets'] = {'private': 'PRIVATE TEXT'}
            cell = next(cell for cell in notebook['cells'] if cell['cell_type'] == 'code')
            cell['execution_count'] = 1
            cell['outputs'] = [{'output_type': 'stream', 'name': 'stdout', 'text': 'PRIVATE TEXT'}]
            private.write_text(json.dumps(notebook))
            original = private.read_bytes()
            (root/'.env').write_text('PRIVATE SECRET')
            (root/'output').mkdir()
            (root/'output/private.csv').write_text('PRIVATE PROJECT')
            copy_sources(root, package)
            self.assertEqual({p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}, set(SOURCE_FILES))
            self.assertNotIn('PRIVATE TEXT', (package/private.name).read_text())
            self.assertEqual(private.read_bytes(), original)

    def test_portable_mac_script_contains_no_checkout_or_python_paths(self):
        source = launcher_source(ROOT, portable=True)
        self.assertNotIn(str(ROOT), source)
        self.assertNotIn(sys.executable, source)
        self.assertIn('set toolsFolder to ""', source)
        self.assertIn('Extract the complete release', source)

    def test_version_cannot_escape_output_directory(self):
        for value in ('../private', '1.1.0', 'v1/../../x', 'v1.1.0; echo bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                asset_name(value, TARGETS[0])

    @unittest.skipUnless(sys.platform in ('darwin', 'win32'), 'Native release builder required')
    def test_native_archive_extracts_and_starts_after_relocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = build_release(ROOT, 'v1.1.0', Path(temporary))
            with zipfile.ZipFile(archive) as zipped:
                self.assertFalse(any('__pycache__' in name or '/.venv/' in name for name in zipped.namelist()))
                self.assertIn(archive.stem+'/INSTALL.txt', zipped.namelist())
            verify_archive(archive)
            with self.assertRaises(FileExistsError):
                build_release(ROOT, 'v1.1.0', Path(temporary))


class FakeGitHub:
    def __init__(self, *, published=False, fail_upload=False):
        self.calls = []
        self.published = published
        self.fail_upload = fail_upload

    def request(self, url, method='GET', body=None, content_type=None):
        self.calls.append((url, method, body))
        if method == 'GET' and '/tags/' in url:
            return {'id': 1, 'draft': False} if self.published else None
        if method == 'GET':
            return []
        if method == 'POST' and url.endswith('/releases'):
            return {'id': 1, 'draft': True}
        if method == 'POST':
            return dict(state='uploaded', size=0 if self.fail_upload else len(body),
                        digest='sha256:'+hashlib.sha256(body).hexdigest())
        if method == 'PATCH':
            return {'id': 1, 'html_url': 'https://github.com/example/tools/releases/tag/v1.1.0'}
        raise AssertionError((url, method))


class PublicationTests(unittest.TestCase):
    def test_all_platforms_and_checksums_are_required_before_api_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_assets(root)
            self.assertEqual(len(validate_assets('v1.1.0', root, REVISION)), 6)
            archive = root/asset_name('v1.1.0', TARGETS[0])
            archive.with_suffix('.zip.sha256').write_text('bad checksum')
            client = FakeGitHub()
            with self.assertRaisesRegex(ValueError, 'checksum'):
                publish('v1.1.0', root, REVISION, 'example/tools', 'Notes', client)
            self.assertEqual(client.calls, [])
            archive.unlink()
            with self.assertRaisesRegex(ValueError, 'all three'):
                publish('v1.1.0', root, REVISION, 'example/tools', 'Notes', client)
            self.assertEqual(client.calls, [])

    def test_commit_mismatch_prevents_uploads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_assets(root)
            client = FakeGitHub()
            with self.assertRaisesRegex(ValueError, 'metadata'):
                publish('v1.1.0', root, 'b'*40, 'example/tools', 'Notes', client)
            self.assertEqual(client.calls, [])

    def test_all_uploads_are_verified_before_release_becomes_public(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_assets(root)
            client = FakeGitHub()
            publish('v1.1.0', root, REVISION, 'example/tools', 'Notes', client)
            uploads = [call for call in client.calls if call[1] == 'POST' and 'uploads.github.com' in call[0]]
            self.assertEqual(len(uploads), 6)
            self.assertEqual(client.calls[-1][1], 'PATCH')
            self.assertFalse(client.calls[-1][2]['draft'])
            client = FakeGitHub(fail_upload=True)
            with self.assertRaisesRegex(RuntimeError, 'remains a draft'):
                publish('v1.1.0', root, REVISION, 'example/tools', 'Notes', client)
            self.assertFalse(any(call[1] == 'PATCH' for call in client.calls))

    def test_existing_public_release_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_assets(root)
            client = FakeGitHub(published=True)
            with self.assertRaisesRegex(ValueError, 'already published'):
                publish('v1.1.0', root, REVISION, 'example/tools', 'Notes', client)
            self.assertEqual(len(client.calls), 1)


if __name__ == '__main__':
    unittest.main()
