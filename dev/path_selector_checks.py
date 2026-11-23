"""Shared browser checks for native path selectors in Jupyter and Voilà."""
from pathlib import Path
from playwright.sync_api import expect


def selector(view, label):
    return view.locator('.journal-path-selector').filter(
        has=view.get_by_role('textbox', name=label, exact=True))


def browse_to(browser, path):
    browser.get_by_role('button', name='Browse…', exact=True).click()
    location = browser.get_by_role('textbox', name='Browse folder:', exact=True)
    location.fill(str(path))
    browser.get_by_role('button', name='Go', exact=True).click()
    expect(location).to_have_value(str(Path(path).resolve()))


def assert_fit(browser):
    result = browser.evaluate('''root => [...root.querySelectorAll('*')].filter(e =>
        e.getClientRects().length && e.clientWidth &&
        !e.matches('input, select, option, textarea') &&
        e.scrollWidth > e.clientWidth + 1).map(e =>
            [e.tagName, e.className, e.clientWidth, e.scrollWidth])''')
    assert not result, result[:8]


def check_creation_selectors(page, view, directory):
    directory = Path(directory).resolve()
    folder = directory/'Selector ü folder'; folder.mkdir(exist_ok=True)
    archive = folder/('long_metadata_'*12 + '.JSON'); archive.write_text('{}')
    (folder/'not-json.txt').write_text('not JSON')
    parent = selector(view, 'Projects parent:')
    original = view.get_by_role('textbox', name='Projects parent:', exact=True).input_value()
    browse_to(parent, folder)
    parent.get_by_role('button', name='Parent folder', exact=True).click()
    expect(parent.get_by_role('textbox', name='Browse folder:', exact=True)).to_have_value(str(directory))
    for width in (900, 520, 320):
        page.set_viewport_size({'width': width, 'height': 850})
        assert_fit(parent)
    parent.get_by_role('button', name='Cancel', exact=True).click()
    expect(view.get_by_role('textbox', name='Projects parent:', exact=True)).to_have_value(original)
    browse_to(parent, folder)
    parent.get_by_role('button', name='Use this folder', exact=True).click()
    expect(view.get_by_role('textbox', name='Projects parent:', exact=True)).to_have_value(str(folder))
    view.get_by_text('Publication date, reproducibility and offline replay', exact=True).click()
    picker = selector(view, 'Archived JSON:')
    picker.get_by_role('button', name='Browse…', exact=True).click()
    entries = picker.get_by_role('listbox', name='Folders / JSON:', exact=True)
    expect(entries.locator('option')).to_have_count(1)
    entries.select_option(label="[JSON] " + archive.name)
    expect(picker.locator('.widget-html-content').filter(has_text=archive.name)).to_be_visible()
    assert_fit(picker)
    picker.get_by_role('button', name='Use selected JSON', exact=True).click()
    expect(view.get_by_role('textbox', name='Archived JSON:', exact=True)).to_have_value(str(archive))
    view.get_by_text('Publication date, reproducibility and offline replay', exact=True).click()


def check_paper_selectors(page, view, directory):
    directory = Path(directory).resolve()
    standalone = directory/'Standalone ü'; standalone.mkdir(exist_ok=True)
    saved = standalone/'saved categorization.json'; saved.write_text('{}')
    folder = selector(view, 'Save folder:')
    browse_to(folder, standalone)
    folder.get_by_role('button', name='Use this folder', exact=True).click()
    expect(view.get_by_role('textbox', name='Save folder:', exact=True)).to_have_value(str(standalone))
    picker = selector(view, 'JSON path:')
    picker.get_by_role('button', name='Browse…', exact=True).click()
    picker.get_by_role('listbox', name='Folders / JSON:', exact=True).select_option(label='[JSON] ' + saved.name)
    picker.get_by_role('button', name='Use selected JSON', exact=True).click()
    expect(view.get_by_role('textbox', name='JSON path:', exact=True)).to_have_value(str(saved))
    expect(view.get_by_role('textbox', name='Cleaned paper:', exact=True)).to_have_value('')
    project = selector(view, 'Project folder:')
    browse_to(project, directory)
    for width in (1440, 900, 520, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert_fit(project)
    project.get_by_role('button', name='Use this folder', exact=True).click()
    expect(view.get_by_role('textbox', name='Project folder:', exact=True)).to_have_value(str(directory))
