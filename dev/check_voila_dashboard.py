"""Check both dashboard pages in a browser with external requests blocked."""
from argparse import ArgumentParser
import json
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import expect, sync_playwright
from path_selector_checks import check_creation_selectors, check_paper_selectors, selector


def assert_no_horizontal_scroll(page, frame):
    overflow = """() => {
        const root = document.scrollingElement;
        const scrollable = [...document.querySelectorAll('main, #rendered_cells *')].filter(element =>
            element.clientWidth && element.scrollWidth > element.clientWidth + 1 &&
            /^(auto|scroll)$/.test(getComputedStyle(element).overflowX) &&
            !element.matches('input, textarea, select'));
        if (root.scrollWidth > root.clientWidth + 1) scrollable.unshift(root);
        return scrollable.map(element =>
            [element.tagName, element.className, element.clientWidth, element.scrollWidth]);
    }"""
    assert not page.evaluate(overflow), page.evaluate(overflow)
    result = frame.locator('body').evaluate(overflow)
    assert not result, result[:8]


def check_pages(service, browser_executable, without_abort_signal_any):
    expect.set_options(timeout=15000)
    with tempfile.TemporaryDirectory(prefix='voila-layout-') as temporary, sync_playwright() as playwright:
        project = Path(temporary)
        paper_title = 'LongPaperTitle' * 12
        heading = 'LongMethodHeading' * 12
        config = {'schema_version': 1, 'journal': 'Layout Test Journal', 'sample_export': 'sample.csv'}
        (project / 'project.json').write_text(json.dumps(config), encoding='utf-8')
        (project / 'sample.csv').write_text(f'doi,title,bibtex_key\n10.1234/layout,{paper_title},layout\n',
                                            encoding='utf-8')
        browser = playwright.chromium.launch(executable_path=browser_executable)
        page = browser.new_page(viewport={'width': 1050, 'height': 850})
        page.set_default_timeout(30000)
        external = []

        def route_request(route):
            url = route.request.url
            if url.startswith(service.base_url):
                route.continue_()
            else:
                external.append(url)
                route.abort()

        page.route('http*://**/*', route_request)
        if without_abort_signal_any:
            page.add_init_script('delete AbortSignal.any;')
        page.goto(service.url, wait_until='domcontentloaded')
        expect(page).to_have_title('Journal Analysis Tools')
        expect(page.locator('#papers-page')).not_to_have_attribute('src', '/voila/render/clean_and_count_text.ipynb')

        projects = page.frame_locator('#projects-page')
        expect(projects.get_by_role('button', name='Find journal', exact=True)).to_be_visible()
        for width in (1050, 900, 520, 320):
            page.set_viewport_size({'width': width, 'height': 850})
            assert_no_horizontal_scroll(page, projects)
        check_creation_selectors(page, projects, project)
        projects.get_by_role('button', name='Manual DOI selection', exact=True).click()
        doi = projects.get_by_role('textbox', name='Paper DOI:', exact=True)
        doi.fill('10.1234/browser.draft')
        expect(projects.locator('.jp-InputArea-editor')).to_have_count(0)
        assert_no_horizontal_scroll(page, projects)

        papers_link = page.get_by_role('link', name='Clean and categorize papers')
        projects_link = page.get_by_role('link', name='Create journal project')
        papers_link.click()
        expect(papers_link).to_have_attribute('aria-current', 'page')
        papers = page.frame_locator('#papers-page')
        expect(papers.get_by_role('textbox', name='Original text:', exact=True)).to_be_visible()
        assert_no_horizontal_scroll(page, papers)
        papers.get_by_role('tab', name='Categorize full paper', exact=True).click()
        check_paper_selectors(page, papers, project)
        papers.get_by_role('button', name='Scan project folder', exact=True).click()
        expect(selector(papers, 'Save folder:').get_by_role('button', name='Browse…', exact=True)).to_be_disabled()
        selection = papers.get_by_role('combobox', name='Sampled paper:', exact=True)
        selection.select_option(label=f'1. {paper_title}')
        papers.get_by_role('button', name='Start / reopen paper', exact=True).click()
        editor = papers.get_by_role('textbox', name='Cleaned paper:', exact=True)
        markdown = f'# Introduction\nOpening paragraph.\n\n## {heading}\nA method paragraph.'
        editor.fill(markdown)
        expect(papers.locator('.paper-section-row')).to_have_count(2)
        expect(papers.locator('.jp-InputArea-editor')).to_have_count(0)
        methods = papers.locator('.paper-section-row').filter(has_text=heading)
        methods.locator('select').select_option(label='Methods')
        expect(papers.locator('.paper-individual-summary')).to_contain_text(heading)
        methods.get_by_role('button', name='Show text', exact=True).click()
        expect(papers.locator('.paper-preview-panel')).to_be_visible()
        assert_no_horizontal_scroll(page, papers)
        papers.locator('.paper-preview-panel').get_by_role('button', name='Hide text', exact=True).click()
        for width in (320, 520, 760, 780, 900, 1050):
            page.set_viewport_size({'width': width, 'height': 850})
            assert_no_horizontal_scroll(page, papers)
            copy = papers.locator('.paper-summary-grid button[title="Copy Introduction — paragraphs"]')
            copy.scroll_into_view_if_needed()
            bounds = copy.bounding_box()
            assert 0 <= bounds['x'] and bounds['x'] + bounds['width'] <= width, (width, bounds)
        papers.get_by_role('tab', name='Project summary', exact=True).click()
        page.set_viewport_size({'width': 320, 'height': 850})
        expect(papers.locator('.project-report-table').first).to_be_visible()
        assert_no_horizontal_scroll(page, papers)
        papers.get_by_role('tab', name='Categorize full paper', exact=True).click()

        kernels = {kernel['id'] for kernel in service.request('api/kernels')}
        assert len(kernels) == 2
        projects_link.click()
        expect(doi).to_have_value('10.1234/browser.draft')
        papers_link.click()
        expect(editor).to_have_value(markdown)
        expect(papers.locator('.paper-section-row')).to_have_count(2)
        assert {kernel['id'] for kernel in service.request('api/kernels')} == kernels
        assert 'token=' not in page.url
        assert not external, external
        browser.close()


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable')
    parser.add_argument('--without-abort-signal-any', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from app.notebook_services import DASHBOARD, NotebookService

    with tempfile.TemporaryDirectory(prefix='voila-browser-') as logs:
        service = NotebookService(DASHBOARD, root, log_dir=logs)
        try:
            service.start()
            check_pages(service, args.browser_executable, args.without_abort_signal_any)
        finally:
            service.stop()
    print('Both pages fit narrow windows and kept their unsaved edits across navigation.')


if __name__ == '__main__':
    main()
