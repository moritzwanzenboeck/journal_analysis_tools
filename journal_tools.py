"""Journal-agnostic Crossref metadata, random sampling and project creation.

Use the desktop app or create_journal_analysis.ipynb as the interactive entry point.
The backend uses only the Python standard library.
"""
from __future__ import annotations

import calendar
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
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
    # Bundled desktop builds carry a CA bundle independent of the host Python.
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
    rows = []
    for doi, item in by_doi.items():
        selected = publication_date(item, basis)
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
        rows.append({
            "bibtex_key": slugify(journal.name).replace("-", "_") + "_" + re.sub(r"[^a-z0-9]+", "_", doi).strip("_"),
            "doi": doi, "title": title, "authors": " and ".join(authors),
            "journal": plain_text(" ".join(item.get("container-title", []))) or journal.name,
            "year": str((printed or selected)[0].year), "volume": item.get("volume", ""),
            "issue": item.get("issue", ""), "pages": item.get("page", ""),
            "article_number": item.get("article-number", ""),
            "publication_date": selected[1], "date_source": selected[3], "date_precision": selected[2],
            "published_online": online[1] if online else "",
            "published_print": printed[1] if printed else "",
            "issn": "; ".join(item.get("ISSN", [])), "publisher": plain_text(item.get("publisher")),
            "url": "https://doi.org/" + quote(doi, safe="/"),
            "abstract": plain_text(item.get("abstract")),
        })
    rows.sort(key=lambda row: (row["publication_date"], row["doi"]), reverse=True)
    if len({row["bibtex_key"] for row in rows}) != len(rows):
        raise ValueError("BibTeX key collision; no exports written.")
    return rows, outside


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
    r"^(?:editorial|corrigendum|corrigenda|erratum|errata|retraction|"
    r"withdrawal|publisher.s note|acknowledg(?:e)?ments?|reviewer acknowledg)\b"
    r"|\b(?:preface|special issue)\b", re.IGNORECASE,
)
NOTICE_FILTER_NOTE = (
    "Title heuristic excluding editorials, corrections, errata, retractions, "
    "withdrawals, publisher notes, acknowledgements, prefaces and special issues. "
    "Review the exclusions; this is not a full article-type classification."
)


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
    excluded = [] if include_notices else [row for row in rows if NOTICE_TITLE.search(row["title"])]
    eligible = list(rows) if include_notices else [row for row in rows if not NOTICE_TITLE.search(row["title"])]
    if count > len(eligible):
        raise ValueError(f"Requested {count} papers, but only {len(eligible)} are eligible ({len(rows)} total).")
    seed = seed if seed is not None else secrets.randbits(64)
    selected = random.Random(seed).sample(sorted(eligible, key=lambda row: row["doi"]), count)
    report = {
        "source_entry_count": len(rows), "eligible_entry_count": len(eligible),
        "include_notices": include_notices, "notice_filter": NOTICE_FILTER_NOTE,
        "excluded_notices": [{"doi": row["doi"], "title": row["title"]} for row in excluded],
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
    projects_root = Path(projects_root).expanduser().resolve()
    if not projects_root.is_dir():
        raise ValueError("Projects root must be an existing directory.")
    name = project_folder_name(journal, start, end) if project_name is None else project_name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", name):
        raise ValueError("Project folder name must be a single name using letters, digits, dots, underscores or hyphens.")
    destination = projects_root / name
    if destination.exists():
        raise FileExistsError(f"Project already exists: {destination}. Choose a different project folder name.")
    template_path = Path(template_path) if template_path else Path(__file__).resolve().with_name("clean_and_count_text.ipynb")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    # Clear saved widget/editor state before making a project-local copy.
    template.get("metadata", {}).pop("widgets", None)
    for cell in template["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    if input_json is None:
        records, queries = fetch_records(journal, start, end, date_basis, email)
    else:
        records = json.loads(Path(input_json).read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("Input JSON must be a list of Crossref work records.")
        queries = []
    rows, outside = normalize(records, journal, start, end, date_basis)
    selected, selection_report = sample_rows(rows, count, seed, include_notices)
    stem = f"{slugify(journal.name)}_{start}_{end}" + (f"_{date_basis}" if date_basis != "first" else "")
    sample_stem = f"{stem}_random{count}"
    created_at = datetime.now(timezone.utc).isoformat()
    config = {
        "schema_version": 1, "journal": journal.name, "issns": list(journal.issns),
        "start_date": str(start), "end_date": str(end), "date_basis": date_basis,
        "sample_size": count, "seed": selection_report["seed"], "include_notices": include_notices,
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
    # Build in a hidden sibling directory. Failed writes do not leave a partial project.
    with tempfile.TemporaryDirectory(prefix=".journal-analysis-", dir=projects_root) as temporary:
        staging = Path(temporary) / name
        staging.mkdir()
        output = staging / "output"
        export(rows, output, stem, report, records)
        write_selection(selected, output, sample_stem, dict(selection_report, source_csv=f"output/{stem}.csv"))
        (staging / "project.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "clean_and_count_text.ipynb").write_text(json.dumps(template, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (staging / "README.md").write_text(
            f"# {journal.name} journal analysis\n\n"
            f"Date range: **{start} through {end}**, inclusive. Publication basis: **{date_basis}**.\n\n"
            f"Selected {count} papers from {selection_report['eligible_entry_count']} eligible records "
            f"({len(rows)} total). Random seed: `{selection_report['seed']}`.\n\n"
            "- `project.json`: configuration and the saved seed.\n"
            "- `output/`: matching CSV/BibTeX full exports and random sample, raw metadata and reports.\n"
            "- `clean_and_count_text.ipynb`: optional notebook version of the text-cleaning tool.\n\n"
            "Use the desktop app’s Clean and count text tab to work without Jupyter. "
            "Choose your own folders and files for PDFs and analysis results. "
            "PDFs are not downloaded. Crossref metadata and the notice-title filter need human review. "
            "The first-publication rule uses the earliest known online, print, published or issued date. "
            "Partial dates use the first day for filtering and retain their precision in exports.\n",
            encoding="utf-8",
        )
        # mkdir reserves the destination exclusively, including against simultaneous runs.
        destination.mkdir(exist_ok=False)
        try:
            for child in staging.iterdir():
                child.rename(destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return {"path": destination, "journal": journal, "rows": rows,
            "selected": selected, "selection_report": selection_report, "config": config}
