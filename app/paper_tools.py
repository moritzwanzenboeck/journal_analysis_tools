"""Full-paper categorization, project discovery and persistence shared with the notebook."""
import re
from .text_tools import LINE_END_HYPHEN, WORD, normalize_newlines, clean_text, count_text, ends_paragraph, find_line_end_hyphens

# Full-paper categorization: self-contained, local helpers.
import json
import csv
import hashlib
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
import tempfile

PAPER_CATEGORIES = (
    "Introduction", "Literature Review", "Theory", "Data", "Methods",
    "Results", "Discussion", "Conclusion", "Not categorizable",
)
PAPER_UNASSIGNED = "Unassigned"
PAPER_EXCLUDED = "Exclude from summary"
PAPER_LABELS = (PAPER_UNASSIGNED, *PAPER_CATEGORIES, PAPER_EXCLUDED)
PAPER_NUMBERED_TITLE = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+([^\W\d_].*)$", re.UNICODE)
PAPER_KNOWN_TITLES = {
    "abstract", "introduction", "literature review", "related literature", "related work",
    "background", "institutional background", "institutional setting", "theory",
    "theoretical framework", "conceptual framework", "data", "data description",
    "data and methods", "data and empirical strategy", "methods", "methodology",
    "empirical methods", "empirical strategy", "research design", "identification",
    "identification strategy", "estimation", "empirical model", "results", "empirical results",
    "robustness checks", "sensitivity analysis", "discussion", "results and discussion",
    "discussion and conclusion", "conclusion", "conclusions", "concluding remarks",
    "references", "bibliography", "acknowledgments", "acknowledgements", "appendix",
}


def paper_detect_headings(text):
    """Suggest short numbered/unnumbered heading lines; the outline remains editable."""
    lines = normalize_newlines(text).split("\n")
    headings = []
    small_words = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    for index, raw in enumerate(lines):
        title = raw.strip()
        words = WORD.findall(title)
        if not title or len(title) > 140 or not words or len(words) > 18:
            continue
        numbered = PAPER_NUMBERED_TITLE.fullmatch(title)
        if numbered:
            parts = numbered.group(1).split(".")
            if len(parts) <= 6 and all(int(number) < 100 for number in parts):
                headings.append({"title": title, "level": len(parts), "line": index + 1})
            continue
        if title.endswith((".", "?", "!", ";", ",")) or re.search(r"[.?!]\d+$", title):
            continue
        name = " ".join(title.rstrip(":").casefold().split())
        known = name in PAPER_KNOWN_TITLES or bool(re.fullmatch(r"appendix\s+[a-z](?:[.:].*)?", name))
        if ends_paragraph(title) and not known:
            continue
        before_blank = index == 0 or not lines[index - 1].strip()
        after_blank = index + 1 == len(lines) or not lines[index + 1].strip()
        content_words = [word for word in words if word.casefold() not in small_words]
        title_case = bool(content_words) and sum(word[0].isupper() for word in content_words) / len(content_words) >= 0.75
        standalone = before_blank and after_blank and len(words) <= 12 and title[0].isupper()
        if known or (len(words) <= 12 and title_case and before_blank) or standalone:
            headings.append({"title": title, "level": 1, "line": index + 1})
    return headings


def paper_clean_text(text, keep_hyphens=()):
    """Apply the existing rules within body spans, preserving suggested heading lines."""
    text = normalize_newlines(text)
    keep = set(keep_hyphens)
    index = 0

    def replace_hyphen(match):
        nonlocal index
        preserve = index in keep
        index += 1
        if not preserve:
            return ""
        return "-" if match.group(0)[0] == "\u00ad" else match.group(0)[0]

    text = LINE_END_HYPHEN.sub(replace_hyphen, text)
    lines = text.split("\n")
    headings = paper_detect_headings(text)
    pieces, cursor = [], 0
    for heading in headings:
        body = "\n".join(lines[cursor:heading["line"] - 1]).strip()
        if body:
            pieces.append(clean_text(body))
        pieces.append(heading["title"])
        cursor = heading["line"]
    body = "\n".join(lines[cursor:]).strip()
    if body:
        pieces.append(clean_text(body))
    return "\n\n".join(pieces)


def paper_outline_text(headings):
    return "\n".join(f"{heading['level']} | {heading['title']}" for heading in headings)


def paper_parse_outline(text):
    headings = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        level, separator, title = line.partition("|")
        if not separator or not level.strip().isdigit() or not 1 <= int(level.strip()) <= 6 or not title.strip():
            raise ValueError(f"Outline line {number}: use level | exact heading title (levels 1–6).")
        headings.append({"level": int(level.strip()), "title": title.strip()})
    return headings


def paper_partition(cleaned_text, headings):
    """Split own body text from child subsections; no span is counted twice."""
    text = normalize_newlines(cleaned_text)
    if not text.strip():
        raise ValueError("Paste or load paper text first.")
    lines = text.split("\n")
    located, cursor = [], 0
    for heading in headings:
        if type(heading.get("level")) is not int or not 1 <= heading["level"] <= 6 or not isinstance(heading.get("title"), str):
            raise ValueError("Invalid heading level or title.")
        title = heading["title"].strip()
        if not title or "\n" in title or "\r" in title:
            raise ValueError("A heading must be a nonempty single line.")
        found = next((i for i in range(cursor, len(lines)) if lines[i].strip() == title), None)
        if found is None:
            raise ValueError(f"Heading not found in order on its own line: {title!r}. Copy its exact title from Cleaned paper.")
        located.append({"title": title, "level": heading["level"], "line": found + 1})
        cursor = found + 1
    units = []
    first_heading = located[0]["line"] - 1 if located else len(lines)
    preamble = "\n".join(lines[:first_heading]).strip()
    if preamble:
        units.append({"title": "", "level": 0, "heading_line": None, "body": preamble})
    for index, heading in enumerate(located):
        end = located[index + 1]["line"] - 1 if index + 1 < len(located) else len(lines)
        units.append({"title": heading["title"], "level": heading["level"], "heading_line": heading["line"],
                      "body": "\n".join(lines[heading["line"]:end]).strip()})
    stack = []
    for index, unit in enumerate(units, 1):
        unit["id"] = f"part_{index:04d}"
        while stack and stack[-1]["level"] >= unit["level"]:
            stack.pop()
        unit["parent_id"] = stack[-1]["id"] if stack and unit["level"] else None
        unit["category"] = PAPER_UNASSIGNED
        if unit["level"]:
            stack.append(unit)
    return units


def paper_make_document(cleaned_text, outline_text, *, previous=None, include_heading_words=True,
                        paper_name="paper", source_text="", keep_hyphens=(), paper_metadata=None, project_metadata=None):
    text = normalize_newlines(cleaned_text)
    units = paper_partition(text, paper_parse_outline(outline_text))
    # Match repeated headings in document order when rebuilding after an edit.
    labels = defaultdict(deque)
    if previous:
        for unit in previous["units"]:
            labels[unit["title"]].append(unit["category"])
    for unit in units:
        if labels[unit["title"]]:
            unit["category"] = labels[unit["title"]].popleft()
    return {"schema_version": 1, "workflow": "full_paper_categorization", "paper_name": paper_name,
            "cleaned_text": text, "source_text": source_text, "keep_hyphens": sorted(set(keep_hyphens)),
            "include_heading_words": bool(include_heading_words), "units": units,
            "paper_metadata": dict(paper_metadata if paper_metadata is not None else (previous or {}).get("paper_metadata", {})),
            "project_metadata": dict(project_metadata if project_metadata is not None else (previous or {}).get("project_metadata", {}))}


def paper_unit_counts(unit, include_heading_words=True):
    body = count_text(unit["body"])
    return {"words": body["words"] + (len(WORD.findall(unit["title"])) if include_heading_words else 0),
            "paragraphs": body["paragraphs"]}


def paper_summary(document):
    rows = {category: {"category": category, "section_titles": [], "subsection_titles": [], "words": 0, "paragraphs": 0}
            for category in PAPER_LABELS}
    by_id = {unit["id"]: unit for unit in document["units"]}
    seen = {category: set() for category in PAPER_LABELS}
    for unit in document["units"]:
        row = rows[unit["category"]]
        counts = paper_unit_counts(unit, document["include_heading_words"])
        row["words"] += counts["words"]
        row["paragraphs"] += counts["paragraphs"]
        root = unit
        while root["parent_id"]:
            root = by_id[root["parent_id"]]
        if root["level"] <= 1 and root["id"] not in seen[unit["category"]]:
            row["section_titles"].append(root["title"] or "[Text before first heading / unheaded text]")
            seen[unit["category"]].add(root["id"])
        if unit["level"] > 1:
            row["subsection_titles"].append(unit["title"])
    return rows


def paper_validate_document(value):
    """Validate JSON before changing the editor; recompute structure and all counts."""
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1 or value.get("workflow") != "full_paper_categorization"):
        raise ValueError("This is not a supported paper-categorization JSON file (schema version 1).")
    if (not isinstance(value.get("cleaned_text"), str) or not isinstance(value.get("source_text", ""), str)
            or not isinstance(value.get("paper_name"), str) or type(value.get("include_heading_words")) is not bool
            or not isinstance(value.get("units"), list)):
        raise ValueError("The saved file has invalid paper text, settings or sections.")
    saved = value["units"]
    if not saved or any(not isinstance(unit, dict) for unit in saved):
        raise ValueError("The saved file has no valid sections.")
    outline = [{"title": unit.get("title"), "level": unit.get("level")} for unit in saved if unit.get("heading_line") is not None]
    units = paper_partition(value["cleaned_text"], outline)
    if len(saved) != len(units):
        raise ValueError("Saved section boundaries do not match the cleaned text.")
    for actual, expected in zip(saved, units):
        for field in ("id", "title", "level", "heading_line", "parent_id", "body"):
            if actual.get(field) != expected[field]:
                raise ValueError(f"Saved section structure does not match the cleaned text ({field}).")
        if actual.get("category") not in PAPER_LABELS:
            raise ValueError("The saved file contains an unknown category.")
        expected["category"] = actual["category"]
    keep = value.get("keep_hyphens", [])
    count = len(find_line_end_hyphens(value.get("source_text", "")))
    if not isinstance(keep, list) or any(type(index) is not int or not 0 <= index < count for index in keep):
        raise ValueError("The saved hyphen selection is invalid.")
    metadata = {}
    for field in ("paper_metadata", "project_metadata"):
        item = value.get(field, {})
        if not isinstance(item, dict) or any(not isinstance(key, str) or not isinstance(val, (str, int, bool, type(None))) for key, val in item.items()):
            raise ValueError("Invalid saved paper/project metadata.")
        metadata[field] = dict(item)
    return {"schema_version": 1, "workflow": "full_paper_categorization", "paper_name": value["paper_name"],
            "cleaned_text": normalize_newlines(value["cleaned_text"]), "source_text": value.get("source_text", ""),
            "keep_hyphens": sorted(set(keep)), "include_heading_words": value["include_heading_words"], "units": units, **metadata}


def paper_export_document(document):
    document = paper_validate_document(document)
    result = dict(document, saved_at_utc=datetime.now(timezone.utc).isoformat())
    result["counting"] = {"words": "Body words plus own heading words when enabled; existing WORD rule.",
                          "paragraphs": "Existing punctuation/footnote rule on own body text; all headings excluded.",
                          "section_titles": "Top-level titles provide context for assigned subsections, even when their parent has another label."}
    result["units"] = [dict(unit, counts=paper_unit_counts(unit, document["include_heading_words"])) for unit in document["units"]]
    result["summary"] = list(paper_summary(document).values())
    return result


def paper_save_files(document, directory, name, overwrite=False):
    """Save matching UTF-8 text/JSON; keep previous files if publication fails."""
    document = paper_export_document(document)
    name = name.strip()
    if not name or name in (".", "..") or any(char in name for char in '/\\\n\r\t<>:"|?*'):
        raise ValueError("Use a file prefix without folders or line breaks.")
    directory = Path(directory).expanduser().resolve()
    targets = (directory / (name + "_cleaned.txt"), directory / (name + "_categories.json"))
    for target in targets:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError(f"Not a regular output file: {target}")
        if target.exists() and not overwrite:
            raise FileExistsError("Files already exist. Choose another prefix or enable Overwrite existing files.")
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".paper-save-", dir=directory) as temporary:
        stage = Path(temporary)
        contents = (document["cleaned_text"], json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        for index, content in enumerate(contents):
            (stage / str(index)).write_text(content, encoding="utf-8")
        backups, published = {}, []
        try:
            for index, target in enumerate(targets):
                if target.exists():
                    backups[target] = stage / ("previous-" + str(index))
                    target.replace(backups[target])
            for index, target in enumerate(targets):
                (stage / str(index)).replace(target)
                published.append(target)
        except BaseException:
            for target in published:
                target.unlink()
            for target, previous in backups.items():
                previous.replace(target)
            raise
    return targets


PAPER_PROJECT_SAVE_FOLDER = "paper_categorizations"


def paper_read_project(directory):
    """Read an existing notebook-created project; never create folders while scanning."""
    root = Path(directory).expanduser().resolve()
    config = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    if (not isinstance(config, dict) or config.get("schema_version") != 1
            or not isinstance(config.get("journal"), str) or not isinstance(config.get("sample_export"), str)):
        raise ValueError("This is not a supported journal-analysis project.json.")
    sample = (root / config["sample_export"]).resolve()
    if not sample.is_relative_to(root) or not sample.is_file():
        raise ValueError("The project's sampled-paper CSV is missing or outside its folder.")
    with sample.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"doi", "title"}.issubset(reader.fieldnames or []):
            raise ValueError("The sample CSV needs DOI and title columns.")
        papers = []
        seen = set()
        for number, row in enumerate(reader, 1):
            doi = (row.get("doi") or "").strip().lower()
            title = (row.get("title") or "").strip()
            if not doi or not title or doi in seen:
                raise ValueError("The sample CSV contains missing or duplicate paper identities.")
            seen.add(doi)
            paper = {key: (row.get(key) or "").strip() for key in ("title", "authors", "bibtex_key", "url")}
            paper.update(doi=doi, title=title, sample_number=number)
            papers.append(paper)
    save_directory = root / PAPER_PROJECT_SAVE_FOLDER
    if save_directory.exists() and (save_directory.is_symlink() or not save_directory.is_dir()):
        raise ValueError("The project's categorization folder must be a regular folder inside the project.")
    return {"root": root, "config": config, "papers": papers, "save_directory": save_directory}


def paper_find_project(directory):
    start = Path(directory).expanduser().resolve()
    for candidate in (start, *start.parents):
        if (candidate / "project.json").is_file():
            return paper_read_project(candidate)
    return None


def paper_project_metadata(context):
    return {"journal": context["config"]["journal"], "sample_export": context["config"]["sample_export"]}


def paper_project_prefix(paper):
    doi = paper["doi"].strip().lower()
    readable = re.sub(r"[^a-z0-9]+", "_", doi).strip("_")[:90]
    suffix = hashlib.sha256(doi.encode("utf-8")).hexdigest()[:10]
    return f"paper_{readable}_{suffix}"


def paper_saved_in_project(context):
    """List supported categorization JSON anywhere inside the project, excluding metadata exports."""
    root = context["root"]
    saved = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [name for name in folders if name not in {".git", ".venv", "venv", "__pycache__", ".ipynb_checkpoints"}]
        for name in files:
            if not name.lower().endswith(".json"):
                continue
            path = Path(directory) / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(value, dict) or value.get("workflow") != "full_paper_categorization":
                    continue
                saved.append({"path": path, "relative_path": path.relative_to(root).as_posix(),
                              "paper_name": str(value.get("paper_name", path.stem)),
                              "doi": str(value.get("paper_metadata", {}).get("doi", "")).lower(),
                              "title": str(value.get("paper_metadata", {}).get("title", "")),
                              "modified": path.stat().st_mtime})
            except (OSError, ValueError, TypeError, AttributeError):
                continue
    return sorted(saved, key=lambda item: (-item["modified"], item["relative_path"]))


def paper_save_in_project(document, context, name=None, overwrite=False):
    # Re-read the manifest and folder constraint at save time, not a disabled UI field.
    current = paper_read_project(context["root"])
    document = dict(document, project_metadata=paper_project_metadata(current))
    return paper_save_files(document, current["save_directory"], name or document["paper_name"], overwrite)
