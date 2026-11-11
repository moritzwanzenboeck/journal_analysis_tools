# Development

Run these commands from the repository root:

```bash
python -m pip install -r dev/requirements.txt
python -m unittest discover -s dev/tests -v
```

Tests use synthetic metadata and temporary folders, including offline project
creation, notebook callbacks, real local Jupyter startup, port fallback, kernel
isolation, shutdown and restart. A hidden GUI test starts both tools, checks their
ports and fallback links, invokes the kernel buttons, and closes the window. On
macOS it closes through Command-Q's handler. No external network is needed.

The compatibility workflow runs this same suite on Windows, Intel macOS
(`macos-15-intel`) and Apple Silicon macOS (`macos-15`), with Python 3.10 and 3.14.
The Intel/Python 3.10 job uses the Python.org 3.10.11 universal2 installer to avoid
the hosted toolcache's mismatched Tk 8.5 headers/8.6 runtime. This pinned legacy
runtime tests the supported 3.10 baseline; use a current Python release for new
installations. Other matrix jobs retain their `setup-python` interpreter.
Native Windows app compilation/startup and Mac app compilation run on their
respective hosts. Native clipboard roundtrips run only when
`JOURNAL_TOOLS_TEST_CLIPBOARD=1`, as configured on the CI desktops, to avoid
changing a developer's clipboard during ordinary local checks. Clipboard routing
and error handling are tested locally without modifying the clipboard.
The GUI driver invokes the same native buttons used by mouse and keyboard users;
it does not send synthetic mouse events to a withdrawn window, which macOS can
discard. The launcher's `--check` also initialises a hidden Tk root to detect
runtime/library mismatches before the tests run.

A workflow definition is not evidence of a successful Mac run: check all three
platform results before distributing a release. Windows-only local tests do not
certify behavior on either Mac architecture.

`app/` contains runtime Python modules, the shared shell entry point and icon
assets. `notebook_launcher.py` is the small user-facing entry point. The notebooks
stay at the root; project creation copies the self-contained text notebook from
there. Keep path lookup independent of the shell's working directory.

To build the Windows app or install the single Finder app on macOS, run this
with the Python environment containing the notebook requirements:

```bash
python dev/build_notebook_launchers.py
```

Both builders default to the tools folder, so the user opens the app beside the
notebooks on either operating system. `--destination` can override this location.
Both apps prefer a neighboring `notebook_launcher.py` after a folder move and
fall back to the checkout path recorded at build time.

On Windows the builder creates `Journal Notebook Launcher.exe`
using the .NET Framework C# compiler. `windows_launcher.cs` opens the existing
Python GUI without a console, forwards command-line options and records startup
errors in the user's launcher log. It prefers `.venv/Scripts/pythonw.exe`, then
the Python used at build time; `JOURNAL_TOOLS_PYTHON` overrides both. Use the
executable's `--check` option to verify startup without opening a window.

On macOS it creates `Journal Notebook Launcher.app`. This is an AppleScript
entry point to the shared shell/Python launcher, using the same GUI and service
controller as Windows. Shell files use LF endings and Bash 3.2-compatible syntax.
Explicit `JOURNAL_TOOLS_PYTHON` choices are authoritative on both platforms.
The builder refuses to overwrite an existing app unless `--replace` is supplied.
Both platforms preserve the previous app on build failure. Windows compiles on
the destination filesystem and publishes the new executable with an atomic
replacement. macOS compiles in `/private/tmp`, sets the icon, then ad-hoc signs
the completed bundle. It copies into a staging folder on the destination
filesystem and validates executable permissions and the signature before
publication. A backup bundle permits rollback on publication failure. Close a
running launcher before rebuilding. For a shared/external drive that cannot
store executable signed apps, select a local destination such as `~/Applications`;
the notebooks remain in the tools folder.

See [one-time setup](SETUP.md) for the matched OS setup instructions and log
locations, and [analysis reference](analysis_reference.md) for export and counting
rules. Keep programming details out of the main user guide.

Generated executables, application bundles, virtual environments, logs and Python caches are
ignored by Git. `logs/` keeps any local diagnostics out of the user-facing folder.
