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
from copy import deepcopy

PAPER_CATEGORIES = (
    "Introduction", "Literature Review", "Theory", "Data", "Methods",
    "Results", "Discussion", "Conclusion", "Not categorizable",
)
PAPER_UNASSIGNED = "Unassigned"
PAPER_EXCLUDED = "Exclude from summary"
PAPER_LABELS = (PAPER_UNASSIGNED, *PAPER_CATEGORIES, PAPER_EXCLUDED)
PAPER_NUMBERED_TITLE = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+([^\W\d_].*)$", re.UNICODE)
PAPER_BARE_NUMBER = re.compile(r"^([1-9]\d?(?:\.[1-9]\d?){1,5})\.?$")
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
        bare = PAPER_BARE_NUMBER.fullmatch(title)
        if bare:
            headings.append({"title": title, "level": len(bare.group(1).split(".")), "line": index + 1})
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


def paper_partition(cleaned_text, headings, manual_boundaries=()):
    """Partition exact text offsets; virtual boundaries never add counted words."""
    text = normalize_newlines(cleaned_text)
    if not text.strip():
        raise ValueError("Paste or load paper text first.")
    lines = text.split("\n")
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line) + 1
    events, cursor = [], 0
    for heading in headings:
        if type(heading.get("level")) is not int or not 1 <= heading["level"] <= 6 or not isinstance(heading.get("title"), str):
            raise ValueError("Invalid heading level or title.")
        title = heading["title"].strip()
        if not title or "\n" in title or "\r" in title:
            raise ValueError("A heading must be a nonempty single line.")
        line = heading.get("line")
        if line is not None:
            if type(line) is not int or not cursor < line <= len(lines) or lines[line - 1].strip() != title:
                raise ValueError("Saved heading line does not match the cleaned text.")
            found = line - 1
        else:
            found = next((i for i in range(cursor, len(lines)) if lines[i].strip() == title), None)
        if found is None:
            raise ValueError(f"Heading not found in order on its own line: {title!r}. Copy its exact title from Cleaned paper.")
        events.append({"title": title, "level": heading["level"], "heading_line": found + 1,
                       "start": offsets[found], "body_start": offsets[found] + len(lines[found]), "virtual": False})
        cursor = found + 1
    for boundary in manual_boundaries:
        if (not isinstance(boundary, dict) or type(boundary.get("offset")) is not int
                or not 0 <= boundary["offset"] < len(text) or type(boundary.get("level")) is not int
                or not 1 <= boundary["level"] <= 6 or not isinstance(boundary.get("title"), str)
                or not boundary["title"].strip() or "\n" in boundary["title"] or "\r" in boundary["title"]):
            raise ValueError("Invalid selected-text boundary.")
        pos = boundary["offset"]
        if any(event["start"] <= pos <= event["body_start"] for event in events if not event["virtual"]):
            raise ValueError("A text boundary cannot overlap a heading. Select body text instead.")
        events.append({"title": boundary["title"], "level": boundary["level"], "heading_line": None,
                       "start": pos, "body_start": pos, "virtual": True})
    events.sort(key=lambda item: item["start"])
    if len({item["start"] for item in events}) != len(events):
        raise ValueError("Two boundaries cannot start at the same position.")
    units = []
    first = events[0]["start"] if events else len(text)
    if text[:first].strip():
        units.append({"title": "", "level": 0, "heading_line": None, "body": text[:first].strip(),
                      "start": 0, "body_start": 0, "end": first, "virtual": False})
    for index, event in enumerate(events):
        end = events[index + 1]["start"] if index + 1 < len(events) else len(text)
        units.append(dict(event, end=end, body=text[event["body_start"]:end].strip()))
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
                        paper_name="paper", source_text="", keep_hyphens=(), paper_metadata=None, project_metadata=None, custom_categories=None, manual_boundaries=None):
    text = normalize_newlines(cleaned_text)
    boundaries = deepcopy(manual_boundaries if manual_boundaries is not None else (previous or {}).get("manual_boundaries", []))
    if boundaries and previous and text != previous["cleaned_text"] and manual_boundaries is None:
        raise ValueError("Selected-text boundaries exist. Use the selection controls to edit headings, or remove text boundaries before editing the text.")
    custom = paper_validate_categories(custom_categories if custom_categories is not None else (previous or {}).get("custom_categories", []))
    headings = paper_parse_outline(outline_text)
    old_headings = [u for u in (previous or {}).get("units", []) if u["heading_line"] is not None]
    if previous and text == previous["cleaned_text"] and [h["title"] for h in headings] == [u["title"] for u in old_headings]:
        headings = [dict(h,line=u["heading_line"]) for h,u in zip(headings,old_headings)]
    units = paper_partition(text, headings, boundaries)
    # Match repeated headings in document order when rebuilding after an edit.
    labels = defaultdict(deque)
    if previous:
        for unit in previous["units"]:
            labels[unit["title"]].append(unit["category"])
    for unit in units:
        if labels[unit["title"]]:
            label = labels[unit["title"]].popleft()
            unit["category"] = label if label in paper_labels({"custom_categories":custom}) else PAPER_UNASSIGNED
    return {"schema_version": 1, "workflow": "full_paper_categorization", "paper_name": paper_name,
            "cleaned_text": text, "source_text": source_text, "keep_hyphens": sorted(set(keep_hyphens)),
            "include_heading_words": bool(include_heading_words), "units": units,
            "custom_categories": custom, "manual_boundaries": boundaries,
            "paper_metadata": dict(paper_metadata if paper_metadata is not None else (previous or {}).get("paper_metadata", {})),
            "project_metadata": dict(project_metadata if project_metadata is not None else (previous or {}).get("project_metadata", {}))}


def paper_unit_counts(unit, include_heading_words=True):
    body = count_text(unit["body"])
    return {"words": body["words"] + (len(WORD.findall(unit["title"])) if include_heading_words and not unit.get("virtual") else 0),
            "paragraphs": body["paragraphs"]}


def paper_summary(document):
    rows = {category: {"category": category, "section_titles": [], "subsection_titles": [], "words": 0, "paragraphs": 0}
            for category in paper_labels(document)}
    by_id = {unit["id"]: unit for unit in document["units"]}
    seen = {category: set() for category in paper_labels(document)}
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
    outline = [{"title": unit.get("title"), "level": unit.get("level"), "line": unit.get("heading_line")} for unit in saved if unit.get("heading_line") is not None]
    custom = paper_validate_categories(value.get("custom_categories", []))
    boundaries = value.get("manual_boundaries", [])
    if not isinstance(boundaries, list):
        raise ValueError("Invalid selected-text boundaries.")
    units = paper_partition(value["cleaned_text"], outline, boundaries)
    if len(saved) != len(units):
        raise ValueError("Saved section boundaries do not match the cleaned text.")
    for actual, expected in zip(saved, units):
        for field in ("id", "title", "level", "heading_line", "parent_id", "body"):
            if actual.get(field) != expected[field]:
                raise ValueError(f"Saved section structure does not match the cleaned text ({field}).")
        for field in ("start", "body_start", "end", "virtual"):
            if field in actual and actual[field] != expected[field]:
                raise ValueError("Saved text offsets do not match the cleaned text.")
        if actual.get("category") not in paper_labels({"custom_categories": custom}):
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
            "keep_hyphens": sorted(set(keep)), "include_heading_words": value["include_heading_words"], "units": units,
            "custom_categories": custom, "manual_boundaries": deepcopy(boundaries), **metadata}


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
    document = paper_set_categories(document, paper_project_categories(current))
    document = dict(document, project_metadata=paper_project_metadata(current))
    return paper_save_files(document, current["save_directory"], name or document["paper_name"], overwrite)


def paper_validate_categories(categories):
    if not isinstance(categories, (list, tuple)):
        raise ValueError("Custom categories must be a list of names.")
    names, seen = [], {name.casefold() for name in PAPER_LABELS}
    for value in categories:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(c in value for c in "\r\n\t"):
            raise ValueError("Use category names of 1–80 characters, one per line.")
        name = value.strip()
        if name.casefold() in seen:
            raise ValueError(f"Duplicate or reserved category name: {name}")
        names.append(name)
        seen.add(name.casefold())
    return names


def paper_categories(document=None):
    return (*PAPER_CATEGORIES[:-1], *(document or {}).get("custom_categories", []), PAPER_CATEGORIES[-1])


def paper_labels(document=None):
    return (PAPER_UNASSIGNED, *paper_categories(document), PAPER_EXCLUDED)


def paper_set_categories(document, categories):
    result = deepcopy(document)
    result["custom_categories"] = paper_validate_categories(categories)
    allowed = paper_labels(result)
    for unit in result["units"]:
        if unit["category"] not in allowed:
            unit["category"] = PAPER_UNASSIGNED
    return result


def paper_select_range(document, start, end, category, title="Selected text", level=1):
    """Create virtual section boundaries around selected body text; preserve all prose."""
    document = paper_validate_document(document)
    text = document["cleaned_text"]
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or not text[start:end].strip():
        raise ValueError("Select body text in Cleaned paper first.")
    if category not in paper_labels(document):
        raise ValueError("Choose a valid category.")
    if any(unit["heading_line"] is not None and start < unit["body_start"] and end > unit["start"] for unit in document["units"]):
        raise ValueError("Select body text without heading lines, or assign the existing section using its dropdown.")
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end-1].isspace():
        end -= 1
    # Cutting a token would count fragments as separate words.
    for pos in (start, end):
        if any(match.start() < pos < match.end() for match in WORD.finditer(text)):
            raise ValueError("Select complete words so counts remain accurate.")
    old = document["units"]
    boundaries = deepcopy(document["manual_boundaries"])
    for pos, name in ((start, title.strip() or "Selected text"), (end, "Unheaded text")):
        next_heading = next((u["start"] for u in old if u["heading_line"] is not None and u["start"] >= pos), len(text))
        if pos < len(text) and text[pos:next_heading].strip() and not any(unit["start"] == pos for unit in old):
            boundaries.append({"offset": pos, "title": name, "level": level})
    headings = [{"title": u["title"], "level": u["level"], "line": u["heading_line"]} for u in old if u["heading_line"] is not None]
    units = paper_partition(text, headings, boundaries)
    for unit in units:
        previous = next((u for u in old if u["start"] <= unit["start"] < u["end"]), None)
        unit["category"] = category if start <= unit["start"] < end else (previous["category"] if previous else PAPER_UNASSIGNED)
    document.update(units=units, manual_boundaries=boundaries)
    return document


def paper_edit_heading(document, start, end, level=None):
    """Mark a selection as a real heading, change its level, or remove boundaries.

    Removing a heading retains its exact words as body text and resets the merged
    section to Unassigned so an old category cannot silently cover different prose.
    """
    document = paper_validate_document(document)
    text = document["cleaned_text"]
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(text):
        raise ValueError("Select text or place the cursor in a heading first.")
    hits = [u for u in document["units"] if (u["start"] <= start < u["end"] if start == end else u["start"] < end and u["end"] > start)]
    if level is None:
        removed = {u["id"] for u in hits if u["level"]}
        if not removed:
            raise ValueError("The selection has no heading or text boundary to remove.")
        headings = [{"title": u["title"], "level": u["level"], "line": u["heading_line"]} for u in document["units"] if u["heading_line"] is not None and u["id"] not in removed]
        boundaries = [b for b in document["manual_boundaries"] if not any(u["id"] in removed and u["start"] == b["offset"] for u in document["units"])]
        units = paper_partition(text, headings, boundaries)
        for unit in units:
            covered = [old for old in document["units"] if old["start"] < unit["end"] and old["end"] > unit["start"]]
            if len(covered) == 1 and covered[0]["id"] not in removed:
                unit["category"] = covered[0]["category"]
        document.update(units=units, manual_boundaries=boundaries)
        return document
    if type(level) is not int or not 1 <= level <= 6:
        raise ValueError("Heading levels must be between 1 and 6.")
    # An existing virtual/real section can be reassigned without changing text.
    existing = next((u for u in hits if u["level"] and (start == end or (u["heading_line"] is not None and end <= u["body_start"]))), None)
    if existing:
        headings = [{"title": u["title"], "line": u["heading_line"], "level": level if u["id"] == existing["id"] else u["level"]} for u in document["units"] if u["heading_line"] is not None]
        boundaries = [dict(b, level=level) if b["offset"] == existing["start"] else b for b in document["manual_boundaries"]]
        units = paper_partition(text, headings, boundaries)
        for old, new in zip(document["units"], units):
            new["category"] = old["category"]
        document.update(units=units, manual_boundaries=boundaries)
        return document
    selected = text[start:end].strip()
    if not selected or "\n" in selected or len(selected) > 200:
        raise ValueError("Select a single heading title of at most 200 characters.")
    left = start + len(text[start:end]) - len(text[start:end].lstrip())
    right = left + len(selected)
    if any(u["heading_line"] is not None and left < u["body_start"] and right > u["start"] for u in document["units"]):
        raise ValueError("Select the complete heading to change its level.")
    if any(match.start() < pos < match.end() for pos in (left,right) for match in WORD.finditer(text)):
        raise ValueError("Select complete words for a heading.")
    before, after = text[:left], text[right:]
    prefix = "" if not before or before.endswith("\n") else "\n\n"
    suffix = "" if not after or after.startswith("\n") else "\n\n"
    new_text = before + prefix + selected + suffix + after
    shift = len(prefix) + len(suffix)
    # Relocate existing boundaries/headings by exact offset, including duplicate titles.
    boundaries = [dict(b, offset=b["offset"] + (shift if b["offset"] >= right else len(prefix) if b["offset"] >= left else 0))
                  for b in document["manual_boundaries"] if not left <= b["offset"] < right]
    events = [(u["start"] + (shift if u["start"] >= right else 0), {"title":u["title"],"level":u["level"]})
              for u in document["units"] if u["heading_line"] is not None]
    events.append((left + len(prefix), {"title":selected,"level":level}))
    units = paper_partition(new_text, [dict(h,line=new_text.count("\n",0,pos)+1) for pos,h in sorted(events,key=lambda pair:pair[0])], boundaries)
    for unit in units:
        old_pos = unit["start"] - (shift if unit["start"] >= right + shift else len(prefix) if unit["start"] >= left else 0)
        old = next((u for u in document["units"] if u["start"] <= old_pos < u["end"]), None)
        if old:
            unit["category"] = old["category"]
    document.update(cleaned_text=new_text, units=units, manual_boundaries=boundaries)
    return document


def paper_project_categories(context):
    path = context["save_directory"] / "categories.json"
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise ValueError("Category settings must be a regular project file.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Invalid project category settings.")
    return paper_validate_categories(value.get("custom_categories"))


def paper_update_project_categories(context, categories):
    """Atomically publish settings and recategorized saved papers, with rollback."""
    context = paper_read_project(context["root"])
    paper_project_categories(context)  # Validate the existing settings before replacing any files.
    categories = paper_validate_categories(categories)
    files, times, changed = {}, {}, 0
    for item in paper_saved_in_project(context):
        original = paper_validate_document(json.loads(item["path"].read_text(encoding="utf-8-sig")))
        updated = paper_set_categories(original, categories)
        changed += sum(a["category"] != b["category"] for a, b in zip(original["units"], updated["units"]))
        stat = item["path"].stat()
        times[item["path"]] = (stat.st_atime_ns,stat.st_mtime_ns)
        files[item["path"]] = json.dumps(paper_export_document(updated), ensure_ascii=False, indent=2) + "\n"
    context["save_directory"].mkdir(parents=True, exist_ok=True)
    files[context["save_directory"] / "categories.json"] = json.dumps({"schema_version": 1, "custom_categories": categories}, ensure_ascii=False, indent=2) + "\n"
    with tempfile.TemporaryDirectory(prefix=".categories-", dir=context["root"]) as temporary:
        stage = Path(temporary)
        backups, published = {}, []
        try:
            for i, (path, content) in enumerate(files.items()):
                (stage / str(i)).write_text(content, encoding="utf-8")
                if path in times:
                    os.utime(stage / str(i),ns=times[path])
            for i, path in enumerate(files):
                if path.exists():
                    backups[path] = stage / ("previous-" + str(i))
                    path.replace(backups[path])
                (stage / str(i)).replace(path)
                published.append(path)
        except BaseException:
            for path in published:
                path.unlink()
            for path, backup in backups.items():
                backup.replace(path)
            raise
    return changed


def paper_project_summary(context):
    """Latest saved categorization per sampled DOI; never count multiple versions."""
    categories = paper_project_categories(context)
    empty = paper_summary({"units": [], "custom_categories": categories})
    saved = paper_saved_in_project(context)
    papers, errors = [], []
    for paper in context["papers"]:
        item = next((s for s in saved if s["doi"] == paper["doi"]), None)
        entry = {"paper": paper, "status": "Not saved", "rows": None, "path": None}
        if item:
            try:
                doc = paper_validate_document(json.loads(item["path"].read_text(encoding="utf-8-sig")))
                doc = paper_set_categories(doc, categories)
                rows = paper_summary(doc)
                remaining = sum(u["category"] == PAPER_UNASSIGNED for u in doc["units"])
                entry.update(rows=rows, path=item["path"], status=f"{remaining} unassigned" if remaining else "Complete")
                for category, row in rows.items():
                    for key in ("section_titles", "subsection_titles"):
                        empty[category][key].extend(f"{paper['sample_number']}. {title}" for title in row[key])
                    for key in ("words", "paragraphs"):
                        empty[category][key] += row[key]
            except (OSError, ValueError, TypeError, KeyError) as error:
                entry["status"] = "Invalid saved JSON"
                errors.append(f"{item['relative_path']}: {error}")
        papers.append(entry)
    return {"rows": empty, "papers": papers, "errors": errors, "custom_categories": categories}
