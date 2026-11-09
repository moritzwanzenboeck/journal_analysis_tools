# Journal analysis tools

Create an analysis project for any journal, fetch its Crossref metadata, draw a
reproducible random sample, and clean copied paper text for word and paragraph
counts. There are no fixed journals, paper titles, personal paths or API keys.

## Open the app — no setup required

Download the macOS ZIP from [GitHub Releases](https://github.com/moritzwanzenboeck/journal_analysis_tools/releases/latest),
unzip it, move **Journal Analysis Tools.app** to your local Applications folder,
and double-click it. Run the app from a local disk: shared/network drives can
strip executable permissions or add metadata that prevents launching. The
repository and project files can remain on the shared drive. Python, Jupyter and a terminal
are not required. Internet access is needed only for journal lookup and fetching;
text cleanup and archived metadata replay work locally.

The first release is built for **Intel Macs (x86_64)**.
It was tested on macOS 13.7.3. Apple Silicon Macs need Rosetta for this build;
a native Apple Silicon build must be produced on that architecture.
The app is ad-hoc signed, not Developer ID signed or notarized. A downloaded copy
may require approval in **System Settings → Privacy & Security → Open Anyway**.
For managed computers, follow your organisation's software policy. A trusted
Developer ID and notarization can be added to later distributions.

### Create project

1. Enter a journal title or ISSN, click **Find journal**, and select the intended result.
2. Choose the inclusive date range using the calendar buttons and set the sample size.
3. Click **Choose folder…** to select where projects should be saved.
4. Click **Create project**. Fetching runs in the background; the window stays responsive.
5. Click **Open project folder** to view the exports in Finder.

The app remembers the selected journal, dates, sample size, destination and last
project. Advanced options contain the publication date basis, random seed,
contact email, notice filter and archived Crossref JSON replay. No project is
created on app startup; creation happens only when you click **Create project**.

The default folder name is
`DDMMYYYY_journalanalysis_<journal>_<start-date>_<end-date>`, using the creation
date in Europe/Zurich. You may enter a different folder name. Existing projects
are never reused or overwritten. A failed fetch or an oversized sample creates
no project. The user chooses how to organise PDFs and analysis results;
`papers/` and `analysis/` are not created.

### Clean and count text

Open the **Clean and count text** tab. Paste PDF text, review line-end hyphens,
and apply cleanup. Counts update when the cleaned text is edited. Copy counts
or cleaned text using the buttons, or save the cleaned result as a text file.
Clipboard buttons work through the native app. The red **Clear original text**
button is separated at the right and preserves the cleaned result.

Only app preferences are saved automatically, in
`~/Library/Application Support/Journal Analysis Tools/settings.json` on macOS.
Pasted and cleaned text, contact emails and random seeds are not saved as app
preferences. Save or copy the cleaned result before closing the window.
Projects and exports remain in the folder you selected. Contact email can
appear in Crossref request URLs saved in a project's retrieval report.

### Optional notebook interface

The notebooks remain available for users who prefer them. Use Python 3.10 or
newer and install `requirements.txt`, then open `create_journal_analysis.ipynb`
or `clean_and_count_text.ipynb` in Jupyter or VS Code. The existing
`start_notebook.command` launcher is retained for that workflow.

## What a project contains

```text
<project>/
├── README.md
├── project.json
├── clean_and_count_text.ipynb
└── output/
    ├── <journal>_<start>_<end>.csv
    ├── <journal>_<start>_<end>.bib
    ├── <journal>_<start>_<end>_crossref.json
    ├── <journal>_<start>_<end>_report.json
    ├── <journal>_<start>_<end>_random<N>.csv
    ├── <journal>_<start>_<end>_random<N>.bib
    └── <journal>_<start>_<end>_random<N>_selection.json
```

CSV files use UTF-8 with a BOM for Excel. Full and sampled paper metadata are
kept in `output/`. Choose your own folders and files for PDFs and analysis
results. PDFs are not downloaded.

`project.json` records the journal, ISSNs, dates, publication basis, chosen sample
size, actual random seed and export paths. CSV and BibTeX exports have identical
DOIs and citation keys in the same order; this is verified before writing.
The reports retain retrieval queries, metadata limitations and sampling
exclusions. No previous journal analysis, completed workbook or paper is
bundled with these tools.

## Metadata and sampling rules

The app and setup notebook replace the journal-specific fetch and sampling
scripts. `journal_tools.py` contains the shared fetching, sampling and project
functions. It works with the standard library; the desktop distribution adds
bundled certificates and timezone data. `text_tools.py` shares the cleaning
rules with the self-contained notebook, with regression tests checking parity.
The notebook's optional code cells also support scripted creation and drawing
a new sample from a saved CSV.

Journal lookup and fetching use the
[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/).
All registered ISSNs for the selected journal are queried, and records are
deduplicated by DOI. An unindexed ISSN returning HTTP 404 is recorded and skipped;
other failures stop the operation. Cursor pagination checks for stalled or
incomplete responses. HTTP 429 and server failures are retried with backoff.
An optional contact email is used for Crossref requests and is not saved as
configuration; request URLs in the retrieval report can contain it.

The default publication basis is the earliest known online, print, published or
issued date. Both range endpoints are inclusive. You can choose online-only or
print-only instead. Partial dates use the first day for filtering and retain
their original precision in exports. The bibliography year uses the print year
when available. Completeness and accuracy depend on publisher deposits.

The sample is uniform without replacement across eligible DOIs. Obvious
editorials, corrections, errata, retractions, withdrawals, publisher notes,
acknowledgements, prefaces and special-issue notices are excluded by a title
heuristic. The full export retains them. Review the exclusions in the selection
report, or enable **Include notices and editorials**. This is not a full
article-type classification. Asking for more papers than are eligible fails
without creating a partial project.

Leave the seed blank for a fresh draw; the actual seed is always saved. The
same seed and the same eligible population produce the same sample even if CSV
row order changes. For exact replay without fetching again, supply the saved
`*_crossref.json` in the advanced options and use the saved seed and settings.
The code example shows constructing a `Journal` directly for a fully offline
replay, which also avoids journal lookup.

## Text cleanup and counting

Use the app's **Clean and count text** tab, or optionally open a project's
**clean_and_count_text.ipynb** and run its cells. Paste PDF text, review line-end
hyphens, and apply cleanup. The editable result has live counts.

- Body lines ending in `.`, `:`, `?` or `!` are paragraph endings. Footnote
  digits attached after the punctuation also count, for example `.12`.
- Leading-zero numeric suffixes such as `0.001` continue into the next line.
  P-value expressions such as `(𝑝<.1\n).` become `(𝑝<.1).` without a false break.
- Missing blank lines between paragraphs are inserted; existing paragraph
  spacing is retained. Unfinished wrapped body lines join with spaces.
- Numbered headings are separate and excluded from paragraph counts. Word
  counts include the displayed headings and any retained mathematics.
- **Copy word count** precedes **Copy paragraph count**. The desktop app uses
  the native clipboard. Notebook clipboard buttons use the local macOS clipboard.
- The red **Clear original text** button sits at the far right and resets the
  original field and hyphen review. The cleaned result remains available.

These are automatic heuristics: compare the result with the PDF. No AI service
is used for cleaning or counting. Saved outputs and widget state are stripped
from the distributed notebooks.

## Development checks

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -v
```

Tests use synthetic metadata and temporary folders, including an end-to-end
offline project creation check and notebook execution. No network is needed.

## Build the desktop app

The developer needs Python with Tk support (the python.org macOS installer
includes it). Create a clean virtual environment and install
`requirements-build.txt`, then run:

```bash
python3 build_app.py
```

On macOS this creates `dist/Journal Analysis Tools.app` and an architecture-named
ZIP. Python, Tcl/Tk, CA certificates, timezone data and the clean notebook
template are included. Jupyter, user preferences, project files and pasted text
are excluded. Build separately on each target operating system/architecture.
`assets/icon.svg` is the editable vector source of the bundled app icon.

The app can also run from source with `python3 desktop_app.py` after installing
`requirements-app.txt`. Source users need Python and Tk; end users of the bundled
app do not. `build/`, `dist/` and generated spec files are ignored by Git.

For an interactive smoke check of the source app or built executable:

```bash
python3 desktop_app.py --smoke-test /tmp/journal-tools-smoke.json
# macOS bundle:
"dist/Journal Analysis Tools.app/Contents/MacOS/Journal Analysis Tools" --smoke-test /tmp/journal-tools-bundle-smoke.json
```

This briefly opens the real window, creates a temporary offline project, checks
text cleanup and the clipboard, verifies settings/certificates/timezone data,
then closes. It writes a small JSON result and deletes all temporary project
and settings files. Ordinary unit tests do not open windows.
