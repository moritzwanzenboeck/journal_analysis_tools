"""Native-widget path browsers, also embedded in the standalone notebooks."""


def path_selector(field, *, mode="folder", title="Choose a folder", start=None):
    """Wrap a path field with a local filesystem browser; never load or write files."""
    from html import escape
    from pathlib import Path
    import os
    import string
    import ipywidgets as widgets

    if mode not in {"folder", "json"}:
        raise ValueError("Selector mode must be folder or json.")
    folder_mode = mode == "folder"
    state = {"directory": None}
    layout = lambda: widgets.Layout(width="100%", min_width="0")
    field.layout = widgets.Layout(width="100%", min_width="0", flex="1 1 280px")
    browse = widgets.Button(description="Browse…", tooltip=title,
                            layout=widgets.Layout(width="105px", flex="0 0 105px"))
    location = widgets.Text(description="Browse folder:", style={"description_width": "120px"}, layout=layout())
    entries = widgets.Select(description="Folders:" if folder_mode else "Folders / JSON:",
                             options=[], value=None, rows=8,
                             style={"description_width": "120px"}, layout=layout())
    go = widgets.Button(description="Go", layout=widgets.Layout(width="65px"))
    up = widgets.Button(description="Parent folder", layout=widgets.Layout(width="125px"))
    home = widgets.Button(description="Home", layout=widgets.Layout(width="80px"))
    open_folder = widgets.Button(description="Open selected folder", disabled=True,
                                 layout=widgets.Layout(width="180px"))
    choose = widgets.Button(description="Use this folder" if folder_mode else "Use selected JSON",
                            button_style="primary", disabled=True, layout=widgets.Layout(width="180px"))
    cancel = widgets.Button(description="Cancel", layout=widgets.Layout(width="85px"))
    status = widgets.HTML(layout=layout())
    selected = widgets.HTML(layout=layout())
    roots = widgets.Dropdown(description="Drive:", options=[], value=None,
                             style={"description_width": "120px"}, layout=layout())
    roots.layout.display = "none" if os.name != "nt" else ""
    css = widgets.HTML("""<style>
    .journal-path-selector, .journal-path-browser { box-sizing:border-box; min-width:0; max-width:100%; }
    .journal-path-selector { margin-inline:0; }
    .journal-path-selector .jupyter-widgets { box-sizing:border-box; min-width:0; max-width:100%; margin-inline:0; }
    .journal-path-selector .widget-hbox { flex-wrap:wrap; gap:4px; min-width:0; }
    .journal-path-selector .widget-html-content { overflow-wrap:anywhere; }
    .journal-path-selector .widget-inline-hbox > :is(input, select) { min-width:0; }
    .journal-path-selector .widget-html { margin-inline:0; }
    .journal-path-browser { padding:10px; border:1px solid #a8b8c8; border-radius:4px; }
    </style>""")
    panel = widgets.VBox([
        widgets.HTML(f"<h4>{escape(title)}</h4><p>Browse folders on the computer running this app. "
                     "Selecting a path fills the field above; it does not load or save anything.</p>"),
        roots, location, widgets.HBox([go, up, home]), entries,
        open_folder, selected, status, widgets.HBox([choose, cancel]),
    ], layout=widgets.Layout(width="100%", min_width="0", display="none"))
    panel.add_class("journal-path-browser")
    box = widgets.VBox([css, widgets.HBox([field, browse], layout=layout()), panel], layout=layout())
    box.add_class("journal-path-selector")

    def error(message):
        status.value = f'<p role="alert">{escape(str(message))}</p>'

    def close(button=None):
        panel.layout.display = "none"
        entries.options = []
        location.value = ""
        status.value = selected.value = ""
        state["directory"] = None
        choose.disabled = open_folder.disabled = True

    def selection_changed(change=None):
        value = entries.value
        if folder_mode:
            choose.description = "Use selected folder" if value else "Use this folder"
        directory = state["directory"]
        open_folder.disabled = True
        choose.disabled = field.disabled or directory is None or (not folder_mode and value is None)
        selected.value = ""
        if value:
            path = Path(value)
            try:
                is_folder = path.is_dir()
                open_folder.disabled = not is_folder
                choose.disabled = field.disabled or (not folder_mode and is_folder)
                selected.value = f"<p><strong>Selected:</strong> {escape(path.name)}</p>"
            except (OSError, ValueError, RuntimeError) as exc:
                choose.disabled = True
                error(exc)

    def navigate(path):
        try:
            directory = Path(path).expanduser().resolve()
            if not directory.is_dir():
                raise ValueError("Choose an existing folder.")
            # Build the new listing before replacing the previous usable folder.
            found = []
            skipped = 0
            for child in directory.iterdir():
                try:
                    is_folder = child.is_dir()
                    if is_folder or (not folder_mode and child.suffix.lower() == ".json" and child.is_file()):
                        found.append((is_folder, child))
                except OSError:
                    skipped += 1
            found.sort(key=lambda item: (not item[0], item[1].name.casefold()))
            state["directory"] = directory
            location.value = str(directory)
            entries.options = [(('[Folder] ' if is_folder else '[JSON] ') + child.name, str(child))
                               for is_folder, child in found]
            entries.value = None
            up.disabled = directory.parent == directory
            selection_changed()
            if skipped:
                status.value = f"<p>{skipped} inaccessible item(s) could not be listed.</p>"
            elif not found:
                status.value = "<p>No subfolders here.</p>" if folder_mode else "<p>No subfolders or JSON files here.</p>"
            else:
                status.value = "<p>Select a folder and click Open selected folder to enter it.</p>"
            return True
        except (OSError, ValueError, RuntimeError) as exc:
            error(f"Could not open folder: {exc}")
            return False

    def open_browser(button=None):
        if field.disabled:
            return
        close()
        panel.layout.display = ""
        try:
            if os.name == "nt":
                roots.options = [(f"{letter}:\\", f"{letter}:\\") for letter in string.ascii_uppercase
                                 if Path(f"{letter}:\\").is_dir()]
                roots.value = None
            raw = field.value.strip() or (start() if callable(start) else start) or Path.cwd()
            candidate = Path(raw).expanduser().resolve()
            original = candidate
            selected_file = candidate if not folder_mode and candidate.is_file() else None
            if not candidate.is_dir():
                candidate = candidate.parent
            while not candidate.is_dir() and candidate != candidate.parent:
                candidate = candidate.parent
            if navigate(candidate):
                if selected_file is not None and str(selected_file) in [value for _, value in entries.options]:
                    entries.value = str(selected_file)
                elif original != candidate:
                    status.value = "<p>The entered path is not an existing selectable item. Showing its nearest existing folder.</p>"
        except (OSError, ValueError, RuntimeError) as exc:
            error(f"Could not open browser: {exc}. Enter another folder above and click Go.")

    def go_to_location(button=None):
        if not location.value.strip():
            error("Enter a folder path, then click Go.")
        else:
            navigate(location.value.strip())

    def enter_selected(button=None):
        if entries.value:
            navigate(entries.value)

    def choose_path(button=None):
        if field.disabled:
            close()
            return
        try:
            value = entries.value or (str(state["directory"]) if folder_mode and state["directory"] else "")
            if not value:
                raise ValueError("Select a folder." if folder_mode else "Select a JSON file.")
            path = Path(value).resolve()
            if folder_mode:
                if not path.is_dir():
                    raise ValueError("The selected folder is no longer available.")
            elif path.suffix.lower() != ".json" or not path.is_file():
                raise ValueError("Select an existing JSON file.")
            field.value = str(path)
            close()
        except (OSError, ValueError, RuntimeError) as exc:
            error(exc)

    def disabled_changed(change=None):
        browse.disabled = field.disabled
        if field.disabled:
            close()

    browse.on_click(open_browser)
    go.on_click(go_to_location)
    up.on_click(lambda _: navigate(state["directory"].parent) if state["directory"] else None)
    home.on_click(lambda _: navigate(Path.home()))
    open_folder.on_click(enter_selected)
    choose.on_click(choose_path)
    cancel.on_click(close)
    entries.observe(selection_changed, names="value")
    roots.observe(lambda change: navigate(change["new"]) if change["new"] else None, names="value")
    field.observe(disabled_changed, names="disabled")
    disabled_changed()
    return {"box": box, "browse": browse, "panel": panel, "location": location,
            "entries": entries, "go": go, "up": up, "home": home, "roots": roots,
            "open_folder": open_folder, "choose": choose, "cancel": cancel,
            "status": status, "selected": selected, "state": state}
