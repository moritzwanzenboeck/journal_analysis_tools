"""OS-dialog wiring, cancellation, responsiveness and locked project destinations."""
import ast
import asyncio
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import ipywidgets as widgets
from app import file_selectors as selectors
from test_notebooks import execute_notebook, ROOT
import test_paper_categorization


class FileSelectorTests(unittest.TestCase):
    def test_folder_selection_only_fills_the_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            selected = root/'Unicode ü and spaces'; selected.mkdir()
            field = widgets.Text(value=str(root/'new'/'destination'))
            browser = selectors.path_selector(field, title='Choose projects parent')
            with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock, return_value=str(selected)) as dialog:
                browser['browse'].click()
            self.assertEqual(field.value, str(selected))
            self.assertEqual(dialog.call_args.kwargs, dict(mode='folder', title='Choose projects parent',
                                                          initialdir=root, initialfile=None))
            self.assertFalse((root/'new').exists())
            self.assertFalse(browser['browse'].disabled)
            self.assertEqual(browser['browse'].description, 'Browse…')

    def test_json_dialog_options_cancel_and_case_insensitive_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            saved = root/'Saved ü.JSON'; saved.write_text('{}')
            field = widgets.Text(value=str(saved))
            browser = selectors.path_selector(field, mode='json')
            with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock, return_value=None) as dialog:
                browser['browse'].click()
            self.assertEqual(field.value, str(saved))
            self.assertEqual(dialog.call_args.kwargs['initialfile'], saved.name)
            self.assertEqual(dialog.call_args.kwargs['initialdir'], root)
            field.value = ''
            with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock, return_value=str(saved)):
                browser['browse'].click()
            self.assertEqual(field.value, str(saved))
            self.assertEqual(browser['status'].layout.display, 'none')

    def test_invalid_or_removed_selection_preserves_field_and_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            field = widgets.Text(value='unchanged')
            browser = selectors.path_selector(field, mode='json', start=root)
            for value in (root/'missing.json', root):
                with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock, return_value=str(value)):
                    browser['browse'].click()
                self.assertEqual(field.value, 'unchanged')
                self.assertIn('existing JSON', browser['status'].value)
                self.assertFalse(browser['browse'].disabled)
            saved = root/'good.json'; saved.write_text('{}')
            with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock, return_value=str(saved)):
                browser['browse'].click()
            self.assertEqual(field.value, str(saved))
            self.assertEqual(browser['status'].layout.display, 'none')

    def test_dialog_error_is_escaped_and_does_not_disable_retry(self):
        field = widgets.Text(value='')
        browser = selectors.path_selector(field)
        with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock,
                          side_effect=RuntimeError('unavailable <desktop>')):
            browser['browse'].click()
        self.assertIn('unavailable &lt;desktop&gt;', browser['status'].value)
        self.assertIn('manually', browser['status'].value)
        self.assertFalse(browser['browse'].disabled)
        self.assertFalse(browser['state']['busy'])

    def test_inflight_dialog_is_async_deduplicated_and_cannot_overwrite_newer_path(self):
        async def check(disable):
            field = widgets.Text(value='')
            browser = selectors.path_selector(field)
            gate = asyncio.Event()
            async def dialog(**kwargs):
                await gate.wait()
                return str(Path.home())
            with patch.object(selectors, 'native_path_dialog', side_effect=dialog) as native:
                browser['browse'].click()
                task = browser['state']['task']
                self.assertTrue(browser['state']['busy'])
                self.assertTrue(browser['browse'].disabled)
                browser['browse'].click()
                await asyncio.sleep(0)
                self.assertEqual(native.call_count, 1)
                field.disabled = disable
                field.value = 'newer path'
                gate.set()
                await task
                self.assertEqual(field.value, 'newer path')
                self.assertEqual(browser['browse'].disabled, disable)
                self.assertFalse(browser['state']['busy'])
        for disable in (False, True):
            asyncio.run(check(disable))

    def test_disabled_field_does_not_open_a_dialog(self):
        field = widgets.Text(value='project location', disabled=True)
        browser = selectors.path_selector(field)
        with patch.object(selectors, 'native_path_dialog', new_callable=AsyncMock) as dialog:
            browser['browse'].click()
        dialog.assert_not_called()
        self.assertEqual(field.value, 'project location')
        self.assertTrue(browser['browse'].disabled)

    def test_helpers_and_script_are_embedded_in_both_notebooks(self):
        expected = ast.parse(inspect.getsource(selectors))
        names = {'native_path_dialog', 'path_selector'}
        functions = {n.name: ast.dump(n, include_attributes=False) for n in expected.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ('create_journal_analysis.ipynb', 'clean_and_count_text.ipynb'):
            notebook = json.loads((ROOT/name).read_text())
            nodes = [n for c in notebook['cells'] if c['cell_type'] == 'code'
                     for n in ast.parse(''.join(c['source'])).body]
            actual = {n.name: ast.dump(n, include_attributes=False) for n in nodes
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names}
            self.assertEqual(functions, actual)
            script = next(n for n in nodes if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == '_NATIVE_PATH_DIALOG' for t in n.targets))
            self.assertEqual(ast.literal_eval(script.value), selectors._NATIVE_PATH_DIALOG)

    def test_creation_and_project_selection_still_require_explicit_actions(self):
        state = execute_notebook('create_journal_analysis.ipynb')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root/'archive.json'; archive.write_text('{}')
            with patch.dict(state, native_path_dialog=AsyncMock(return_value=str(root))):
                state['root_selector']['browse'].click()
            with patch.dict(state, native_path_dialog=AsyncMock(return_value=str(archive))):
                state['archive_selector']['browse'].click()
            self.assertEqual(state['root_field'].value, str(root))
            self.assertEqual(state['archive_field'].value, str(archive))
            self.assertIsNone(state['last_project'])
        state = execute_notebook('clean_and_count_text.ipynb')
        with tempfile.TemporaryDirectory() as temporary:
            root = test_paper_categorization.ProjectPaperTests.make_project(self, temporary)
            with patch.dict(state, native_path_dialog=AsyncMock(return_value=str(root))):
                state['paper_project_selector']['browse'].click()
            self.assertIsNone(state['paper_state']['project'])
            state['paper_scan_project_button'].click()
            self.assertTrue(state['paper_folder_selector']['browse'].disabled)
            self.assertTrue(state['paper_folder'].disabled)
            self.assertEqual(state['paper_folder'].value, str(root.resolve()/'paper_categorizations'))
            self.assertFalse((root/'paper_categorizations').exists())


class NativeProcessTests(unittest.TestCase):
    def test_worker_uses_tk_native_dialogs_and_returns_json(self):
        from itertools import product
        for platform, mode in product(('darwin', 'win32'), ('folder', 'json')):
            root = MagicMock()
            tk = types.ModuleType('tkinter'); tk.Tk = MagicMock(return_value=root)
            dialogs = types.ModuleType('tkinter.filedialog')
            dialogs.askdirectory = MagicMock(return_value='/selected folder')
            dialogs.askopenfilename = MagicMock(return_value='/selected ü.JSON')
            tk.filedialog = dialogs
            stream = io.StringIO()
            request = dict(mode=mode, title='Native chooser', initialdir='/initial', initialfile='prior.json')
            with patch.object(sys, 'platform', platform), \
                    patch.dict(sys.modules, {'tkinter': tk, 'tkinter.filedialog': dialogs}), \
                    patch.object(sys, 'stdin', io.StringIO(json.dumps(request))), \
                    patch.object(sys, 'stdout', stream):
                exec(selectors._NATIVE_PATH_DIALOG, {})
            dialog = dialogs.askdirectory if mode == 'folder' else dialogs.askopenfilename
            if platform == 'darwin':
                self.assertNotIn('parent', dialog.call_args.kwargs)
            else:
                self.assertEqual(dialog.call_args.kwargs['parent'], root)
            self.assertEqual(dialog.call_args.kwargs['initialdir'], '/initial')
            if mode == 'folder':
                self.assertTrue(dialog.call_args.kwargs['mustexist'])
            else:
                self.assertEqual(dialog.call_args.kwargs['initialfile'], 'prior.json')
                self.assertEqual(dialog.call_args.kwargs['filetypes'][0][0], 'JSON files')
            root.destroy.assert_called_once()
            self.assertIn('path', json.loads(stream.getvalue()))

    def test_native_process_is_isolated_and_paths_use_stdin_without_a_shell(self):
        import subprocess
        process = MagicMock(returncode=0)
        process.communicate.return_value = (json.dumps({'path': '/Unicode ü/file.json'}), '')
        process.poll.return_value = 0
        with patch.object(subprocess, 'Popen', return_value=process) as popen:
            result = asyncio.run(selectors.native_path_dialog(mode='json', title='Choose $(literal)', initialdir='/a "folder"'))
        self.assertEqual(result, '/Unicode ü/file.json')
        self.assertEqual(popen.call_args.args[0][:4], [sys.executable, '-I', '-B', '-c'])
        self.assertNotIn('shell', popen.call_args.kwargs)
        request = json.loads(process.communicate.call_args.args[0])
        self.assertEqual(request['title'], 'Choose $(literal)')
        self.assertEqual(request['initialdir'], '/a "folder"')
        process.kill.assert_not_called()

    def test_cancelling_the_task_kills_only_its_own_dialog_process(self):
        import subprocess
        import threading
        process = MagicMock(returncode=None)
        ended = threading.Event()
        def communicate(payload):
            ended.wait(5)
            return ('', '')
        process.communicate.side_effect = communicate
        process.poll.return_value = None
        process.kill.side_effect = ended.set
        async def check():
            with patch.object(subprocess, 'Popen', return_value=process):
                task = asyncio.create_task(selectors.native_path_dialog(mode='folder', title='Cancel', initialdir='/'))
                await asyncio.sleep(0.02)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        asyncio.run(check())
        process.kill.assert_called_once()
        process.wait.assert_called_once()
