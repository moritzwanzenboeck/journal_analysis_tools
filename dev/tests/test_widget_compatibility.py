"""Catch frontend dependency regressions that Python widget tests cannot see."""
from pathlib import Path
import unittest
from unittest.mock import patch

import anywidget

ROOT=Path(__file__).resolve().parents[2]


class WidgetCompatibilityTests(unittest.TestCase):
    def test_installed_frontend_avoids_the_api_that_breaks_older_safari(self):
        self.assertEqual(anywidget.__version__,'0.9.16')
        self.assertIn('anywidget==0.9.16',(ROOT/'requirements.txt').read_text())
        scripts=list((Path(anywidget.__file__).parent/'labextension/static').glob('*.js'))
        self.assertTrue(scripts,'The browser extension is missing from the installed wheel.')
        frontend='\n'.join(path.read_text(encoding='utf-8') for path in scripts)
        self.assertNotIn('AbortSignal.any(',frontend)

    def test_incompatible_package_shows_a_service_restart_instruction(self):
        with patch.object(anywidget,'__version__','0.11.0'):
            with self.assertRaises(ImportError) as caught:
                exec(compile((ROOT/'dev/selection_widget.py').read_text(), 'selection_widget.py','exec'),{})
        message=str(caught.exception)
        self.assertIn('Safari compatibility',message)
        self.assertIn('loaded version is 0.11.0',message)
        self.assertIn('stop/start the notebook service',message)
        self.assertIn('Restarting only the kernel',message)

if __name__=='__main__':unittest.main()
