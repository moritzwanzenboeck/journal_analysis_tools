# Analysis reference

Detailed export formats, metadata rules and text-counting behavior. For everyday
use, see the [user guide](../README.md).

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

Custom project folder names use the same portable character rules on both
platforms. Trailing dots and Windows device names such as `CON`, `NUL` and
`COM1` are rejected on macOS as well, before metadata is fetched.

CSV files use UTF-8 with a BOM for Excel. Full and sampled paper metadata are
kept in `output/`. Choose your own folders and files for PDFs and analysis
results. PDFs are not downloaded. The full-paper workflow creates
`paper_categorizations/` only when you save a categorization; project creation
does not create PDF or analysis folders.

`project.json` records the journal, ISSNs, dates, publication basis, chosen sample
size, actual random seed and export paths. CSV and BibTeX exports have identical
DOIs and citation keys in the same order; this is verified before writing.
The reports retain retrieval queries, metadata limitations and sampling
exclusions. No previous journal analysis, completed workbook or paper is
bundled with these tools.

## Metadata and sampling rules

The setup notebook replaces the journal-specific fetch and sampling
scripts. `app/journal_tools.py` contains the shared fetching, sampling and project
functions. Its core uses the standard library, with optional `certifi` certificates;
the requirements include timezone data for platforms that lack it. `app/text_tools.py`
shares the cleaning rules with the self-contained notebook, with regression tests
checking parity.
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

Start the **Clean and count text** service, or open a project's
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
- **Copy word count** precedes **Copy paragraph count**. Notebook clipboard
  buttons work on Windows and macOS when the notebook runs locally.
- The red **Clear original text** button sits at the far right and resets the
  original field and hyphen review. The cleaned result remains available.

These are automatic heuristics: compare the result with the PDF. No AI service
is used for cleaning or counting. Saved outputs and widget state are stripped
from the distributed notebooks.

## Full-paper categorization

The **Categorize full paper** tab uses the same punctuation, footnote, p-value
and hyphen cleanup rules as the original workflow. It protects detected headings
before joining body lines. It recognizes numbered headings and conservative
unnumbered candidates; this is a heuristic, so review the outline. Each outline
entry has `level | exact heading title`, with levels 1–6. Duplicate titles are
matched in order. Text before the first heading is a separate preamble unit.

Each unit owns the body text from its heading up to the next heading. A parent's
body does not include its children's bodies. This prevents duplicate word and
paragraph totals when sections and subsections have different categories.
Heading words are included by default and can be switched off; paragraph counts
use body text only. Top-level titles appear as context alongside subsections in
the summary even if the parent belongs to another category. Repeated context
titles do not add words or paragraphs. Unassigned units need review; excluded
units deliberately contribute no category totals. The eight summary rows remain
fixed even when a category is empty. Copy buttons read current values.

Editing the cleaned text or outline invalidates the displayed categorization
until **Apply reviewed outline** is clicked. Matching headings retain labels
when rebuilding. **Fill labels from titles / parents** suggests labels only on
request and fills unassigned units. A parent assignment propagates only when
**Apply to subsections** is clicked. Individual subsection labels remain editable.

### Project-aware selection and persistence

The notebook searches its working directory and ancestors for a supported
`project.json`, or reads the project selected in **Project folder**. The
manifest's `sample_export` CSV supplies the sampled paper list, with its saved
sample size (10 or any other chosen number). DOI links each paper to its saved
categorization. **Start / reopen paper** opens the newest saved JSON for that
DOI; **Associate current text** attaches an already pasted paper without clearing
it. A stable DOI-derived prefix avoids relying on CSV row order.

**Saved JSON** scans the project recursively for full-paper categorization JSON,
including files in older locations. It ignores Crossref exports, sampling
reports, project configuration and unrelated JSON, and skips symlinked files
and directories. Loading an older file does not move it. Every subsequent save
within that project writes both files into `<project>/paper_categorizations/`,
regardless of the loaded file's location. The project save-folder field is locked.
Outside a generated project, a save folder can be chosen freely.

A save produces `<prefix>_cleaned.txt` and `<prefix>_categories.json` in UTF-8.
Both files require explicit overwrite permission if either already exists.
Writes are staged and previous files are restored if publication fails.
JSON schema version 1 contains the workflow identifier, paper name, raw pasted
source, cleaned text, retained hyphens, heading-word option, units and category
assignments. Optional `paper_metadata` records the sampled DOI/title/citation
key and `project_metadata` records journal/sample-export information without an
absolute machine path. Earlier version-1 files without these fields still load.
Counts and summary are recomputed from validated text and assignments on load.
Unsupported schemas or inconsistent heading/body data are rejected before
replacing the current paper. A `.txt` export alone cannot restore assignments.

Save JSON before stopping, restarting or rerunning all cells. Switching to
another sampled paper or loading JSON protects unsaved edits unless the explicit
replacement checkbox is enabled. A section's **Show text** opens a floating
preview; toggling it or **Hide text** removes the entire preview and clears its
text. Summary cells keep fixed sizes, long title lists scroll vertically inside
them, and narrow windows use one outer horizontal scrollbar.
