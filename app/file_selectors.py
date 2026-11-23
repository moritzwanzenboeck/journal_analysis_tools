"""Operating-system path dialogs, also embedded in standalone project notebooks."""


_NATIVE_PATH_DIALOG = r'''
import json
import sys
import tkinter as tk
from tkinter import filedialog

root = None
try:
    request = json.load(sys.stdin)
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    options = dict(parent=root, title=request["title"], initialdir=request["initialdir"])
    if request["mode"] == "folder":
        selected = filedialog.askdirectory(mustexist=True, **options)
    elif request["mode"] == "json":
        if request.get("initialfile"):
            options["initialfile"] = request["initialfile"]
        selected = filedialog.askopenfilename(
            filetypes=[("JSON files", ("*.json", "*.JSON")), ("All files", "*")], **options)
    else:
        raise ValueError("Unknown selection mode.")
    print(json.dumps({"path": selected or ""}), flush=True)
except Exception as error:
    print(json.dumps({"error": str(error)}), flush=True)
    sys.exit(1)
finally:
    if root is not None:
        root.destroy()
'''


async def native_path_dialog(*, mode, title, initialdir, initialfile=None):
    """Run Tk on its own process/main thread while the kernel stays responsive."""
    import asyncio
    import json
    import subprocess
    import sys

    request = dict(mode=mode, title=title, initialdir=str(initialdir), initialfile=initialfile)
    # A worker thread waits for the child, which owns the native GUI. This also
    # works with Windows Jupyter's selector event loop (no async subprocess API).
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", _NATIVE_PATH_DIALOG],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
    )
    try:
        stdout, stderr = await asyncio.to_thread(process.communicate, json.dumps(request))
        try:
            response = json.loads(stdout)
        except (ValueError, TypeError):
            raise RuntimeError("The system file chooser could not start. You can still enter a path manually.") from None
        if process.returncode or response.get("error"):
            raise RuntimeError(response.get("error") or "The system file chooser could not start.")
        if not isinstance(response.get("path"), str):
            raise RuntimeError("The system file chooser returned an invalid path.")
        return response["path"] or None
    finally:
        if process.poll() is None:
            process.kill()
            await asyncio.to_thread(process.wait)


def path_selector(field, *, mode="folder", title="Choose a folder", start=None):
    """Add a native folder/file dialog button; selection only fills the path field."""
    import asyncio
    from html import escape
    from pathlib import Path
    import ipywidgets as widgets

    if mode not in {"folder", "json"}:
        raise ValueError("Selector mode must be folder or json.")
    state = {"busy": False, "task": None}
    field.layout = widgets.Layout(width="100%", min_width="0", flex="1 1 280px")
    browse = widgets.Button(description="Browse…", tooltip=title,
                            layout=widgets.Layout(width="105px", flex="0 0 105px"))
    status = widgets.HTML(layout=widgets.Layout(width="100%", min_width="0", display="none"))
    css = widgets.HTML("""<style>
    .journal-path-selector { box-sizing:border-box; min-width:0; max-width:100%; margin-inline:0; }
    .journal-path-selector .jupyter-widgets { box-sizing:border-box; min-width:0; max-width:100%; margin-inline:0; }
    .journal-path-selector .widget-hbox { flex-wrap:wrap; gap:4px; min-width:0; }
    .journal-path-selector .widget-html-content { overflow-wrap:anywhere; }
    .journal-path-selector .widget-inline-hbox > input { min-width:0; }
    </style>""")
    row = widgets.HBox([field, browse], layout=widgets.Layout(width="100%", min_width="0"))
    box = widgets.VBox([css, row, status], layout=widgets.Layout(width="100%", min_width="0"))
    box.add_class("journal-path-selector")

    def disabled_changed(change=None):
        browse.disabled = field.disabled or state["busy"]

    def show_error(message):
        status.value = f'<p role="alert">{escape(str(message))} You can enter a path manually.</p>'
        status.layout.display = ""

    async def select_path(original):
        try:
            raw = original.strip() or (start() if callable(start) else start) or Path.cwd()
            candidate = Path(raw).expanduser().resolve()
            initialfile = candidate.name if mode == "json" and candidate.is_file() else None
            directory = candidate if candidate.is_dir() else candidate.parent
            while not directory.is_dir() and directory != directory.parent:
                directory = directory.parent
            selected = await native_path_dialog(mode=mode, title=title,
                                                initialdir=directory, initialfile=initialfile)
            if not selected:
                return
            # A project scan or manual edit may have changed the destination while
            # the native chooser was open. Never overwrite that newer choice.
            if field.disabled or field.value != original:
                return
            path = Path(selected).expanduser().resolve()
            if mode == "folder":
                if not path.is_dir():
                    raise ValueError("The selected folder is no longer available.")
            elif path.suffix.lower() != ".json" or not path.is_file():
                raise ValueError("Select an existing JSON file.")
            field.value = str(path)
        except Exception as error:
            show_error(error)
        finally:
            state["busy"] = False
            browse.description = "Browse…"
            disabled_changed()

    def open_dialog(button=None):
        if field.disabled or state["busy"]:
            return
        status.value = ""
        status.layout.display = "none"
        state["busy"] = True
        browse.description = "Choosing…"
        disabled_changed()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Also support ordinary Python callers and synchronous widget tests.
            asyncio.run(select_path(field.value))
        else:
            state["task"] = loop.create_task(select_path(field.value))

    field.observe(disabled_changed, names="disabled")
    browse.on_click(open_dialog)
    disabled_changed()
    return {"box": box, "browse": browse, "status": status, "state": state}
