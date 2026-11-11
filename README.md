# Journal Analysis Tools

Create a random sample of papers from a journal, or clean text copied from a PDF
and count its words and paragraphs, or categorize a whole paper by section.

## Open the app

Download the ZIP for your computer from [Releases](https://github.com/moritzwanzenboeck/journal_analysis_tools/releases/latest),
then extract the complete folder onto a local disk. Choose a platform ZIP under
**Assets**; the automatic **Source code** downloads do not contain compiled apps.
Each platform ZIP includes its ready-to-open launcher, so no compilation is needed.

Double-click **Journal Notebook Launcher** in the extracted tools folder:

| Your computer | App to open |
| --- | --- |
| Windows (`windows-x86_64` ZIP) | **Journal Notebook Launcher.exe** |
| Intel Mac (`macos-x86_64` ZIP) | **Journal Notebook Launcher.app** |
| Apple Silicon Mac (`macos-arm64` ZIP) | **Journal Notebook Launcher.app** |

On a new computer, complete the [one-time setup](dev/SETUP.md) first, or ask the
person providing these tools to do it. Python and Jupyter are still required;
the compiled launcher does not bundle them. After setup, you can use the app
without typing commands. Keep the complete extracted tools folder together on
a local disk. Your analysis projects and output can be saved on a shared drive.

1. Click **Start** next to the tool you want to use.
2. Its notebook opens in your web browser. In the notebook's **Run** menu, choose
   **Run All Cells** to show the controls.
3. Follow the steps below. You can use both tools at the same time.

If the browser does not open, click **Open notebook** in the launcher. You can
also copy the address beside it and paste it into your browser.

## Create a journal project

1. Start **Create journal project** and run all notebook cells.
2. Enter the journal title or ISSN, click **Find journal**, and select the journal.
3. Choose the start and end dates, the number of papers, and where to save the
   project. Both dates are included.
4. Click **Create project**.
5. Open the new project folder. Its `output` folder contains the full paper list
   and random sample as CSV tables for Excel and BibTeX bibliography files.

Existing projects are never overwritten. Paper information comes from Crossref;
PDFs are not downloaded. Finding journals and fetching paper information require
an internet connection.

## Clean and count text

1. Start **Clean and count text** and run all notebook cells.
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

1. In **Save and reload**, check **Project folder** and click **Scan project
   folder**. A notebook opened inside a generated journal project detects that
   project automatically. When using the central launcher, select your project
   folder here.
2. Select one of the randomly sampled papers and click **Start / reopen paper**.
   This opens its latest saved categorization, or prepares a new paper. To attach
   text you have already pasted, use **Associate current text** instead.
3. Paste the whole paper into **Original paper**, excluding table text, figure
   notes and formulas. Review line-end hyphens, then click **Clean full paper**.
4. Review the cleaned text and detected headings. Under **Review / correct heading
   boundaries**, edit the outline as `level | exact heading title`, then click
   **Apply reviewed outline**. Reapply the outline after editing the cleaned text.
5. Assign each section or subsection to Introduction, Literature Review, Theory,
   Data, Methods, Results, Discussion or Conclusion. **Apply to subsections**
   assigns a parent and its descendants; individual labels can then be changed.
   Leave unfinished labels **Unassigned**, or choose **Exclude from summary**.
6. Use the summary's copy buttons for section titles, subsection titles, words
   and paragraphs, or copy the whole table into Excel. Title lists scroll within
   their cells; the cells and copy buttons keep their positions.
7. Click **Save cleaned text + JSON**. In a journal project both files always go
   into its `paper_categorizations` folder. **Saved JSON** lists categorizations
   found throughout the project; select one and click **Load selected JSON** to
   revise it. Other project JSON files are excluded from this list.

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
| Open a running tool again | Click **Open notebook**. |
| Recover a notebook that has stopped responding | Click **Kill kernels**, reopen the notebook, then choose **Run All Cells**. This clears its working text and variables. |
| Stop one tool | Click **Stop**. |
| Stop a tool that will not shut down | Click **Force stop**. |
| Finish using both tools | Close the launcher and confirm that its tools should stop. |

Closing a browser tab leaves the tool running. The launcher shows each running
tool's port and link; you do not need to choose a port yourself. Saved project
files remain on disk after you stop the tools.

For more detail, see [setup and troubleshooting](dev/SETUP.md),
[analysis and counting rules](dev/analysis_reference.md), or
[development instructions](dev/README.md).
