# Repository guidance

This repository provides two Jupyter notebook services: project creation and text
cleanup and full-paper categorization. `notebook_launcher.py` opens `app/launcher.py`, their shared control window;
`app/notebook_services.py` owns Jupyter processes and their lifecycle. Keep analysis
and text editing in the notebooks rather than rebuilding a full desktop client.

- Support Python 3.10+ and paths containing spaces and non-ASCII characters.
- Keep user-facing files at the top level, runtime support and assets in `app/`,
  and tests/build tools in `dev/`. Keep the Windows/macOS app builder in
  `dev/build_notebook_launchers.py` and route `start_notebook.command` through
  `app/launch_notebook.sh`. The launcher uses an existing
  Python environment in source checkouts. Release downloads bundle a relocatable
  Python runtime and notebook dependencies under `app/python/`; never install
  packages or download a runtime on startup.
  The Windows app is a small native entry point compiled from
  `dev/windows_launcher.cs`; keep generated executables out of Git.
- Bind managed servers to loopback with token authentication. Display actual
  ports and working notebook links only after the server is ready. Never stop
  unrelated Jupyter servers or kill a process merely because it occupies a port.
- Keep lifecycle work off the GUI thread. Stop managed servers and their kernels
  on exit, and retain an explicit force-stop action for unresponsive services.
- Preserve journal-independent metadata/sampling behavior, offline archive replay,
  project creation without overwrites, and notebook/text rule parity.
- Distributed notebooks must have no saved outputs, execution counts or widgets.
  Do not commit project data, local settings, tokens, logs or generated app bundles.
- Install development dependencies with `python -m pip install -r dev/requirements.txt`.
  Run `python -m unittest discover -s dev/tests -v`; launcher integration tests start local
  Jupyter servers and kernels. Compile the Finder app on macOS when available.
- Update README instructions when changing launch, shutdown or installation flows.
- Keep README focused on opening the app and completing the two user tasks, with
  equal Windows/macOS instructions. Put setup commands in `dev/SETUP.md` and
  detailed analysis rules in `dev/analysis_reference.md`; omit development history.
- Keep controls, clipboard actions, notebook behavior and shutdown consistent on
  Windows, Intel macOS and Apple Silicon macOS. Both native app builders default
  to the tools folder. Preserve the compatibility workflow for all three targets;
  distinguish configured CI checks from results actually run on a platform.

- Keep the notebook self-contained and its full-paper model in parity with
  `app/paper_tools.py`. Preserve the original clean-and-count tab. In generated
  projects read sampled papers from `project.json`'s CSV and always save cleaned
  text/assignment JSON in that project's `paper_categorizations/` folder. Do not
  commit user text or categorization files.
- Update summary widgets in place. Keep the individual-paper grid fixed; project
  summary tables and the outline card should wrap and expand without internal
  scroll areas. Keep previews out of the document flow. Hiding a preview must clear and hide the
  whole panel. Maintain project, persistence and layout regression checks.

- Preserve both random journal sampling and manual DOI selection. Manual lookup
  must preload complete export metadata, deduplicate bare DOI/resolver URL forms,
  and reuse cached successes on retry. Creation from checked records must not
  fetch again or sample explicit choices. Exclude non-scientific articles in
  random sampling and manual DOI validation; retain reasons and full raw exports. Show the journal/count/year
  overview and multi-journal warning before creation. Keep manual project exports
  compatible with the categorization notebook's `sample_export` contract.

- When project-backend behavior changes, bump `PROJECT_NOTEBOOK_API_VERSION` in
  the backend and its required value in the project notebook. Older running
  kernels must reload the backend before showing controls. Keep lookup setup
  inside exception handling so failed previews cannot leave buttons disabled.

- Mac platform downloads must embed runtime and tool code inside the signed app;
  adjacent files are unavailable during App Translocation. Sign nested Mach-O
  files before the outer app. Never remove quarantine attributes on startup.
- Store editable Mac notebooks outside the bundle and retain existing edits.
  Verify the compiled Finder app itself, plus real embedded Python and kernels;
  the shell shortcut alone is insufficient release-startup coverage.

- Use native notebook text controls and Markdown `#` through `######` for heading
  editing. Prefix edits update structure/counts live; canonical saved text omits
  markers. Preserve old JSON and virtual-label counts when reloading. Retain
  matching labels and reset merged parts to Unassigned when a marker is removed.
- Project categories live in `paper_categorizations/categories.json`. Removing
  one resets all saved and active assignments to Unassigned with transactional
  rollback; preserve file mtimes so newest-version resolution remains stable.
  The project summary counts the latest saved JSON once per sampled DOI and
  reports missing/invalid papers without silently substituting an older file.

- The editor must work without a custom browser module or anywidget dependency.
  Keep the browser check that removes `AbortSignal.any` to catch regressions on
  older Safari, alongside the normal native widget and fixed-layout checks.

- Keep the OS-dialog worker, `native_path_dialog` and `path_selector` in parity
  in both notebooks and `app/file_selectors.py`. Run Tk on a separate process's
  main thread and wait asynchronously; retain Windows selector-loop support and
  suppress child consoles. Dialogs must only fill paths; keep scan/load/create
  explicit, ignore stale results and preserve disabled project save destinations.
  Generated project notebooks must work without importing the tools package.
  Retain cancellation/cleanup, Unicode and browser-wiring/layout coverage.
  Mac pickers must omit the withdrawn Tk parent; verify real panel visibility
  and independent presentation with `dev/check_native_dialogs.py`.
