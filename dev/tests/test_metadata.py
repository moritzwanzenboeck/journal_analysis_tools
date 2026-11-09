"""Offline regression checks for date selection, pagination and matching exports."""

import csv
from datetime import date
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app import journal_tools as tools

JOURNAL = tools.Journal("Example Journal", ("1234-5679", "2049-3630"))


def article(doi="10.1080/example.1", online=(2026, 1, 10), printed=(2026, 4, 3)):
    return {
        "DOI": doi, "type": "journal-article", "ISSN": list(JOURNAL.issns),
        "title": ["GDP & Growth: 50% of {Output}"],
        "author": [{"given": "René", "family": "Müller"}],
        "published-online": {"date-parts": [list(online)]},
        "published-print": {"date-parts": [list(printed)]},
        "container-title": [JOURNAL.name], "volume": "44", "issue": "2", "page": "10-20",
    }


class ExportTests(unittest.TestCase):
    start, end = date(2025, 10, 5), date(2026, 10, 5)

    def test_calendar_months_and_leap_day(self):
        self.assertEqual(tools.months_before(date(2024, 2, 29), 12), date(2023, 2, 28))
        self.assertEqual(tools.months_before(self.end, 12), self.start)

    def test_online_first_inclusion_and_inclusive_boundaries(self):
        rows, _ = tools.normalize([
            article("10.1080/start", (2025, 10, 5)),
            article("10.1080/end", (2026, 10, 5), (2027, 1, 1)),
            article("10.1080/old", (2025, 10, 4)),
            article("10.1080/future", (2026, 10, 6), (2027, 1, 1)),
        ], JOURNAL, self.start, self.end, "first")
        self.assertEqual({row["doi"] for row in rows}, {"10.1080/start", "10.1080/end"})
        printed, _ = tools.normalize([article(online=(2025, 10, 4))], JOURNAL, self.start, self.end, "print")
        self.assertEqual(len(printed), 1)

    def test_deduplication_and_partial_dates(self):
        item = article(online=(2026, 1))
        duplicate = dict(item, DOI=item["DOI"].upper(), abstract="<jats:p>Rich &amp; complete.</jats:p>")
        rows, _ = tools.normalize([item, duplicate], JOURNAL, self.start, self.end, "first")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["publication_date"], "2026-01")
        self.assertEqual(rows[0]["date_precision"], "month")
        self.assertEqual(rows[0]["abstract"], "Rich & complete.")

    def test_pagination_over_registered_issns(self):
        pages = []

        def response(url, email):
            cursor = parse_qs(urlparse(url).query)["cursor"][0]
            pages.append(cursor)
            return {"items": [article()] if cursor == "*" else [],
                    "total-results": 1, "next-cursor": "cursor+with/special=chars"}

        with patch.object(tools, "get_json", side_effect=response), patch.object(tools.time, "sleep"):
            records, queries = tools.fetch_records(JOURNAL, self.start, self.end, "first", page_size=1)
        self.assertEqual(pages, ["*", "cursor+with/special=chars"] * len(JOURNAL.issns))
        self.assertEqual(len(records), len(JOURNAL.issns))
        self.assertEqual(len(queries), len(JOURNAL.issns))

    def test_stalled_pagination_fails(self):
        response = {"items": [article()], "total-results": 3, "next-cursor": "unchanged"}
        with patch.object(tools, "get_json", return_value=response), patch.object(tools.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                tools.fetch_records(JOURNAL, self.start, self.end, "first", page_size=1)

    def test_incomplete_response_fails(self):
        response = {"items": [article()], "total-results": 2, "next-cursor": "next"}
        with patch.object(tools, "get_json", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "fewer records"):
                tools.fetch_records(JOURNAL, self.start, self.end, "first", page_size=500)

    def test_serialized_files_have_same_entries_and_valid_escaping(self):
        raw = [article(), article("10.1080/example.2", (2026, 2, 1))]
        rows, _ = tools.normalize(raw, JOURNAL, self.start, self.end, "first")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            tools.export(rows, output, "test", {"entry_count": 2}, raw)
            with (output / "test.csv").open(encoding="utf-8-sig", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            bib = (output / "test.bib").read_text(encoding="utf-8")
            self.assertEqual({row["doi"] for row in csv_rows}, set(re.findall(r"doi = \{([^}]+)\}", bib)))
            self.assertEqual(len(re.findall(r"^@article", bib, re.MULTILINE)), 2)
            self.assertIn(r"GDP \& Growth: 50\% of \{Output\}", bib)
            self.assertIn("Müller, René", bib)
            self.assertIn("pages = {10--20}", bib)
            self.assertEqual(json.loads((output / "test_report.json").read_text())["entry_count"], 2)


if __name__ == "__main__":
    unittest.main()
