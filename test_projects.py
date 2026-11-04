"""Journal resolution, sampling and complete offline project workflows."""
import csv
from datetime import date
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import journal_tools as tools
from test_metadata import article, JOURNAL


class JournalTests(unittest.TestCase):
    def test_issn_validation_and_normalization(self):
        self.assertEqual(tools.canonical_issn('12345679'), '1234-5679')
        self.assertEqual(tools.Journal(' Example ', ('12345679', '1234-5679')).issns, ('1234-5679',))
        for value in ('1234-5678', '../test', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tools.canonical_issn(value)

    def test_title_search_returns_candidates_and_exact_issn_expands_identifiers(self):
        message = {'title': JOURNAL.name, 'ISSN': list(JOURNAL.issns)}
        with patch.object(tools, 'get_json', return_value={'items': [message]}) as get:
            self.assertEqual(tools.find_journals('Example'), [JOURNAL])
            self.assertIn('query=Example', get.call_args.args[0])
        with patch.object(tools, 'get_json', return_value=message) as get:
            self.assertEqual(tools.find_journals('12345679'), [JOURNAL])
            self.assertTrue(get.call_args.args[0].endswith('/journals/1234-5679'))

    def test_unindexed_issn_is_recorded_but_other_identifier_is_fetched(self):
        def response(url, email):
            if JOURNAL.issns[0] in url:
                raise HTTPError(url, 404, 'not indexed', {}, None)
            return {'items': [article()], 'total-results': 1}
        with patch.object(tools, 'get_json', side_effect=response), patch.object(tools.time, 'sleep'):
            records, queries = tools.fetch_records(JOURNAL, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(len(records), 1)
        self.assertEqual(queries[0]['status'], 'not indexed (404)')
        self.assertEqual(queries[1]['total_results'], 1)

    def test_all_unindexed_and_server_failures_abort(self):
        for status in (404, 500):
            error = HTTPError('https://example.invalid', status, 'error', {}, None)
            with patch.object(tools, 'get_json', side_effect=error), patch.object(tools.time, 'sleep'):
                with self.assertRaises((ValueError, HTTPError)):
                    tools.fetch_records(JOURNAL, date(2026, 1, 1), date(2026, 12, 31))

    def test_wrong_journal_and_missing_doi_fail(self):
        for item in (dict(article(), ISSN=['9999-9999']), dict(article(), DOI='')):
            with self.assertRaises(ValueError):
                tools.normalize([item], JOURNAL, date(2026, 1, 1), date(2026, 12, 31))


class SamplingTests(unittest.TestCase):
    def population(self):
        rows, _ = tools.normalize([article(f'10.1234/{n}') for n in range(12)], JOURNAL,
                                  date(2026, 1, 1), date(2026, 12, 31))
        notices = []
        for n, title in enumerate(('Editorial Board', 'Corrigendum to an article', 'A special issue on learning')):
            notices.append(dict(rows[0], title=title, doi=f'10.1234/notice{n}', bibtex_key=f'notice{n}'))
        return rows + notices

    def test_seed_survives_reordering_and_notices_are_reported(self):
        rows = self.population()
        first, report = tools.sample_rows(rows, 10, seed=42)
        second, _ = tools.sample_rows(list(reversed(rows)), 10, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(len({row['doi'] for row in first}), 10)
        self.assertEqual(report['eligible_entry_count'], 12)
        self.assertEqual(len(report['excluded_notices']), 3)
        self.assertEqual(len(tools.sample_rows(rows, 15, include_notices=True)[0]), 15)
        with self.assertRaises(ValueError):
            tools.sample_rows(rows, 13)
        with self.assertRaises(ValueError):
            tools.sample_rows(rows + [rows[0]], 1)

    def test_selection_serialization_matches_dois_and_keys(self):
        selected, report = tools.sample_rows(self.population(), 10, seed=0)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            tools.write_selection(selected, output, 'sample', report)
            csv_rows = list(csv.DictReader(io.StringIO((output/'sample.csv').read_text(encoding='utf-8-sig'))))
            bib = (output/'sample.bib').read_text()
            self.assertEqual([row['doi'] for row in csv_rows], re.findall(r'^  doi = \{([^\n]+)\},$', bib, re.M))
            self.assertTrue(json.loads((output/'sample_selection.json').read_text())['matching_dois_and_keys_verified'])


class ProjectTests(unittest.TestCase):
    start, end = date(2026, 1, 1), date(2026, 12, 31)

    def test_complete_project_and_offline_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root/'archive.json'
            raw.write_text(json.dumps([article(f'10.1234/{n}') for n in range(8)]))
            with patch.object(tools, 'get_json', side_effect=AssertionError('Offline replay used network')):
                result = tools.create_project(JOURNAL, self.start, self.end, 4, root,
                                              seed=42, project_name='first', input_json=raw)
                second = tools.create_project(JOURNAL, self.start, self.end, 4, root,
                                              seed=42, project_name='second', input_json=raw)
            project = result['path']
            self.assertEqual(result['selected'], second['selected'])
            self.assertEqual(json.loads((project/'project.json').read_text())['seed'], 42)
            self.assertFalse((project/'papers').exists())
            self.assertFalse((project/'analysis').exists())
            self.assertEqual({p.name for p in project.iterdir()},
                             {'project.json', 'README.md', 'clean_and_count_text.ipynb', 'output'})
            with (project/result['config']['sample_export']).open(encoding='utf-8-sig', newline='') as handle:
                exported_sample = list(csv.DictReader(handle))
            self.assertEqual([row['doi'] for row in exported_sample], [row['doi'] for row in result['selected']])
            self.assertEqual(len(list((project/'output').iterdir())), 7)
            notebook = json.loads((project/'clean_and_count_text.ipynb').read_text())
            self.assertNotIn('widgets', notebook['metadata'])
            self.assertTrue(all(c.get('outputs', []) == [] for c in notebook['cells']))
            original = (project/'project.json').read_bytes()
            with patch.object(tools, 'fetch_records', side_effect=AssertionError('Should fail before fetching')):
                with self.assertRaises(FileExistsError):
                    tools.create_project(JOURNAL, self.start, self.end, 4, root, project_name='first')
            self.assertEqual((project/'project.json').read_bytes(), original)
            self.assertFalse(list(root.glob('.journal-analysis-*')))

    def test_failures_leave_no_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for raw in ([article()], []):
                with patch.object(tools, 'fetch_records', return_value=(raw, [])):
                    with self.assertRaises(ValueError):
                        tools.create_project(JOURNAL, self.start, self.end, 2, root, project_name='too-large')
                self.assertEqual(list(root.iterdir()), [])
            with patch.object(tools, 'fetch_records', side_effect=RuntimeError('network unavailable')):
                with self.assertRaises(RuntimeError):
                    tools.create_project(JOURNAL, self.start, self.end, 1, root, project_name='network')
            self.assertEqual(list(root.iterdir()), [])
            with patch.object(tools, 'fetch_records', return_value=([article()], [])), \
                    patch.object(tools, 'write_selection', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    tools.create_project(JOURNAL, self.start, self.end, 1, root, project_name='disk')
            self.assertEqual(list(root.iterdir()), [])

    def test_invalid_configuration_is_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(tools, 'fetch_records', side_effect=AssertionError('Should not fetch')):
            for kwargs in ({'project_name': '../escape'}, {'date_basis': 'bad'}, {'seed': 'abc'}, {'project_name': '/absolute'}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    tools.create_project(JOURNAL, self.start, self.end, 1, root, **kwargs)
            with self.assertRaises(ValueError):
                tools.create_project(JOURNAL, self.end, self.start, 1, root)
            with self.assertRaises(ValueError):
                tools.create_project(JOURNAL, self.start, self.end, 0, root)


if __name__ == '__main__':
    unittest.main()
