"""Journal-agnostic Crossref metadata, random sampling and project creation.

Use create_journal_analysis.ipynb as the interactive entry point.
The backend uses only the Python standard library.
"""
from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import random
import re
import secrets
import shutil
import ssl
import sys
import tempfile
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, unquote, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

# Increment with the required version in the project notebook when its backend API changes.
PROJECT_NOTEBOOK_API_VERSION = 2

FIELDS = (
    "bibtex_key", "doi", "title", "authors", "journal", "year", "volume",
    "issue", "pages", "article_number", "publication_date", "date_source",
    "date_precision", "published_online", "published_print", "issn",
    "publisher", "url", "abstract",
)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag.split(":")[-1] in {"p", "br", "sec", "title"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag.split(":")[-1] in {"p", "sec", "title"}:
            self.parts.append(" ")


def plain_text(value):
    parser = PlainText()
    parser.feed(str(value or ""))
    return " ".join(unescape("".join(parser.parts)).split())


def months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def metadata_date(item, field):
    parts = item.get(field, {}).get("date-parts", [[]])[0]
    if not parts:
        return None
    try:
        # Preserve the supplied precision in output; first day is used only for filtering.
        day = date(parts[0], parts[1] if len(parts) > 1 else 1,
                   parts[2] if len(parts) > 2 else 1)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field} date for {item.get('DOI')}: {parts}")
    precision = ("year", "month", "day")[min(len(parts), 3) - 1]
    return day, day.isoformat()[:(4, 7, 10)[min(len(parts), 3) - 1]], precision


def publication_date(item, basis):
    if basis != "first":
        field = f"published-{basis}"
        parsed = metadata_date(item, field)
        return (*parsed, field) if parsed else None
    candidates = []
    for field in ("published-online", "published-print", "published", "issued"):
        parsed = metadata_date(item, field)
        if parsed:
            candidates.append((*parsed, field))
    return min(candidates, key=lambda value: value[0]) if candidates else None


def tls_context():
    # Use a current CA bundle when installed, independently of the host Python.
    try:
        import certifi
    except ImportError:
        context = ssl.create_default_context()
    else:
        context = ssl.create_default_context(cafile=certifi.where())
    # python.org macOS builds can lack their own CA bundle. Keep verification on
    # and additionally load the operating system's CA certificates when available.
    system_bundle = Path("/etc/ssl/cert.pem")
    if system_bundle.is_file():
        context.load_verify_locations(cafile=str(system_bundle))
    return context


def get_json(url, email=None):
    agent = "JournalAnalysisTools/1.0"
    if email:
        agent += f" (mailto:{email})"
    request = Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=60, context=tls_context()) as response:
                payload = json.load(response)
            if payload.get("status") != "ok":
                raise ValueError(f"Crossref returned an unsuccessful response: {payload}")
            return payload["message"]
        except HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code <= 599:
                raise
            try:
                delay = min(60, max(1, float(exc.headers.get("Retry-After", 2 ** attempt))))
            except ValueError:
                delay = 2 ** attempt
            error = exc
        except (URLError, TimeoutError) as exc:
            error, delay = exc, 2 ** attempt
        if attempt == 4:
            raise RuntimeError(f"Crossref request failed after 5 attempts: {error}") from error
        print(f"Request failed; retrying in {delay:g}s: {error}", file=sys.stderr)
        time.sleep(delay)


def fetch_records(journal, start, end, basis="first", email=None, page_size=500):
    validate_window(start, end, basis)
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")
    date_filter = {"first": "pub-date", "online": "online-pub-date",
                   "print": "print-pub-date"}[basis]
    records, queries = [], []
    for issn in journal.issns:
        params = {
            "filter": f"type:journal-article,from-{date_filter}:{start},until-{date_filter}:{end}",
            "rows": page_size,
            "cursor": "*",
        }
        if email:
            params["mailto"] = email
        cursors = set()
        count = 0
        while True:
            url = f"https://api.crossref.org/journals/{issn}/works?{urlencode(params)}"
            try:
                message = get_json(url, email)
            except HTTPError as exc:
                if exc.code != 404 or count:
                    raise
                queries.append({"issn": issn, "url": url, "status": "not indexed (404)"})
                break
            items = message["items"]
            if count == 0:
                queries.append({"issn": issn, "url": url,
                                "total_results": message["total-results"]})
            records.extend(items)
            count += len(items)
            print(f"ISSN {issn}: fetched {count} / {message['total-results']}", file=sys.stderr)
            if len(items) < page_size:
                if count < message["total-results"]:
                    raise RuntimeError("Crossref returned fewer records than advertised; no exports written.")
                break
            cursor = message.get("next-cursor")
            if not cursor or cursor in cursors:
                raise RuntimeError("Crossref pagination stopped prematurely; no exports written.")
            cursors.add(cursor)
            params["cursor"] = cursor
            time.sleep(0.2)
        time.sleep(0.2)
    if not any("total_results" in query for query in queries):
        raise ValueError("None of the journal ISSNs are indexed by Crossref.")
    return records, queries


def normalize(records, journal, start, end, basis="first"):
    validate_window(start, end, basis)
    by_doi = {}
    outside = 0
    for item in records:
        if item.get("type") != "journal-article" or not set(item.get("ISSN", [])) & set(journal.issns):
            raise ValueError(f"Unexpected journal/type in API record: {item.get('DOI')}")
        doi = str(item.get("DOI", "")).strip().lower()
        if not doi:
            raise ValueError("A record lacks a DOI; cannot guarantee matching exports.")
        selected = publication_date(item, basis)
        if not selected:
            raise ValueError(f"No {basis} publication date for {doi}")
        if not start <= selected[0] <= end:
            outside += 1
            continue
        # Prefer the richer record when the same DOI appears more than once.
        if doi not in by_doi or len(json.dumps(item)) > len(json.dumps(by_doi[doi])):
            by_doi[doi] = item
    rows = [_record_row(item, doi, journal.name, basis) for doi, item in by_doi.items()]
    rows.sort(key=lambda row: (row["publication_date"], row["doi"]), reverse=True)
    if len({row["bibtex_key"] for row in rows}) != len(rows):
        raise ValueError("BibTeX key collision; no exports written.")
    return rows, outside


def _record_row(item, doi, journal_name, basis="first"):
    selected = publication_date(item, basis)
    if not selected:
        raise ValueError(f"No {basis} publication date for {doi}")
    online, printed = metadata_date(item, "published-online"), metadata_date(item, "published-print")
    title = plain_text(" ".join(item.get("title", [])))
    if not title:
        raise ValueError(f"Missing title for {doi}")
    authors = []
    for author in item.get("author", []):
        family, given = plain_text(author.get("family")), plain_text(author.get("given"))
        name = f"{family}, {given}" if family and given else family or given
        if not name:
            name = plain_text(author.get("name"))
            if name:
                name = "{" + name + "}"  # BibTeX corporate author.
        if not name:
            raise ValueError(f"Unusable author metadata for {doi}")
        authors.append(name)
    return {
        "bibtex_key": slugify(journal_name).replace("-", "_") + "_" + re.sub(r"[^a-z0-9]+", "_", doi).strip("_"),
        "doi": doi, "title": title, "authors": " and ".join(authors),
        "journal": plain_text(" ".join(item.get("container-title", []))) or journal_name,
        "year": str((printed or selected)[0].year), "volume": item.get("volume", ""),
        "issue": item.get("issue", ""), "pages": item.get("page", ""),
        "article_number": item.get("article-number", ""),
        "publication_date": selected[1], "date_source": selected[3], "date_precision": selected[2],
        "published_online": online[1] if online else "",
        "published_print": printed[1] if printed else "",
        "issn": "; ".join(item.get("ISSN", [])), "publisher": plain_text(item.get("publisher")),
        "url": "https://doi.org/" + quote(doi, safe="/"),
        "abstract": plain_text(item.get("abstract")),
    }


def bibtex_escape(value):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
                    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                    "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(char, char) for char in str(value))


def render_bibtex(rows):
    entries = []
    mapping = {"bibtex_key": None, "authors": "author", "issue": "number",
               "article_number": "eid"}
    for row in rows:
        lines = [f"@article{{{row['bibtex_key']},"]
        for source in FIELDS:
            field = mapping.get(source, source)
            value = row[source]
            if field is None or value == "":
                continue
            if field in {"doi", "url"}:
                # Verbatim identifier fields: do not turn DOI underscores into '\\_'.
                escaped = str(value)
                if any(char in escaped for char in "{}\\\n\r"):
                    raise ValueError(f"Unsupported character in {field}: {escaped}")
            elif field == "author":
                escaped = " and ".join(
                    "{" + bibtex_escape(name[1:-1]) + "}" if name.startswith("{") and name.endswith("}")
                    else bibtex_escape(name) for name in str(value).split(" and ")
                )
            else:
                escaped = bibtex_escape(value)
                if field == "pages":
                    escaped = re.sub(r"(?<=\d)[-–](?=\d)", "--", escaped)
                if field == "title":
                    escaped = "{" + escaped + "}"  # Protect capitalization.
            lines.append(f"  {field} = {{{escaped}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + ("\n" if entries else "")


def export(rows, output_dir, stem, report, raw_records):
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    csv_text, bib_text = csv_buffer.getvalue(), render_bibtex(rows)
    # Check the actual serialized exports, including order and uniqueness.
    csv_rows = list(csv.DictReader(io.StringIO(csv_text)))
    bib_ids = re.findall(r"^  doi = \{([^\n]+)\},$", bib_text, re.MULTILINE)
    bib_keys = re.findall(r"^@article\{([^,]+),$", bib_text, re.MULTILINE)
    if [row["doi"] for row in csv_rows] != bib_ids or [row["bibtex_key"] for row in csv_rows] != bib_keys:
        raise ValueError("CSV/BibTeX identity verification failed; no exports written.")
    output_dir.mkdir(parents=True, exist_ok=True)
    content = {
        ".csv": "\ufeff" + csv_text,  # UTF-8 BOM helps Excel recognize accents.
        ".bib": bib_text,
        "_report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        "_crossref.json": json.dumps(raw_records, ensure_ascii=False, indent=2) + "\n",
    }
    # Render and validate everything before replacing any existing output.
    with tempfile.TemporaryDirectory(dir=output_dir) as temporary:
        for suffix, text in content.items():
            Path(temporary, stem + suffix).write_text(text, encoding="utf-8", newline="")
        for suffix in content:
            Path(temporary, stem + suffix).replace(output_dir / (stem + suffix))



def canonical_issn(value):
    compact = re.sub(r"[\s-]", "", str(value)).upper()
    if not re.fullmatch(r"\d{7}[\dX]", compact):
        raise ValueError(f"Invalid ISSN format: {value!r}")
    digits = [int(char) if char != "X" else 10 for char in compact]
    if sum(number * weight for number, weight in zip(digits, range(8, 0, -1))) % 11:
        raise ValueError(f"Invalid ISSN checksum: {value!r}")
    return compact[:4] + "-" + compact[4:]


@dataclass(frozen=True)
class Journal:
    name: str
    issns: tuple[str, ...]

    def __post_init__(self):
        name = self.name.strip()
        if not name:
            raise ValueError("A journal name is required.")
        issns = tuple(dict.fromkeys(canonical_issn(value) for value in self.issns))
        if not issns:
            raise ValueError("At least one ISSN is required.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "issns", issns)


def find_journals(query, email=None, limit=10):
    """Find candidates by title, or resolve an exact ISSN; never pick a fuzzy match."""
    query = query.strip()
    if not query:
        raise ValueError("Enter a journal title or ISSN.")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if re.fullmatch(r"\d{4}-?\d{3}[\dXx]", query):
        issn = canonical_issn(query)
        message = get_json(f"https://api.crossref.org/journals/{issn}", email)
        items = [dict(message, ISSN=list(dict.fromkeys([issn, *message.get("ISSN", [])])))]
    else:
        params = {"query": query, "rows": limit}
        if email:
            params["mailto"] = email
        items = get_json("https://api.crossref.org/journals?" + urlencode(params), email)["items"]
    journals = []
    for item in items:
        if item.get("title") and item.get("ISSN"):
            candidate = Journal(plain_text(item["title"]), tuple(item["ISSN"]))
            if candidate not in journals:
                journals.append(candidate)
    return journals


def slugify(value):
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:64].rstrip("-") or "journal"


def validate_window(start, end, basis):
    if type(start) is not date or type(end) is not date:
        raise ValueError("Choose valid start and end dates.")
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    if basis not in {"first", "online", "print"}:
        raise ValueError("date_basis must be first, online or print")


NOTICE_TITLE = re.compile(
    r"^(?:(?:guest |managing |from the )?editorials?|editor(?:'s|s’|’s) (?:note|introduction)|"
    r"corrigendum|corrigenda|correction(?: to|:|$)|erratum|errata|retraction|withdrawal|"
    r"publisher.s note|acknowledg(?:e)?ments?|reviewer acknowledg|"
    r"front[\s-]*matter|back[\s-]*matter|cover(?: page| image)?(?=$|\s*:)|"
    r"table of contents|contents(?:$|:)|index(?=$|\s*(?::|to volume|to issue))|author index|subject index|"
    r"masthead|imprint|copyright|permissions|instructions (?:to|for) authors|"
    r"information for (?:authors|contributors)|call for papers|announcement|"
    r"obituar(?:y|ies)|in memoriam|book review|books received|preface|foreword|"
    r"(?:an? |introduction to (?:the )?)?special issue)\b", re.IGNORECASE,
)
NOTICE_FILTER_NOTE = (
    "Exclude non-scientific items using publisher article-type metadata when available "
    "and a title heuristic for editorials, front/back matter, notices, corrections, "
    "contents, covers, book reviews and similar material. Full exports retain excluded "
    "records; selection reports list the DOI, title and reason. Review publisher metadata."
)


def non_scientific_reason(record):
    """Use explicit publisher labels and conservative title prefixes, never subjects."""
    labels = []
    for key in ("subtype", "article-type", "article_type"):
        value = record.get(key, "")
        labels.extend(value if isinstance(value, list) else [value])
    for item in record.get("assertion", []) or []:
        if isinstance(item, dict) and re.search(r"article.?type|content.?type", str(item.get("name", "")) + " " + str(item.get("label", "")), re.I):
            labels.append(item.get("value", ""))
    for value in labels:
        label = re.sub(r"[-_]", " ", plain_text(str(value))).strip()
        if NOTICE_TITLE.search(label):
            return "Publisher article type: " + label
    title = plain_text(" ".join(record.get("title", [])))
    if NOTICE_TITLE.search(title):
        return "Non-scientific title: " + title
    return ""


def sample_rows(rows, count, seed=None, include_notices=False):
    """Draw distinct DOIs uniformly; sort the population so a seed survives reordering."""
    if type(count) is not int or count < 1:
        raise ValueError("Number of papers must be an integer of at least 1.")
    if seed is not None and type(seed) is not int:
        raise ValueError("Seed must be an integer or None.")
    for field in ("doi", "bibtex_key"):
        values = [row[field].strip().lower() for row in rows]
        if any(not value for value in values) or len(set(values)) != len(values):
            raise ValueError(f"Source has empty or duplicate {field} values.")
    excluded = [row for row in rows if NOTICE_TITLE.search(row["title"])]
    eligible = [row for row in rows if not NOTICE_TITLE.search(row["title"])]
    if count > len(eligible):
        raise ValueError(f"Requested {count} papers, but only {len(eligible)} are eligible ({len(rows)} total).")
    seed = seed if seed is not None else secrets.randbits(64)
    selected = random.Random(seed).sample(sorted(eligible, key=lambda row: row["doi"]), count)
    report = {
        "source_entry_count": len(rows), "eligible_entry_count": len(eligible),
        "include_notices": False, "notice_filter": NOTICE_FILTER_NOTE,
        "excluded_notices": [{"doi": row["doi"], "title": row["title"], "reason": "Non-scientific title"} for row in excluded],
        "selected_entry_count": count, "seed": seed,
        "sampling": "uniform random sample without replacement; population sorted by DOI",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_dois": [row["doi"] for row in selected],
        "selected_bibtex_keys": [row["bibtex_key"] for row in selected],
    }
    return selected, report


def write_selection(rows, output_dir, stem, report):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    csv_text, bib_text = buffer.getvalue(), render_bibtex(rows)
    serialized = list(csv.DictReader(io.StringIO(csv_text)))
    dois = re.findall(r"^  doi = \{([^\n]+)\},$", bib_text, re.MULTILINE)
    keys = re.findall(r"^@article\{([^,]+),$", bib_text, re.MULTILINE)
    if ([row["doi"] for row in serialized] != dois
            or [row["bibtex_key"] for row in serialized] != keys):
        raise ValueError("Selection CSV/BibTeX identity verification failed.")
    report = dict(report, matching_dois_and_keys_verified=True)
    for suffix, text in {
        ".csv": "\ufeff" + csv_text,
        ".bib": bib_text,
        "_selection.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    }.items():
        (output_dir / (stem + suffix)).write_text(text, encoding="utf-8", newline="")


def project_folder_name(journal, start, end, created_on=None):
    created_on = created_on or datetime.now(ZoneInfo("Europe/Zurich")).date()
    return f"{created_on:%d%m%Y}_journalanalysis_{slugify(journal.name)}_{start}_{end}"


def _prepare_project(projects_root, name, template_path=None):
    projects_root = Path(projects_root).expanduser().resolve()
    if not projects_root.is_dir():
        raise ValueError("Projects root must be an existing directory.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", name):
        raise ValueError("Project folder name must be a single name using letters, digits, dots, underscores or hyphens.")
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(1, 10)}
    if name.endswith('.') or name.split('.')[0].upper() in reserved:
        raise ValueError("Choose a folder name that works on Windows and macOS: avoid trailing dots and reserved names such as CON, NUL or COM1.")
    destination = projects_root / name
    if destination.exists():
        raise FileExistsError(f"Project already exists: {destination}. Choose a different project folder name.")
    template_path = Path(template_path) if template_path else Path(__file__).resolve().parent.parent / "clean_and_count_text.ipynb"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    # Clear saved widget/editor state before making a project-local copy.
    template.get("metadata", {}).pop("widgets", None)
    for cell in template["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    return projects_root, destination, template


def create_project(journal, start, end, count, projects_root, *, date_basis="first",
                   seed=None, include_notices=False, email=None, project_name=None,
                   input_json=None, template_path=None):
    """Fetch, validate and sample before creating a fresh analysis project.

    Existing directories are never reused. input_json replays saved Crossref
    records without a network request. PDFs must be obtained separately.
    """
    validate_window(start, end, date_basis)
    # Validate count/seed before requesting metadata.
    if type(count) is not int or count < 1:
        raise ValueError("Number of papers must be an integer of at least 1.")
    if seed is not None and type(seed) is not int:
        raise ValueError("Seed must be an integer or None.")
    name = project_folder_name(journal, start, end) if project_name is None else project_name
    projects_root, destination, template = _prepare_project(projects_root, name, template_path)
    if input_json is None:
        records, queries = fetch_records(journal, start, end, date_basis, email)
    else:
        records = json.loads(Path(input_json).read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("Input JSON must be a list of Crossref work records.")
        queries = []
    rows, outside = normalize(records, journal, start, end, date_basis)
    reasons = {}
    for record in records:
        reason = non_scientific_reason(record)
        if reason:
            reasons[str(record.get("DOI", "")).strip().lower()] = reason
    eligible = [row for row in rows if not reasons.get(row["doi"])]
    if count > len(eligible):
        raise ValueError(f"Requested {count} papers, but only {len(eligible)} are eligible ({len(rows)} total).")
    selected, selection_report = sample_rows(eligible, count, seed)
    excluded = [{"doi": row["doi"], "title": row["title"], "reason": reasons[row["doi"]]} for row in rows if reasons.get(row["doi"])]
    selection_report["source_entry_count"] = len(rows)
    selection_report["excluded_notices"] = excluded + selection_report["excluded_notices"]
    stem = f"{slugify(journal.name)}_{start}_{end}" + (f"_{date_basis}" if date_basis != "first" else "")
    sample_stem = f"{stem}_random{count}"
    created_at = datetime.now(timezone.utc).isoformat()
    config = {
        "schema_version": 1, "journal": journal.name, "issns": list(journal.issns),
        "start_date": str(start), "end_date": str(end), "date_basis": date_basis,
        "sample_size": count, "seed": selection_report["seed"], "include_notices": False,
        "created_at_utc": created_at, "full_export": f"output/{stem}.csv",
        "sample_export": f"output/{sample_stem}.csv",
    }
    report = {
        **config, "queries": queries, "retrieved_at_utc": created_at,
        "source": "Crossref publisher-deposited metadata",
        "replayed_from": str(Path(input_json).resolve()) if input_json else None,
        "raw_record_count": len(records), "out_of_window_record_count": outside,
        "entry_count": len(rows), "matching_dois_and_keys_verified": True,
        "records_without_authors": sum(not row["authors"] for row in rows),
        "records_without_abstracts": sum(not row["abstract"] for row in rows),
        "records_with_partial_dates": sum(row["date_precision"] != "day" for row in rows),
        "coverage_note": "All matching Crossref journal-article records; completeness depends on publisher deposits.",
    }
    return _write_project(destination, template, config, rows, selected, selection_report, records, report, journal)


def _write_project(destination, template, config, rows, selected, selection_report, records, report, journal=None):
    """Publish either selection mode with the same transactional folder/export checks."""
    projects_root, name = destination.parent, destination.name
    stem = Path(config["full_export"]).stem
    sample_stem = Path(config["sample_export"]).stem
    manual = config.get("selection_method") == "manual"
    selection_note = (f"Manually selected {len(selected)} papers. No random sampling was applied."
                      if manual else f"Selected {len(selected)} papers from {selection_report['eligible_entry_count']} eligible records "
                      f"({len(rows)} total). Random seed: `{selection_report['seed']}`.")
    readme = (
        f"# {config['journal']} journal analysis\n\n"
        f"Date range: **{config['start_date']} through {config['end_date']}**, inclusive. "
        f"Publication basis: **{config['date_basis']}**.\n\n{selection_note}\n\n"
        "- `project.json`: configuration and selection provenance.\n"
        "- `output/`: matching CSV/BibTeX exports, selected papers, raw metadata and reports.\n"
        "- `clean_and_count_text.ipynb`: self-contained cleaning, counting and full-paper categorization notebook.\n\n"
        "Open the text-cleaning notebook in Jupyter and run all cells. Choose Clean & count (original) "
        "for the existing workflow, or Categorize full paper to label sections. Above the tabs, select this project; "
        "the paper selector at the top of the full-paper tab reads its selected papers. Use Start / reopen paper, or Associate current text "
        "for a paper already pasted. Save cleaned text and reloadable categorization JSON into this project's "
        "paper_categorizations/ folder. Saved JSON lists existing categorizations throughout the project. "
        "Mark headings or select body text to assign categories directly. Manage project categories above the tabs; "
        "removing a custom category resets its assignments to Unassigned in all saved papers. "
        "The Project summary tab totals the latest saved JSON per paper and shows missing or incomplete papers. "
        "Editorials, front/back matter and similar non-scientific articles are excluded from project selections. "
        "Choose your own folders and files for PDFs and analysis results. PDFs are not downloaded. "
        "Crossref metadata needs human review. The first-publication rule uses the earliest known online, "
        "print, published or issued date. Partial dates use the first day for filtering and retain their precision in exports.\n"
    )
    if manual:
        readme += "\nJournals: " + "; ".join(item["name"] for item in config["journals"]) + ".\n"
        if len(config["journals"]) > 1:
            readme += "Warning: this manual selection contains papers from multiple journals.\n"
    # Build in a hidden sibling directory. Failed writes do not leave a partial project.
    with tempfile.TemporaryDirectory(prefix=".journal-analysis-", dir=projects_root) as temporary:
        staging = Path(temporary) / name
        staging.mkdir()
        output = staging / "output"
        export(rows, output, stem, report, records)
        write_selection(selected, output, sample_stem, dict(selection_report, source_csv=config["full_export"]))
        (staging / "project.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "clean_and_count_text.ipynb").write_text(json.dumps(template, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (staging / "README.md").write_text(readme, encoding="utf-8")
        destination.mkdir(exist_ok=False)
        try:
            for child in staging.iterdir():
                child.rename(destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return {"path": destination, "journal": journal, "rows": rows,
            "selected": selected, "selection_report": selection_report, "config": config}


def normalize_doi(value):
    """Accept a bare DOI or DOI resolver URL without guessing away suffix punctuation."""
    value = str(value).strip()
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    if re.match(r"^(?:dx\.|www\.)?doi\.org/", value, re.IGNORECASE):
        value = "https://" + value
    if re.match(r"^https?://", value, re.IGNORECASE):
        parts = urlsplit(value)
        if parts.hostname is None or parts.hostname.lower() not in {"doi.org", "dx.doi.org", "www.doi.org"}:
            raise ValueError("Use a DOI or a doi.org URL, not a publisher webpage.")
        value = unquote(parts.path.lstrip("/"))
    if not re.fullmatch(r"10\.\d{4,9}/[^\s\x00-\x1f\x7f]+", value, flags=re.IGNORECASE):
        raise ValueError("Enter a DOI such as 10.1234/example or https://doi.org/10.1234/example.")
    return value.lower()


def manual_record_row(record):
    if not isinstance(record, dict) or record.get("type") != "journal-article":
        raise ValueError("The DOI must identify a journal article in Crossref.")
    reason = non_scientific_reason(record)
    if reason:
        raise ValueError("Excluded non-scientific article: " + reason)
    doi = normalize_doi(record.get("DOI", ""))
    journal_name = plain_text(" ".join(record.get("container-title", [])))
    if not journal_name:
        raise ValueError(f"Missing journal name for {doi}; this record cannot be used in a journal project.")
    return _record_row(record, doi, journal_name)


def lookup_doi(value, cache=None, email=None):
    """Preload the full Crossref record and validate export metadata once per DOI."""
    doi = normalize_doi(value)
    if cache is not None and doi in cache:
        record = deepcopy(cache[doi])
    else:
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        if email:
            url += "?" + urlencode({"mailto": email})
        try:
            record = get_json(url, email)
        except HTTPError as error:
            if error.code == 404:
                raise ValueError(f"DOI not found in Crossref: {doi}") from error
            raise
    row = manual_record_row(record)
    if row["doi"] != doi:
        raise ValueError(f"Crossref returned a different DOI for {doi}; no paper was selected.")
    if cache is not None:
        cache[doi] = deepcopy(record)
    return deepcopy(record)


def check_dois(text, cache=None, email=None):
    """Check all unique newline-separated DOIs; keep successful lookups for retries."""
    cache = {} if cache is None else cache
    entries, errors, duplicates, seen = [], [], [], set()
    for number, raw in enumerate(str(text).splitlines(), 1):
        if not raw.strip():
            continue
        try:
            doi = normalize_doi(raw)
        except ValueError as error:
            errors.append({"line": number, "input": raw, "error": str(error)})
            continue
        if doi in seen:
            duplicates.append(doi)
            continue
        seen.add(doi)
        entries.append((number, raw, doi))
    def check(entry):
        number, raw, doi = entry
        try:
            # New lookups use their own cache; only this caller updates the shared cache.
            record = lookup_doi(doi, {doi: cache[doi]} if doi in cache else None, email)
            return record, None
        except Exception as error:
            return None, {"line": number, "input": raw, "error": str(error)}
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for record, error in pool.map(check, entries):
            if error:
                errors.append(error)
            else:
                records.append(record)
                cache[normalize_doi(record["DOI"])] = deepcopy(record)
    return {"records": records, "errors": sorted(errors, key=lambda item: item["line"]), "duplicates": duplicates}


def manual_overview(records):
    """Summarize explicit choices; retain input order and merge journal ISSN aliases."""
    rows, unique, seen, journals = [], [], set(), []
    for record in records:
        row = manual_record_row(record)
        if row["doi"] in seen:
            continue
        seen.add(row["doi"])
        rows.append(row)
        unique.append(record)
        identifiers = set(record.get("ISSN", []))
        matches = [item for item in journals if row["journal"].casefold() in
                   {name.casefold() for name in [item["name"], *item["aliases"]]}
                   or identifiers.intersection(item["issns"])]
        if matches:
            group = matches[0]
            for other in matches[1:]:
                group["paper_count"] += other["paper_count"]
                group["issns"] = sorted(set(group["issns"]) | set(other["issns"]))
                group["aliases"].extend([other["name"], *other["aliases"]])
                journals.remove(other)
        else:
            group = {"name": row["journal"], "aliases": [], "issns": [], "paper_count": 0}
            journals.append(group)
        if row["journal"] != group["name"]:
            group["aliases"].append(row["journal"])
        group["aliases"] = list(dict.fromkeys(group["aliases"]))
        group["issns"] = sorted(set(group["issns"]) | identifiers)
        group["paper_count"] += 1
    years = [int(row["year"]) for row in rows]
    dates = [publication_date(record, "first")[0] for record in unique]
    return {"rows": rows, "records": unique, "journals": journals, "paper_count": len(rows),
            "year_start": min(years) if years else None, "year_end": max(years) if years else None,
            "start_date": min(dates) if dates else None, "end_date": max(dates) if dates else None,
            "multiple_journals": len(journals) > 1}


def manual_project_folder_name(overview):
    label = overview["journals"][0]["name"] if len(overview["journals"]) == 1 else "multiple-journals"
    created = datetime.now(ZoneInfo("Europe/Zurich")).date()
    return f"{created:%d%m%Y}_journalanalysis_{slugify(label)}_{overview['start_date']}_{overview['end_date']}_manual"


def create_manual_project(records, projects_root, *, project_name=None, template_path=None):
    """Create a project solely from preloaded records: no API calls or random sampling."""
    overview = manual_overview(records)
    if not overview["paper_count"]:
        raise ValueError("Select at least one checked DOI before creating a manual project.")
    rows, records = overview["rows"], overview["records"]
    if len({row["bibtex_key"] for row in rows}) != len(rows):
        raise ValueError("BibTeX key collision; no project created.")
    name = manual_project_folder_name(overview) if project_name is None else project_name
    _, destination, template = _prepare_project(projects_root, name, template_path)
    label = overview["journals"][0]["name"] if not overview["multiple_journals"] else "Multiple journals"
    stem = f"{slugify(label)}_{overview['start_date']}_{overview['end_date']}_manual"
    selected_stem = f"{stem}_selected{len(rows)}"
    created = datetime.now(timezone.utc).isoformat()
    config = {"schema_version": 1, "selection_method": "manual", "journal": label,
              "journals": overview["journals"], "issns": sorted({issn for item in overview["journals"] for issn in item["issns"]}),
              "start_date": str(overview["start_date"]), "end_date": str(overview["end_date"]), "date_basis": "first",
              "year_range": [overview["year_start"], overview["year_end"]], "sample_size": len(rows),
              "seed": None, "include_notices": False, "created_at_utc": created,
              "full_export": f"output/{stem}.csv", "sample_export": f"output/{selected_stem}.csv",
              "selection_export": f"output/{selected_stem}.csv"}
    selection = {"selection_method": "manual", "sampling": "explicit DOI selection; no random sampling",
                 "source_entry_count": len(rows), "eligible_entry_count": len(rows), "selected_entry_count": len(rows),
                 "seed": None, "include_notices": False, "excluded_notices": [], "created_at_utc": created,
                 "selected_dois": [row["doi"] for row in rows], "selected_bibtex_keys": [row["bibtex_key"] for row in rows]}
    report = {**config, "source": "Crossref metadata preloaded during DOI lookup", "queries": [],
              "raw_record_count": len(records), "entry_count": len(rows), "matching_dois_and_keys_verified": True,
              "multiple_journals_warning": overview["multiple_journals"],
              "coverage_note": "Only the explicitly selected DOIs; not a complete journal export or random sample."}
    result = _write_project(destination, template, config, rows, rows, selection, records, report)
    result["overview"] = overview
    return result
