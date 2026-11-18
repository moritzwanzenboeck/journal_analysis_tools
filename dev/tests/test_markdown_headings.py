"""Markdown heading editing, count parity, legacy migration and live widgets."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import paper_tools as tools
from app.text_tools import WORD
from test_paper_categorization import notebook_state


class MarkdownModelTests(unittest.TestCase):
    def test_explicit_levels_and_canonical_text_exclude_syntax(self):
        md='Preamble.\n\n# Introduction\nAn opening.\n\n## Data\nOur data.\n\n### Estimation ###\nA result!\n\n###### Details\nMore detail.'
        doc=tools.paper_make_markdown_document(md)
        self.assertEqual([u['level'] for u in doc['units']],[0,1,2,3,6])
        self.assertEqual(doc['units'][3]['title'],'Estimation')
        self.assertNotIn('#',doc['cleaned_text'])
        self.assertEqual(sum(tools.paper_unit_counts(u)['words'] for u in doc['units']),len(WORD.findall(md)))
        self.assertEqual(sum(tools.paper_unit_counts(u)['paragraphs'] for u in doc['units']),5)
        self.assertEqual(tools.paper_validate_document(tools.paper_export_document(doc)),doc)

    def test_cleanup_seeds_plain_numbered_headings_and_preserves_explicit_levels(self):
        raw='1. Introduction\nA result?\n2.2\nWe test it!'
        md=tools.paper_suggest_markdown(tools.paper_clean_text(raw))
        self.assertIn('# 1. Introduction',md);self.assertIn('## 2.2',md)
        raw='# Custom intro\nResult (𝑝<.1\n).\n### 2.2 More detail\nA footnote.12\nNext!'
        md=tools.paper_suggest_markdown(tools.paper_clean_text(raw))
        self.assertIn('### 2.2 More detail',md)
        doc=tools.paper_make_markdown_document(md)
        self.assertEqual([u['level'] for u in doc['units']],[1,3])
        self.assertIn('Result (𝑝<.1).',doc['cleaned_text'])
        self.assertIn('A footnote.12\n\nNext!',doc['cleaned_text'])

    def test_only_explicit_markers_define_boundaries_during_editing(self):
        md='# Start\nBody.\n\n2. Results\nMore body.\n\n## Real subsection\nEnd.'
        doc=tools.paper_make_markdown_document(md)
        self.assertEqual([u['title'] for u in doc['units']],['Start','Real subsection'])
        self.assertIn('2. Results',doc['units'][0]['body'])
        text='# Start\nBody.\n```python\n# Not a heading\n```\n## End\nLast.'
        self.assertEqual([h['title'] for h in tools.paper_markdown_headings(text)],['Start','End'])
        self.assertEqual(tools.paper_markdown_headings('####### Seven\n#No space\n\\# Literal'),[])
        for text in ('#','## ','###\nBody.','# ###'):
            with self.assertRaisesRegex(ValueError,'add a heading title'):
                tools.paper_make_markdown_document(text)

    def test_relevel_rename_and_repeated_titles_keep_the_correct_labels(self):
        text='# Repeated\nFirst body.\n\n## Repeated\nSecond body.'
        doc=tools.paper_make_markdown_document(text)
        doc['units'][0]['category']='Introduction';doc['units'][1]['category']='Data'
        changed=tools.paper_make_markdown_document(text.replace('## Repeated','### Renamed'),previous=doc)
        self.assertEqual([(u['level'],u['category']) for u in changed['units']],[(1,'Introduction'),(3,'Data')])
        remaining=tools.paper_make_markdown_document('## Repeated\nSecond body.',previous=doc)
        self.assertEqual(remaining['units'][0]['category'],'Data')
        self.assertEqual(tools.paper_validate_document(tools.paper_export_document(changed)),changed)

    def test_removing_marker_retains_words_and_resets_the_merged_assignment(self):
        md='# Intro\nFirst body.\n\n## Context\nOther body.'
        doc=tools.paper_make_markdown_document(md)
        doc['units'][0]['category']='Introduction';doc['units'][1]['category']='Data'
        merged=tools.paper_make_markdown_document(md.replace('## Context','Context'),previous=doc)
        self.assertEqual(len(merged['units']),1)
        self.assertEqual(merged['units'][0]['category'],'Unassigned')
        self.assertIn('Context\nOther body.',merged['cleaned_text'])
        self.assertEqual(len(WORD.findall(doc['cleaned_text'])),len(WORD.findall(merged['cleaned_text'])))
        deleted=tools.paper_make_markdown_document(md.replace('## Context\n',''),previous=doc)
        self.assertEqual(deleted['units'][0]['category'],'Unassigned')

    def test_legacy_virtual_sections_preserve_counts_and_accept_prose_edits(self):
        text='First paragraph.\n\n𝑝 values guide our method.\n\nFinal result!'
        old=tools.paper_make_document(text,'')
        old=tools.paper_select_range(old,text.index('𝑝'),text.index('\n\nFinal'),'Methods','Legacy selected text')
        md=tools.paper_document_markdown(old)
        self.assertIn('# Legacy selected text',md)
        updated=tools.paper_make_markdown_document(md,previous=old)
        self.assertEqual(tools.paper_summary(updated),tools.paper_summary(old))
        self.assertNotIn('Legacy selected text',updated['cleaned_text'])
        edited=tools.paper_make_markdown_document(md.replace('our method','a better method'),previous=updated)
        self.assertIn('a better method',edited['cleaned_text'])
        self.assertEqual(edited['units'][1]['category'],'Methods')
        self.assertEqual(tools.paper_validate_document(tools.paper_export_document(edited)),edited)


class MarkdownNotebookTests(unittest.TestCase):
    def test_native_editor_live_updates_and_reuses_widgets_on_body_edits(self):
        s=notebook_state()
        import ipywidgets
        self.assertIsInstance(s['paper_cleaned'],ipywidgets.Textarea)
        self.assertNotIn('paper_mark_heading_button',s)
        self.assertNotIn('paper_selection_category',s)
        s['paper_original'].value='Introduction\nOpening.\nMethods\nA method.';s['paper_clean_button'].click()
        self.assertIn('# Introduction',s['paper_cleaned'].value)
        doc=s['paper_state']['document']
        uid=doc['units'][0]['id'];s['paper_state']['dropdowns'][uid].value='Introduction'
        dropdown=s['paper_state']['dropdowns'][uid];grid=s['paper_state']['summary_grid']
        s['paper_cleaned'].value=s['paper_cleaned'].value.replace('Opening.','A longer opening.')
        self.assertIs(s['paper_state']['dropdowns'][uid],dropdown)
        self.assertIs(s['paper_state']['summary_grid'],grid)
        self.assertEqual(s['paper_state']['document']['units'][0]['category'],'Introduction')
        self.assertTrue(s['paper_is_current']());self.assertFalse(s['paper_save_button'].disabled)
        s['paper_cleaned'].value=s['paper_cleaned'].value.replace('# Methods','## Methods')
        self.assertEqual(s['paper_state']['document']['units'][1]['level'],2)

    def test_incomplete_heading_blocks_stale_exports_and_recovers_without_reset(self):
        s=notebook_state();s['paper_cleaned'].value='# Intro\nBody.'
        self.assertTrue(s['paper_is_current']())
        before=s['paper_state']['document']
        s['paper_cleaned'].value+='\n\n## '
        self.assertIs(s['paper_state']['document'],before)
        self.assertFalse(s['paper_is_current']());self.assertTrue(s['paper_save_button'].disabled)
        self.assertTrue(s['paper_copy_table_button'].disabled)
        s['paper_cleaned'].value+='Data\nOur data.'
        self.assertTrue(s['paper_is_current']());self.assertFalse(s['paper_save_button'].disabled)
        self.assertEqual([u['title'] for u in s['paper_state']['document']['units']],['Intro','Data'])

    def test_save_reload_and_legacy_source_text_remain_separate(self):
        s=notebook_state();s['original_editor'].value='Legacy workflow text.'
        s['paper_cleaned'].value='# Intro\nAn opening.\n\n## Data\nOur data.'
        doc=s['paper_state']['document'];s['paper_state']['dropdowns'][doc['units'][0]['id']].value='Introduction'
        with tempfile.TemporaryDirectory() as tmp:
            s['paper_folder'].value=tmp;s['paper_save_button'].click()
            path=Path(tmp)/'paper_categories.json'
            self.assertTrue(path.exists(),s['paper_save_status'].value)
            raw=Path(tmp,'paper_cleaned.txt').read_text()
            self.assertNotIn('# ',raw)
            s['paper_load_document'](json.loads(path.read_text()))
            self.assertIn('## Data',s['paper_cleaned'].value)
            self.assertEqual(s['paper_state']['document']['units'][0]['category'],'Introduction')
            self.assertEqual(s['original_editor'].value,'Legacy workflow text.')

    def test_notebook_has_no_custom_browser_editor_dependency(self):
        root=Path(__file__).resolve().parents[2]
        source=(root/'clean_and_count_text.ipynb').read_text()
        self.assertNotIn('anywidget',source)
        self.assertNotIn('anywidget',(root/'requirements.txt').read_text())

if __name__=='__main__':unittest.main()
