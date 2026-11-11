"""Check the shared launcher and real Jupyter process/kernel lifecycle offline."""
from dataclasses import replace
from contextlib import redirect_stderr
import io
from pathlib import Path
import os
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs

from dev.build_notebook_launchers import APP_NAME, WINDOWS_APP_NAME, install, install_windows, publish_app
from app.notebook_services import NotebookService, SERVICES

ROOT = Path(__file__).resolve().parents[2]


class LauncherTests(unittest.TestCase):
    def test_preflight_reports_a_tk_runtime_mismatch(self):
        import tkinter as tk
        from app.launcher import main

        errors = io.StringIO()
        with patch.object(sys, 'argv', ['notebook_launcher.py', '--check']), \
                patch.object(tk, 'Tk', side_effect=RuntimeError('tk.h version (8.5) does not match libtk.a version (8.6)')), \
                redirect_stderr(errors), self.assertRaises(SystemExit) as stopped:
            main()
        self.assertEqual(stopped.exception.code, 1)
        self.assertIn('Tk could not initialise', errors.getvalue())
        self.assertIn('matching Tcl/Tk libraries', errors.getvalue())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows app compiler required')
    def test_windows_app_compiles_and_launches_real_python_without_a_console(self):
        with tempfile.TemporaryDirectory(prefix="journal's app ä ") as temporary:
            destination = Path(temporary)
            executable = install_windows(ROOT, destination)
            self.assertEqual(executable.name, WINDOWS_APP_NAME)
            binary = executable.read_bytes()
            pe_offset = struct.unpack_from('<I', binary, 0x3c)[0]
            self.assertEqual(binary[pe_offset:pe_offset + 4], b'PE\x00\x00')
            # The PE Windows GUI subsystem avoids a console when double-clicked.
            self.assertEqual(struct.unpack_from('<H', binary, pe_offset + 24 + 68)[0], 2)
            result = subprocess.run([str(executable), '--check'], cwd=destination,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, 'The native app failed to start its Python launcher.')
            original = executable.read_bytes()
            with self.assertRaises(FileExistsError):
                install_windows(ROOT, destination)
            self.assertEqual(executable.read_bytes(), original)

            original_run = subprocess.run

            def fail_compilation(command, **options):
                if str(command[0]).lower().endswith('csc.exe'):
                    raise subprocess.CalledProcessError(1, command)
                return original_run(command, **options)

            with patch('dev.build_notebook_launchers.subprocess.run', side_effect=fail_compilation):
                with self.assertRaises(subprocess.CalledProcessError):
                    install_windows(ROOT, destination, replace=True)
            self.assertEqual(executable.read_bytes(), original)
            executable.write_bytes(b'Previous launcher')
            install_windows(ROOT, destination, replace=True)
            self.assertTrue(executable.read_bytes().startswith(b'MZ'))
            result = subprocess.run([str(executable), '--check'], cwd=destination,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0)

            # An invalid explicit Python choice must fail, rather than silently
            # use a different environment. This is also checked by the Mac script.
            result = subprocess.run([str(executable), '--check'], cwd=destination,
                                    env=dict(os.environ, JOURNAL_TOOLS_PYTHON=str(destination / 'missing-python.exe')),
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)

    def test_preflight_checks_both_notebooks_without_opening_a_window(self):
        result = subprocess.run([sys.executable, str(ROOT / 'notebook_launcher.py'), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for spec in SERVICES:
            self.assertIn(spec.notebook, result.stdout)

    @unittest.skipUnless(os.name == 'posix' and Path('/bin/bash').exists(), 'POSIX shell required')
    def test_command_shortcuts_use_the_shared_launcher(self):
        for script in ('start_notebook.command',):
            result = subprocess.run(['/bin/bash', str(ROOT / script), '--check'],
                                    capture_output=True, text=True,
                                    env=dict(os.environ, JOURNAL_TOOLS_NO_DIALOG='1', JOURNAL_TOOLS_PYTHON=sys.executable))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('create_journal_analysis.ipynb', result.stdout)
            self.assertIn('clean_and_count_text.ipynb', result.stdout)

        result = subprocess.run(['/bin/bash', str(ROOT / 'start_notebook.command'), '--check'],
                                capture_output=True, text=True,
                                env=dict(os.environ, JOURNAL_TOOLS_NO_DIALOG='1', JOURNAL_TOOLS_PYTHON='/missing/python'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requirements.txt', result.stderr)

    @unittest.skipUnless(os.name == 'posix' and Path('/bin/bash').exists(), 'POSIX shell required')
    def test_python_starts_from_a_local_directory_when_checkout_is_on_a_share(self):
        import shlex
        with tempfile.TemporaryDirectory(prefix="journal's cwd check ä ") as temporary:
            trace = Path(temporary) / 'working-directories.txt'
            wrapper = Path(temporary) / 'python-wrapper'
            wrapper.write_text('#!/bin/bash\n/bin/pwd -P >> ' + shlex.quote(str(trace)) +
                               '\nexec ' + shlex.quote(sys.executable) + ' "$@"\n', encoding='utf-8')
            wrapper.chmod(0o700)
            result = subprocess.run(['/bin/bash', str(ROOT / 'start_notebook.command'), '--check'],
                                    cwd=ROOT, capture_output=True, text=True,
                                    env=dict(os.environ, JOURNAL_TOOLS_NO_DIALOG='1',
                                             JOURNAL_TOOLS_PYTHON=str(wrapper)))
            self.assertEqual(result.returncode, 0, result.stderr)
            directories = trace.read_text(encoding='utf-8').splitlines()
            self.assertGreaterEqual(len(directories), 2)
            self.assertTrue(all(Path(path) == Path('/tmp').resolve() for path in directories))
            self.assertIn(str(ROOT / 'clean_and_count_text.ipynb'), result.stdout)

    def test_installer_validates_checkout_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / 'Applications'
            with self.assertRaises(FileNotFoundError):
                install(root, destination)
            self.assertFalse(destination.exists())

    def test_installer_preserves_existing_apps(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary) / APP_NAME
            app.mkdir()
            marker = app / 'keep.txt'
            marker.write_text('Existing app', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                install(ROOT, Path(temporary))
            self.assertEqual(marker.read_text(encoding='utf-8'), 'Existing app')

    def test_bundle_replacement_restores_previous_app_on_publication_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            output = destination / APP_NAME
            output.mkdir()
            (output / 'previous.txt').write_text('Previous launcher', encoding='utf-8')
            built = destination / 'staged.app'
            built.mkdir()
            (built / 'new.txt').write_text('New launcher', encoding='utf-8')
            original_rename = Path.rename

            def fail_publication(source, target):
                if source == built:
                    raise OSError('Simulated publication failure')
                return original_rename(source, target)

            with patch.object(Path, 'rename', autospec=True, side_effect=fail_publication):
                with self.assertRaisesRegex(OSError, 'publication failure'):
                    publish_app(built, output, replace=True)
            self.assertEqual((output / 'previous.txt').read_text(encoding='utf-8'), 'Previous launcher')
            self.assertTrue((built / 'new.txt').is_file())
            self.assertFalse(list(destination.glob('.*.previous-*')))
            publish_app(built, output, replace=True)
            self.assertFalse((output / 'previous.txt').exists())
            self.assertTrue((output / 'new.txt').is_file())

    @unittest.skipUnless(sys.platform == 'darwin', 'AppleScript apps are macOS only')
    def test_mac_compiler_stays_off_destination_and_installed_signature_is_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'shared destination'
            original_run = subprocess.run
            compiled_paths = []

            def record_compilation(command, **options):
                if command[0] == '/usr/bin/osacompile':
                    compiled = Path(command[2])
                    self.assertNotIn(destination, compiled.parents)
                    self.assertEqual(Path(options['cwd']), compiled.parent)
                    compiled_paths.append(compiled)
                return original_run(command, **options)

            with patch('dev.build_notebook_launchers.subprocess.run', side_effect=record_compilation):
                output = install(ROOT, destination)
            self.assertEqual(len(compiled_paths), 1)
            self.assertFalse(compiled_paths[0].exists(), 'Local compilation staging must be cleaned up')
            self.assertFalse(list(destination.glob('.journal-notebook-launcher-*')))
            subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(output)], check=True)
            icon = ROOT / 'app' / 'assets' / 'app.icns'
            if icon.is_file():
                self.assertEqual((output / 'Contents/Resources/applet.icns').read_bytes(), icon.read_bytes())

    @unittest.skipUnless(sys.platform == 'darwin', 'AppleScript apps are macOS only')
    def test_mac_destination_that_strips_permissions_keeps_previous_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            output = destination / APP_NAME
            output.mkdir()
            marker = output / 'keep.txt'
            marker.write_text('Previous launcher', encoding='utf-8')
            original_access = os.access

            def destination_access(path, mode, **options):
                if mode == os.X_OK and '.journal-notebook-launcher-' in str(path):
                    return False
                return original_access(path, mode, **options)

            with patch('dev.build_notebook_launchers.os.access', side_effect=destination_access):
                with self.assertRaisesRegex(OSError, 'local disk'):
                    install(ROOT, destination, replace=True)
            self.assertEqual(marker.read_text(encoding='utf-8'), 'Previous launcher')
            self.assertFalse(list(destination.glob('.journal-notebook-launcher-*')))

    @unittest.skipUnless(sys.platform == 'darwin', 'AppleScript apps are macOS only')
    def test_installs_one_finder_app_with_spaces_quotes_and_unicode_in_path(self):
        import shutil
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Moritz\'s "journal" tools ä'
            root.mkdir()
            for name in ('app/launch_notebook.sh', 'notebook_launcher.py', 'app/__init__.py',
                         'app/launcher.py', 'app/notebook_services.py',
                         'create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, root / name)
            destination = Path(temporary) / 'Applications'
            install(root, destination)
            self.assertEqual([path.name for path in destination.iterdir()], [APP_NAME])
            self.assertTrue((destination / APP_NAME / 'Contents' / 'MacOS' / 'applet').is_file())
            (destination / APP_NAME / 'obsolete.txt').touch()
            install(root, destination, replace=True)
            self.assertFalse((destination / APP_NAME / 'obsolete.txt').exists())
            self.assertTrue((destination / APP_NAME / 'Contents' / 'MacOS' / 'applet').is_file())


class ServiceTests(unittest.TestCase):
    def test_missing_notebook_creates_no_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = NotebookService(SERVICES[0], temporary, log_dir=temporary)
            with self.assertRaisesRegex(FileNotFoundError, 'Notebook not found'):
                service.start()
            self.assertIsNone(service.process)
            self.assertIsNone(service.url)

    def test_startup_timeout_cleans_up_process_and_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            service = NotebookService(SERVICES[0], ROOT, log_dir=temporary)
            with self.assertRaises(TimeoutError):
                service.start(timeout=0)
            self.assertFalse(service.running)
            self.assertIsNone(service.process)
            self.assertIsNone(service._runtime)
            self.assertIsNone(service.url)

    def test_ports_links_kernel_isolation_shutdown_and_restart(self):
        with tempfile.TemporaryDirectory(prefix="journal's launch tests ä ") as temporary, \
                socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            preferred_port = occupied.getsockname()[1]
            services = [NotebookService(replace(spec, preferred_port=preferred_port), ROOT, log_dir=temporary)
                        for spec in SERVICES]
            for service in services:
                self.addCleanup(service.force_stop)
            project, text = services
            try:
                for service in services:
                    service.start()
                    self.assertTrue(service.running)
                    # Server startup stays on local storage; notebook URLs still
                    # refer to the configured checkout, including shared drives.
                    import psutil
                    self.assertEqual(Path(psutil.Process(service.process.pid).cwd()).resolve(),
                                     Path(service._runtime.name).resolve())
                    self.assertNotEqual(service.port, preferred_port)
                    address = urlparse(service.url)
                    self.assertEqual(address.hostname, '127.0.0.1')
                    self.assertEqual(address.port, service.port)
                    self.assertEqual(parse_qs(address.query)['token'], [service.token])
                    self.assertTrue(address.path.endswith('/' + service.spec.notebook))
                    with service._opener.open(service.url, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                    with self.assertRaises(HTTPError) as denied:
                        service._opener.open(service.base_url + 'api/kernels', timeout=3)
                    self.assertEqual(denied.exception.code, 403)
                    denied.exception.close()
                self.assertNotEqual(project.port, text.port)
                original_process = project.process
                project.start()
                self.assertIs(project.process, original_process)

                project.request('api/kernels', 'POST')
                text_kernel = text.request('api/kernels', 'POST')
                self.assertEqual(project.kill_kernels(), 1)
                self.assertEqual(project.request('api/kernels'), [])
                self.assertEqual(text.request('api/kernels')[0]['id'], text_kernel['id'])
                self.assertTrue(project.running)

                # Force stop also ends kernels without relying on HTTP shutdown.
                project.request('api/kernels', 'POST')
                project.track_children()
                owned = set(project._children)
                self.assertTrue(owned, 'Expected a real kernel child process')
                old_token = project.token
                project.force_stop()
                self.assertTrue(all(not process.is_running() for process in owned))
                self.assertIsNone(project.port)
                self.assertIsNone(project.url)
                self.assertTrue(text.running)
                self.assertEqual(occupied.getsockname()[1], preferred_port)

                project.start()
                self.assertNotEqual(project.token, old_token)
                project.stop()
                self.assertFalse(project.running)
                text.track_children()
                owned = set(text._children)
                text.stop()
                self.assertFalse(text.running)
                self.assertTrue(all(not process.is_running() for process in owned))
            except Exception:
                for service in services:
                    if service.log_path.is_file():
                        log = service.log_path.read_text(encoding='utf-8', errors='replace')
                        if service.token:
                            log = log.replace(service.token, '<redacted>')
                        print(log[-6000:], file=sys.stderr)
                raise
            finally:
                for service in services:
                    service.force_stop()


if __name__ == '__main__':
    unittest.main()
