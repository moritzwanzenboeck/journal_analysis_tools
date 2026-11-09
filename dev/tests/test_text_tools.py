"""Keep reusable text rules in sync with the self-contained notebook."""
import json
from pathlib import Path
import unittest

from app import text_tools

ROOT = Path(__file__).resolve().parents[2]


class CleaningTests(unittest.TestCase):
    def test_module_and_notebook_share_the_same_rules(self):
        notebook = json.loads((ROOT / 'clean_and_count_text.ipynb').read_text(encoding='utf-8'))
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
                exec(compile(''.join(cell['source']), 'regressions with text module', 'exec'), vars(text_tools).copy())


if __name__ == '__main__':
    unittest.main()
