"""Check both dashboard pages in a browser with external requests blocked."""
from argparse import ArgumentParser
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import expect, sync_playwright


def check_pages(service, browser_executable, without_abort_signal_any):
    with sync_playwright() as playwright:
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
        projects.get_by_role('button', name='Manual DOI selection', exact=True).click()
        doi = projects.get_by_role('textbox', name='Paper DOI:', exact=True)
        doi.fill('10.1234/browser.draft')
        expect(projects.locator('.jp-InputArea-editor')).to_have_count(0)

        papers_link = page.get_by_role('link', name='Clean and categorize papers')
        projects_link = page.get_by_role('link', name='Create journal project')
        papers_link.click()
        expect(papers_link).to_have_attribute('aria-current', 'page')
        papers = page.frame_locator('#papers-page')
        papers.get_by_role('tab', name='Categorize full paper', exact=True).click()
        editor = papers.get_by_role('textbox', name='Cleaned paper:', exact=True)
        markdown = '# Introduction\nOpening paragraph.\n\n## Methods\nA method paragraph.'
        editor.fill(markdown)
        expect(papers.locator('.paper-section-row')).to_have_count(2)
        expect(papers.locator('.jp-InputArea-editor')).to_have_count(0)

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
    print('Both pages rendered and kept their unsaved edits across navigation.')


if __name__ == '__main__':
    main()
