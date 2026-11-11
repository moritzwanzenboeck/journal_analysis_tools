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
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable', help='Optional installed Chrome/Chromium path')
    parser.add_argument('--artifacts', type=Path, help='Keep screenshot/results in this directory')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='journal-paper-browser-') as temporary:
        stage = args.artifacts.expanduser().resolve() if args.artifacts else Path(temporary)
        stage.mkdir(parents=True, exist_ok=True)
        # Copy only the notebook: the browser may autosave outputs in this scratch copy.
        root = Path(temporary) / 'tools'
        root.mkdir()
        (root / 'clean_and_count_text.ipynb').write_bytes((ROOT / 'clean_and_count_text.ipynb').read_bytes())
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
                grid=page.locator('.paper-summary-grid')
                grid.wait_for(state='attached',timeout=30000)
                grid.scroll_into_view_if_needed()
                metrics='''() => {
                    const grid=document.querySelector('.paper-summary-grid'), r=grid.getBoundingClientRect();
                    return Array.from(grid.querySelectorAll('button')).map(e=>{const b=e.getBoundingClientRect();return {x:b.x-r.x,y:b.y-r.y,w:b.width,h:b.height}})
                }'''
                before=page.evaluate(metrics)
                data_row=page.locator('.paper-section-row').filter(has_text='2. Data').first
                data_row.locator('select').select_option(label='Data')
                data_row.get_by_role('button',name='Apply to subsections',exact=True).click()
                page.wait_for_function("document.querySelector('.paper-summary-grid').textContent.includes('VeryLongHeadingWord')")
                after=page.evaluate(metrics)
                assert len(before)==32 and len(after)==32
                assert all(abs(a[k]-b[k])<0.6 for a,b in zip(before,after) for k in ('x','y','w','h')),(before,after)
                overflow=grid.locator('.paper-summary-cell,.paper-summary-content').evaluate_all("es=>es.filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({width:e.clientWidth,scroll:e.scrollWidth,cls:e.className}))")
                assert not overflow,overflow
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
                (stage/'browser-result.json').write_text(json.dumps({'status':'passed','checks':['10 sampled papers','fixed button bounds','no cell horizontal overflow','full preview hide','narrow viewport','locked project save folder']}))
                print('Browser layout checks passed.'+(' Artifacts: '+str(stage) if args.artifacts else ''))
                browser.close()
        finally:
            service.force_stop()


if __name__ == "__main__":
    main()
