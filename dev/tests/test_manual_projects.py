"""Manual DOI lookup, preload reuse and project creation using synthetic metadata."""
import copy
import csv
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit

from app import journal_tools as tools
from app import paper_tools
from test_metadata import article
from test_notebooks import execute_notebook


def other_article():
    return dict(article('10.1234/other', online=(2021, 2, 1), printed=(2022, 1, 1)),
                ISSN=['0002-8282'], **{'container-title':['Other Journal'], 'title':['Another paper']})


class ManualLookupTests(unittest.TestCase):
    def test_doi_forms_and_suffix_punctuation(self):
        for value in (' 10.1234/Example(A). ', 'doi: 10.1234/Example(A).',
                      'https://doi.org/10.1234/Example%28A%29.',
                      'http://dx.doi.org/10.1234/Example(A).?utm_source=test',
                      'DOI.ORG/10.1234/Example(A).'):
            self.assertEqual(tools.normalize_doi(value), '10.1234/example(a).')
        for value in ('', '10.12/a', '10.1234/', '10.1234/a b', 'https://publisher.example/10.1234/a',
                      'https://doi.org.evil.example/10.1234/a', '10.1234/a\nb'):
            with self.subTest(value=value), self.assertRaises(ValueError):tools.normalize_doi(value)

    def test_lookup_preloads_all_metadata_and_reuses_cache(self):
        raw=dict(article(),abstract='<p>Full abstract.</p>',publisher='A publisher')
        cache={}
        with patch.object(tools,'get_json',return_value=raw) as get:
            first=tools.lookup_doi('https://doi.org/'+raw['DOI'],cache,email='contact@example.org')
            first['title'][0]='Changed outside cache'
            second=tools.lookup_doi(raw['DOI'].upper(),cache)
        self.assertEqual(get.call_count,1)
        self.assertIn('/works/10.1080%2Fexample.1',get.call_args.args[0])
        self.assertIn('mailto=contact%40example.org',get.call_args.args[0])
        self.assertEqual(second,raw)
        self.assertEqual(second['abstract'],'<p>Full abstract.</p>')

    def test_unusable_metadata_and_mismatched_responses_are_not_cached(self):
        missing_date=article();missing_date.pop('published-online');missing_date.pop('published-print')
        invalid=[dict(article(),type='book'),dict(article(),title=[]),
                 dict(article(),**{'container-title':[]}),missing_date,dict(article(),DOI='10.1234/wrong')]
        for raw in invalid:
            cache={}
            with patch.object(tools,'get_json',return_value=raw), self.assertRaises(ValueError):
                tools.lookup_doi('10.1080/example.1',cache)
            self.assertEqual(cache,{})
        with patch.object(tools,'get_json',side_effect=HTTPError('https://example.invalid',404,'missing',{},None)), \
                self.assertRaisesRegex(ValueError,'not found in Crossref'):
            tools.lookup_doi('10.1234/missing')

    def test_bulk_reports_all_errors_and_retries_only_missing_metadata(self):
        cache={};raws={'10.1234/a':article('10.1234/a'),'10.1234/b':other_article()}
        raws['10.1234/b']['DOI']='10.1234/b'
        def response(url,email):
            doi=unquote(urlsplit(url).path.removeprefix('/works/'))
            if doi.endswith('/missing'):raise HTTPError(url,404,'missing',{},None)
            return raws[doi]
        text='10.1234/a\nhttps://doi.org/10.1234/A\nnot a doi\n10.1234/missing\n10.1234/b'
        with patch.object(tools,'get_json',side_effect=response) as get:
            result=tools.check_dois(text,cache)
            self.assertEqual(get.call_count,3)
            self.assertEqual([row['line'] for row in result['errors']],[3,4])
            self.assertEqual(result['duplicates'],['10.1234/a'])
            self.assertEqual([row['DOI'] for row in result['records']],['10.1234/a','10.1234/b'])
            result=tools.check_dois('10.1234/a\n10.1234/b',cache)
            self.assertEqual(get.call_count,3)
            self.assertFalse(result['errors'])


class ManualProjectTests(unittest.TestCase):
    def test_overview_journals_years_and_identifier_aliases(self):
        first=article();alias=dict(article('10.1234/alias'),**{'container-title':['Journal alternate spelling']})
        summary=tools.manual_overview([first,other_article(),alias,first])
        self.assertEqual(summary['paper_count'],3)
        self.assertEqual(len(summary['journals']),2)
        self.assertEqual(summary['journals'][0]['paper_count'],2)
        self.assertTrue(summary['multiple_journals'])
        self.assertEqual((summary['year_start'],summary['year_end']),(2022,2026))
        self.assertEqual(summary['start_date'],date(2021,2,1))
        self.assertFalse(tools.manual_overview([first,alias])['multiple_journals'])
        no_issn=dict(first,ISSN=[])
        self.assertEqual(tools.manual_overview([no_issn])['paper_count'],1)
        print_only=dict(article('10.1234/print'),ISSN=['1234-5679'],**{'container-title':['Print journal name']})
        online_only=dict(article('10.1234/online'),ISSN=['2049-3630'],**{'container-title':['Online journal name']})
        combined=article('10.1234/combined')
        self.assertFalse(tools.manual_overview([print_only,online_only,combined])['multiple_journals'])

    def test_complete_manual_project_uses_preloaded_records_and_integrates_with_paper_selector(self):
        first=dict(article(),title=['Editorial explicitly selected'],abstract='<p>An abstract.</p>')
        raw=[first,other_article(),first]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch.object(tools,'get_json',side_effect=AssertionError('Metadata fetched twice')), \
                 patch.object(tools,'fetch_records',side_effect=AssertionError('Fetched journal')), \
                 patch.object(tools,'sample_rows',side_effect=AssertionError('Random sampling applied')):
                result=tools.create_manual_project(raw,root,project_name='manual')
            project=result['path'];config=result['config']
            self.assertEqual(config['selection_method'],'manual')
            self.assertIsNone(config['seed'])
            self.assertEqual(config['sample_size'],2)
            self.assertEqual(len(config['journals']),2)
            self.assertIn('_selected2.csv',config['sample_export'])
            with (project/config['sample_export']).open(encoding='utf-8-sig',newline='') as handle:
                exported=list(csv.DictReader(handle))
            self.assertEqual([row['doi'] for row in exported],[first['DOI'],raw[1]['DOI']])
            self.assertEqual(exported[0]['abstract'],'An abstract.')
            context=paper_tools.paper_read_project(project)
            self.assertEqual(len(context['papers']),2)
            self.assertIn('multiple journals',(project/'README.md').read_text(encoding='utf-8'))
            self.assertEqual(len(list((project/'output').iterdir())),7)
            self.assertEqual({p.name for p in project.iterdir()},{'README.md','project.json','clean_and_count_text.ipynb','output'})
            original=(project/'project.json').read_bytes()
            with self.assertRaises(FileExistsError):tools.create_manual_project(raw,root,project_name='manual')
            self.assertEqual((project/'project.json').read_bytes(),original)

    def test_invalid_inputs_and_failed_writes_leave_no_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for raw,name in (([],'empty'),([dict(article(),type='book')],'invalid'),([article()],'CON'),
                             ([article()],'../escape'),([article('10.1234/a-b'),article('10.1234/a_b')],'collision')):
                with self.assertRaises(ValueError):tools.create_manual_project(raw,root,project_name=name)
                self.assertEqual(list(root.iterdir()),[])
            with patch.object(tools,'write_selection',side_effect=OSError('disk full')), self.assertRaises(OSError):
                tools.create_manual_project([article()],root,project_name='failure')
            self.assertEqual(list(root.iterdir()),[])


class ManualFormTests(unittest.TestCase):
    def setUp(self):
        self.s=execute_notebook('create_journal_analysis.ipynb')
        self.s['project_mode'].value='manual'

    def test_enter_search_rich_dropdown_selection_and_cached_lookup(self):
        s=self.s;s['manual_doi_query'].value='https://doi.org/10.1080/example.1'
        self.assertTrue(s['create_button'].disabled)
        with patch.object(tools,'get_json',return_value=article()) as get:
            # Invoke the same submit callback registry used by ipywidgets' Enter event.
            s['manual_doi_query']._submission_callbacks(s['manual_doi_query'])
            self.assertEqual(get.call_count,1)
            dropdown=s['manual_result_dropdown']
            self.assertEqual(dropdown.selected_index,0)
            html=dropdown.children[0].children[0].value
            self.assertIn('<strong',html)
            for label in ('Journal','Year','DOI','Example Journal','2026','10.1080/example.1'):
                self.assertIn(label,html)
            dropdown.children[0].children[1].click()
            self.assertEqual(len(s['manual_state']['selected']),1)
            s['manual_doi_query'].value='10.1080/example.1'
            s['manual_search_button'].click()
            self.assertEqual(get.call_count,1)
            s['manual_result_dropdown'].children[0].children[1].click()
            self.assertEqual(len(s['manual_state']['selected']),1)
        self.assertFalse(s['create_button'].disabled)
        s['manual_doi_query'].value='10.1234/not-searched'
        self.assertEqual(s['manual_result_dropdown'].children,())

    def test_bulk_errors_prevent_partial_addition_and_reuse_successful_lookups(self):
        s=self.s;s['manual_bulk_input'].value='10.1080/example.1\nbad entry'
        with patch.object(tools,'get_json',return_value=article()) as get:
            s['manual_bulk_button'].click()
            self.assertEqual(s['manual_state']['selected'],{})
            self.assertIn('Line 2',s['manual_bulk_status'].value)
            self.assertTrue(s['create_button'].disabled)
            s['manual_bulk_input'].value='10.1080/example.1\nhttps://doi.org/10.1080/example.1'
            s['manual_bulk_button'].click()
            self.assertEqual(get.call_count,1)
        self.assertEqual(len(s['manual_state']['selected']),1)
        self.assertFalse(s['create_button'].disabled)
        s['manual_bulk_input'].value+='\n10.1234/unchecked'
        self.assertTrue(s['create_button'].disabled)
        s['manual_bulk_input'].value=''
        self.assertFalse(s['create_button'].disabled)

    def test_overview_removal_and_creation_without_network(self):
        s=self.s
        s['manual_add_paper'](article());s['manual_add_paper'](other_article())
        overview=s['manual_overview_html'].value
        for value in ('Example Journal','Other Journal','Papers:</strong> 2','2022–2026','multiple journals'):
            self.assertIn(value,overview)
        with tempfile.TemporaryDirectory() as temporary:
            s['root_field'].value=temporary;s['folder_field'].value='from-form'
            # Random-mode date fields must not filter an explicit manual selection.
            s['start_field'].value=date(2030,1,1);s['end_field'].value=date(2031,1,1)
            with patch.object(tools,'get_json',side_effect=AssertionError('Refetched metadata')):
                s['create_button'].click()
            self.assertEqual(s['last_project']['config']['sample_size'],2)
            text_state=execute_notebook('clean_and_count_text.ipynb')
            text_state['paper_project_folder'].value=str(s['last_project']['path'])
            text_state['paper_scan_project_button'].click()
            self.assertEqual(text_state['paper_sample_choice'].description,'Selected paper:')
            self.assertEqual(len(text_state['paper_sample_choice'].options),3)
            self.assertIn('2 selected paper(s)',text_state['paper_project_status'].value)
        s['manual_selected_rows'].children[1].children[1].click()
        self.assertNotIn('multiple journals',s['manual_overview_html'].value)
        s['manual_selected_rows'].children[0].children[1].click()
        self.assertTrue(s['create_button'].disabled)
        s['project_mode'].value='random'
        self.assertIsNone(s['journal_choice'].value)
        self.assertTrue(s['create_button'].disabled)


if __name__=='__main__':unittest.main()
