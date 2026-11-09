"""Check notebook launcher preflight and compile real Finder launchers on macOS."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from build_notebook_launchers import launcher_source

ROOT = Path(__file__).resolve().parent


class LauncherTests(unittest.TestCase):
    def test_both_notebooks_pass_preflight(self):
        for name in ('create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
            result = subprocess.run(['/bin/bash', str(ROOT/'launch_notebook.sh'), str(ROOT), name, '--check'],
                                    capture_output=True, text=True,
                                    env=dict(os.environ, JOURNAL_TOOLS_NO_DIALOG='1', JOURNAL_TOOLS_PYTHON=sys.executable))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(ROOT/name), result.stdout)
            self.assertIn('Python:', result.stdout)

    def test_missing_notebook_has_a_clear_error(self):
        result = subprocess.run(['/bin/bash', str(ROOT/'launch_notebook.sh'), str(ROOT), 'missing.ipynb', '--check'],
                                capture_output=True, text=True, env=dict(os.environ, JOURNAL_TOOLS_NO_DIALOG='1'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Notebook not found', result.stderr)

    @unittest.skipUnless(sys.platform == 'darwin', 'AppleScript apps are macOS only')
    def test_finder_launcher_compiles_with_spaces_and_quotes_in_the_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary)/'launch.applescript'
            script.write_text(launcher_source(Path(temporary)/"Moritz's journal tools", 'clean_and_count_text.ipynb'))
            result = subprocess.run(['/usr/bin/osacompile', '-o', str(Path(temporary)/'Open notebook.app'), str(script)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(temporary)/'Open notebook.app/Contents/MacOS/applet').is_file())


if __name__ == '__main__':
    unittest.main()
