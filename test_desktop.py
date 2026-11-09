"""Desktop input/settings checks and parity with the notebook's text rules."""
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from app_support import load_settings, project_options, save_settings
import text_tools
from test_metadata import JOURNAL

ROOT = Path(__file__).resolve().parent


class SettingsTests(unittest.TestCase):
    def test_missing_and_corrupt_settings_fall_back_to_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'settings.json'
            self.assertEqual(load_settings(path), {})
            for content in ('not json', '[]', 'null'):
                path.write_text(content)
                self.assertEqual(load_settings(path), {})

    def test_settings_roundtrip_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'nested' / 'settings.json'
            settings = {'query': 'Example', 'parent': temporary, 'count': 10}
            save_settings(settings, path)
            self.assertEqual(load_settings(path), settings)
            save_settings({'query': 'Another'}, path)
            self.assertEqual(load_settings(path), {'query': 'Another'})
            self.assertFalse(path.with_suffix('.tmp').exists())


class FormTests(unittest.TestCase):
    def test_valid_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            options = project_options(JOURNAL, '2024-01-01', '2024-12-31', '5', temporary,
                                      seed='42', folder='custom-project')
            self.assertEqual(options['start'], date(2024, 1, 1))
            self.assertEqual(options['count'], 5)
            self.assertEqual(options['seed'], 42)
            self.assertEqual(options['project_name'], 'custom-project')
            self.assertIsNone(options['input_json'])

    def test_invalid_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            valid = dict(journal=JOURNAL, start='2024-01-01', end='2024-12-31', count='5', parent=temporary)
            for bad in ({'journal': None}, {'start': '2024-02-30'}, {'start': '2025-01-01'},
                        {'count': '0'}, {'count': '2.5'}, {'seed': 'abc'}, {'parent': ''},
                        {'basis': 'invalid'}, {'archive': str(Path(temporary)/'missing.json')}):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    project_options(**dict(valid, **bad))

    def test_offline_archive_is_optional(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)/'archive.json'
            archive.write_text('[]')
            options = project_options(JOURNAL, '2024-01-01', '2024-12-31', '1', temporary, archive=str(archive))
            self.assertEqual(options['input_json'], archive)


class CleaningTests(unittest.TestCase):
    def test_app_and_notebook_share_the_same_rules(self):
        notebook = json.loads((ROOT/'clean_and_count_text.ipynb').read_text())
        source = next(''.join(c['source']) for c in notebook['cells'] if 'def clean_text' in ''.join(c['source']))
        namespace = {}
        exec(compile(source, 'notebook functions', 'exec'), namespace)
        inputs = ['Result (𝑝<.1\n).\nNext!', 'p = 0.001\nand continues.',
                  'First.12\nNext?', '1. Introduction\nBody.\n\nNext!', 'well-\nknown.']
        for value in inputs:
            self.assertEqual(text_tools.clean_text(value), namespace['clean_text'](value))
            self.assertEqual(text_tools.count_text(value), namespace['count_text'](value))
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code' and '# Checks for automatic paragraph' in ''.join(cell['source']):
                exec(compile(''.join(cell['source']), 'regressions with app module', 'exec'), vars(text_tools).copy())


if __name__ == '__main__':
    unittest.main()
