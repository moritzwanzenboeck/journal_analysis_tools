# Opening the app and troubleshooting

Platform release downloads include Python, Tk, Voilà, Jupyter and all notebook
packages. Windows, Intel Mac and Apple Silicon Mac users need no terminal setup.

## Open a self-contained release

Download the platform ZIP from **Assets** on the latest GitHub release.
Follow the download steps in [Open the app](../README.md#open-the-app).
Extract the **whole folder** onto a local disk. On Windows keep the app beside
`notebook_launcher.py` and `app/`, including `app/python`. The Mac app includes
its tools and runtime inside the signed bundle and may be moved as a whole into
Applications. Open **Journal Notebook Launcher.exe** on Windows or
**Journal Notebook Launcher.app** on Mac. Choose a tool in the local web app
that opens in your browser.

Moving the Windows folder or Mac app does not require recreating an environment.
No packages or runtime are downloaded or installed on startup. Mac notebooks
are copied into a writable user workspace and retained between launches.
Do not run the app builder or create a `.venv` for a release download.
GitHub's automatic **Source code** ZIPs lack the compiled app and bundled Python.

For releases before v1.3.0, use their included setup instructions or download
a current self-contained release instead.

## Folder and file selection

Use **Browse…** beside path fields to choose existing folders or JSON files
inside the web app. Windows drive selection, Home and Parent folder navigation
are available. You may also paste a path into **Browse folder** and click **Go**.
The browser uses the app computer's filesystem and permissions. If a folder
cannot be opened, check that a shared drive is mounted and accessible to your
account, or choose a local folder. Cancel leaves the original path unchanged.
Selecting a path does not perform the associated scan, load, save or creation.

## Mac downloads and editable notebooks

The Mac release keeps its interpreter, extension modules and tools inside the
signed `.app`, so they remain available when Gatekeeper runs a downloaded app
from an isolated location. No security attributes are removed on startup.
Approve the app through macOS's normal Privacy & Security controls when needed.

Editable notebook copies are stored under
`~/Library/Application Support/Journal Analysis Tools/Notebooks/<template-id>/`.
Existing notebook edits are retained. An updated set of templates gets a separate
workspace; previous workspaces remain available. Save full-paper work as JSON
before switching versions. New projects default to Documents; their saved files
remain wherever you chose to put them.

Older v1.3.0 Mac downloads can report **Tools folder not found**, even with all
files together, or have their unsigned Python process blocked. Use a rebuilt Mac
app containing the runtime. The source checkout supports `--replace`; compiled
release users should use a corrected platform download when published.

## Source checkouts only: install Python and packages

The commands below are for developers and source-code downloads. Platform
release users skip them.

### Before you start with source code

Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
On Windows, include **Tcl/Tk and IDLE** and the Python launcher in the installer.
On a Mac, use the **universal2** installer, which includes Tk and supports Intel
and Apple Silicon. Use a Python release that supports your macOS version.

Keep the downloaded tools together in a local folder. Create the Python
environment on that computer; do not copy `.venv` from another computer or
operating system. Source checkouts use this environment; they do not install
packages on startup.

### Windows source checkout

Open the tools folder in File Explorer. Right-click an empty area and choose
**Open in Terminal**, using PowerShell. Run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then build the launcher using the source-checkout instructions below.

### Mac source checkout: Intel and Apple Silicon

Open Terminal in the tools folder and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Then build the launcher using the source-checkout instructions below, or open
the `.command` shortcut, which starts the same control window.

With native Python and dependencies, Apple Silicon does not need Rosetta.

## Tools stored on a shared or external drive

Some shared/external filesystems add Finder metadata or strip executable
permissions from `.app` bundles. For a release, keep the entire
extracted tools folder and its bundled runtime on a local disk. Choose a shared project
output destination in the notebook when needed.

For an advanced **source checkout** on a shared drive, you can build a launcher
bound to that checkout and install it locally:

```bash
.venv/bin/python dev/build_notebook_launchers.py --destination "$HOME/Applications" --replace
```

Open **Journal Notebook Launcher.app** in your home folder's **Applications**
folder. It still opens the notebooks in the original tools folder.

This also resolves `resource fork, Finder information, or similar detritus not
allowed` / `osacompile ... (-4960)` when the build destination is on a shared
drive. The Mac builder compiles and signs in local temporary storage, validates
its destination copy, and preserves the previous app if any step fails. It does
not remove extended attributes from your tools or project folders.

## Source checkouts: build or rebuild a launcher

This section is for source-code downloads and developers. Users of the platform
release ZIPs skip compilation. After installing the requirements above, create
the launcher once:

| Windows | Mac |
| --- | --- |
| `.venv\Scripts\python.exe dev/build_notebook_launchers.py` | `.venv/bin/python dev/build_notebook_launchers.py` |

To rebuild it, close the launcher and run the builder with `--replace`:

| Windows | Mac |
| --- | --- |
| `.venv\Scripts\python.exe dev/build_notebook_launchers.py --replace` | `.venv/bin/python dev/build_notebook_launchers.py --replace` |

The existing app stays in place while the replacement is built. If compilation
fails, the previous app is kept. An open Windows launcher must be closed before
its executable can be replaced.

## Update the notebook tools

Changes to notebooks and runtime Python files do not require recompiling an
existing launcher. Keep all updated files together. Save each active paper as
categorization JSON, then restart the launcher and reopen the web app. In
standalone Jupyter, restart the kernel and choose **Run All Cells** to load the
new code.

Generated journal projects contain a self-contained copy of
`clean_and_count_text.ipynb`. Existing copies are not replaced automatically.
After saving active categorizations, copy the updated notebook from the tools
folder into the project, replacing that notebook only. Keep `project.json`,
`output/` and `paper_categorizations/` intact. You can also open **Clean and
categorize papers** in the web app and choose the existing **Project folder**.

In a source checkout, run `python notebook_launcher.py --classic` with the
project's Python environment to open the standalone Jupyter notebook controls.
On Windows you can also pass `--classic` to the compiled launcher from a terminal.

## If something does not work

| Problem | What to check |
| --- | --- |
| No launcher app in the folder | Choose the platform ZIP under **Assets** and extract the complete folder. For a source checkout, use the build instructions above. |
| The builder says an app already exists | Close the launcher and rebuild with `--replace`, as shown above. |
| The app cannot find Python or a required package | Extract the complete platform release ZIP again, including `app/python`. For a source checkout, reinstall `requirements.txt` using its `.venv` Python. |
| The browser does not open | Click **Open web app** in the launcher, or copy its address into the browser. |
| No project papers appear | Select the generated project folder and click **Scan project folder**. It needs its original `project.json` and the CSV named by `sample_export`. The central launcher cannot infer which project you want. |
| A saved paper is missing from the JSON list | Scan again after saving externally. Only full-paper categorization JSON is listed, not Crossref or sampling reports. You can also load a file by path or upload. |
| Saving reports that files exist | Review the paper prefix and enable **Overwrite existing files** only to replace that saved pair. All saves in a project use `paper_categorizations/`. |
| Loading or changing paper reports unsaved work | Save the current paper first, or explicitly enable **Allow replacing the current unsaved paper**. |
| Counts pause while editing a Markdown heading | Finish the title after `# ` or `## `; counts and assignments resume automatically. |
| A section preview remains open | Click its **Hide text** button, or toggle the section's text button. If using an old notebook session, save JSON and restart the kernel with the updated notebook. |
| Reading a long report or outline | Project summary tables and the heading-outline card expand to show their contents. Use normal notebook page scrolling. The individual-paper category grid retains its cell scrollbars. |
| DOI lookup stays on “Looking up…” after updating the tools | Save completed work, then reload the web app. Startup refreshes an outdated imported backend. Lookup errors release both search buttons so you can retry. |
| A DOI lookup fails | Use a bare DOI or doi.org URL. The DOI must be a journal article registered with Crossref and have title, journal and publication-date metadata. Publisher webpages are not DOI URLs. |
| The manual Create button is disabled | Add at least one checked paper. Correct and recheck any nonempty bulk list, or clear that input to proceed with the existing selection. |
| Manual DOI selection disappears | Restarting or rerunning the notebook clears the in-memory selection/cache. Keep the kernel running until creation; completed projects retain their archived metadata. |
| The copy button cannot access the clipboard | Select the displayed count and copy it manually. The notebook must run on your own computer to use its clipboard. |
| The app fails after the tools folder was moved | Keep the app beside `notebook_launcher.py` and the complete `app/` folder. Release downloads need no environment recreation. Source checkouts may need their `.venv` recreated or a separately installed launcher rebuilt. |
| macOS blocks the app | For an app you trust, use the approval offered in **System Settings → Privacy & Security**, following your organisation's policy. |

### Python reports `OSError: [Errno 45] Operation not supported` on a Mac

A mounted/shared directory can temporarily have an unavailable working-directory
handle. Python searches that directory during imports, so even `import platform`
can fail. VS Code's Python startup script may be the first place this appears.
This does not mean that `platform` needs to be installed.

If the Python prompt (`>>>`) is open, enter `exit()` first. Then start Python
from a local directory:

```bash
cd /private/tmp
python3
```

To open these tools, use **Journal Notebook Launcher.app** or the `.command`
shortcut. The Mac shell launcher switches to `/tmp` before checking or starting
Python. Managed Jupyter servers also start in their own local temporary folders;
their notebook links and project destinations still point to the tools and
projects you selected. Windows uses its normal local temporary directory for
managed servers as well. VS Code settings and its startup script are unchanged.

For a source-level environment check without opening a window:

| Windows | Mac |
| --- | --- |
| `.venv\Scripts\python.exe notebook_launcher.py --check` | `.venv/bin/python notebook_launcher.py --check` |

If you need help, the launcher's error message identifies the relevant log.
Logs are stored here:

| Computer | Log folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Journal Analysis Tools\Logs\` |
| Mac | `~/Library/Logs/Journal Analysis Tools/` |

Logs and notebook links can contain local access tokens. Share only the relevant
error text when requesting help.


## Editing paper headings

The full-paper editor uses standard ipywidgets controls. Mark heading lines with
`# `, `## `, `### ` and so on through six levels. Changes update the section list
and counts automatically. The earlier custom anywidget editor is no longer
required; an older installed copy can remain without affecting this workflow.
After updating the notebook, save current paper work as JSON, reload the page
and run all cells. Previously saved JSON remains supported.
