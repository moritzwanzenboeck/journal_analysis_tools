"""Native desktop interface. Run directly or build the self-contained macOS app."""
from __future__ import annotations

import calendar
from datetime import date
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from app_support import APP_NAME, VERSION, default_dates, load_settings, project_options, save_settings
import journal_tools as tools
import text_tools


class DateField(ttk.Frame):
    """ISO date entry with a keyboard-accessible calendar picker."""
    def __init__(self, parent, value):
        super().__init__(parent)
        self.value = tk.StringVar(value=value)
        ttk.Entry(self, textvariable=self.value, width=13).pack(side='left')
        ttk.Button(self, text='Choose…', command=self.pick, width=8).pack(side='left', padx=(5, 0))

    def pick(self):
        try:
            current = date.fromisoformat(self.value.get())
        except ValueError:
            current = date.today()
        popup = tk.Toplevel(self)
        popup.title('Choose date')
        popup.transient(self.winfo_toplevel())
        popup.resizable(False, False)
        frame = ttk.Frame(popup, padding=14)
        frame.pack()
        month = [current.year, current.month]
        title = ttk.Label(frame, anchor='center', width=24)
        title.grid(row=0, column=1, columnspan=5, pady=(0, 8))
        days = ttk.Frame(frame)
        days.grid(row=1, column=0, columnspan=7)

        def choose(day):
            self.value.set(date(month[0], month[1], day).isoformat())
            popup.destroy()

        def draw(step=0):
            year, index = divmod(month[0] * 12 + month[1] - 1 + step, 12)
            if not 1 <= year <= 9999:
                return
            month[:] = [year, index + 1]
            title.config(text=f'{calendar.month_name[index + 1]} {year}')
            for child in days.winfo_children():
                child.destroy()
            for column, name in enumerate(('Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su')):
                ttk.Label(days, text=name, anchor='center', width=4).grid(row=0, column=column)
            for row, week in enumerate(calendar.monthcalendar(year, index + 1), 1):
                for column, day in enumerate(week):
                    if day:
                        ttk.Button(days, text=str(day), width=3,
                                   command=lambda number=day: choose(number)).grid(row=row, column=column, padx=1, pady=1)
        ttk.Button(frame, text='‹', width=3, command=lambda: draw(-1)).grid(row=0, column=0)
        ttk.Button(frame, text='›', width=3, command=lambda: draw(1)).grid(row=0, column=6)
        popup.bind('<Escape>', lambda event: popup.destroy())
        draw()
        popup.update_idletasks()
        popup.geometry(f'+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height()}')
        popup.grab_set()


class JournalApp(tk.Tk):
    def __init__(self, settings_file=None):
        super().__init__()
        self.settings_file = settings_file
        self.settings = load_settings(settings_file)
        self.title(APP_NAME)
        width = min(1080, max(820, self.winfo_screenwidth() - 80))
        height = min(850, max(640, self.winfo_screenheight() - 120))
        self.geometry(f'{width}x{height}')
        self.minsize(820, 640)
        self.configure(background='#F3F5F7')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Helvetica', 12), background='#F3F5F7', foreground='#253548')
        style.configure('TButton', padding=(12, 7))
        style.configure('Primary.TButton', background='#236A63', foreground='white')
        style.map('Primary.TButton', background=[('active', '#18544E'), ('disabled', '#B0C4C0')])
        style.configure('Danger.TButton', background='#BA3737', foreground='white')
        style.map('Danger.TButton', background=[('active', '#922B2B')])
        style.configure('Title.TLabel', font=('Helvetica', 23, 'bold'))
        style.configure('Subtitle.TLabel', foreground='#5D6B7B')
        style.configure('TLabelframe', padding=12)
        style.configure('TNotebook.Tab', padding=(20, 10))
        self.events = queue.Queue()
        self.busy = False
        self.candidates = []
        self.selected_journal = None
        self.last_project = self.settings.get('last_project', '')
        self.split_source = None
        self.splits = []
        self.counts_job = None
        heading = ttk.Frame(self, padding=(24, 20, 24, 12))
        heading.pack(fill='x')
        ttk.Label(heading, text=APP_NAME, style='Title.TLabel').pack(anchor='w')
        ttk.Label(heading, text='Create a project. Work with paper text. Everything stays on your computer.',
                  style='Subtitle.TLabel').pack(anchor='w', pady=(5, 0))
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=20, pady=(0, 18))
        self.build_project_tab()
        self.build_text_tab()
        self.restore_journal()
        self.query.trace_add('write', self.query_changed)
        self.protocol('WM_DELETE_WINDOW', self.close_app)
        self.after(100, self.poll_events)

    def build_project_tab(self):
        self.project_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.project_tab, text='Create project')
        self.project_canvas = tk.Canvas(self.project_tab, highlightthickness=0, background='#F3F5F7')
        scrollbar = ttk.Scrollbar(self.project_tab, orient='vertical', command=self.project_canvas.yview)
        self.project_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.project_canvas.pack(side='left', fill='both', expand=True)
        page = ttk.Frame(self.project_canvas, padding=18)
        window = self.project_canvas.create_window((0, 0), window=page, anchor='nw')
        page.bind('<Configure>', lambda event: self.project_canvas.configure(scrollregion=self.project_canvas.bbox('all')))
        self.project_canvas.bind('<Configure>', lambda event: self.project_canvas.itemconfigure(
            window, width=self.project_canvas.winfo_width(),
            height=max(self.project_canvas.winfo_height(), page.winfo_reqheight())))
        self.bind_all('<MouseWheel>', self.scroll_project, add='+')
        page.columnconfigure(1, weight=1)
        self.query = tk.StringVar(value=self.settings.get('query', ''))
        ttk.Label(page, text='Journal title or ISSN').grid(row=0, column=0, sticky='w', padx=(0, 15))
        entry = ttk.Entry(page, textvariable=self.query)
        entry.grid(row=0, column=1, sticky='ew')
        entry.bind('<Return>', lambda event: self.search())
        self.search_button = ttk.Button(page, text='Find journal', command=self.search)
        self.search_button.grid(row=0, column=2, padx=(10, 0))
        ttk.Label(page, text='Select journal').grid(row=1, column=0, sticky='w', pady=12)
        self.journals = ttk.Combobox(page, state='readonly')
        self.journals.grid(row=1, column=1, columnspan=2, sticky='ew')
        self.journals.bind('<<ComboboxSelected>>', self.journal_selected)
        first, last = default_dates()
        ttk.Label(page, text='Date range (inclusive)').grid(row=2, column=0, sticky='w')
        dates = ttk.Frame(page)
        dates.grid(row=2, column=1, columnspan=2, sticky='w')
        self.start = DateField(dates, self.settings.get('start', first))
        self.start.pack(side='left')
        ttk.Label(dates, text=' through ').pack(side='left', padx=8)
        self.end = DateField(dates, self.settings.get('end', last))
        self.end.pack(side='left')
        ttk.Label(page, text='Random papers').grid(row=3, column=0, sticky='w', pady=12)
        self.count = tk.StringVar(value=str(self.settings.get('count', 10)))
        ttk.Spinbox(page, from_=1, to=1000000, textvariable=self.count, width=10).grid(row=3, column=1, sticky='w')
        ttk.Label(page, text='Save projects in').grid(row=4, column=0, sticky='w')
        documents = Path.home() / 'Documents'
        self.parent_path = tk.StringVar(value=self.settings.get('parent', str(documents if documents.is_dir() else Path.home())))
        ttk.Entry(page, textvariable=self.parent_path).grid(row=4, column=1, sticky='ew')
        ttk.Button(page, text='Choose folder…', command=self.choose_parent).grid(row=4, column=2, padx=(10, 0))
        ttk.Label(page, text='Project folder name').grid(row=5, column=0, sticky='w', pady=(12, 0))
        self.folder = tk.StringVar()
        ttk.Entry(page, textvariable=self.folder).grid(row=5, column=1, columnspan=2, sticky='ew', pady=(12, 0))
        ttk.Label(page, text='Leave blank to use the creation date, journal and date range.',
                  style='Subtitle.TLabel').grid(row=6, column=1, columnspan=2, sticky='w', pady=(4, 10))
        self.advanced_visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(page, text='Advanced options', variable=self.advanced_visible,
                        command=self.toggle_advanced).grid(row=7, column=0, columnspan=3, sticky='w')
        self.advanced = ttk.Frame(page, padding=(0, 10))
        self.advanced.columnconfigure(1, weight=1)
        self.basis = tk.StringVar(value=self.settings.get('basis', 'first'))
        self.seed = tk.StringVar()
        self.email = tk.StringVar()
        self.archive = tk.StringVar()
        self.include_notices = tk.BooleanVar(value=self.settings.get('include_notices', False))
        ttk.Label(self.advanced, text='Publication date').grid(row=0, column=0, sticky='w', padx=(0, 15))
        ttk.Combobox(self.advanced, values=('first', 'online', 'print'), state='readonly',
                     textvariable=self.basis, width=12).grid(row=0, column=1, sticky='w')
        ttk.Label(self.advanced, text='Random seed (optional)').grid(row=1, column=0, sticky='w', pady=8)
        ttk.Entry(self.advanced, textvariable=self.seed, width=20).grid(row=1, column=1, sticky='w')
        ttk.Label(self.advanced, text='Contact email (optional)').grid(row=2, column=0, sticky='w')
        ttk.Entry(self.advanced, textvariable=self.email).grid(row=2, column=1, sticky='ew')
        ttk.Checkbutton(self.advanced, text='Include notices and editorials in the sample',
                        variable=self.include_notices).grid(row=3, column=0, columnspan=3, sticky='w', pady=8)
        ttk.Label(self.advanced, text='Archived metadata (optional)').grid(row=4, column=0, sticky='w')
        ttk.Entry(self.advanced, textvariable=self.archive).grid(row=4, column=1, sticky='ew')
        ttk.Button(self.advanced, text='Choose JSON…', command=self.choose_archive).grid(row=4, column=2, padx=(10, 0))
        actions = ttk.Frame(page)
        actions.grid(row=9, column=0, columnspan=3, sticky='ew', pady=(16, 8))
        self.create_button = ttk.Button(actions, text='Create project', style='Primary.TButton', command=self.create, state='disabled')
        self.create_button.pack(side='left')
        self.open_button = ttk.Button(actions, text='Open project folder', command=self.open_project,
                                      state='normal' if self.last_project and Path(self.last_project).is_dir() else 'disabled')
        self.open_button.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(page, mode='indeterminate')
        self.progress.grid(row=10, column=0, columnspan=3, sticky='ew', pady=(0, 8))
        self.project_status = tk.StringVar(value='Find a journal to begin. Projects contain metadata exports and the text-cleaning notebook.')
        ttk.Label(page, textvariable=self.project_status, wraplength=740).grid(row=11, column=0, columnspan=3, sticky='w', pady=(0, 8))
        self.project_log = ScrolledText(page, height=8, wrap='word', font=('Helvetica', 11), relief='solid', borderwidth=1)
        self.project_log.grid(row=12, column=0, columnspan=3, sticky='nsew')
        self.project_log.config(state='disabled')
        page.rowconfigure(12, weight=1)

    def scroll_project(self, event):
        if self.tabs.select() == str(self.project_tab) and not isinstance(event.widget, tk.Text):
            delta = -int(event.delta / 120) if abs(event.delta) >= 120 else -int(event.delta)
            self.project_canvas.yview_scroll(delta, 'units')

    def toggle_advanced(self):
        if self.advanced_visible.get():
            self.advanced.grid(row=8, column=0, columnspan=3, sticky='ew')
        else:
            self.advanced.grid_remove()
        self.update_idletasks()
        self.project_canvas.event_generate("<Configure>")

    def choose_parent(self):
        path = filedialog.askdirectory(parent=self, title='Choose where to save new projects', initialdir=self.parent_path.get())
        if path:
            self.parent_path.set(path)

    def choose_archive(self):
        path = filedialog.askopenfilename(parent=self, title='Choose archived Crossref metadata', filetypes=[('JSON metadata', '*.json')])
        if path:
            self.archive.set(path)

    def restore_journal(self):
        saved = self.settings.get('journal')
        try:
            if saved:
                self.candidates = [tools.Journal(saved['name'], tuple(saved['issns']))]
                self.journals.config(values=[self.journal_label(self.candidates[0])])
                self.journals.current(0)
                self.journal_selected()
        except (KeyError, TypeError, ValueError):
            pass

    @staticmethod
    def journal_label(journal):
        return f"{journal.name} ({', '.join(journal.issns)})"

    def query_changed(self, *args):
        self.selected_journal = None
        self.candidates = []
        self.journals.set('')
        self.journals.config(values=[])
        self.create_button.config(state='disabled')

    def journal_selected(self, event=None):
        index = self.journals.current()
        self.selected_journal = self.candidates[index] if 0 <= index < len(self.candidates) else None
        self.create_button.config(state='normal' if self.selected_journal and not self.busy else 'disabled')

    def run_job(self, function, finished, status):
        if self.busy:
            return
        self.busy = True
        self.search_button.config(state='disabled')
        self.create_button.config(state='disabled')
        self.progress.start(12)
        self.project_status.set(status)

        def work():
            try:
                result = function()
            except Exception as error:
                self.events.put(('error', str(error)))
            else:
                self.events.put(('success', (finished, result)))
        threading.Thread(target=work, name='journal-request', daemon=False).start()

    def poll_events(self):
        try:
            kind, payload = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            self.search_button.config(state='normal')
            self.journal_selected()
            if kind == 'error':
                self.project_status.set(payload)
                messagebox.showerror('Could not complete the request', payload, parent=self)
            else:
                finished, result = payload
                finished(result)
        self.after(100, self.poll_events)

    def search(self):
        if self.busy:
            return
        query = self.query.get().strip()
        if not query:
            self.project_status.set('Enter a journal title or ISSN.')
            return
        email = self.email.get().strip() or None
        self.query_changed()

        def complete(candidates):
            if self.query.get().strip() != query:
                self.project_status.set('The search changed. Click Find journal for the new query.')
                return
            self.candidates = candidates
            self.journals.config(values=[self.journal_label(j) for j in candidates])
            self.project_status.set(f'Found {len(candidates)} journal(s). Select the intended journal.' if candidates else 'No matching journals. Try an ISSN or a more specific title.')
            if candidates:
                self.journals.focus_set()
        self.run_job(lambda: tools.find_journals(query, email), complete, 'Looking up journals…')

    def create(self):
        if self.busy:
            return
        try:
            options = project_options(self.selected_journal, self.start.value.get(), self.end.value.get(),
                                      self.count.get(), self.parent_path.get(), basis=self.basis.get(),
                                      seed=self.seed.get(), folder=self.folder.get(), archive=self.archive.get())
        except ValueError as error:
            messagebox.showerror('Check project settings', str(error), parent=self)
            return
        options.update(include_notices=self.include_notices.get(), email=self.email.get().strip() or None)
        self.run_job(lambda: tools.create_project(**options), self.project_created,
                     'Fetching metadata and preparing the sample. This can take a few minutes…')

    def project_created(self, result):
        self.last_project = str(result['path'])
        self.open_button.config(state='normal')
        report = result['selection_report']
        self.project_status.set(f"Created {len(result['selected'])} sampled papers from {len(result['rows'])} records. Your project is ready.")
        lines = [f"Project: {self.last_project}", f"Journal: {result['journal'].name}",
                 f"Eligible records: {report['eligible_entry_count']}; saved seed: {result['config']['seed']}", '']
        lines += [f"{i}. {row['title']}\n   {row['url']}" for i, row in enumerate(result['selected'], 1)]
        self.project_log.config(state='normal')
        self.project_log.delete('1.0', 'end')
        self.project_log.insert('1.0', '\n'.join(lines))
        self.project_log.config(state='disabled')
        self.persist()

    def open_project(self):
        if not self.last_project or not Path(self.last_project).is_dir():
            messagebox.showerror('Folder unavailable', 'The project folder has moved or is unavailable.', parent=self)
            return
        if sys.platform == 'darwin':
            subprocess.Popen(['open', self.last_project])
        elif sys.platform == 'win32':
            import os
            os.startfile(self.last_project)
        else:
            subprocess.Popen(['xdg-open', self.last_project])

    def build_text_tab(self):
        page = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(page, text='Clean and count text')
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        page.rowconfigure(6, weight=1)
        ttk.Label(page, text='Original text', font=('Helvetica', 13, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.original = ScrolledText(page, height=7, undo=True, wrap='word', font=('Helvetica', 12))
        self.original.grid(row=1, column=0, sticky='nsew')
        actions = ttk.Frame(page)
        actions.grid(row=2, column=0, sticky='ew', pady=10)
        ttk.Button(actions, text='Find line-end hyphens', command=self.find_splits).pack(side='left')
        ttk.Button(actions, text='Apply cleanup', style='Primary.TButton', command=self.apply_cleanup).pack(side='left', padx=8)
        ttk.Button(actions, text='Clear original text', style='Danger.TButton', command=self.clear_original).pack(side='right', padx=(32, 0))
        self.review = ttk.Frame(page)
        self.review.columnconfigure(0, weight=1)
        ttk.Label(self.review, text='Select splits that should keep a genuine hyphen (multiple selections allowed):').grid(row=0, column=0, sticky='w')
        self.hyphens = tk.Listbox(self.review, height=3, selectmode='multiple', exportselection=False, font=('Helvetica', 11))
        self.hyphens.grid(row=1, column=0, sticky='ew', pady=(5, 5))
        self.text_status = tk.StringVar(value='Paste text copied from a paper, then apply cleanup. Review automatic paragraph boundaries against the PDF.')
        ttk.Label(page, textvariable=self.text_status, wraplength=740, style='Subtitle.TLabel').grid(row=4, column=0, sticky='w', pady=(0, 10))
        ttk.Label(page, text='Cleaned text — editable', font=('Helvetica', 13, 'bold')).grid(row=5, column=0, sticky='w', pady=(0, 6))
        self.cleaned = ScrolledText(page, height=9, undo=True, wrap='word', font=('Helvetica', 12))
        self.cleaned.grid(row=6, column=0, sticky='nsew')
        self.cleaned.bind('<<Modified>>', self.cleaned_changed)
        self.counts = tk.StringVar()
        ttk.Label(page, textvariable=self.counts, font=('Helvetica', 12, 'bold')).grid(row=7, column=0, sticky='w', pady=10)
        bottom = ttk.Frame(page)
        bottom.grid(row=8, column=0, sticky='ew')
        ttk.Button(bottom, text='Copy word count', command=lambda: self.copy_count('words')).pack(side='left')
        ttk.Button(bottom, text='Copy paragraph count', command=lambda: self.copy_count('paragraphs')).pack(side='left', padx=8)
        ttk.Button(bottom, text='Save cleaned text…', command=self.save_text).pack(side='right')
        ttk.Button(bottom, text='Copy cleaned text', command=lambda: self.copy(self.cleaned.get('1.0', 'end-1c'))).pack(side='right', padx=8)
        self.copy_status = tk.StringVar()
        ttk.Label(page, textvariable=self.copy_status, style='Subtitle.TLabel').grid(row=9, column=0, sticky='w', pady=(7, 0))
        self.update_counts()

    def find_splits(self):
        self.split_source = self.original.get('1.0', 'end-1c')
        self.splits = text_tools.find_line_end_hyphens(self.split_source)
        self.hyphens.delete(0, 'end')
        for split in self.splits:
            self.hyphens.insert('end', f"Line {split['line']}: {split['left']}- | {split['right']} → {split['joined']} (select to keep {split['hyphenated']})")
        if self.splits:
            self.review.grid(row=3, column=0, sticky='ew')
        else:
            self.review.grid_remove()
        self.text_status.set(f'Found {len(self.splits)} line-end split(s). Select genuine hyphens, then click Apply cleanup.')

    def apply_cleanup(self):
        if self.split_source != self.original.get('1.0', 'end-1c'):
            self.find_splits()
            if self.splits:
                return
        result = text_tools.clean_text(self.split_source, keep_hyphens=set(self.hyphens.curselection()))
        self.cleaned.delete('1.0', 'end')
        self.cleaned.insert('1.0', result)
        self.update_counts()
        self.text_status.set('Cleanup applied. Edit the cleaned result as needed; counts update automatically.')

    def clear_original(self):
        self.original.delete('1.0', 'end')
        self.split_source = None
        self.splits = []
        self.hyphens.delete(0, 'end')
        self.review.grid_remove()
        self.text_status.set('Original text cleared.')

    def cleaned_changed(self, event=None):
        if self.cleaned.edit_modified():
            self.cleaned.edit_modified(False)
            if self.counts_job is not None:
                self.after_cancel(self.counts_job)
            self.counts_job = self.after(150, self.update_counts)

    def update_counts(self):
        if self.counts_job is not None:
            self.after_cancel(self.counts_job)
            self.counts_job = None
        counts = text_tools.count_text(self.cleaned.get('1.0', 'end-1c'))
        self.counts.set(f"Words: {counts['words']}     Paragraphs: {counts['paragraphs']}     Characters: {counts['characters_including_whitespace']}     Without whitespace: {counts['characters_excluding_whitespace']}")
        self.copy_status.set('')
        return counts

    def copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self.copy_status.set('Copied to clipboard.')

    def copy_count(self, metric):
        self.copy(str(self.update_counts()[metric]))

    def save_text(self):
        path = filedialog.asksaveasfilename(parent=self, title='Save cleaned text', defaultextension='.txt', filetypes=[('Text file', '*.txt')])
        if path:
            try:
                Path(path).write_text(self.cleaned.get('1.0', 'end-1c'), encoding='utf-8')
            except OSError as error:
                messagebox.showerror('Could not save text', str(error), parent=self)
            else:
                self.copy_status.set('Cleaned text saved.')

    def persist(self):
        settings = dict(query=self.query.get(), start=self.start.value.get(), end=self.end.value.get(),
                        count=self.count.get(), parent=self.parent_path.get(), basis=self.basis.get(),
                        include_notices=self.include_notices.get(), last_project=self.last_project)
        if self.selected_journal:
            settings['journal'] = dict(name=self.selected_journal.name, issns=list(self.selected_journal.issns))
        try:
            save_settings(settings, self.settings_file)
        except OSError:
            self.project_status.set('Settings could not be saved. Your project files are still available.')

    def close_app(self):
        if self.busy and not messagebox.askyesno('Close window?', 'The current request will finish in the background. Close this window?', parent=self):
            return
        self.persist()
        self.destroy()


def smoke_test(report_path):
    """Exercise the actual app, bundled resources and offline project creation."""
    import tempfile
    import time
    from app_support import default_dates
    with tempfile.TemporaryDirectory(prefix='journal-app-smoke-') as temporary:
        settings = Path(temporary) / 'settings.json'
        app = JournalApp(settings_file=settings)
        app.geometry('900x680')
        app.update()
        app.advanced_visible.set(True)
        app.toggle_advanced()
        app.update()
        assert app.project_canvas.bbox('all')[3] >= app.project_canvas.winfo_height()
        app.start.pick()
        app.update()
        for child in app.start.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        journal = tools.Journal('Smoke Test Journal', ('1234-5679',))
        raw = [{'DOI': '10.1234/smoke', 'type': 'journal-article', 'ISSN': ['1234-5679'],
                'title': ['Test paper'], 'published': {'date-parts': [[2024, 6, 1]]}}]
        archive = Path(temporary) / 'archive.json'
        archive.write_text(json.dumps(raw))
        app.query.set('Smoke Test Journal')
        app.candidates = [journal]
        app.journals.config(values=[app.journal_label(journal)])
        app.journals.current(0)
        app.journal_selected()
        app.start.value.set('2024-01-01')
        app.end.value.set('2024-12-31')
        app.count.set('1')
        app.parent_path.set(temporary)
        app.folder.set('test-project')
        app.archive.set(str(archive))
        app.create()
        deadline = time.monotonic() + 15
        while app.busy and time.monotonic() < deadline:
            app.update()
            time.sleep(0.02)
        assert not app.busy, 'Background project creation timed out'
        assert app.last_project, 'No project was created'
        project = Path(app.last_project)
        assert (project / 'output').is_dir()
        assert not (project / 'papers').exists()
        assert not (project / 'analysis').exists()
        assert (project / 'clean_and_count_text.ipynb').is_file()
        app.tabs.select(1)
        app.original.insert('1.0', 'Result (𝑝<.1\n).\nNext!')
        app.apply_cleanup()
        assert app.cleaned.get('1.0', 'end-1c') == 'Result (𝑝<.1).\n\nNext!'
        assert app.update_counts()['paragraphs'] == 2
        app.copy_count('paragraphs')
        assert app.clipboard_get() == '2'
        cleaned = app.cleaned.get('1.0', 'end-1c')
        app.clear_original()
        assert app.original.get('1.0', 'end-1c') == ''
        assert app.cleaned.get('1.0', 'end-1c') == cleaned
        app.persist()
        assert load_settings(settings)['last_project'] == str(project)
        # Ensure TLS certificates and timezone resources are present in the bundle.
        assert tools.tls_context().cert_store_stats()['x509_ca'] > 0
        assert default_dates()[0]
        app.destroy()
        Path(report_path).write_text(json.dumps({'status': 'passed', 'version': VERSION,
            'checks': ['window', 'compact layout', 'calendar', 'background project', 'bundled template', 'text cleanup', 'clipboard', 'clear button', 'settings', 'TLS certificates', 'timezone']}))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        smoke_test(sys.argv[2])
        return
    JournalApp().mainloop()


if __name__ == '__main__':
    main()
