"""One small control window for the two notebook services; no analysis UI."""
from __future__ import annotations

import argparse
from pathlib import Path
import queue
import threading
import webbrowser

from .notebook_services import NotebookService, SERVICES


def main():
    import tkinter as tk
    from tkinter import messagebox, ttk

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', choices=[spec.key for spec in SERVICES])
    parser.add_argument('--check', action='store_true', help='Check dependencies and notebook paths without opening a window')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        import notebook, ipykernel, ipywidgets  # noqa: F401
        for spec in SERVICES:
            if not (root / spec.notebook).is_file():
                raise FileNotFoundError(f'Notebook not found: {root / spec.notebook}')
    except (ImportError, FileNotFoundError) as error:
        if args.check:
            parser.exit(1, str(error) + '\nInstall requirements.txt in this Python environment.\n')
        messagebox.showerror('Cannot launch notebooks',
                             f'{error}\n\nInstall requirements.txt in this Python environment.')
        return
    if args.check:
        print('Python, Tk, Jupyter Notebook, ipykernel and ipywidgets are available.')
        for spec in SERVICES:
            print(f'{spec.title}: {root / spec.notebook}')
        return

    window = tk.Tk()
    window.title('Journal Notebook Launcher')
    window.minsize(720, 370)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Journal notebook services', font=('', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Start a service, then run all notebook cells in your browser.').pack(anchor='w', pady=(5, 12))
    events = queue.Queue()
    rows = {}
    closing = False

    def background(key, action, callback):
        row = rows[key]
        row['busy'] = True
        render(key)

        def work():
            try:
                result = action()
                events.put((key, callback, result, None))
            except Exception as error:
                events.put((key, callback, None, error))
        threading.Thread(target=work, daemon=True).start()

    def open_notebook(key):
        row = rows[key]
        url = row['service'].url
        if url:
            def opened(result):
                row['message'].set('Running' if result else 'Browser did not open. Copy the link into your browser.')
            background(key, lambda: webbrowser.open(url), opened)

    def start(key):
        row = rows[key]
        row['message'].set('Starting Jupyter…')
        background(key, row['service'].start, lambda _: open_notebook(key))

    def stop(key, force=False):
        row = rows[key]
        row['message'].set('Stopping service and kernels…')
        background(key, row['service'].force_stop if force else row['service'].stop,
                   lambda _: row['message'].set('Stopped'))

    def kill(key):
        if messagebox.askyesno('Kill kernels?', 'Stop all kernels for this service? Unsaved variables will be lost.', parent=window):
            row = rows[key]
            row['message'].set('Killing kernels…')
            background(key, row['service'].kill_kernels,
                       lambda count: row['message'].set(f'Killed {count} kernel(s). Reopen the notebook and run all cells.'))

    def render(key):
        row = rows[key]
        service = row['service']
        busy = row['busy'] or closing
        row['start'].configure(state='disabled' if busy or service.running else 'normal')
        for name in ('stop', 'force'):
            row[name].configure(state='normal' if not busy and service.running else 'disabled')
        row['kill'].configure(state='normal' if not busy and service.running and service.port else 'disabled')
        row['port'].set(f'Port: {service.port}' if service.port else 'Port: —')
        row['link'].configure(text='Open notebook' if service.url else 'Start to get a link',
                              foreground='#145ea8' if service.url else '#666666',
                              cursor='hand2' if service.url else '')
        address = service.url or ''
        if row['url'].get() != address:
            row['url'].set(address)

    for spec in SERVICES:
        box = ttk.LabelFrame(frame, text=spec.title, padding=10)
        box.pack(fill='x', pady=(0, 10))
        row = dict(service=NotebookService(spec, root), busy=False,
                   message=tk.StringVar(value='Stopped'), port=tk.StringVar(value='Port: —'), url=tk.StringVar())
        rows[spec.key] = row
        ttk.Label(box, textvariable=row['message']).grid(row=0, column=0, columnspan=4, sticky='w')
        ttk.Label(box, textvariable=row['port']).grid(row=0, column=4, sticky='e')
        for column, (name, label, command) in enumerate((
                ('start', 'Start', lambda key=spec.key: start(key)),
                ('kill', 'Kill kernels', lambda key=spec.key: kill(key)),
                ('stop', 'Stop', lambda key=spec.key: stop(key)),
                ('force', 'Force stop', lambda key=spec.key: stop(key, True)))):
            row[name] = ttk.Button(box, text=label, command=command)
            row[name].grid(row=1, column=column, sticky='w', pady=6, padx=(0, 6))
        row['link'] = ttk.Label(box)
        row['link'].grid(row=2, column=0, sticky='w', padx=(0, 10))
        row['link'].bind('<Button-1>', lambda event, key=spec.key: open_notebook(key) if not rows[key]['busy'] and not closing else None)
        ttk.Entry(box, textvariable=row['url'], state='readonly').grid(row=2, column=1, columnspan=4, sticky='ew')
        box.columnconfigure(4, weight=1)
        render(spec.key)

    ttk.Label(frame, text='Links open the notebook and can also be copied. Closing this window stops both services.').pack(anchor='w')

    def close():
        nonlocal closing
        if any(row['busy'] for row in rows.values()):
            messagebox.showinfo('Please wait', 'Wait for the current service action to finish, then close the launcher.', parent=window)
            return
        if any(row['service'].running for row in rows.values()) and not messagebox.askyesno(
                'Stop notebook services?', 'Close the launcher and stop its services and kernels? Save your notebooks first.', parent=window):
            return
        closing = True
        for key, row in rows.items():
            background(key, row['service'].stop, lambda _: None)

    window.protocol('WM_DELETE_WINDOW', close)
    if window.tk.call('tk', 'windowingsystem') == 'aqua':
        # Command-Q must use the same save prompt and cleanup as closing the window.
        window.createcommand('::tk::mac::Quit', close)

    def poll():
        while True:
            try:
                key, callback, result, error = events.get_nowait()
            except queue.Empty:
                break
            row = rows[key]
            row['busy'] = False
            if error:
                row['message'].set(str(error))
                messagebox.showerror('Notebook service', f'{error}\n\nLog: {row["service"].log_path}', parent=window)
            else:
                callback(result)
        for key, row in rows.items():
            service = row['service']
            if not row['busy']:
                service.track_children()
            if not row['busy'] and service.process is not None and not service.running:
                row['message'].set(f'Service exited. See {service.log_path}')
                background(key, service.force_stop, lambda _: None)
            render(key)
        if closing and all(not row['busy'] for row in rows.values()):
            if all(row['service'].process is None for row in rows.values()):
                window.destroy()
                return
            # A failed shutdown leaves the controls available for another attempt.
            cancel_close()
        window.after(200, poll)

    def cancel_close():
        nonlocal closing
        closing = False

    window.after(100, poll)
    if args.service:
        window.after(200, lambda: start(args.service))
    try:
        window.mainloop()
    finally:
        for row in rows.values():
            row['service'].stop()


if __name__ == '__main__':
    main()
