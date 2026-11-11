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
  Python environment; it does not bundle Python or install packages on startup.
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
- Update summary widgets in place, preserve fixed cell/button positions and keep
  previews out of the document flow. Hiding a preview must clear and hide the
  whole panel. Maintain project, persistence and layout regression checks.
