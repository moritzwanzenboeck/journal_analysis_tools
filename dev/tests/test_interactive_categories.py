"""Selection boundaries, project categories, legacy reload and project-wide totals."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import paper_tools as tools
from app.text_tools import WORD, clean_text
from test_paper_categorization import notebook_state
import test_paper_categorization as paper_tests


class SelectedTextTests(unittest.TestCase):
    def test_inline_selection_editor_matches_development_source(self):
        import ast
        import nbformat
        root=Path(__file__).resolve().parents[2]
        notebook=nbformat.read(root/'clean_and_count_text.ipynb',as_version=4)
        inline=next(c.source for c in notebook.cells if 'class PaperSelectionEditor' in c.source)
        def editor(source):
            return next(ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='PaperSelectionEditor')
        self.assertEqual(editor(inline),editor((root/'dev/selection_widget.py').read_text()))

    def test_bare_numbered_subsections_survive_cleanup(self):
        raw='1. Introduction\nOpening.\n2.2\nWe examine the data.\n2.3.\nA final result!'
        text=tools.paper_clean_text(raw)
        headings=tools.paper_detect_headings(text)
        self.assertEqual([(h['title'],h['level']) for h in headings],[('1. Introduction',1),('2.2',2),('2.3.',2)])
        self.assertIn('2.2\n\nWe',text)
        self.assertFalse(tools.paper_detect_headings('0.001\n0.1'))
        doc=tools.paper_make_document('2.2\n\nThe data.','2 | 2.2')
        doc['units'][0]['category']='Data'
        self.assertEqual(tools.paper_summary(doc)['Data']['section_titles'],[])
        self.assertEqual(tools.paper_summary(doc)['Data']['subsection_titles'],['2.2'])
        self.assertIn('2.2\n',clean_text(raw))

    def test_assign_reassign_remove_unheaded_text_and_roundtrip(self):
        text='First opening paragraph.\n\n𝑝 values guide our method.\n\nThe final result!'
        doc=tools.paper_make_document(text,'')
        start=text.index('𝑝');end=text.index('\n\nThe')
        split=tools.paper_select_range(doc,start,end,'Methods','Empirical approach',2)
        self.assertEqual(split['cleaned_text'],text)
        self.assertEqual([u['category'] for u in split['units']],['Unassigned','Methods','Unassigned'])
        summary=tools.paper_summary(split)
        self.assertEqual(summary['Methods']['words'],len(WORD.findall(text[start:end])))
        self.assertEqual(sum(r['words'] for r in summary.values()),len(WORD.findall(text)))
        self.assertEqual(sum(r['paragraphs'] for r in summary.values()),3)
        self.assertEqual(tools.paper_validate_document(tools.paper_export_document(split)),split)
        again=tools.paper_select_range(split,start,end,'Data','',1)
        self.assertEqual(len(again['units']),3)
        self.assertEqual(again['units'][1]['category'],'Data')
        changed=tools.paper_edit_heading(again,start,start,1)
        self.assertEqual(changed['units'][1]['level'],1)
        removed=tools.paper_edit_heading(changed,start,start)
        self.assertEqual(len(removed['units']),2)
        self.assertEqual(removed['units'][0]['category'],'Unassigned')
        self.assertEqual(removed['cleaned_text'],text)
        self.assertEqual(sum(tools.paper_unit_counts(u)['words'] for u in removed['units']),len(WORD.findall(text)))

    def test_heading_marking_relevel_deletion_and_ambiguous_duplicates(self):
        text='A question. Same title\n\nOther prose. Same title\n\nMore body.'
        doc=tools.paper_make_document(text,'')
        start=text.rindex('Same title');end=start+len('Same title')
        changed=tools.paper_edit_heading(doc,start,end,2)
        heading=next(u for u in changed['units'] if u['level'])
        self.assertEqual(heading['heading_line'],5)
        self.assertEqual(heading['title'],'Same title')
        rebuilt=tools.paper_make_document(changed['cleaned_text'],'2 | Same title',previous=changed)
        self.assertEqual(rebuilt['units'][1]['heading_line'],5)
        self.assertEqual(tools.paper_validate_document(tools.paper_export_document(changed)),changed)
        relevel=tools.paper_edit_heading(changed,heading['start'],heading['start'],1)
        self.assertEqual(relevel['units'][1]['level'],1)
        removed=tools.paper_edit_heading(relevel,heading['start'],heading['start'])
        self.assertEqual(len(removed['units']),1)
        self.assertEqual(len(WORD.findall(removed['cleaned_text'])),len(WORD.findall(text)))

    def test_legacy_json_defaults_and_invalid_offsets(self):
        doc=tools.paper_make_document('1. Intro\nBody.','1 | 1. Intro')
        old=copy.deepcopy(doc)
        old.pop('manual_boundaries');old.pop('custom_categories')
        for u in old['units']:
            for key in ('start','end','body_start','virtual'):u.pop(key)
        self.assertEqual(tools.paper_validate_document(old),doc)
        bad=copy.deepcopy(doc);bad['manual_boundaries']=[{'offset':2,'level':1,'title':'Oops'}]
        with self.assertRaises(ValueError):tools.paper_validate_document(bad)
        with self.assertRaisesRegex(ValueError,'heading'):
            tools.paper_select_range(doc,0,len(doc['cleaned_text']),'Data')
        bare=tools.paper_make_document('First paragraph.','')
        with self.assertRaisesRegex(ValueError,'complete words'):
            tools.paper_select_range(bare,1,5,'Data')

    def test_body_selection_before_next_heading_has_no_empty_continuation(self):
        text='1. Intro\n\nFirst paragraph.\n\n2. Results\n\nA result.'
        doc=tools.paper_make_document(text,'1 | 1. Intro\n1 | 2. Results')
        start=text.index('First');end=start+len('First paragraph.')
        changed=tools.paper_select_range(doc,start,end,'Introduction')
        self.assertEqual(len(changed['units']),3)
        self.assertEqual(changed['units'][1]['body'],'First paragraph.')
        self.assertEqual(changed['units'][2]['title'],'2. Results')


class ProjectCategoryTests(unittest.TestCase):
    def project(self,temporary):
        root=paper_tests.ProjectPaperTests().make_project(temporary)
        return tools.paper_read_project(root)

    def save(self,context,number=0,label='Introduction',name=None):
        paper=context['papers'][number]
        doc=tools.paper_make_document('1. Intro\nA paragraph.','1 | 1. Intro',paper_metadata=paper,
            custom_categories=tools.paper_project_categories(context))
        doc['units'][0]['category']=label
        return tools.paper_save_in_project(doc,context,name or tools.paper_project_prefix(paper))

    def test_project_categories_removal_rewrites_all_files_including_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            context=self.project(tmp)
            tools.paper_update_project_categories(context,['Institutions','Mechanisms'])
            self.assertEqual(tools.paper_project_categories(context),['Institutions','Mechanisms'])
            path=self.save(context,label='Institutions')[1]
            archived=context['root']/'archive.json';archived.write_bytes(path.read_bytes())
            self.assertEqual(tools.paper_update_project_categories(context,['Mechanisms']),2)
            for file in (path,archived):
                doc=tools.paper_validate_document(json.loads(file.read_text()))
                self.assertEqual(doc['units'][0]['category'],'Unassigned')
                self.assertEqual(doc['custom_categories'],['Mechanisms'])
            self.assertEqual(tools.paper_categories(doc)[-1],'Not categorizable')
            for names in (['Data'],['data'],['X','x'],['Unassigned'],['Bad\nname']):
                with self.assertRaises(ValueError):tools.paper_update_project_categories(context,names)
            self.assertEqual(tools.paper_project_categories(context),['Mechanisms'])

    def test_category_rewrite_preserves_latest_saved_version_order(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            context=self.project(tmp);tools.paper_update_project_categories(context,['Custom'])
            old=self.save(context,label='Introduction',name='old')[1]
            newest=self.save(context,label='Custom',name='new')[1]
            os.utime(old,(1000000000,1000000000));os.utime(newest,(2000000000,2000000000))
            tools.paper_update_project_categories(context,[])
            summary=tools.paper_project_summary(context)
            self.assertEqual(summary['papers'][0]['path'],newest)
            self.assertEqual(summary['papers'][0]['status'],'1 unassigned')

    def test_text_edit_reset_boundary_workflow_retains_edited_prose(self):
        s=notebook_state()
        s['paper_original'].value='First body paragraph.\nSecond body paragraph.';s['paper_clean_button'].click()
        text=s['paper_cleaned'].value;start=text.index('Second')
        s['paper_cleaned'].selection={'start':start,'end':len(text),'snapshot':text}
        s['paper_selection_category'].value='Methods';s['paper_assign_selection_button'].click()
        edited=text.replace('First body','Changed body')
        s['paper_cleaned'].value=edited;s['paper_rebuild_button'].click()
        self.assertIn('Selected-text boundaries',s['paper_status'].value)
        s['paper_reset_boundaries_button'].click()
        self.assertEqual(s['paper_state']['document']['cleaned_text'],edited)
        self.assertEqual(s['paper_state']['document']['manual_boundaries'],[])
        self.assertTrue(s['paper_is_current']())
        self.assertEqual(len(s['paper_state']['document']['units']),1)
        self.assertEqual(s['paper_state']['document']['units'][0]['category'],'Unassigned')

    def test_failed_category_publication_rolls_back_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            context=self.project(tmp);tools.paper_update_project_categories(context,['Custom'])
            self.save(context,label='Custom');self.save(context,number=1,label='Custom')
            files=list(context['save_directory'].glob('*.json'));before={p:p.read_bytes() for p in files}
            original=Path.replace
            def fail(source,target):
                if source.name=='1':raise OSError('Disk failure')
                return original(source,target)
            with patch.object(Path,'replace',autospec=True,side_effect=fail):
                with self.assertRaises(OSError):tools.paper_update_project_categories(context,[])
            self.assertEqual(before,{p:p.read_bytes() for p in files})

    def test_summary_latest_version_missing_paper_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            context=self.project(tmp)
            self.save(context,label='Introduction',name='old')
            latest=self.save(context,label='Data',name='new')[1]
            import os
            os.utime(latest,(2000000000,2000000000))
            summary=tools.paper_project_summary(context)
            self.assertEqual(summary['rows']['Introduction']['words'],0)
            self.assertEqual(summary['rows']['Data']['words'],4)
            self.assertEqual([p['status'] for p in summary['papers']],['Complete','Not saved'])
            value=json.loads(latest.read_text());value['units'][0]['body']='Corrupt';latest.write_text(json.dumps(value))
            os.utime(latest,(2000000000,2000000000))
            summary=tools.paper_project_summary(context)
            self.assertEqual(summary['papers'][0]['status'],'Invalid saved JSON')
            self.assertEqual(summary['rows']['Data']['words'],0)
            self.assertTrue(summary['errors'])

    def test_notebook_selection_controls_categories_and_summary_tab(self):
        s=notebook_state()
        with tempfile.TemporaryDirectory() as tmp:
            context=self.project(tmp)
            s['paper_project_folder'].value=str(context['root']);s['paper_scan_project_button'].click()
            s['paper_custom_categories'].value='Institutions';s['paper_apply_categories_button'].click()
            s['paper_sample_choice'].value=context['papers'][0]['doi'];s['paper_use_sample_button'].click()
            s['paper_original'].value='First paragraph.\nSecond paragraph.';s['paper_clean_button'].click()
            text=s['paper_cleaned'].value;start=text.index('Second')
            s['paper_cleaned'].selection={'start':start,'end':len(text),'snapshot':text,'text':text[start:]}
            s['paper_selection_category'].value='Institutions';s['paper_assign_selection_button'].click()
            self.assertEqual(s['paper_state']['document']['units'][1]['category'],'Institutions')
            s['paper_save_button'].click()
            s['workflow_tabs'].selected_index=2
            self.assertIn('1/2 papers saved',s['project_summary_status'].value)
            self.assertIn('category:Institutions',s['paper_state']['project_report_blocks'])
            with patch.object(s['shutil'],'which',return_value=None):s['project_summary_copy_button'].click()
            self.assertIn('Article overview',s['project_summary_fallback'].value)
            s['paper_custom_categories'].value='';s['paper_apply_categories_button'].click()
            self.assertEqual(s['paper_state']['document']['units'][1]['category'],'Unassigned')
            self.assertIn(s['paper_project_folder'],s['paper_project_controls'].children)
            self.assertLess(s['paper_workflow'].children.index(s['paper_sample_choice']),s['paper_workflow'].children.index(s['paper_original']))
            # Selection state must match the visible text; stale frontend events cannot change a newer paper.
            before=copy.deepcopy(s['paper_state']['document'])
            s['paper_cleaned'].selection={'start':0,'end':5,'snapshot':'different'}
            s['paper_assign_selection_button'].click()
            self.assertEqual(s['paper_state']['document'],before)


if __name__=='__main__':unittest.main()
