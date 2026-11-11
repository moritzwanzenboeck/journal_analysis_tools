"""Exercise the same real, hidden control window on Windows and both Mac runners."""
from dataclasses import replace
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import launcher
from app.notebook_services import NotebookService


@unittest.skipUnless(sys.platform in ('win32', 'darwin') or os.environ.get('DISPLAY'), 'A desktop session is required')
class LauncherWindowTests(unittest.TestCase):
    def test_start_links_kernel_buttons_and_close_cleanup(self):
        import tkinter as tk
        from tkinter import messagebox, ttk

        window = tk.Tk()
        window.withdraw()
        failures, managed = [], []
        stage = 0

        def fail(error):
            failures.append(error)
            window.destroy()

        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)

        def text(widget):
            variable = widget.cget('textvariable')
            return str(widget.getvar(variable)) if variable else str(widget.cget('text'))

        window.report_callback_exception = lambda kind, error, traceback: fail(error)
        with tempfile.TemporaryDirectory(prefix="journal's window tests ä ") as temporary:
            def service(spec, root):
                instance = NotebookService(replace(spec, preferred_port=0), root, log_dir=temporary)
                managed.append(instance)
                return instance

            with patch.object(tk, 'Tk', return_value=window), \
                    patch.object(launcher, 'NotebookService', side_effect=service), \
                    patch.object(launcher.webbrowser, 'open', return_value=False) as browser, \
                    patch.object(messagebox, 'askyesno', return_value=True), \
                    patch.object(messagebox, 'showerror', side_effect=lambda *args, **kwargs: fail(AssertionError(str(args)))), \
                    patch.object(sys, 'argv', ['notebook_launcher.py']):
                def tick():
                    nonlocal stage
                    try:
                        items = list(widgets(window))
                        buttons = [item for item in items if isinstance(item, ttk.Button)]
                        labels = [item for item in items if isinstance(item, ttk.Label)]
                        messages = [text(item) for item in labels]
                        kills = [item for item in buttons if text(item) == 'Kill kernels']
                        links = [item for item in buttons if text(item) == 'Open notebook']
                        if stage == 0:
                            for button in buttons:
                                if text(button) == 'Start':
                                    button.invoke()
                            stage = 1
                        elif stage == 1 and sum('Browser did not open' in value for value in messages) == 2:
                            addresses = [item.get() for item in items if isinstance(item, ttk.Entry)]
                            for instance in managed:
                                self.assertIn(f'Port: {instance.port}', messages)
                                self.assertIn(instance.url, addresses)
                            self.assertNotEqual(managed[0].port, managed[1].port)
                            managed[0].request('api/kernels', 'POST')
                            self.assertEqual(len(links), 2)
                            for button in links:
                                self.assertFalse(button.instate(['disabled']))
                                button.invoke()
                            stage = 2
                        elif stage == 2 and browser.call_count == 4 and all(not button.instate(['disabled']) for button in kills):
                            for button in kills:
                                button.invoke()
                            stage = 3
                        elif stage == 3 and sum(value.startswith('Killed ') for value in messages) == 2:
                            self.assertTrue(any(value.startswith('Killed 1 kernel') for value in messages))
                            self.assertTrue(any(value.startswith('Killed 0 kernel') for value in messages))
                            for instance in managed:
                                self.assertEqual(instance.request('api/kernels'), [])
                            stage = 4
                            if window.tk.call('tk', 'windowingsystem') == 'aqua':
                                window.tk.call('::tk::mac::Quit')
                            else:
                                window.tk.call(window.protocol('WM_DELETE_WINDOW'))
                        if stage < 4:
                            window.after(100, tick)
                    except Exception as error:
                        fail(error)

                window.after(200, tick)
                def timed_out():
                    details = [(item.spec.key, item.running, item.port) for item in managed]
                    fail(TimeoutError(f'Window test timed out at stage {stage}; '
                                      f'browser calls={browser.call_count}; services={details}'))

                window.after(90000, timed_out)
                try:
                    launcher.main()
                finally:
                    for instance in managed:
                        instance.force_stop()
            if failures:
                raise failures[0]
            self.assertEqual(stage, 4)
            self.assertTrue(all(instance.process is None for instance in managed))
