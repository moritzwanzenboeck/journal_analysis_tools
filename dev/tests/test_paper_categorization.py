import copy
import csv
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import nbformat

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT/'clean_and_count_text.ipynb'
PAPER=('Front matter.\n1. Introduction\nA socio-\neconomic question?\n'
       '2. Methods\nAn overview.\n2.1 Data\nThe sample is useful.12\n'
       '2.2 Estimation\nResult (𝑝<.1\n).\n3. Conclusion\nWe conclude!\nReferences\nA reference.')


def notebook_state():
    state={}
    n=nbformat.read(NOTEBOOK,as_version=4)
    nbformat.validate(n)
    with patch('IPython.display.display'):
        for i,c in enumerate(n.cells):
            if c.cell_type=='code': exec(compile(c.source,f'cell {i}','exec'),state)
    return state


def populate(state):
    state['paper_original'].value=PAPER
    state['paper_find_button'].click()
    state['paper_keep'].value=(0,)
    state['paper_clean_button'].click()
    assert state['paper_is_current']()
    return state['paper_state']['document']


class FullPaperTests(unittest.TestCase):
    def setUp(self):
        self.s=notebook_state()

    def test_hierarchy_totals_and_existing_rules(self):
        s=self.s; doc=populate(s)
        units=doc['units']
        self.assertEqual([u['title'] for u in units], ['', '1. Introduction','2. Methods','2.1 Data','2.2 Estimation','3. Conclusion','References'])
        self.assertIn('socio-economic',units[1]['body'])
        self.assertEqual(units[4]['body'],'Result (𝑝<.1).')
        units[0]['category']=s['PAPER_EXCLUDED']
        units[2]['category']='Methods';units[3]['category']='Data';units[4]['category']='Results'
        rows=s['paper_summary'](doc)
        self.assertEqual(rows['Methods']['paragraphs'],1)
        self.assertEqual(rows['Data']['section_titles'],['2. Methods'])
        self.assertEqual(rows['Data']['subsection_titles'],['2.1 Data'])
        self.assertEqual(sum(row['words'] for row in rows.values()),len(s['WORD'].findall(doc['cleaned_text'])))
        self.assertEqual(sum(row['paragraphs'] for row in rows.values()),7)
        before=sum(row['words'] for row in rows.values())
        doc['include_heading_words']=False
        self.assertEqual(sum(row['words'] for row in s['paper_summary'](doc).values()), before-sum(len(s['WORD'].findall(u['title'])) for u in units))

    def test_plain_numbered_and_unnumbered_headings_and_duplicates(self):
        s=self.s
        text=s['paper_clean_text']('Introduction\nBody?\n2 Methods\nOverview.\n2.1 Sample\nFirst.\n2.2 Sample\nSecond!')
        headings=s['paper_detect_headings'](text)
        self.assertEqual([h['level'] for h in headings],[1,1,2,2])
        doc=s['paper_make_document'](text,s['paper_outline_text'](headings))
        doc['units'][2]['category']='Data';doc['units'][3]['category']='Results'
        new=s['paper_make_document'](text,s['paper_outline_text'](headings),previous=doc)
        self.assertEqual([u['category'] for u in new['units']],[s['PAPER_UNASSIGNED'],s['PAPER_UNASSIGNED'],'Data','Results'])
        validated=s['paper_validate_document'](s['paper_export_document'](new))
        self.assertEqual(validated,new)
        whole=s['paper_make_document']('A paper without headings.','')
        self.assertEqual(len(whole['units']),1)
        self.assertEqual(whole['units'][0]['body'],'A paper without headings.')

    def test_save_reload_relabel_and_overwrite_protection(self):
        s=self.s; doc=populate(s)
        s['paper_state']['dropdowns'][doc['units'][3]['id']].value='Data'
        with tempfile.TemporaryDirectory() as temporary:
            s['paper_folder'].value=temporary;s['paper_name'].value='Author_2026'
            s['paper_save_button'].click()
            text=Path(temporary)/'Author_2026_cleaned.txt';data=Path(temporary)/'Author_2026_categories.json'
            self.assertTrue(data.is_file(),s['paper_save_status'].value)
            self.assertEqual(text.read_text(),doc['cleaned_text'])
            saved=json.loads(data.read_text())
            saved['units'][3]['counts']={'words':999999,'paragraphs':999999}
            s['paper_load_document'](saved)
            self.assertEqual(s['paper_state']['document']['units'][3]['category'],'Data')
            self.assertNotEqual(s['paper_summary'](s['paper_state']['document'])['Data']['words'],999999)
            s['paper_state']['dropdowns'][doc['units'][3]['id']].value='Results'
            original=data.read_bytes()
            s['paper_save_button'].click()
            self.assertEqual(data.read_bytes(),original)
            self.assertIn('already exist',s['paper_save_status'].value)
            s['paper_overwrite'].value=True;s['paper_save_button'].click()
            self.assertEqual(json.loads(data.read_text())['units'][3]['category'],'Results')
            s['paper_upload_changed']({'new':({'name':'saved.json','content':memoryview(data.read_bytes())},)})
            self.assertEqual(s['paper_state']['document']['units'][3]['category'],'Results')

    def test_failed_publication_restores_both_previous_files(self):
        s=self.s;doc=populate(s)
        with tempfile.TemporaryDirectory() as temporary:
            paths=s['paper_save_files'](doc,temporary,'paper')
            old=[p.read_bytes() for p in paths]
            doc['units'][1]['category']='Introduction'
            real=Path.replace
            def fail_second(source,target):
                if source.name=='1' and Path(target)==paths[1]: raise OSError('Disk failure')
                return real(source,target)
            with patch.object(Path,'replace',autospec=True,side_effect=fail_second):
                with self.assertRaisesRegex(OSError,'Disk failure'):
                    s['paper_save_files'](doc,temporary,'paper',True)
            self.assertEqual([p.read_bytes() for p in paths],old)
            self.assertFalse(list(Path(temporary).glob('.paper-save-*')))

    def test_parent_assignment_child_override_and_suggestions(self):
        s=self.s;doc=populate(s)
        parent=doc['units'][2]
        s['paper_state']['dropdowns'][parent['id']].value='Methods'
        row=s['paper_section_rows'].children[2]
        button=next(child for child in row.children if getattr(child,'description','')=='Apply to subsections')
        button.click()
        self.assertEqual(doc['units'][3]['category'],'Methods')
        self.assertEqual(doc['units'][4]['category'],'Methods')
        s['paper_state']['dropdowns'][doc['units'][3]['id']].value='Data'
        s['paper_suggest_button'].click()
        self.assertEqual(doc['units'][3]['category'],'Data')
        self.assertEqual(doc['units'][1]['category'],'Introduction')
        self.assertEqual(doc['units'][5]['category'],'Conclusion')
        self.assertEqual(doc['units'][6]['category'],'Unassigned')

    def test_dirty_edits_disable_stale_counts_and_rebuild_retains_labels(self):
        s=self.s;doc=populate(s)
        uid=doc['units'][1]['id'];s['paper_state']['dropdowns'][uid].value='Introduction'
        text=s['paper_cleaned'].value
        s['paper_cleaned'].value=text+'\n\nAdditional paragraph.'
        self.assertTrue(s['paper_save_button'].disabled)
        self.assertTrue(s['paper_copy_table_button'].disabled)
        self.assertEqual(s['paper_section_rows'].children,())
        s['paper_cleaned'].value=text
        self.assertFalse(s['paper_save_button'].disabled)
        s['paper_cleaned'].value=text.replace('A socio-economic question?','A changed socio-economic question?')
        s['paper_rebuild_button'].click()
        self.assertTrue(s['paper_is_current']())
        self.assertEqual(s['paper_state']['document']['units'][1]['category'],'Introduction')
        before=copy.deepcopy(s['paper_state']['document'])
        s['paper_outline'].value='1 | Missing heading'
        s['paper_rebuild_button'].click()
        self.assertIn('not found',s['paper_status'].value)
        self.assertEqual(s['paper_state']['document'],before)

    def test_summary_copy_native_and_fallback_and_legacy_independence(self):
        s=self.s
        s['original_editor'].value='Old input.';s['cleaned_editor'].value='Legacy result.'
        doc=populate(s);s['paper_state']['dropdowns'][doc['units'][3]['id']].value='Data'
        grid=s['paper_summary_box'].children[0]
        words_button=grid.children[5+3*5+3].children[1]
        expected=str(s['paper_summary'](doc)['Data']['words'])
        for system,encoding in [('darwin','utf-8'),('win32','utf-16-le')]:
            with patch.object(s['sys'],'platform',system), patch.object(s['shutil'],'which',return_value='clipboard'), \
                 patch.object(s['subprocess'],'CREATE_NO_WINDOW',0x08000000,create=True), patch.object(s['subprocess'],'run') as run:
                words_button.click()
                self.assertEqual(run.call_args.kwargs['input'].decode(encoding),expected)
                s['paper_copy_table_button'].click()
                self.assertIn('Category\tSection titles\tSubsection titles\tWords\tParagraphs',run.call_args.kwargs['input'].decode(encoding))
        with patch.object(s['shutil'],'which',return_value=None): words_button.click()
        self.assertEqual(s['paper_copy_fallback'].value,expected)
        self.assertEqual(s['original_editor'].value,'Old input.')
        self.assertEqual(s['cleaned_editor'].value,'Legacy result.')
        clean=s['paper_cleaned'].value;s['paper_clear_button'].click()
        self.assertEqual(s['paper_cleaned'].value,clean)
        self.assertTrue(s['paper_is_current']())

    def test_invalid_load_keeps_current_paper_and_invalid_names_do_not_write(self):
        s=self.s;doc=populate(s);before=copy.deepcopy(doc)
        for field,value in [('schema_version',2),('units',[]),('cleaned_text','Completely different.')]:
            bad=copy.deepcopy(doc);bad[field]=value
            with self.assertRaises(ValueError): s['paper_load_document'](bad)
            self.assertEqual(s['paper_state']['document'],before)
        bad=copy.deepcopy(doc);bad['units'][1]['category']='Unknown'
        with self.assertRaises(ValueError):s['paper_load_document'](bad)
        with tempfile.TemporaryDirectory() as temporary:
            for name in ('../escape','bad:name','bad/name','bad\\name',''):
                with self.assertRaises(ValueError):s['paper_save_files'](doc,temporary,name)
            self.assertEqual(list(Path(temporary).iterdir()),[])

class ProjectPaperTests(unittest.TestCase):
    def make_project(self, directory):
        root=Path(directory)/'project'
        (root/'output').mkdir(parents=True)
        config={'schema_version':1,'journal':'Example Journal','sample_export':'output/example_random2.csv','sample_size':2}
        (root/'project.json').write_text(json.dumps(config))
        with (root/config['sample_export']).open('w',encoding='utf-8-sig',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=['doi','title','authors','bibtex_key','url'])
            writer.writeheader()
            writer.writerows([{'doi':f'10.1234/paper{n}','title':f'Sampled paper {n}','authors':'Example Author','bibtex_key':f'paper{n}'} for n in (1,2)])
        return root

    def test_reusable_model_and_notebook_remain_in_sync(self):
        from app import paper_tools
        n=nbformat.read(NOTEBOOK,as_version=4)
        source=next(cell.source for cell in n.cells if 'def paper_make_document' in cell.source)
        functions={node.name:ast.dump(node,include_attributes=False) for node in ast.parse(source).body if isinstance(node,ast.FunctionDef)}
        reusable={node.name:ast.dump(node,include_attributes=False) for node in ast.parse((ROOT/'app/paper_tools.py').read_text()).body if isinstance(node,ast.FunctionDef)}
        self.assertEqual(functions,reusable)
        self.assertEqual(paper_tools.PAPER_CATEGORIES,('Introduction','Literature Review','Theory','Data','Methods','Results','Discussion','Conclusion'))

    def test_project_detection_sample_list_and_saved_json_scan(self):
        from app import paper_tools as tools
        with tempfile.TemporaryDirectory() as temporary:
            root=self.make_project(temporary)
            nested=root/'nested';nested.mkdir()
            context=tools.paper_find_project(nested)
            self.assertEqual(context['root'],root.resolve())
            self.assertEqual(len(context['papers']),2)
            self.assertFalse(context['save_directory'].exists())
            doc=tools.paper_make_document('1. Introduction\nA result.','1 | 1. Introduction',paper_metadata=context['papers'][0])
            doc['paper_name']=tools.paper_project_prefix(context['papers'][0])
            first=tools.paper_save_in_project(doc,context)
            self.assertEqual(first[0].parent,root.resolve()/'paper_categorizations')
            (root/'archive').mkdir()
            legacy=root/'archive/old.json';legacy.write_text(json.dumps(tools.paper_export_document(doc)))
            (root/'output/raw.json').write_text(json.dumps([{'DOI':'10.1234/raw'}]))
            saved=tools.paper_saved_in_project(context)
            self.assertEqual({item['path'] for item in saved},{first[1],legacy.resolve()})
            self.assertEqual({item['doi'] for item in saved},{'10.1234/paper1'})
            # Schema-v1 files made before project metadata was introduced still load.
            old=tools.paper_export_document(doc);old.pop('paper_metadata');old.pop('project_metadata')
            self.assertEqual(tools.paper_validate_document(old)['paper_metadata'],{})

    def test_project_controls_keep_saves_in_one_folder_and_reopen_papers(self):
        s=notebook_state()
        with tempfile.TemporaryDirectory() as temporary:
            root=self.make_project(temporary)
            outside=Path(temporary)/'outside';outside.mkdir()
            s['paper_project_folder'].value=str(root);s['paper_scan_project_button'].click()
            self.assertTrue(s['paper_folder'].disabled)
            self.assertEqual(len(s['paper_sample_choice'].options),3)
            s['paper_sample_choice'].value='10.1234/paper1';s['paper_use_sample_button'].click()
            s['paper_original'].value='1. Introduction\nFirst result.';s['paper_clean_button'].click()
            doc=s['paper_state']['document']
            s['paper_state']['dropdowns'][doc['units'][0]['id']].value='Introduction'
            # Changing a disabled UI value programmatically still cannot redirect saves.
            s['paper_folder'].value=str(outside)
            s['paper_save_button'].click()
            self.assertEqual(list(outside.iterdir()),[])
            saved=next((root/'paper_categorizations').glob('*_categories.json'))
            data=json.loads(saved.read_text())
            self.assertEqual(data['paper_metadata']['doi'],'10.1234/paper1')
            self.assertEqual(len(s['paper_state']['saved_files']),1)
            s['paper_sample_choice'].value='10.1234/paper2';s['paper_use_sample_button'].click()
            self.assertEqual(s['paper_original'].value,'')
            s['paper_original'].value='2. Methods\nA second result.';s['paper_clean_button'].click()
            s['paper_sample_choice'].value='10.1234/paper1';s['paper_use_sample_button'].click()
            self.assertEqual(s['paper_state']['active_paper']['doi'],'10.1234/paper2')
            self.assertIn('Save the current paper',s['paper_status'].value)
            s['paper_replace_current'].value=True;s['paper_use_sample_button'].click()
            self.assertEqual(s['paper_state']['active_paper']['doi'],'10.1234/paper1')
            self.assertEqual(s['paper_state']['document']['units'][0]['category'],'Introduction')
            self.assertEqual(s['paper_folder'].value,str(root.resolve()/'paper_categorizations'))
            # Loading an older categorization from another subfolder keeps the fixed save root.
            archived=root/'old.json';archived.write_text(json.dumps(data))
            s['paper_scan_project_button'].click()
            self.assertIn(str(archived.resolve()),[value for _,value in s['paper_saved_choice'].options])
            s['paper_saved_choice'].value=str(archived.resolve());s['paper_load_saved_button'].click()
            self.assertEqual(s['paper_folder'].value,str(root.resolve()/'paper_categorizations'))

    def test_preview_fully_hides_and_summary_widgets_stay_identical(self):
        s=notebook_state();doc=populate(s)
        grid=s['paper_state']['summary_grid'];children=grid.children
        for i,unit in enumerate(doc['units']):
            s['paper_state']['dropdowns'][unit['id']].value=s['PAPER_CATEGORIES'][i%8]
            self.assertIs(s['paper_state']['summary_grid'],grid)
            self.assertEqual(s['paper_state']['summary_grid'].children,children)
        uid=doc['units'][1]['id'];control=s['paper_state']['preview_buttons'][uid]
        control.click()
        self.assertEqual(s['paper_preview_panel'].layout.display,'flex')
        self.assertTrue(s['paper_preview'].value)
        control.click()
        self.assertEqual(s['paper_preview_panel'].layout.display,'none')
        self.assertEqual(s['paper_preview'].value,'')
        self.assertEqual(s['paper_preview_title'].value,'')
        control.click();s['paper_hide_text_button'].click()
        self.assertEqual(s['paper_preview_panel'].layout.display,'none')
        self.assertEqual(grid.layout.grid_template_rows,'36px repeat(8, 156px)')
        for value,button in s['paper_state']['summary_cells'].values():
            self.assertEqual(value.layout.height,'102px')
            self.assertEqual(button.layout.height,'32px')
        # Existing copy buttons must use the latest values without recreating the controls.
        unit=doc['units'][1];s['paper_state']['dropdowns'][unit['id']].value='Data'
        button=s['paper_state']['summary_cells'][('Data','words')][1]
        expected=str(s['paper_summary'](doc)['Data']['words'])
        with patch.object(s['shutil'],'which',return_value=None):button.click()
        self.assertEqual(s['paper_copy_fallback'].value,expected)

if __name__=='__main__':unittest.main()
