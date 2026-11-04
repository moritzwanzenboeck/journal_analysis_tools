# Journal analysis tools

Create an analysis project for any journal, fetch its Crossref metadata, draw a
reproducible random sample, and clean copied paper text for word and paragraph
counts. There are no fixed journals, paper titles, personal paths or API keys.

## Start

Use Python 3.10 or newer. From this repository folder:

```bash
python3 -m pip install -r requirements.txt
python3 -m notebook create_journal_analysis.ipynb
```

On macOS you can double-click `start_notebook.command` after installing the
requirements. Its root is the tools folder's parent, so generated sibling
projects are accessible in the same Jupyter session. The launcher resolves its
own location and supports paths containing spaces; it contains no fixed path.
Alternatively, open the notebooks in VS Code and select a Python environment
with these dependencies.

1. Open **create_journal_analysis.ipynb** and run its cells in order.
2. Enter a journal title or ISSN, click **Find journal**, and select the intended
   result. Title search never silently chooses a journal.
3. Choose the inclusive start/end dates and number of random papers.
4. Choose an existing parent directory. By default it is this repository's
   parent, so analysis projects sit alongside the tools folder.
5. Click **Create project**. Review the printed sample and export reports.

The default folder name is
`DDMMYYYY_journalanalysis_<journal>_<start-date>_<end-date>`, using the creation
date in Europe/Zurich. You may enter a different folder name. Existing projects
are never reused or overwritten. A failed fetch or an oversized sample creates
no project. A rerun against an existing folder asks you to choose a different
name; the original random sample and analysis are preserved.

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

The setup notebook replaces the journal-specific fetch and sampling scripts.
A shared, standard-library-only `journal_tools.py` contains the reusable
functions; the notebook supplies the interactive workflow. Its optional code
cells also support scripted creation and drawing a new sample from a saved CSV.

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

Open a project's **clean_and_count_text.ipynb**, run its cells, paste PDF text,
review line-end hyphens, and apply cleanup. The editable result has live counts.

- Body lines ending in `.`, `:`, `?` or `!` are paragraph endings. Footnote
  digits attached after the punctuation also count, for example `.12`.
- Leading-zero numeric suffixes such as `0.001` continue into the next line.
  P-value expressions such as `(𝑝<.1\n).` become `(𝑝<.1).` without a false break.
- Missing blank lines between paragraphs are inserted; existing paragraph
  spacing is retained. Unfinished wrapped body lines join with spaces.
- Numbered headings are separate and excluded from paragraph counts. Word
  counts include the displayed headings and any retained mathematics.
- **Copy word count** precedes **Copy paragraph count**. Clipboard buttons use
  the local macOS clipboard; elsewhere copy the displayed counts manually.
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
