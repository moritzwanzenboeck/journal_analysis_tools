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
unnumbered candidates; this is a heuristic, so review the outline. Suggested headings are prefixed with Markdown markers in the cleaned editor.
`#` through `######` set levels 1–6; a space separates the prefix and title.
After cleanup, only explicitly marked lines define headings. Duplicate titles
are matched using their body text and document order. Text before the first heading is a separate preamble unit.

Each unit owns the body text from its heading up to the next heading. A parent's
body does not include its children's bodies. This prevents duplicate word and
paragraph totals when sections and subsections have different categories.
Heading words are included by default and can be switched off; paragraph counts
use body text only. Top-level titles appear as context alongside subsections in
the summary even if the parent belongs to another category. Repeated context
titles do not add words or paragraphs. Unassigned units need review; excluded
units deliberately contribute no category totals. The nine default summary rows and any project custom-category rows remain
fixed even when a category is empty. Copy buttons read current values.

The native cleaned-paper textarea updates structure, counts and summaries as you
edit Markdown headings or body text. Matching headings retain their labels;
new headings start Unassigned. Renames with a uniquely matching body retain the
previous label. Removing a prefix retains the heading words as body text and
resets the merged assignment to Unassigned for review. A bare unfinished marker
such as `## ` displays a prompt and blocks saving/copying stale counts until a
title is entered. The previous valid document remains available while typing.
**Fill labels from titles / parents** fills unassigned units only on request.
Parent assignments propagate through **Apply to subsections**; child labels
remain editable.

The alternative **Review / correct heading outline** field uses one
`level | exact title` entry per line, in document order. **Apply reviewed outline**
rewrites only Markdown heading markers: changing a level updates its prefix,
adding an entry marks an existing own-line title, and omission unmarks a title
while retaining its words. Titles must already exist; rename them in the text.
Existing marked occurrences are preferred over identical body lines unless extra
occurrences are explicitly requested. Invalid/out-of-order titles or headings
inside fenced text blocks are rejected without changing the editor or model.

The outline follows valid Markdown changes automatically. An edited outline is
a draft and is not overwritten by further Markdown edits. Apply it or use
**Refresh from Markdown** to replace it with the current headings. Pending drafts
block copying/saving and count as unsaved work for paper switching. Loading a
paper resets the outline from its stored sections, including legacy virtual
labels. The alternative editor uses the same native widgets as the Markdown view.

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


### Markdown headings and project categories

The cleaned-paper editor is a standard ipywidgets textarea. It requires no
custom browser module. Heading prefixes use one to six `#` characters and a
space at the start of a line (up to three leading spaces). Optional trailing
hashes are omitted from the title. Inline hashes, escaped prefixes and lines
inside backtick/tilde fences remain body text. Cleanup protects explicitly
marked heading lines, or seeds markers from the existing conservative detector
for unmarked source text. Editing never silently reruns that detector.

The JSON and cleaned TXT keep canonical text without Markdown heading markers.
Printed titles remain in that text and use the saved heading-word option;
markers contribute no words or paragraphs. Reload reconstructs the editable
Markdown view from stored section levels. Original pasted source remains
separate. Old schema-1 files, including selected-text `manual_boundaries`, are
supported: old virtual labels are displayed as heading lines but remain virtual
for counting and are omitted from canonical prose. They can be edited without
clearing boundaries first. No JSON migration overwrites a file on load.

Ordinary body edits update existing section/count widgets in place. Changes to
headings rebuild section rows as needed while keeping the summary grid fixed.

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

The project-summary tab reads identities and available abstracts from
`sample_export` and chooses only the most recently modified saved categorization
per DOI. A paper contributes once even if several versions exist. Missing
papers and invalid newest JSON are reported rather than counted as completed
zeros or silently replaced with an older file. Status identifies partial
assignments. Unsaved editor state is excluded. The tab refreshes when opened
and has an explicit refresh button. No metadata is fetched for this report.

The article overview contains article number, total sections, total word count,
total paragraphs, total words in titles, words per title, words per abstract
and status. There is no Content column. Article-number tooltips identify the
title/DOI; abstract-count tooltips identify the source.

- Section and title statistics use **top-level units only** (`level == 1`)
  assigned to normal categories, including custom labels and Not categorizable.
  Subsections, preambles, Unassigned and excluded headings do not add sections
  or title words. Context titles displayed for children do not count again.
- A manually created top-level text section counts as a section. Its virtual
  display title contributes no title words and is omitted from the title average.
- Printed heading words use the existing WORD rule, including printed section
  numbers. Words per title is total printed-title words divided by the number
  of printed top-level titles; no titles means undefined, displayed as a dash.
- Body totals sum normal-category word/paragraph counts across all levels,
  counting each unit once. They respect each saved paper's heading-word option.
  The separate title statistics remain available when that option is off.
- Abstract length counts body words under an exact Abstract heading and its
  descendants, excluding heading words, regardless of its assigned category.
  If absent, the preloaded project CSV abstract is used, then optional saved
  paper metadata. Missing abstracts are undefined, not invented zero lengths.
  Abstracts should normally be marked Exclude from summary when they are to
  remain outside body totals.

Each normal/custom category has a table with article number, words per title,
sum words, Min, Max and paragraphs. Title averages use only that
category's own printed top-level headings. The Summary row puts the mean directly under **Sum words**, followed by the
minimum and maximum of **positive category word counts** across saved papers.
Missing/invalid papers and zero-word categories are excluded from these
statistics. Partially assigned saved papers contribute their current category
counts and retain their incomplete status in the article overview. Every tie
gets `x` in the corresponding Min/Max column; a sole positive value is both.
No positive entries means undefined statistics.

Missing numeric values display a dash and copy as blank cells. Actual zero
counts remain zero. Decimal output uses up to nine fractional digits without
thousands separators or division-error strings. Whole-report TSV exports use
vertical overview/category blocks, headers and Summary rows in display order.
Individual tables can also be copied. TSV quoting preserves cell boundaries.
Project report cells wrap at the available width and all rows expand in the
normal notebook page flow. Tables, status panels and the aggregate-title grid
have no internal scroll areas. The earlier aggregate grid remains in a collapsed
accordion and uses flexible columns in project mode; the individual-paper grid
retains its existing fixed layout. The outline textarea grows with its text
using a hidden text mirror that measures wrapping at the actual browser width,
so long outlines remain editable without internal scrolling or custom JavaScript.
The copied-text fallback uses the same sizing mechanism.

## Folder and JSON selection

Both notebooks embed the OS-dialog helpers from `app/file_selectors.py`, so
copied project notebooks remain self-contained. `Browse…` launches a short-lived
Python subprocess using the current interpreter. That child creates Tk and runs
`filedialog.askdirectory` or `askopenfilename` on its main thread, giving macOS
and Windows their system dialogs. On macOS the parent is omitted, giving a
independent panel instead of a sheet attached to a hidden window.
Windows retains the Tk parent. Tk is never initialized in the kernel.

An asynchronous callback waits for the child's result via a worker thread,
keeping the kernel responsive without relying on Windows async subprocess
support. The child receives a JSON request on standard input and returns JSON;
paths never enter shell commands. Windows suppresses a console window. Cancelling
the task terminates only its own dialog subprocess. Native dialog cancellation
leaves the path unchanged; errors restore the button and allow manual path entry.

Dialog requests start at the entered path or its nearest existing ancestor.
JSON mode filters for JSON files; the selected result is revalidated, with a
case-insensitive `.json` extension. Selection only fills the existing field,
whose scan/load/create action remains explicit. A disabled field cannot open a
dialog; a selection returning after the field changes or becomes disabled is
ignored. Project saves remain constrained to `paper_categorizations/`.

Native dialogs need a graphical desktop on the kernel computer. When the notebook
runs remotely, enter a server path or use the existing JSON upload control for a
file on the browser computer.
