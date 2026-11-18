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
there. `app/paper_tools.py` mirrors the self-contained notebook's full-paper
model, including project discovery, sampled DOI metadata and JSON persistence.
`dev/tests/test_paper_categorization.py` checks model parity, count boundaries,
label changes, roundtrip/rollback, project selection and the fixed save-folder
invariant. Notebook callbacks are tested with temporary synthetic projects.
Completion warnings track unassigned sections, with row highlights updated in place.
The warning uses a fixed-height slot, so clearing it does not shift the summary.
The final counted category is Not categorizable; individual title buttons copy
newline-separated titles while whole-table exports preserve spreadsheet columns.
Summary refreshes update existing widgets in place; copy callbacks compute the
current value. Fixed grid rows/columns and bounded title panels prevent controls
from moving. The floating preview must fully hide and clear its text.
Keep path lookup independent of the shell's working directory.

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
errors in the user's launcher log. It prefers `app/python/pythonw.exe` in
bundled releases, then `.venv/Scripts/pythonw.exe` and the Python used at build
time in source checkouts; `JOURNAL_TOOLS_PYTHON` overrides these. Use the
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

See [setup and troubleshooting](SETUP.md) for source setup instructions and log
locations, and [analysis reference](analysis_reference.md) for export and counting
rules. Keep programming details out of the main user guide.

Generated executables, application bundles, virtual environments, logs and Python caches are
ignored by Git. `logs/` keeps any local diagnostics out of the user-facing folder.

## Prepare a self-contained release

`dev/package_release.py` builds a portable native launcher and packages it with
an explicit whitelist of runtime/notebook files. Saved notebook outputs and
widget state are stripped from the copy. No venv, settings, project output or
logs are included. `dev/bundle_python.py` downloads a relocatable Python from
[python-build-standalone](https://github.com/astral-sh/python-build-standalone),
using the release, version and SHA-256 values pinned in `dev/python_runtime.json`.
It installs runtime wheels at build time into `app/python/` (embedded inside the
Mac app before signing), retains Python and
third-party licenses, records installed package versions in
`app/runtime-packages.json` and removes debug symbols and unused script entry
points. The app downloads and installs nothing on startup.

```bash
python dev/package_release.py --version v1.3.0 --output dist
```

Run this separately on Windows x86_64, Intel macOS and Apple Silicon macOS.
The script creates an OS/architecture-specific ZIP and `.zip.sha256` checksum,
then extracts and moves the ZIP and checks native startup with system Python
removed from PATH and unrelated Python environment settings present. The bundled
runtime must initialize Tk, start both Jupyter servers, execute both notebooks
in real bundled kernels, kill kernels and shut down its owned processes.
`dev/check_bundled_runtime.py` performs those checks using runtime dependencies
only. Mac app signatures and executable modes survive ZIP extraction. Windows
checks run the compiled GUI executable. Portable builds omit checkout and Python
fallback paths from the build machine; normal `--destination` builds retain
those fallbacks for a locally installed app.

For routine releases, commit release notes in `dev/releases/<tag>.md`, then push
a version tag:

```bash
git tag v1.3.0
git push origin v1.3.0
```

`.github/workflows/release.yml` calls the compatibility workflow for all six
Windows/Intel/Apple Silicon and Python 3.10/3.14 combinations. The three Python
3.14 jobs also build and verify platform ZIPs and upload them as workflow
artifacts. All Python 3.14 jobs also verify a self-contained package on ordinary
branch/PR runs, using a temporary `v0.0.0-ci` version without publishing.
Publication waits for every matrix job to pass, downloads the three
native packages, verifies their checksums and commit metadata, uploads all six
files to a draft GitHub release and only then publishes it. The built-in
`GITHUB_TOKEN` supplies release access; no personal token is stored in the repo.
Published versions are never overwritten. Use a new tag for another release.

A workflow or local Mac run alone does not certify Windows or Apple Silicon:
inspect the actual release-run results. Users download the attached platform
ZIPs under Assets, not GitHub's automatically generated Source code archives.
They do not install Python, run setup commands, a compiler or the app builder.

Runtime archive downloads are cached in ignored `dist/runtime-cache/`; override
with `--runtime-cache` if needed. The unit suite remains offline; the packaging
step requires build-time access to GitHub and PyPI. To repeat the complete native
bundle integration through unittest, set `JOURNAL_TOOLS_TEST_BUNDLE=1`.

## Check the full-paper layout in a browser

The unit suite checks widget identities, dimensions, callbacks and preview state.
For actual browser geometry, install the optional browser dependencies and run:

```bash
python -m pip install -r dev/requirements-browser.txt
python -m playwright install chromium
python dev/check_paper_layout.py
```

This starts an isolated local Jupyter service and headless browser, uses a
synthetic 10-paper project, and checks long-title wrapping, stable copy-button
positions after relabeling, preview hiding, narrow windows and
the locked project save folder. It also tests actual Unicode text selection,
live Markdown heading levels/removal, custom-category deletion and
the all-paper summary. It does not use the system clipboard. Pass
`--browser-executable` to use an installed Chrome/Chromium instead of downloading
a browser, and `--artifacts` to retain the screenshot and result JSON. This is an
optional browser check; the compatibility workflow runs the unit/service suite.

## Manual DOI projects

`app/journal_tools.py` implements DOI normalization, full-record lookup/cache,
ordered bulk validation, journal/year overview and `create_manual_project`.
Both creation modes share row serialization and transactional folder publication;
manual creation has no network or random-sampling step. Keep the schema-1
`sample_export` contract so generated projects work with the self-contained
categorization notebook. Manual records retain selection order; non-scientific
items are rejected by publisher-type and title rules in both creation modes.

`dev/tests/test_manual_projects.py` tests DOI URL formats, metadata validation,
cache reuse and partial failures, explicit-selection exports, multiple journals,
no-network creation, rollback and notebook callbacks. The optional browser check
also exercises actual Enter-key submission and the rich result dropdown:

```bash
python dev/check_manual_project.py
```

Install `dev/requirements-browser.txt` and Chromium first, as described above.
`--browser-executable` and `--artifacts` work as in the layout check. This uses
synthetic metadata, blocks duplicate API lookups, and verifies selected-paper
exports after browser-driven creation. It makes no external metadata requests.

The project notebook checks `PROJECT_NOTEBOOK_API_VERSION` at startup and reloads
an older imported backend before creating controls. Keep its expected version
and the backend marker aligned whenever project-backend behavior changes. This matters when
a user reruns cells in a kernel started before an update. Lookup setup and form
refresh both need exception handling: every failure must release the busy flag
and buttons, display an error, and permit another search without kernel restart.

## Self-contained Mac app validation

Portable Mac builds embed the pre-whitelisted tool payload and runtime under
`Journal Notebook Launcher.app/Contents/Resources/JournalTools/`. Every Mach-O
interpreter, helper, library and extension is ad-hoc signed before sealing the
outer app. The flat duplicate runtime is omitted from the Mac ZIP. Windows keeps
its existing adjacent-runtime layout. This still needs normal user approval for
an ad-hoc signed download; Apple Developer ID notarization is not provided.

`app/macos_bootstrap.py` creates editable notebook copies outside the bundle and
never overwrites an existing edited copy. Template changes create a new workspace.
Bundled code stays in the app; managed kernels receive the explicit backend path.
The launcher uses the workspace as its notebook root and Documents as the default
project destination. `-I -B` prevents user Python configuration and bytecode writes
from altering the signed bundle. No runtime or packages are installed on startup.

Release verification invokes the compiled Mac app itself with
`JOURNAL_TOOLS_APP_CHECK=1`, rather than substituting the `.command` shortcut.
`JOURNAL_TOOLS_WORKSPACE` confines native test notebooks to temporary storage.
The native unit fixture tests an app with no adjacent files and validates its
signature afterward; full package verification uses the actual embedded runtime,
GUI and kernels. CI does not automate macOS Gatekeeper approval dialogs.


## Interactive categorization model

The cleaned-paper editor is a native ipywidgets Textarea. It stores an editable
Markdown view separately from canonical saved text. Keep the model inline and
in parity with `app/paper_tools.py`. `paper_make_markdown_document` parses only
explicit marked lines, preserves matching labels, and resets merged spans after
heading removal. No anywidget/browser-extension dependency is needed.
`dev/tests/test_markdown_headings.py` checks live edits, marker parsing, counts,
legacy virtual sections, incomplete-heading recovery and save/reload.

`dev/tests/test_interactive_categories.py` exercises exact/virtual heading
boundaries, Unicode offsets, legacy JSON, category removal rollback, newest-file
ordering, missing/invalid project papers and notebook callbacks.
`dev/tests/test_article_exclusions.py` verifies non-scientific metadata/title
filtering in random replay and explicit DOI lookup/creation. Exclusions retain
reasons in the selection report; full metadata exports are kept for auditing.
Project settings belong in `paper_categorizations/categories.json`, and deleting
a custom name must rewrite every saved assignment to Unassigned transactionally.
Do not make ordinary category changes recreate fixed summary controls.


## Project report tables

`paper_report_metrics`, `paper_report_tables` and `paper_report_tsv` in
`app/paper_tools.py` (mirrored inline) build the spreadsheet-shaped overview and
category blocks. Count each actual assigned top-level title once, independently
of parent-context titles and subsection headings. Virtual labels add no title
words. Missing and zero values must remain distinct; positive category counts
supply mean/min/max and all ties get markers. Abstracts come from cleaned text
or existing metadata without a network lookup. `dev/tests/test_project_summary_report.py`
covers these rules, report copying, metadata fallback and widget reuse.
The browser layout check also covers report headers, rows and stable copy buttons.


## Browser compatibility

The editor uses the built-in ipywidgets textarea, with no custom JavaScript
module. The optional browser check can still remove the API that previously
failed in older Safari, confirming the complete workflow without it:

```bash
python dev/check_paper_layout.py --without-abort-signal-any
```

Run the same check without the flag for a normal browser. Install runtime
requirements in the isolated test environment; anywidget is not required.


## Alternative heading outline

`paper_apply_outline` validates `level | exact title` entries and maps them back
to Markdown prefixes without dropping prose. The notebook keeps automatic
Markdown-to-outline synchronization separate from pending drafts; copying and
saving wait until a draft is applied or refreshed. `dev/tests/test_heading_outline.py`
checks duplicate occurrences, invalid ordering, draft protection, virtual labels
and category retention. The browser workflow also exercises the outline field.
