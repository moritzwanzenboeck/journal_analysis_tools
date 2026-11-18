"""Optional browser regression check using only a temporary synthetic project."""
import argparse
import csv
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.notebook_services import NotebookService, SERVICES


def main():
    from playwright.sync_api import sync_playwright, expect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable', help='Optional installed Chrome/Chromium path')
    parser.add_argument('--artifacts', type=Path, help='Keep screenshot/results in this directory')
    parser.add_argument('--without-abort-signal-any',action='store_true',help='Emulate browsers missing AbortSignal.any, including older Safari')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='journal-paper-browser-') as temporary:
        stage = args.artifacts.expanduser().resolve() if args.artifacts else Path(temporary)
        stage.mkdir(parents=True, exist_ok=True)
        # Copy only the notebook: the browser may autosave outputs in this scratch copy.
        root = Path(temporary) / 'tools'
        root.mkdir()
        notebook=json.loads((ROOT/'clean_and_count_text.ipynb').read_text(encoding='utf-8'))
        # Exercise copy fallback without changing the user's real clipboard.
        code=next(c for c in reversed(notebook['cells']) if c['cell_type']=='code')
        code['source']=''.join(code['source']) + "\n_browser_which = shutil.which\nshutil.which = lambda name, *a, **kw: None if name in {'pbcopy','clip.exe'} else _browser_which(name,*a,**kw)\n"
        (root/'clean_and_count_text.ipynb').write_text(json.dumps(notebook),encoding='utf-8')
        project=stage/'browser-project'
        (project/'output').mkdir(parents=True,exist_ok=True)
        (project/'project.json').write_text(json.dumps({'schema_version':1,'journal':'Browser Test Journal','sample_export':'output/random10.csv'}))
        with (project/'output/random10.csv').open('w',newline='',encoding='utf-8-sig') as h:
            w=csv.DictWriter(h,fieldnames=['doi','title','bibtex_key']);w.writeheader()
            w.writerows([{'doi':f'10.1234/test{i}','title':f'Browser paper {i}','bibtex_key':f'test{i}'} for i in range(1,11)])
        service=NotebookService(next(s for s in SERVICES if s.key=='text'),root,log_dir=stage/'browser-logs')
        try:
            service.start()
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.browser_executable,headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.on('dialog',lambda dialog:dialog.dismiss())
                browser_messages=[]
                page.on('console',lambda message:browser_messages.append(message.text) if message.type=='error' else None)
                if args.without_abort_signal_any:
                    page.add_init_script('delete AbortSignal.any;')
                page.goto(service.url,wait_until='domcontentloaded',timeout=60000)
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    kernels=service.request('api/kernels')
                    if kernels and kernels[0].get('execution_state')=='idle': break
                    time.sleep(0.25)
                else:
                    raise RuntimeError('The notebook kernel did not become idle before the browser check.')
                page.get_by_role('menuitem',name='Run',exact=True).click(timeout=60000)
                page.get_by_role('menuitem',name='Run All Cells',exact=True).click()
                try:
                    page.get_by_role('tab',name='Categorize full paper',exact=True).click(timeout=60000)
                except Exception:
                    page.screenshot(path=str(stage/'browser-failure.png'))
                    (stage/'browser-failure.txt').write_text(page.locator('.jp-OutputArea-output').all_text_contents().__repr__())
                    raise
                page.get_by_role('textbox',name='Cleaned paper:',exact=True).wait_for(state='visible',timeout=15000)
                page.get_by_role('textbox',name='Project folder:',exact=True).fill(str(project))
                page.get_by_role('button',name='Scan project folder',exact=True).click()
                page.get_by_role('combobox',name='Sampled paper:',exact=True).select_option(label='1. Browser paper 1')
                page.get_by_role('button',name='Start / reopen paper',exact=True).click()
                lines=['1. Introduction','The opening paragraph.','2. Data','A data overview.']
                for i in range(1,13):
                    lines += [f'2.{i} '+('VeryLongHeadingWord'*5)+f' {i}',f'The body for subsection {i}.']
                lines += ['3. Results','A final result!']
                page.get_by_role('textbox',name='Original paper:',exact=True).fill('\n'.join(lines))
                page.get_by_role('button',name='Clean full paper',exact=True).click()
                page.wait_for_function("document.querySelectorAll('.paper-section-row').length===15")
                grid=page.locator('.paper-summary-grid')
                grid.wait_for(state='attached',timeout=30000)
                grid.scroll_into_view_if_needed()
                metrics='''() => {
                    const grid=document.querySelector('.paper-summary-grid'), r=grid.getBoundingClientRect();
                    return Array.from(grid.querySelectorAll('button')).map(e=>{const b=e.getBoundingClientRect();return {x:b.x-r.x,y:b.y-r.y,w:b.width,h:b.height}})
                }'''
                before=page.evaluate(metrics)
                original_top=grid.evaluate("e=>e.offsetTop")
                page.wait_for_function("document.querySelectorAll('.paper-section-row.paper-unassigned').length===15")
                assert page.locator('.paper-section-row.paper-unassigned').count()==15
                data_row=page.locator('.paper-section-row').filter(has_text='2. Data').first
                data_row.locator('select').select_option(label='Data')
                data_row.get_by_role('button',name='Apply to subsections',exact=True).click()
                page.wait_for_function("document.querySelector('.paper-summary-grid').textContent.includes('VeryLongHeadingWord')")
                after=page.evaluate(metrics)
                assert len(before)==36 and len(after)==36
                assert all(abs(a[k]-b[k])<0.6 for a,b in zip(before,after) for k in ('x','y','w','h')),(before,after)
                overflow=grid.locator('.paper-summary-cell,.paper-summary-content').evaluate_all("es=>es.filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({width:e.clientWidth,scroll:e.scrollWidth,cls:e.className}))")
                assert not overflow,overflow
                page.wait_for_function("document.querySelectorAll('.paper-section-row.paper-unassigned').length===2")
                assert page.locator('.paper-section-row.paper-unassigned').count()==2
                warning=page.locator('.paper-completion-warning')
                assert '2 section(s)' in warning.inner_text()
                intro=page.locator('.paper-section-row').filter(has_text='1. Introduction').first
                intro.locator('select').select_option(label='Not categorizable')
                result=page.locator('.paper-section-row').filter(has_text='3. Results').first
                result.locator('select').select_option(label='Exclude from summary')
                page.wait_for_function("document.querySelectorAll('.paper-section-row.paper-unassigned').length===0")
                assert 'All sections have been categorized' in warning.inner_text()
                assert grid.evaluate("e=>e.offsetTop")==original_top
                assert page.evaluate(metrics)==after
                # Show/hide is a floating inspector; it must not move any table button.
                data_row.get_by_role('button',name='Show text',exact=True).click()
                panel=page.locator('.paper-preview-panel');panel.wait_for(state='visible')
                assert page.evaluate("getComputedStyle(document.querySelector('.paper-preview-panel')).position")=='fixed'
                page.get_by_role('button',name='Hide text',exact=True).last.click()
                panel.wait_for(state='hidden')
                assert panel.locator('textarea').input_value()==''
                assert page.evaluate(metrics)==after
                # Narrow screens get one outer scrollbar, without resizing table cells.
                page.set_viewport_size({'width':900,'height':1000})
                page.wait_for_timeout(300)
                assert page.evaluate(metrics)==after
                page.set_viewport_size({'width':1440,'height':1800})
                grid.scroll_into_view_if_needed()
                grid.screenshot(path=str(stage/'fixed-summary.png'))
                assert page.get_by_role('textbox',name='Save folder:',exact=True).is_disabled()
                assert page.get_by_role('textbox',name='Save folder:',exact=True).input_value()==str(project/'paper_categorizations')
                # Native textarea: add, change and remove Markdown headings live.
                page.get_by_role('checkbox',name='Allow replacing the current unsaved paper',exact=True).check()
                page.get_by_role('combobox',name='Sampled paper:',exact=True).select_option(label='2. Browser paper 2')
                page.get_by_role('button',name='Start / reopen paper',exact=True).click()
                expect(page.get_by_role('textbox',name='Original paper:',exact=True)).to_have_value('')
                raw='Opening 𝑝 paragraph.\nA method paragraph.\nA final result!'
                page.get_by_role('textbox',name='Original paper:',exact=True).fill(raw)
                page.get_by_role('button',name='Clean full paper',exact=True).click()
                editor=page.get_by_role('textbox',name='Cleaned paper:',exact=True)
                page.wait_for_function("document.querySelector('.paper-markdown-editor textarea')?.value.includes('A method paragraph.')")
                markdown='# Opening\nOpening 𝑝 paragraph.\n\n## Approach\nA method paragraph.\n\n# Results\nA final result!'
                editor.fill(markdown)
                page.wait_for_function("document.querySelectorAll('.paper-section-row').length===3")
                selected_row=page.locator('.paper-section-row').filter(has_text='Approach').first
                expect(selected_row).to_contain_text('Subsection (level 2)')
                selected_row.locator('select').select_option(label='Methods')
                editor.fill(markdown.replace('## Approach','# Approach'))
                expect(selected_row).to_contain_text('Section:')
                expect(selected_row.locator('select')).to_have_value('Methods')
                editor.fill(markdown.replace('## Approach','Approach'))
                page.wait_for_function("document.querySelectorAll('.paper-section-row').length===2")
                assert 'Approach' in editor.input_value()
                # Newly marked text needs its own label; ordinary edits keep matching labels.
                editor.fill(markdown.replace('## Approach','# Approach'))
                page.wait_for_function("document.querySelectorAll('.paper-section-row').length===3")
                selected_row=page.locator('.paper-section-row').filter(has_text='Approach').first
                selected_row.locator('select').select_option(label='Methods')
                editor.fill(editor.input_value().replace('A method paragraph.','A revised method paragraph.'))
                expect(selected_row.locator('select')).to_have_value('Methods')
                editor.fill(editor.input_value()+'\n\n## ')
                expect(page.get_by_role('button',name='Save cleaned text + JSON',exact=True)).to_be_disabled()
                editor.fill(editor.input_value()+'Note\nAdditional body.')
                expect(page.get_by_role('button',name='Save cleaned text + JSON',exact=True)).to_be_enabled()
                editor.fill(editor.input_value().replace('\n\n## Note\nAdditional body.',''))
                page.wait_for_function("document.querySelectorAll('.paper-section-row').length===3")
                def assert_no_internal_scroll(selector):
                    problems=page.locator(selector).evaluate("""root => {
                      const elements=[root,...root.querySelectorAll('*')];
                      return elements.filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                        return r.width>0 && r.height>0 && s.visibility!=='hidden' &&
                          (e.scrollWidth>e.clientWidth+1 || (/auto|scroll|hidden|clip/.test(s.overflowY) && e.scrollHeight>e.clientHeight+1));
                      }).map(e=>({tag:e.tagName,cls:e.className,w:e.clientWidth,sw:e.scrollWidth,h:e.clientHeight,sh:e.scrollHeight,overflow:getComputedStyle(e).overflow}));
                    }""")
                    assert not problems,(selector,problems)
                # The alternative outline supports reviewed levels and stays synchronized.
                outline=page.get_by_role('textbox',name='Heading outline:',exact=True)
                expect(outline).to_have_value('1 | Opening\n1 | Approach\n1 | Results')
                outline.fill('1 | Opening\n2 | Approach\n1 | Results')
                expect(page.get_by_role('button',name='Save cleaned text + JSON',exact=True)).to_be_disabled()
                page.get_by_role('button',name='Apply reviewed outline',exact=True).click()
                page.wait_for_function("document.querySelector('.paper-markdown-editor textarea').value.includes('## Approach')")
                expect(selected_row.locator('select')).to_have_value('Methods')
                editor.fill(editor.input_value().replace('## Approach','### Approach'))
                expect(outline).to_have_value('1 | Opening\n3 | Approach\n1 | Results')
                outline.fill('1 | Opening\n2 | Approach\n1 | Results')
                editor.fill(editor.input_value().replace('A revised method paragraph.','An updated method paragraph.'))
                expect(outline).to_have_value('1 | Opening\n2 | Approach\n1 | Results')
                page.get_by_role('button',name='Refresh from Markdown',exact=True).click()
                expect(outline).to_have_value('1 | Opening\n3 | Approach\n1 | Results')
                # Long/wrapped outline text expands the card at each browser width.
                draft='\n'.join(f'2 | {i}. '+('LongHeadingWord'*12) for i in range(60))
                outline.fill(draft)
                for width in (1440,900,520):
                    page.set_viewport_size({'width':width,'height':1000})
                    page.wait_for_timeout(250)
                    assert_no_internal_scroll('.paper-heading-options')
                    assert outline.evaluate('e=>e.scrollHeight<=e.clientHeight+1')
                page.set_viewport_size({'width':1440,'height':1800})
                page.get_by_role('button',name='Refresh from Markdown',exact=True).click()
                expect(outline).to_have_value('1 | Opening\n3 | Approach\n1 | Results')
                # Project controls are outside the tabs and categories apply to every paper.
                page.get_by_text('Manage project categories',exact=True).last.click()
                page.get_by_role('textbox',name='Custom categories:',exact=True).fill('Institutions')
                page.get_by_role('button',name='Save project categories',exact=True).click()
                page.wait_for_function("Array.from(document.querySelectorAll('select option')).some(e=>e.textContent==='Institutions')")
                selected_row=page.locator('.paper-section-row').filter(has_text='Approach').first
                selected_row.locator('select').select_option(label='Institutions')
                expect(selected_row.locator('select')).to_have_value('Institutions')
                page.get_by_role('button',name='Save cleaned text + JSON',exact=True).click()
                page.wait_for_function("document.body.textContent.includes('Saved reloadable JSON:')")
                page.get_by_role('tab',name='Project summary',exact=True).click()
                page.wait_for_function("document.body.textContent.includes('1/10 papers saved')")
                assert page.locator('.project-report-overview tbody tr').count()==10
                assert 'Browser paper 2' in page.locator('.project-report-overview tbody tr').nth(1).locator('th').get_attribute('title')
                category=page.locator('.project-report-category').filter(has=page.locator('caption').filter(has_text='Institutions')).first
                assert category.locator('thead th').all_text_contents()==['Article no.','Words per title','Sum words','Min','Max','Paragraphs']
                assert category.locator('.project-report-statistics td').first.inner_text()==''
                assert float(category.locator('.project-report-statistics td').nth(1).inner_text())>0
                for width in (1440,900,520):
                    page.set_viewport_size({'width':width,'height':1000})
                    page.wait_for_timeout(250)
                    assert_no_internal_scroll('.project-summary-workflow')
                page.set_viewport_size({'width':1440,'height':1800})
                # Spreadsheet-shaped report: fixed controls, top-level metrics, summaries and copying.
                overview=page.locator('.project-report-overview')
                assert overview.locator('thead th').all_text_contents()==['Article no.','Total sections','Total word count','Total paragraphs','Total words in titles','Words per title','Words per abstract','Status']
                assert page.locator('.project-report-category').count()==10
                assert page.locator('.project-report-statistics').count()==10
                assert not any('#DIV/0!' in text for text in page.locator('.project-report-overview,.project-report-category').all_text_contents())
                report_buttons=page.get_by_role('button',name='Copy table (Excel)',exact=True)
                def report_bounds():
                    return report_buttons.evaluate_all("es=>es.map(e=>{const p=document.querySelector('.project-summary-workflow').getBoundingClientRect(),r=e.getBoundingClientRect();return {x:r.x-p.x,y:r.y-p.y,w:r.width,h:r.height}})")
                positions=report_bounds()
                page.get_by_role('button',name='Refresh project summary',exact=True).click()
                page.wait_for_timeout(300)
                assert positions==report_bounds()
                page.get_by_role('button',name='Copy whole report (Excel)',exact=True).click()
                page.wait_for_function("document.body.textContent.includes('Clipboard unavailable')")
                assert 'Article overview' in page.get_by_role('textbox',name='Copy manually:',exact=True).input_value()
                assert positions==report_bounds()
                overview.screenshot(path=str(stage/'article-overview.png'))
                page.get_by_role('textbox',name='Custom categories:',exact=True).fill('')
                page.get_by_role('button',name='Save project categories',exact=True).click()
                page.wait_for_function("document.body.textContent.includes('1 saved assignment(s) reset to Unassigned')")
                page.get_by_role('tab',name='Categorize full paper',exact=True).click()
                expect(selected_row.locator('select')).to_have_value('Unassigned')
                assert (project/'paper_categorizations/categories.json').exists()
                # Large saved analyses also expand the aggregate-title table and copy fallback.
                from app import paper_tools
                context=paper_tools.paper_read_project(project)
                stress_text='\n\n'.join('# '+str(i)+'. '+('LongHeadingWord'*10)+'\nBody paragraph.' for i in range(60))
                document=paper_tools.paper_make_markdown_document(stress_text,paper_metadata=context['papers'][0])
                for unit in document['units']:unit['category']='Data'
                paper_tools.paper_save_in_project(document,context,'layout-stress')
                page.get_by_role('tab',name='Project summary',exact=True).click()
                page.wait_for_function("document.body.textContent.includes('2/10 papers saved')")
                page.get_by_text('Aggregate category totals and titles',exact=True).last.click()
                for width in (1440,900,520):
                    page.set_viewport_size({'width':width,'height':1000})
                    page.wait_for_timeout(250)
                    assert_no_internal_scroll('.project-summary-workflow')
                page.set_viewport_size({'width':1440,'height':1800})
                (stage/'browser-result.json').write_text(json.dumps({'status':'passed','checks':['10 sampled papers','fixed button bounds','unassigned warnings and highlights','counted Not categorizable category','no cell horizontal overflow','full preview hide','narrow viewport','locked project save folder','native Markdown heading editor','live heading levels and removal','live edits and incomplete heading recovery','manual outline apply, synchronization and draft refresh','project categories and saved assignment rewrite','project-wide summary','article overview and category statistics','report copying and stable controls','average below Sum words','no inner scrollbars in long outline or project summary at 1440, 900 and 520 pixels'] + (['browser without AbortSignal.any'] if args.without_abort_signal_any else [])}))
                print('Browser layout checks passed.'+(' Artifacts: '+str(stage) if args.artifacts else ''))
                browser.close()
        except Exception:
            if 'browser_messages' in locals():
                (stage/'browser-console.txt').write_text('\n'.join(browser_messages),encoding='utf-8')
            try:
                page.screenshot(path=str(stage/'browser-failure.png'))
                (stage/'browser-failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            except Exception:
                pass
            raise
        finally:
            service.force_stop()


if __name__ == "__main__":
    main()
