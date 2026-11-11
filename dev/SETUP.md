# One-time setup and troubleshooting

These steps prepare the same launcher and notebook tools on Windows and macOS.
They are needed once on each computer. If you are unfamiliar with Python or the
terminal, ask the person providing these tools to prepare the folder for you.

## Before you start

Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
On Windows, include **Tcl/Tk and IDLE** and the Python launcher in the installer.
On a Mac, use the **universal2** installer, which includes Tk and supports Intel
and Apple Silicon. Use a Python release that supports your macOS version.

Keep the downloaded tools together in a local folder. Create the Python
environment on that computer; do not copy `.venv` from another computer or
operating system. The launcher uses this environment and does not bundle or
automatically install Python or Jupyter.

## Windows

Open the tools folder in File Explorer. Right-click an empty area and choose
**Open in Terminal**, using PowerShell. Run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe dev\build_notebook_launchers.py
```

Then double-click **Journal Notebook Launcher.exe** in the tools folder.
The app builder uses the C# compiler included with .NET Framework on Windows.

## Mac: Intel and Apple Silicon

Open Terminal in the tools folder and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python dev/build_notebook_launchers.py
```

Then double-click **Journal Notebook Launcher.app** in the tools folder.
An existing copy installed in your Applications folder also works with the
original tools folder. The `.command` shortcut opens the same launcher.

With native Python and dependencies, Apple Silicon does not need Rosetta.

## Rebuild an existing launcher

Close the launcher, then run the builder with `--replace`:

| Windows | Mac |
| --- | --- |
| `.venv\Scripts\python.exe dev/build_notebook_launchers.py --replace` | `.venv/bin/python dev/build_notebook_launchers.py --replace` |

The existing app stays in place while the replacement is built. If compilation
fails, the previous app is kept. An open Windows launcher must be closed before
its executable can be replaced.

## If something does not work

| Problem | What to check |
| --- | --- |
| No launcher app in the folder | Complete the setup steps for your operating system. |
| The builder says an app already exists | Close the launcher and rebuild with `--replace`, as shown above. |
| The app cannot find Python or a required package | Reinstall `requirements.txt` using the `.venv` Python command above. |
| The browser does not open | Click **Open notebook** in the launcher, or copy its address into the browser. |
| The copy button cannot access the clipboard | Select the displayed count and copy it manually. The notebook must run on your own computer to use its clipboard. |
| The app fails after the tools folder was moved | Keep the app beside `notebook_launcher.py` and `app/`, or rebuild it for the new folder. |
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
