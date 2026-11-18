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
`COM1` are rejected on macOS as well. Random-mode names are checked before
metadata is fetched; manual-mode names are checked before files are written.

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
heuristic. The full export retains them. Publisher article-type labels also exclude non-scientific items, including
front/back matter, contents, covers, book reviews and similar material. Review
the DOI/title/reason entries in the selection report. There is no inclusion
checkbox; legacy `include_notices=True` calls cannot bypass the exclusion.
Incomplete publisher metadata can still require human review. Asking for more papers than are eligible fails
without creating a partial project.

Leave the seed blank for a fresh draw; the actual seed is always saved. The
same seed and the same eligible population produce the same sample even if CSV
row order changes. For exact replay without fetching again, supply the saved
`*_crossref.json` in the advanced options and use the saved seed and settings.
The code example shows constructing a `Journal` directly for a fully offline
replay, which also avoids journal lookup.

## Manual DOI selection

The project notebook also accepts an explicit paper selection. Bare DOIs,
`doi:` prefixes and doi.org/dx.doi.org URLs normalize to the same lowercase
identity. Resolver URL encoding is decoded; DOI suffix punctuation is retained.
Publisher URLs and whitespace-separated identifiers are rejected. Use one DOI
per line in bulk mode. Duplicate identities are included once, in selection
order, without random sampling. Non-scientific articles are rejected during
lookup, cached-record validation and creation using the same metadata/title
rules as random projects.

Each lookup fetches the full Crossref `/works/{doi}` record and validates the
journal-article type, matching DOI, title, journal name and usable publication
date. Author, abstract and export metadata are available from the same record;
missing optional fields remain empty. Records without ISSNs can still be used
when their journal name and other required metadata are present. Crossref-only
coverage means some valid DOIs cannot be resolved by this tool.

Successful results are cached for the current kernel session. Bulk checks use
up to three concurrent requests and report every failed line; cached successes
are retained when a list needs correction. No papers from an invalid list are
added. Editing a nonempty DOI list requires a new check before creation. Clearing
that input leaves the explicitly selected papers available. A pending single
search result becomes selected only through **Add paper**.

Before creation, the overview lists journal names with paper counts, total
papers and bibliography-year range (print year when available). Journal groups
merge matching names or shared ISSNs. Multiple journals produce a visible
warning. Date bounds in `project.json` use the earliest-known publication dates
of the chosen papers; random-mode dates and count do not filter manual choices.

Creation uses only the preloaded records, with no further API request. The same
transactional publication and CSV/BibTeX identity checks apply to both modes.
Manual exports use a `_manual` stem, with `_selected<N>.csv`, `.bib` and
`_selection.json` for the selected list. Both full and selected exports describe
the chosen papers. Raw Crossref metadata remains archived alongside them.

The schema-1 manifest adds `selection_method: "manual"`, journal groups and a
bibliography-year range. `seed` is null. `sample_export` and `selection_export`
both reference the selected-paper CSV, preserving compatibility with existing
categorization notebooks. Reports and the project README identify the selection
as manual, retain the multi-journal warning, and do not claim complete journal
coverage or a random draw. The project still creates no PDF or analysis folders.

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
before joining body lines. It recognizes numbered headings (including bare dotted numbers such as `2.2`) and conservative
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
units deliberately contribute no category totals. The nine default summary rows and any project custom-category rows remain
fixed even when a category is empty. Copy buttons read current values.

Editing the cleaned text or outline invalidates the displayed categorization
until **Apply reviewed outline** is clicked. Matching headings retain labels
when rebuilding. **Fill labels from titles / parents** suggests labels only on
request and fills unassigned units. A parent assignment propagates only when
**Apply to subsections** is clicked. Individual subsection labels remain editable.

### Project-aware selection and persistence

The notebook searches its working directory and ancestors for a supported
`project.json`, or reads the project selected in **Project folder**. The
manifest's `sample_export` CSV supplies the project paper list, with its saved
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

The final normal category, **Not categorizable**, includes its words, paragraphs
and titles in the summary like any other category. **Unassigned** triggers a
completion warning and highlights the corresponding section/subsection rows;
**Exclude from summary** is an explicit exclusion and does not trigger a warning.
Empty categories are valid. Highlights and the warning update in place when
labels change, including parent assignments and reloaded JSON. Individual title
buttons copy newline-separated titles. The whole-table Excel export retains
semicolon-separated lists within each tab-separated cell.

DOI search results and selected-paper cards show all available author names,
including organisation authors. Names are read from the preloaded record; no
extra lookup is required. Missing author metadata displays **Not available**.


### Selecting text and project categories

The cleaned-paper editor uses an inline anywidget module, with no remote scripts.
Browser UTF-16 selection offsets are converted to Python Unicode code points;
a selection includes a snapshot of its text so stale selections cannot annotate
a newer paper. Marking a title puts it on its own line and retains its words.
Existing heading levels can be changed. Removing a boundary retains the text and
resets the merged part to Unassigned. Clearing assignments resets whole parts
intersecting the selection, while keeping their boundaries.

Selecting body text creates virtual boundaries at its start and end as needed;
no synthetic title is inserted into the cleaned text or counted as words. Select
complete words; selections overlapping real heading lines are rejected. Existing
headings and section dropdowns can be used to label such parts instead. Virtual
boundaries must be removed before manually changing the prose. **Reset text
boundaries** applies the current outline without the virtual boundaries and
discards their assignments, so text edits never silently shift saved ranges.
Schema-1 JSON adds optional `manual_boundaries` and `custom_categories`; old files
without these fields remain supported. Structural offsets are recomputed and
validated on load. The cleaned TXT retains the full prose.

Project selection is above the workflow tabs and the paper/saved-file selectors
are at the top of the full-paper tab. Project category names are stored in
`paper_categorizations/categories.json`, separately from `project.json`.
Default labels are reserved case-insensitively. Custom names are unique, 1–80
characters, one per line, and precede the final Not categorizable category.
Removing a name resets assignments in the active document and every recognized
saved categorization JSON in the project, including older locations. All files
are validated before publication; a failed write restores previous files.
The setting and rewritten files are staged together. Original file modification
times are retained to preserve the latest-version ordering. Standalone JSON
retains its own custom category list for portability; project settings are
authoritative when it is loaded or saved inside a project.

### Project summary

The project-summary tab reads the paper identities from `sample_export` and
chooses only the most recently modified saved categorization per DOI. Each
contributes once, including when several versions exist in different subfolders.
A missing paper or invalid newest JSON is reported rather than counted as a
completed zero or silently replaced with an older version. Unassigned counts
remain visible through each paper's status. Aggregate rows use the same counting
rules and fixed copy controls as the individual-paper summary; title lists
include the paper number. A separate all-paper table and TSV export retain
paper title, DOI, completion status and category values. Unsaved editor state is
excluded. The tab refreshes when opened and has an explicit refresh button.
