"""Spreadsheet summary metrics, abstract sources, zero/missing entries and copying."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import paper_tools as tools
import test_paper_categorization as paper_tests


def document():
    text=('Abstract\n\nA short abstract.\n\n1. Introduction\n\nFirst question.\n\n'
          '1.1 Background\n\nFurther context.\n\n2. Results and discussion\n\nA finding.\n\n'
          'References\n\nAn excluded reference.')
    doc=tools.paper_make_document(text,tools.paper_outline_text(tools.paper_detect_headings(text)))
    categories=['Exclude from summary','Introduction','Introduction','Results','Exclude from summary']
    assert len(doc['units'])==len(categories)
    for unit,category in zip(doc['units'],categories):unit['category']=category
    return doc


class ReportMetricsTests(unittest.TestCase):
    def test_only_own_top_level_titles_count_once_and_body_counts_include_subsections(self):
        doc=document()
        doc['units'][2]['category']='Data'
        metrics=tools.paper_report_metrics(doc)
        summary={'custom_categories':[], 'papers':[{'paper':{'sample_number':1,'title':'Article','doi':'10.1234/test'},
                 'rows':tools.paper_summary(doc),'metrics':metrics,'status':'Complete'}]}
        tables=tools.paper_report_tables(summary)
        overview=tables[0]
        self.assertNotIn('Content',overview['columns'])
        # Title words use the same WORD rule, including printed section numbers.
        self.assertEqual(overview['rows'][0][:7],[1,2,15,3,6,3,3])
        data=next(t for t in tables if t.get('category')=='Data')['rows'][0]
        self.assertIsNone(data[1])  # A Data subsection supplies no own top-level heading.
        self.assertEqual(data[2],5)
        introduction=next(t for t in tables if t.get('category')=='Introduction')['rows'][0]
        self.assertEqual(introduction[1],2)
        doc['include_heading_words']=False
        self.assertEqual(tools.paper_report_metrics(doc)['words'],6)
        # Turning heading words off affects body totals but leaves title statistics meaningful.
        metrics2=tools.paper_report_metrics(doc)
        self.assertEqual(sum(h['words'] for h in metrics2['headings'] if h['level']==1),6)

    def test_abstract_prefers_cleaned_body_then_metadata_and_has_no_false_zero(self):
        doc=document()
        self.assertEqual(tools.paper_abstract_count(doc,{'abstract':'Metadata with different words.'}),
                         {'words':3,'source':'Cleaned paper'})
        doc=tools.paper_make_document('1. Intro\nA paragraph.','1 | 1. Intro',paper_metadata={'abstract':'A saved abstract.'})
        self.assertEqual(tools.paper_abstract_count(doc)['words'],3)
        self.assertEqual(tools.paper_abstract_count(doc,{'abstract':'Project abstract.'})['words'],2)
        self.assertEqual(tools.paper_abstract_count()['words'],None)
        self.assertEqual(tools.paper_abstract_count(metadata={'abstract':''})['words'],None)
        nested=tools.paper_make_document('Abstract\nOpening.\nSummary details\nMore body.\n1. Intro\nBody.',
            '1 | Abstract\n2 | Summary details\n1 | 1. Intro')
        self.assertEqual(tools.paper_abstract_count(nested)['words'],3)

    def test_virtual_section_counts_without_synthetic_title_words(self):
        doc=tools.paper_make_document('First paragraph.\n\nSecond paragraph.','')
        doc=tools.paper_select_range(doc,0,len(doc['cleaned_text']),'Methods','A synthetic heading')
        metrics=tools.paper_report_metrics(doc)
        summary={'custom_categories':[], 'papers':[{'paper':{'sample_number':1,'title':'Paper','doi':'10.1234/test'},
                 'rows':tools.paper_summary(doc),'metrics':metrics,'status':'Complete'}]}
        row=tools.paper_report_tables(summary)[0]['rows'][0]
        self.assertEqual(row[1],1)
        self.assertEqual(row[4],0)
        self.assertIsNone(row[5])
        self.assertEqual(row[2],4)

    def test_statistics_ignore_zeros_missing_and_invalid_files_mark_every_tie(self):
        doc=document();metrics=tools.paper_report_metrics(doc)
        papers=[]
        for number,words in enumerate([10,0,30,10,None],1):
            rows=tools.paper_summary(doc) if words is not None else None
            if rows:rows['Introduction']['words']=words
            papers.append({'paper':{'sample_number':number,'title':f'Paper {number}','doi':f'10.1234/{number}'},
                           'rows':rows,'metrics':metrics if rows else None,'status':'Complete' if rows else 'Not saved'})
        report=tools.paper_report_tables({'papers':papers,'custom_categories':[]})
        intro=next(t for t in report if t.get('category')=='Introduction')
        self.assertEqual(intro['rows'][-1],["Summary","",50/3,10,30,""])
        self.assertEqual(intro['columns'][2],'Sum words')
        self.assertNotIn('Average',intro['columns'])
        copied=list(csv.reader(io.StringIO(tools.paper_report_tsv([intro])),delimiter='\t'))
        self.assertEqual(copied[-1][2],'16.666666667')
        self.assertEqual([r[3] for r in intro['rows'][:-1]],['x','','','x',''])
        self.assertEqual([r[4] for r in intro['rows'][:-1]],['','','x','',''])
        self.assertEqual(intro['rows'][1][2],0)
        self.assertIsNone(intro['rows'][4][2])
        absent=next(t for t in report if t.get('category')=='Theory')
        self.assertEqual(absent['rows'][-1],["Summary","",None,None,None,""])
        single=tools.paper_report_tables({'papers':[papers[0]],'custom_categories':[]})[1]
        self.assertEqual(single['rows'][0][3:5],['x','x'])
        self.assertIsNone(report[0]['rows'][-1][1])

    def test_custom_category_overview_has_a_distinct_table_key(self):
        tables=tools.paper_report_tables({'custom_categories':['overview'],'papers':[]})
        self.assertEqual(tables[0]['key'],'overview')
        self.assertEqual(next(t for t in tables if t.get('category')=='overview')['key'],'category:overview')
        self.assertEqual(len({t['key'] for t in tables}),len(tables))

    def test_excel_export_has_vertical_blocks_no_content_and_safe_decimals(self):
        table={'title':'Custom\tcategory','key':'custom','columns':['Article no.','Words per title'],
               'rows':[[1,13/3],[2,None],[3,0]]}
        result=tools.paper_report_tsv([table,table])
        rows=list(csv.reader(io.StringIO(result),delimiter='\t'))
        self.assertEqual(rows[0],['Custom\tcategory'])
        self.assertEqual(rows[2],['1','4.333333333'])
        self.assertEqual(rows[3],['2',''])
        self.assertEqual(rows[4],['3','0'])
        self.assertEqual(rows[5],[])
        self.assertNotIn('#DIV/0!',result)
        self.assertEqual(tools.paper_report_value(2.0),'2')


class ReportIntegrationTests(unittest.TestCase):
    def test_project_csv_abstract_available_for_saved_and_unprocessed_papers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=paper_tests.ProjectPaperTests().make_project(tmp)
            csv_path=root/'output/example_random2.csv'
            rows=list(csv.DictReader(io.StringIO(csv_path.read_text(encoding='utf-8-sig'))))
            for row in rows:row['abstract']='Project abstract text.'
            with csv_path.open('w',newline='',encoding='utf-8-sig') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            context=tools.paper_read_project(root)
            doc=tools.paper_make_document('1. Intro\nBody.','1 | 1. Intro',paper_metadata={'doi':rows[0]['doi']})
            doc['units'][0]['category']='Introduction'
            tools.paper_save_in_project(doc,context,'paper1')
            summary=tools.paper_project_summary(context)
            report=tools.paper_report_tables(summary)
            self.assertEqual([row[6] for row in report[0]['rows']],[3,3])
            self.assertIsNone(report[0]['rows'][1][2])
            self.assertEqual(summary['papers'][0]['metrics']['abstract']['source'],'Project metadata')

    def test_notebook_report_copies_current_values_and_reuses_controls(self):
        s=paper_tests.notebook_state()
        with tempfile.TemporaryDirectory() as tmp:
            root=paper_tests.ProjectPaperTests().make_project(tmp)
            s['paper_project_folder'].value=str(root);s['paper_scan_project_button'].click()
            context=s['paper_state']['project']
            doc=document();doc['paper_metadata']=dict(context['papers'][0])
            path=tools.paper_save_in_project(doc,context,'paper1')[1]
            s['workflow_tabs'].selected_index=2
            overview=s['paper_state']['project_report_blocks']['overview'][0]
            self.assertIn('Total words in titles',overview.value)
            self.assertEqual(s['project_summary_status'].layout.min_height,'76px')
            self.assertGreater(s['project_summary_workflow'].children.index(s['project_summary_fallback_box']),s['project_summary_workflow'].children.index(s['project_summary_details']))
            self.assertNotIn('<th scope="col">Content</th>',overview.value)
            self.assertIsNone(overview.layout.max_height)
            self.assertEqual(overview.layout.overflow,'visible')
            self.assertEqual(s['paper_state']['project_summary_grid'].layout.width,'100%')
            for value,button in s['paper_state']['project_summary_cells'].values():
                self.assertIsNone(value.layout.max_height)
                self.assertEqual(value.layout.overflow,'visible')
                self.assertEqual(button.icon,'copy')
            blocks=dict(s['paper_state']['project_report_blocks'])
            s['project_summary_refresh_button'].click()
            for key,controls in blocks.items():self.assertEqual(s['paper_state']['project_report_blocks'][key],controls)
            with patch.object(s['shutil'],'which',return_value=None):
                s['project_summary_copy_button'].click()
            exported=s['project_summary_fallback'].value
            self.assertIn('Article overview',exported)
            self.assertIn('Summary',exported)
            self.assertIn('Words per abstract',exported)
            self.assertNotIn('#DIV/0!',exported)
            # Change a label on a valid saved document rather than changing its structural text.
            value=json.loads(path.read_text());value['units'][1]['category']='Theory'
            path.write_text(json.dumps(value))
            s['project_summary_refresh_button'].click()
            with patch.object(s['shutil'],'which',return_value=None):
                blocks['category:Theory'][1].click()
            copied=s['project_summary_fallback'].value
            self.assertTrue(copied.startswith('Theory\n'))
            self.assertNotIn('Article overview',copied)
            self.assertIn('Summary',copied)

if __name__=='__main__':unittest.main()
