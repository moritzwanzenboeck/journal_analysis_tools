"""Archive extraction must preserve relocatability without unsafe links."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from dev.bundle_python import download_runtime, extract_runtime


class RuntimeTests(unittest.TestCase):
    def archive(self, directory, entries):
        archive = directory/'runtime.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name, data, link in entries:
                member = tarfile.TarInfo(name)
                member.mode = 0o755
                if link is not None:
                    member.type = tarfile.SYMTYPE
                    member.linkname = link
                    tar.addfile(member)
                else:
                    member.size = len(data)
                    tar.addfile(member, io.BytesIO(data))
        return archive

    def test_interpreter_links_are_materialized_and_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [('python/bin/python3.14', b'interpreter', None),
                                          ('python/bin/python3', b'', 'python3.14'),
                                          ('python/bin/python', b'', 'python3')])
            extract_runtime(archive, root/'runtime')
            for name in ('python', 'python3', 'python3.14'):
                path = root/'runtime/bin'/name
                self.assertEqual(path.read_bytes(), b'interpreter')
                self.assertFalse(path.is_symlink())
                if os.name == 'posix':
                    self.assertTrue(path.stat().st_mode & 0o100)

    def test_unsafe_paths_and_links_are_rejected_before_payload_writes(self):
        for name, link in [('../outside', None), ('/absolute', None), ('python/../../outside', None),
                           ('python/C:/outside', None), ('python/bin/python', '../../../outside'),
                           ('python/bin/python', '/outside'), ('python/bin/python', 'python')]:
            with self.subTest(name=name, link=link), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = self.archive(root, [('python/safe.txt', b'safe', None), (name, b'bad', link)])
                with self.assertRaises(ValueError):
                    extract_runtime(archive, root/'runtime')
                self.assertFalse((root/'runtime/safe.txt').exists())

    def test_cached_runtime_is_checksum_verified_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.archive(root, [('python/python.exe', b'interpreter', None)])
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps(dict(provider='https://example.invalid', release='test', targets={'test': dict(
                archive=archive.name, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())})))
            with patch('dev.bundle_python.MANIFEST', manifest), patch('dev.bundle_python.urlopen') as network:
                self.assertEqual(download_runtime('test', root)[0], archive)
                archive.write_bytes(b'corrupted')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    download_runtime('test', root)
                network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
