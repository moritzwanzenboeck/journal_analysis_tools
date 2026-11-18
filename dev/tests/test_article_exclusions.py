"""Non-scientific articles stay out of both random and explicit DOI selections."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import journal_tools as tools
from test_metadata import article,JOURNAL


class ScientificSelectionTests(unittest.TestCase):
    def test_titles_and_publisher_types_without_excluding_research_topics(self):
        excluded=['Editorial','Guest editorial: this issue','Front Matter','Back-matter','Table of contents',
                  'Cover image','Cover: This month','Masthead','Publisher’s note','Book review: Work','Obituary','Instructions for authors',
                  'Correction to: Results','Preface','Introduction to the special issue: Methods']
        for title in excluded:
            with self.subTest(title=title):
                record=dict(article(),title=[title])
                self.assertTrue(tools.non_scientific_reason(record))
                with self.assertRaisesRegex(ValueError,'non-scientific'):tools.manual_record_row(record)
        research=['The effects of editorial policies on firm behavior','Front and back matter in economic discourse',
                  'A review of labor market theories','Correction mechanisms in labor markets','Cover crops and farmer incomes','Index of inequality in cities']
        # Correction mechanisms is a scientific topic; use explicit notice forms.
        for title in research:
            with self.subTest(title=title):self.assertFalse(tools.non_scientific_reason(dict(article(),title=[title])))
        for extra in ({'subtype':'editorial'}, {'article-type':'front-matter'},
                      {'assertion':[{'name':'article_type','value':'back-matter'}]}):
            record=dict(article(),**extra)
            self.assertIn('Publisher article type',tools.non_scientific_reason(record))

    def test_random_and_offline_replay_report_exclusions_manual_rejects_without_fetch(self):
        records=[article('10.1234/good'),dict(article('10.1234/front'),title=['Front matter']),
                 dict(article('10.1234/editor'),subtype='editorial')]
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw.json';raw.write_text(json.dumps(records))
            with patch.object(tools,'get_json',side_effect=AssertionError('No network')):
                result=tools.create_project(JOURNAL,tools.date(2026,1,1),tools.date(2026,12,31),1,tmp,
                    input_json=raw,project_name='offline',include_notices=True)
                self.assertEqual([r['doi'] for r in result['selected']],['10.1234/good'])
                self.assertEqual(len(result['rows']),3)
                self.assertEqual(len(result['selection_report']['excluded_notices']),2)
                self.assertFalse(result['config']['include_notices'])
                with self.assertRaisesRegex(ValueError,'non-scientific'):
                    tools.create_manual_project(records,tmp,project_name='manual')
                self.assertFalse((Path(tmp)/'manual').exists())
            with patch.object(tools,'get_json',return_value=records[1]):
                with self.assertRaisesRegex(ValueError,'non-scientific'):tools.lookup_doi('10.1234/front')

if __name__=='__main__':unittest.main()
