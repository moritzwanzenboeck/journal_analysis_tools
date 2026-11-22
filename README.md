# Journal Analysis Tools

Create journal projects from a random sample or your own DOI selection, clean
text copied from PDFs, and categorize whole papers by section.

## Open the app

Open the latest [GitHub release](https://github.com/moritzwanzenboeck/journal_analysis_tools/releases/latest).
Under **Assets**, download the platform ZIP for your computer and extract the
whole folder onto a local disk. Each platform ZIP includes the compiled app,
Python and all required notebook packages.

Double-click **Journal Notebook Launcher** in the extracted tools folder:

| Your computer                           | App to open                             |
| --------------------------------------- | --------------------------------------- |
| Windows (`windows-x86_64` ZIP)        | **Journal Notebook Launcher.exe** |
| Intel Mac (`macos-x86_64` ZIP)        | **Journal Notebook Launcher.app** |
| Apple Silicon Mac (`macos-arm64` ZIP) | **Journal Notebook Launcher.app** |

Keep the extracted tools on a local disk. On Windows keep the app beside the
`app` folder. The Mac app contains its Python and tools, so you can also move the
whole `.app` into Applications. Your projects and output can stay on a shared
drive. Opening the app downloads or installs no packages. On Mac, editable
notebooks are copied to your user account and retained between launches.
If macOS blocks the first launch, follow the [Mac first-launch steps](#mac-first-launch-warning) below.

The local web app opens in your default browser. Choose **Create journal project**
or **Clean and categorize papers** in the navigation bar. You can switch tools
without clearing unsaved work while that browser tab stays open.

If the browser does not open, click **Open web app** in the launcher. You can
also copy the address beside it and paste it into your browser.

### Mac first-launch warning

Current Mac downloads are **ad-hoc signed**, without an Apple Developer ID or
Apple notarization. macOS may therefore show **Apple could not verify that
Journal Notebook Launcher is free of malware** or an unidentified-developer
warning. For a trusted download from this repository's Releases page:

1. Try opening **Journal Notebook Launcher.app**. Dismiss the warning with
   **Done** or **Cancel**.
2. Open **Apple menu → System Settings → Privacy & Security**, then scroll to
   **Security**.
3. Find the message about the blocked launcher and click **Open Anyway**.
4. Authenticate if prompted, then click **Open** in the confirmation dialog.

If **Open Anyway** is missing, try opening the app again and return to
**Privacy & Security**. Apple records an exception for this specific app, so
later launches can use the normal double-click. See
[Apple&#39;s instructions for safely opening apps](https://support.apple.com/en-us/102445).

## Create a journal project

1. Open **Create journal project** in the web app.
2. Choose **Random journal sample**, enter the journal title or ISSN, click
   **Find journal**, and select the journal.
3. Choose the start and end dates, the number of papers, and where to save the
   project. Both dates are included.
4. Click **Create project**.
5. Open the new project folder. Its `output` folder contains the full paper list
   and random sample as CSV tables for Excel and BibTeX bibliography files.

Existing projects are never overwritten. Paper information comes from Crossref;
PDFs are not downloaded. Finding journals and fetching paper information require
an internet connection.

## Create a project from your own papers

1. Open **Create journal project** and choose **Manual DOI selection**.
2. Use either entry method:
   - **Search one DOI:** paste a DOI or full `https://doi.org/...` URL and press
     **Enter** (or **Search DOI**). Review the dropdown result, which shows a bold
     title plus authors, journal, year and DOI, then click **Add paper**. Repeat as needed.
   - **Paste DOI list:** paste one DOI or DOI URL per line and click **Check and
     add DOI list**. Correct any listed errors and check again. A list is added
     only when all its entries validate; repeated DOIs are included once.
3. Review **Selected papers** and remove any unwanted entries. The overview shows
   journal names, number of papers and year range. A warning appears when papers
   come from multiple journals; you can still create that project.
4. Choose the projects parent and optional project folder name, then click
   **Create project**.

Lookup preloads the available metadata for exports, including authors and
abstracts. Successful checks are reused when you retry a list or search the same
DOI. Creation uses those preloaded records without fetching them again. Keep the
notebook kernel running until creation; restarting it clears the selection and
lookup cache. DOIs must resolve to journal articles in Crossref.

Manual projects retain the checked scientific articles in selection order; they
are not random samples. Editorials, front/back matter, corrections and similar
non-scientific items are rejected during DOI checks. Random selection excludes
the same material and records the exclusions in its selection report. Their selected-paper exports use
`_selected<N>` names in `output/`. In **Clean and categorize papers**, select the
project folder to load these papers in **Categorize full paper**.

## Clean and count text

1. Open **Clean and categorize papers** and choose **Clean & count (original)**.
2. Paste the copied PDF text into **Original text**.
3. Click **Find line-end hyphens**. Select any words that should keep their hyphen,
   then click **Apply cleanup**.
4. Review and edit **Cleaned text**. The word and paragraph counts update as you edit.
5. Use **Copy word count** or **Copy paragraph count** to copy the number, or select
   the cleaned text and copy it into your document.

The copy buttons work on Windows and macOS when the tool runs on your computer.
Text cleanup works without internet access. Review the result against the PDF:
automatic cleanup can misinterpret headings, line breaks and hyphens.

## Categorize a whole paper

The same notebook has a separate **Categorize full paper** tab. The original
clean-and-count workflow remains in **Clean & count (original)**.

1. Above the workflow tabs, check **Project folder** and click **Scan project
   folder**. A notebook opened inside a generated journal project detects that
   project automatically. When using the central launcher, select your project
   folder here.
2. Select one of the project’s papers and click **Start / reopen paper**.
   This opens its latest saved categorization, or prepares a new paper. To attach
   text you have already pasted, use **Associate current text** instead.
3. Paste the whole paper into **Original paper**, excluding table text, figure
   notes and formulas. Review line-end hyphens, then click **Clean full paper**.
4. Review **Cleaned paper** and mark headings directly in the text, like Markdown:

   ```text
   # 1. Introduction
   Opening paragraph.

   ## 1.1 Background
   Subsection text.

   ### Details
   Further text.
   ```

   Cleanup suggests prefixes for detected headings. Add `# ` to mark a section,
   `## ` for a subsection, and up to six `#` characters for deeper levels. Change
   the number of `#` characters to change the level, or remove the prefix to
   return a heading to body text. The section list and counts update as you type.
   For papers without headings, insert your own heading lines at the boundaries
   you want to categorize. Markdown prefixes are excluded from counts and the
   saved cleaned-text file.
   Alternatively, use **Review / correct heading outline**. Enter one
   `level | exact heading title` per line, for example `1 | Introduction` and
   `2 | Background`, then click **Apply reviewed outline**. Add missed titles
   from their own lines in Cleaned paper, change levels, or remove entries to
   unmark headings. Rename titles directly in Cleaned paper. The outline follows
   Markdown edits automatically; pending outline drafts stay intact until you
   apply them or click **Refresh from Markdown**. Apply or refresh a draft before
   copying the summary or saving.

5. Assign each section or subsection to Introduction, Literature Review, Theory,
   Data, Methods, Results, Discussion, Conclusion or Not categorizable. **Apply to subsections**
   assigns a parent and its descendants; individual labels can then be changed.
   Use **Not categorizable** for parts that should be counted but do not fit the
   other categories. Leave unfinished labels **Unassigned**, or choose **Exclude from summary**.
   The summary warns about unassigned parts and highlights their rows above;
   empty categories are allowed.
6. Use the summary's copy buttons for section titles, subsection titles, words
   and paragraphs, or copy the whole table into Excel. Title buttons copy one
   title per line. Title lists scroll within
   their cells; the cells and copy buttons keep their positions.
7. Click **Save cleaned text + JSON**. In a journal project both files always go
   into its `paper_categorizations` folder. **Saved JSON** lists categorizations
   found throughout the project; select one and click **Load selected JSON** to
   revise it. Other project JSON files are excluded from this list.

Under **Manage project categories** above the tabs, add your own category names,
one per line, and click **Save project categories**. Removing a name resets all
its assignments to **Unassigned** in the current paper and every saved
categorization in that project. The editor warns about this before you apply
changes. Custom categories appear before the final **Not categorizable** row.

The **Project summary** tab starts with an article overview: section count, word
and paragraph totals, total words in section titles, words per title and abstract
length. Only top-level sections contribute to section/title statistics. There is
no Content column. Body totals include assigned subsections and follow each
paper's heading-word setting; Unassigned and excluded text are omitted.

Each category, including custom categories, has its own per-article table with
words per title, total words and paragraphs. Its Summary row shows the average under **Sum words**, alongside the
minimum and maximum word count across papers where that category is present;
zero-word and missing entries are excluded. An **x** marks every minimum/maximum
tie. Missing analyses and unavailable abstracts show a dash; undefined averages
never produce division errors. Abstracts use a cleaned Abstract section when
available, then the project's saved metadata.

Copy the whole report or an individual table into Excel. The earlier aggregate
category/title grid is available under **Aggregate category totals and titles**.
The project tables wrap to the available width and expand to show every row;
the heading-outline card also grows with its text. Read longer reports using
normal notebook page scrolling.
The report uses the latest saved JSON per DOI. Save the current paper first;
unsaved edits are excluded. Click **Refresh project summary** after changes made
in another notebook.

Matching headings keep their category when their prose, title or level changes.
New headings start Unassigned. Removing a heading prefix keeps its words in the
body and resets the merged part to Unassigned for review. Older categorization
JSON still loads; earlier text-only section labels retain their counting rules.

**Show text** opens a floating section preview; click it again or **Hide text**
to close the preview completely. The summary stays in place. Review automatic
heading boundaries against the PDF before using the counts. Heading words are
included by default; paragraph counts cover body text. See the
[counting reference](dev/analysis_reference.md) for details.

Outside a project you can choose a save folder and load JSON using its file
picker or path. Save before switching papers. If you intentionally want to
replace unsaved work, enable **Allow replacing the current unsaved paper**.
Existing files require **Overwrite existing files** before replacement.

## Finish or recover a tool

Copy any standalone cleaned text you want to keep into your document, and save
full-paper categorizations as JSON before stopping or restarting a tool. Saving
the notebook itself is not a substitute for saving categorization JSON.

| What you need | What to do |
| --- | --- |
| Open the running web app | Click **Open web app**. |
| Recover a page that has stopped responding | Click **Kill kernels**, then reload the web app. This clears unsaved work on both pages. |
| Stop the web app | Click **Stop**. |
| Stop the web app if it will not shut down | Click **Force stop**. |
| Finish using both tools | Close the launcher and confirm. |

Closing the browser tab leaves the local server running. Save your work before
closing or reloading the tab. The launcher shows the server's port and link.
Saved project files remain on disk after you stop the web app.

For more detail, see [setup and troubleshooting](dev/SETUP.md),
[analysis and counting rules](dev/analysis_reference.md), or
[development instructions](dev/README.md).
