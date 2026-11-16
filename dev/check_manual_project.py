"""Optional offline browser check for manual DOI selection, Enter submission and cache reuse."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.notebook_services import NotebookService, SERVICES


def fixture(doi, title, journal, year, issn):
    return {'DOI':doi,'type':'journal-article','title':[title],'container-title':[journal],
            'published':{'date-parts':[[year,1,1]]},'ISSN':[issn],
            'author':[{'given':'Example','family':'Author'}],'abstract':'<p>Preloaded abstract.</p>'}


def main():
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable')
    parser.add_argument('--artifacts',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='journal-manual-browser-') as temporary:
        stage=args.artifacts.expanduser().resolve() if args.artifacts else Path(temporary)
        stage.mkdir(parents=True,exist_ok=True)
        root=Path(temporary)/'tools';root.mkdir()
        shutil.copytree(ROOT/'app',root/'app',ignore=shutil.ignore_patterns('__pycache__','assets'))
        shutil.copyfile(ROOT/'clean_and_count_text.ipynb',root/'clean_and_count_text.ipynb')
        projects=Path(temporary)/'projects';projects.mkdir()
        calls=Path(temporary)/'api-calls.json'
        records={r['DOI']:r for r in (
            fixture('10.1234/first','First selected paper','First Journal',2020,'1234-5679'),
            fixture('10.1234/second','Second selected paper','Second Journal',2025,'0002-8282'))}
        preload=f'''from urllib.parse import unquote, urlsplit
from copy import deepcopy
_fixture_records = {records!r}
_fixture_calls = []
def _offline_get_json(url, email=None):
    doi = unquote(urlsplit(url).path.removeprefix('/works/'))
    if doi in _fixture_calls:
        raise AssertionError('A preloaded DOI was fetched twice')
    _fixture_calls.append(doi)
    Path({str(calls)!r}).write_text(__import__('json').dumps(_fixture_calls))
    return deepcopy(_fixture_records[doi])
tools.get_json = _offline_get_json
'''
        notebook=json.loads((ROOT/'create_journal_analysis.ipynb').read_text(encoding='utf-8'))
        notebook['cells'].insert(3,{'cell_type':'code','id':'offline-doi-fixtures','metadata':{},'execution_count':None,'outputs':[],'source':preload.splitlines(True)})
        # Reproduce a kernel holding the backend from before manual DOI support.
        notebook['cells'].insert(2,{'cell_type':'code','id':'stale-import-fixture','metadata':{},'execution_count':None,'outputs':[],
            'source':["from app import journal_tools as _old_tools\n",
                      "del _old_tools.PROJECT_NOTEBOOK_API_VERSION\n",
                      "del _old_tools.lookup_doi\n", "del _old_tools.manual_overview\n"]})
        (root/'create_journal_analysis.ipynb').write_text(json.dumps(notebook),encoding='utf-8')
        service=NotebookService(next(s for s in SERVICES if s.key=='project'),root,log_dir=Path(temporary)/'logs')
        try:
            service.start()
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.browser_executable,headless=True)
                page=browser.new_page(viewport={'width':1400,'height':1400})
                page.goto(service.url,wait_until='domcontentloaded',timeout=60000)
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    kernels=service.request('api/kernels')
                    if kernels and kernels[0].get('execution_state')=='idle':break
                    time.sleep(0.25)
                else:raise RuntimeError('Notebook kernel did not become ready')
                page.get_by_role('menuitem',name='Run',exact=True).click(timeout=60000)
                page.get_by_role('menuitem',name='Run All Cells',exact=True).click()
                page.get_by_role('button',name='Manual DOI selection',exact=True).click(timeout=60000)
                query=page.get_by_role('textbox',name='Paper DOI:',exact=True)
                query.fill('https://doi.org/10.1234/first');query.press('Enter')
                result=page.locator('.manual-doi-result');result.wait_for(state='visible')
                assert result.locator('strong').inner_text()=='First selected paper'
                assert result.locator('strong').evaluate('e=>Number(getComputedStyle(e).fontWeight)')>=600
                for value in ('Authors:','Example Author','First Journal','2020','10.1234/first'):assert value in result.inner_text()
                result.screenshot(path=str(stage/'doi-search-result.png'))
                result.get_by_role('button',name='Add paper',exact=True).click()
                page.wait_for_function("document.querySelectorAll('.manual-selected-paper').length===1")
                assert 'Example Author' in page.locator('.manual-selected-paper').first.inner_text()
                page.get_by_role('tab',name='Paste DOI list',exact=True).click()
                bulk=page.get_by_role('textbox',name='DOI list:',exact=True)
                bulk.fill('10.1234/first\nhttps://doi.org/10.1234/second\nbad entry')
                page.get_by_role('button',name='Check and add DOI list',exact=True).click()
                page.get_by_text('No papers from this list were added.',exact=False).wait_for()
                assert page.locator('.manual-selected-paper').count()==1
                assert page.get_by_role('button',name='Create project',exact=True).is_disabled()
                bulk.fill('10.1234/first\nhttps://doi.org/10.1234/second')
                page.get_by_role('button',name='Check and add DOI list',exact=True).click()
                page.wait_for_function("document.querySelectorAll('.manual-selected-paper').length===2")
                overview=page.locator('.manual-project-overview')
                for value in ('First Journal','Second Journal','2020–2025','multiple journals'):assert value in overview.inner_text()
                overview.screenshot(path=str(stage/'selection-overview.png'))
                page.get_by_role('textbox',name='Projects parent:',exact=True).fill(str(projects))
                page.get_by_role('textbox',name='Project folder:',exact=True).fill('browser-manual')
                page.get_by_role('button',name='Create project',exact=True).click()
                page.get_by_text('Manually selected papers: 2.',exact=False).wait_for()
                config=json.loads((projects/'browser-manual/project.json').read_text(encoding='utf-8'))
                assert config['selection_method']=='manual'
                assert len(json.loads(calls.read_text()))==2
                with (projects/'browser-manual'/config['sample_export']).open(encoding='utf-8-sig',newline='') as handle:
                    rows=list(csv.DictReader(handle))
                assert [row['doi'] for row in rows]==['10.1234/first','10.1234/second']
                assert all(row['abstract']=='Preloaded abstract.' for row in rows)
                browser.close()
            (stage/'manual-browser-result.json').write_text(json.dumps({'status':'passed','checks':['stale import refreshed before form startup','Enter triggers lookup','bold title and structured DOI dropdown','bulk all-or-nothing validation','cached retry','mixed-journal overview','offline project creation','selected-paper exports']}))
            print('Manual project browser checks passed.')
        finally:
            service.force_stop()


if __name__=='__main__':main()
