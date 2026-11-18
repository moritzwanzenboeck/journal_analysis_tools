"""Alternative level | title editing stays synchronized with Markdown headings."""
import copy
import tempfile
import unittest
from unittest.mock import patch
from app import paper_tools as tools
from test_paper_categorization import notebook_state


class OutlineModelTests(unittest.TestCase):
    def test_levels_additions_and_removal_change_only_heading_markers(self):
        md='# Introduction\nOpening.\n\nData\nOur data.\n\n# Results\nA finding.'
        result=tools.paper_apply_outline(md,'1 | Introduction\n2 | Data')
        self.assertEqual(result,'# Introduction\nOpening.\n\n## Data\nOur data.\n\nResults\nA finding.')
        self.assertEqual(tools.paper_apply_outline(md,''),'Introduction\nOpening.\n\nData\nOur data.\n\nResults\nA finding.')

    def test_duplicate_body_lines_do_not_steal_existing_headings(self):
        md='Repeated\nUnmarked prose.\n\n# Repeated\nFirst section.\n\n## Repeated\nSecond section.'
        result=tools.paper_apply_outline(md,'2 | Repeated\n3 | Repeated')
        self.assertTrue(result.startswith('Repeated\nUnmarked prose.'))
        self.assertIn('## Repeated\nFirst section.',result)
        self.assertIn('### Repeated\nSecond section.',result)
        # An extra explicitly listed occurrence can mark the earlier body line.
        result=tools.paper_apply_outline(md,'1 | Repeated\n2 | Repeated\n3 | Repeated')
        self.assertTrue(result.startswith('# Repeated'))
        self.assertEqual(len(tools.paper_markdown_headings(result)),3)

    def test_invalid_missing_out_of_order_and_fenced_entries_fail(self):
        md='# Intro\nBody.\n\n# Methods\nMore body.'
        for outline in ('0 | Intro','7 | Intro','1 Intro','1 | Missing','1 | Methods\n1 | Intro'):
            with self.subTest(outline=outline),self.assertRaises(ValueError):tools.paper_apply_outline(md,outline)
        with self.assertRaisesRegex(ValueError,'fenced'):
            tools.paper_apply_outline('# Intro\nBody.\n```\nCode title\n```','1 | Intro\n2 | Code title')


class OutlineNotebookTests(unittest.TestCase):
    def state(self):
        s=notebook_state();s['paper_cleaned'].value='# Introduction\nOpening.\n\n# Results\nA finding.'
        return s

    def test_outline_uses_a_width_sensitive_content_mirror(self):
        s=self.state()
        self.assertEqual(s['paper_outline'].layout.height,'100%')
        self.assertEqual(s['paper_outline_box'].layout.overflow,'visible')
        draft='1 | A <long> title\n' * 40
        s['paper_outline'].value=draft
        self.assertIn('A &lt;long&gt; title',s['paper_outline_sizer'].value)
        self.assertEqual(s['paper_outline_sizer'].value.count('A &lt;long&gt; title'),40)
        self.assertIsNone(s['paper_outline_status'].layout.height)

    def test_field_syncs_live_and_apply_changes_markdown_and_preserves_labels(self):
        s=self.state()
        self.assertEqual(s['paper_outline'].value,'1 | Introduction\n1 | Results')
        unit=s['paper_state']['document']['units'][1]
        s['paper_state']['dropdowns'][unit['id']].value='Results'
        s['paper_outline'].value='1 | Introduction\n2 | Results'
        self.assertTrue(s['paper_save_button'].disabled)
        s['paper_apply_outline_button'].click()
        self.assertIn('## Results',s['paper_cleaned'].value)
        self.assertEqual(s['paper_state']['document']['units'][1]['category'],'Results')
        self.assertEqual(s['paper_state']['document']['units'][1]['level'],2)
        self.assertFalse(s['paper_save_button'].disabled)
        s['paper_cleaned'].value=s['paper_cleaned'].value.replace('## Results','### Findings')
        self.assertEqual(s['paper_outline'].value,'1 | Introduction\n3 | Findings')

    def test_pending_draft_is_preserved_on_markdown_edit_until_apply_or_refresh(self):
        s=self.state();s['paper_state']['unsaved']=False
        s['paper_outline'].value='2 | Introduction\n1 | Results'
        s['paper_cleaned'].value=s['paper_cleaned'].value.replace('Opening.','A changed opening.')
        self.assertEqual(s['paper_outline'].value,'2 | Introduction\n1 | Results')
        self.assertTrue(s['paper_has_unsaved_work']())
        self.assertTrue(s['paper_copy_table_button'].disabled)
        s['paper_refresh_outline_button'].click()
        self.assertEqual(s['paper_outline'].value,'1 | Introduction\n1 | Results')
        self.assertFalse(s['paper_state']['outline_dirty'])
        self.assertFalse(s['paper_save_button'].disabled)
        # Reverting a draft also refreshes it if the Markdown title changed meanwhile.
        s['paper_outline'].value='2 | Introduction\n1 | Results'
        s['paper_cleaned'].value=s['paper_cleaned'].value.replace('# Results','# Findings')
        s['paper_outline'].value='1 | Introduction\n1 | Results'
        self.assertEqual(s['paper_outline'].value,'1 | Introduction\n1 | Findings')

    def test_invalid_outline_preserves_text_and_document_and_blocks_stale_saves(self):
        s=self.state();before=copy.deepcopy(s['paper_state']['document']);text=s['paper_cleaned'].value
        s['paper_outline'].value='1 | Missing'
        s['paper_apply_outline_button'].click()
        self.assertEqual(s['paper_state']['document'],before)
        self.assertEqual(s['paper_cleaned'].value,text)
        self.assertIn('not found',s['paper_outline_status'].value)
        with tempfile.TemporaryDirectory() as tmp:
            s['paper_folder'].value=tmp;s['paper_save']()
            self.assertIn('Apply reviewed outline',s['paper_save_status'].value)
        with patch.object(s['shutil'],'which',return_value=None):s['paper_copy_summary']()
        self.assertEqual(s['paper_copy_fallback'].value,'')

    def test_load_synchronizes_outline_and_legacy_virtual_counts_survive_apply(self):
        s=self.state();text='First paragraph.\n\nSecond paragraph.'
        doc=tools.paper_make_document(text,'')
        doc=tools.paper_select_range(doc,text.index('Second'),len(text),'Data','Legacy text section')
        s['paper_load_document'](tools.paper_export_document(doc))
        self.assertEqual(s['paper_outline'].value,'1 | Legacy text section')
        s['paper_outline'].value='2 | Legacy text section';s['paper_apply_outline_button'].click()
        self.assertEqual(s['paper_state']['document']['units'][1]['category'],'Data')
        self.assertNotIn('Legacy text section',s['paper_state']['document']['cleaned_text'])
        self.assertEqual(sum(tools.paper_unit_counts(u)['words'] for u in doc['units']),sum(tools.paper_unit_counts(u)['words'] for u in s['paper_state']['document']['units']))
        self.assertTrue(s['paper_is_current']())

if __name__=='__main__':unittest.main()
