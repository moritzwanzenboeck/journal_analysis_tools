# Journal Analysis Tools

Create a random sample of papers from a journal, or clean text copied from a PDF
and count its words and paragraphs.

## Open the app

Double-click **Journal Notebook Launcher** in the tools folder:

| Your computer | App to open |
| --- | --- |
| Windows | **Journal Notebook Launcher.exe** |
| Mac, Intel or Apple Silicon | **Journal Notebook Launcher.app** |

On a new computer, complete the [one-time setup](dev/SETUP.md) first, or ask the
person providing these tools to do it. After setup, you can use the app without
typing commands. Keep the tools folder together.

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

## Finish or recover a tool

Copy any cleaned text you want to keep into your document before stopping a tool.

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
