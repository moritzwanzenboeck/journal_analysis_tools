"""Execute both notebooks with real widgets and exercise their callbacks offline."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nbformat
from app import journal_tools as tools
from test_metadata import article, JOURNAL

ROOT = Path(__file__).resolve().parents[2]


def execute_notebook(name):
    notebook = nbformat.read(ROOT/name, as_version=4)
    nbformat.validate(notebook)
    namespace = {}
    with patch('IPython.display.display'):
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type == 'code':
                exec(compile(cell.source, f'{name}:cell {index}', 'exec'), namespace)
    return namespace


class NotebookTests(unittest.TestCase):
    def test_copy_buttons_copy_only_the_count_on_windows_and_mac(self):
        state = execute_notebook('clean_and_count_text.ipynb')
        state['cleaned_editor'].value = 'One two.\n\nThree four.'
        for platform, utility, encoding in (('win32', 'clip.exe', 'utf-16-le'), ('darwin', 'pbcopy', 'utf-8')):
            for button, expected in (('copy_word_button', '4'), ('copy_paragraph_button', '2')):
                with self.subTest(platform=platform, button=button), \
                        patch.object(state['sys'], 'platform', platform), \
                        patch.object(state['shutil'], 'which', return_value=utility), \
                        patch.object(state['subprocess'], 'CREATE_NO_WINDOW', 0x08000000, create=True), \
                        patch.object(state['subprocess'], 'run') as run:
                    state[button].click()
                    self.assertEqual(run.call_args.args[0], [utility])
                    self.assertEqual(run.call_args.kwargs['input'].decode(encoding), expected)
                    self.assertIn('Copied', state['copy_status'].value)

    def test_clipboard_failure_preserves_text_and_offers_manual_copy(self):
        state = execute_notebook('clean_and_count_text.ipynb')
        state['cleaned_editor'].value = 'Keep this result.'
        with patch.object(state['shutil'], 'which', return_value=None):
            state['copy_word_button'].click()
        self.assertIn('copy it manually', state['copy_status'].value)
        with patch.object(state['shutil'], 'which', return_value='clipboard-tool'), \
                patch.object(state['subprocess'], 'run', side_effect=OSError('Clipboard unavailable')):
            state['copy_word_button'].click()
        self.assertIn('copy it manually', state['copy_status'].value)
        self.assertEqual(state['cleaned_editor'].value, 'Keep this result.')

    @unittest.skipUnless(os.environ.get('JOURNAL_TOOLS_TEST_CLIPBOARD') == '1', 'Native clipboard test runs on CI desktops')
    def test_native_copy_buttons_roundtrip_without_extra_characters(self):
        import tkinter as tk
        window = tk.Tk()
        window.withdraw()
        try:
            try:
                original = window.clipboard_get()
            except tk.TclError:
                original = None
            state = execute_notebook('clean_and_count_text.ipynb')
            state['cleaned_editor'].value = 'One two.\n\nThree four.'
            for button, expected in (('copy_word_button', '4'), ('copy_paragraph_button', '2')):
                state[button].click()
                window.update()
                self.assertIn('Copied', state['copy_status'].value)
                self.assertEqual(window.clipboard_get(), expected)
        finally:
            window.clipboard_clear()
            if original is not None:
                window.clipboard_append(original)
            window.update()
            window.destroy()

    def test_cleaning_regressions_and_clear_button(self):
        state = execute_notebook('clean_and_count_text.ipynb')
        state['original_editor'].value = 'well-\nknown.'
        state['find_button'].click()
        state['keep_selector'].value = (0,)
        state['cleaned_editor'].value = 'Keep this edited result.'
        state['clear_original_button'].click()
        self.assertEqual(state['original_editor'].value, '')
        self.assertEqual(state['keep_selector'].options, ())
        self.assertIsNone(state['review_state']['source'])
        self.assertEqual(state['cleaned_editor'].value, 'Keep this edited result.')
        self.assertEqual(state['clear_original_button'].button_style, 'danger')

    def test_project_form_lookup_creation_and_stale_query_reset(self):
        state = execute_notebook('create_journal_analysis.ipynb')
        self.assertTrue(state['create_button'].disabled)
        state['journal_query'].value = 'Example'
        with patch.object(tools, 'find_journals', return_value=[JOURNAL]):
            state['search_button'].click()
        self.assertIsNone(state['journal_choice'].value)
        self.assertTrue(state['create_button'].disabled)
        state['journal_choice'].value = JOURNAL
        self.assertFalse(state['create_button'].disabled)
        state['start_field'].value = tools.date(2026, 1, 1)
        state['end_field'].value = tools.date(2026, 12, 31)
        state['count_field'].value = 1
        with tempfile.TemporaryDirectory() as root:
            state['root_field'].value = root
            state['folder_field'].value = 'widget-created'
            with patch.object(tools, 'fetch_records', return_value=([article()], [])):
                state['create_button'].click()
            self.assertEqual(state['last_project']['path'], Path(root).resolve()/'widget-created')
            self.assertTrue((Path(root)/'widget-created/output').is_dir())
            self.assertFalse((Path(root)/'widget-created/papers').exists())
            self.assertFalse((Path(root)/'widget-created/analysis').exists())
        state['journal_query'].value = 'Other journal'
        self.assertIsNone(state['journal_choice'].value)
        self.assertTrue(state['create_button'].disabled)

    def test_distributed_notebooks_contain_no_saved_outputs(self):
        for path in ROOT.glob('*.ipynb'):
            notebook = json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn('widgets', notebook['metadata'])
            for cell in notebook['cells']:
                self.assertEqual(cell.get('outputs', []), [])
                self.assertIsNone(cell.get('execution_count'))


if __name__ == '__main__':
    unittest.main()
