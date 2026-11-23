"""Path browsing, cancellation, file validation and project save constraints."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ipywidgets as widgets

from app.file_selectors import path_selector
from test_notebooks import execute_notebook, ROOT
import test_paper_categorization


class FileSelectorTests(unittest.TestCase):
    def test_folder_navigation_selection_and_cancel_do_not_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            nested = root / 'Unicode ü and spaces'
            nested.mkdir()
            (root/'ignore.json').write_text('{}')
            field = widgets.Text(value=str(root))
            browser = path_selector(field)
            browser['browse'].click()
            self.assertEqual([v for _, v in browser['entries'].options], [str(nested)])
            browser['entries'].value = str(nested)
            browser['open_folder'].click()
            self.assertEqual(browser['state']['directory'], nested)
            browser['up'].click()
            self.assertEqual(browser['state']['directory'], root)
            browser['location'].value = str(nested)
            browser['go'].click()
            browser['cancel'].click()
            self.assertEqual(field.value, str(root))
            self.assertEqual(browser['panel'].layout.display, 'none')
            browser['browse'].click()
            browser['entries'].value = str(nested)
            browser['choose'].click()
            self.assertEqual(field.value, str(nested))
            self.assertEqual(browser['entries'].options, ())
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['Unicode ü and spaces', 'ignore.json'])

    def test_json_filter_existing_selection_and_removed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sub = root/'nested'; sub.mkdir()
            chosen = root/'Saved ü.JSON'; chosen.write_text('{}')
            other = root/'other.txt'; other.write_text('text')
            field = widgets.Text(value=str(chosen))
            browser = path_selector(field, mode='json')
            browser['browse'].click()
            self.assertEqual(browser['entries'].value, str(chosen))
            self.assertEqual({v for _, v in browser['entries'].options}, {str(sub), str(chosen)})
            browser['entries'].value = str(sub)
            self.assertTrue(browser['choose'].disabled)
            self.assertFalse(browser['open_folder'].disabled)
            browser['entries'].value = str(chosen)
            chosen.unlink()
            browser['choose'].click()
            self.assertIn('existing JSON', browser['status'].value)
            self.assertNotEqual(browser['panel'].layout.display, 'none')
            self.assertEqual(field.value, str(chosen))
            chosen.write_text('{}')
            browser['choose'].click()
            self.assertEqual(browser['panel'].layout.display, 'none')

    def test_start_nearest_parent_and_manual_paths_remain_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            missing = root/'new'/'project'
            field = widgets.Text(value=str(missing))
            browser = path_selector(field)
            browser['browse'].click()
            self.assertEqual(browser['state']['directory'], root)
            self.assertEqual(field.value, str(missing))
            self.assertFalse(missing.exists())
            browser['cancel'].click()
            field.value = ''
            browser = path_selector(field, mode='json', start=lambda: root)
            browser['browse'].click()
            self.assertEqual(browser['state']['directory'], root)
            self.assertTrue(browser['choose'].disabled)
            browser['location'].value = ''
            browser['go'].click()
            self.assertIn('Enter a folder', browser['status'].value)

    def test_permission_failure_preserves_previous_listing_and_can_recover(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            field = widgets.Text(value=str(root))
            browser = path_selector(field)
            browser['browse'].click()
            with patch.object(Path, 'iterdir', side_effect=PermissionError('denied <private>')):
                browser['go'].click()
            self.assertIn('denied &lt;private&gt;', browser['status'].value)
            self.assertEqual(browser['state']['directory'], root)
            browser['go'].click()
            self.assertNotIn('denied', browser['status'].value)
            self.assertFalse(browser['choose'].disabled)

    def test_disabling_field_closes_browser_and_prevents_stale_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            field = widgets.Text(value=str(root))
            browser = path_selector(field)
            browser['browse'].click()
            field.disabled = True
            self.assertTrue(browser['browse'].disabled)
            self.assertEqual(browser['panel'].layout.display, 'none')
            browser['browse'].click()
            browser['choose'].click()
            self.assertEqual(field.value, str(root))
            self.assertEqual(browser['panel'].layout.display, 'none')
            field.disabled = False
            self.assertFalse(browser['browse'].disabled)

    def test_embedded_helpers_match_the_reusable_module(self):
        import app.file_selectors as module
        import inspect
        expected = ast.dump(ast.parse(inspect.getsource(module.path_selector)), include_attributes=False)
        for name in ('create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
            notebook = json.loads((ROOT/name).read_text())
            functions = [node for cell in notebook['cells'] if cell['cell_type'] == 'code'
                         for node in ast.parse(''.join(cell['source'])).body
                         if isinstance(node, ast.FunctionDef) and node.name == 'path_selector']
            self.assertEqual(len(functions), 1)
            self.assertEqual(ast.dump(ast.Module(body=functions, type_ignores=[]), include_attributes=False), expected)

    def test_creation_selectors_only_fill_fields_without_creating_or_fetching(self):
        state = execute_notebook('create_journal_analysis.ipynb')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root/'archive.json'; archive.write_text('{}')
            state['root_field'].value = str(root)
            browser = state['root_selector']
            browser['browse'].click(); browser['choose'].click()
            self.assertEqual(state['root_field'].value, str(root))
            browser = state['archive_selector']
            browser['browse'].click()
            browser['entries'].value = str(archive)
            browser['choose'].click()
            self.assertEqual(state['archive_field'].value, str(archive))
            self.assertIsNone(state['last_project'])
            self.assertEqual(list(root.iterdir()), [archive])

    def test_project_selector_preserves_scan_and_locked_save_folder(self):
        state = execute_notebook('clean_and_count_text.ipynb')
        with tempfile.TemporaryDirectory() as temporary:
            root = test_paper_categorization.ProjectPaperTests.make_project(self, temporary)
            state['paper_project_folder'].value = str(root)
            browser = state['paper_project_selector']
            browser['browse'].click(); browser['choose'].click()
            self.assertIsNone(state['paper_state']['project'])
            state['paper_scan_project_button'].click()
            self.assertEqual(state['paper_state']['project']['root'], root.resolve())
            self.assertTrue(state['paper_folder_selector']['browse'].disabled)
            self.assertTrue(state['paper_folder'].disabled)
            self.assertEqual(state['paper_folder'].value, str(root.resolve()/'paper_categorizations'))
            self.assertFalse((root/'paper_categorizations').exists())
