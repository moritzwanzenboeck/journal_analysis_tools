"""Browser wiring checks; native dialog results are stubbed only in scratch notebooks."""
from pathlib import Path
from playwright.sync_api import expect


def stub_native_dialogs(notebook, directory):
    """Keep automated browser checks from opening OS dialogs or changing real files."""
    directory = Path(directory).resolve()
    folder = directory/'Selector ü folder'; folder.mkdir(exist_ok=True)
    archive = folder/('long_metadata_'*12 + '.JSON'); archive.write_text('{}')
    standalone = directory/'Standalone ü'; standalone.mkdir(exist_ok=True)
    saved = standalone/'saved categorization.json'; saved.write_text('{}')
    responses = {
        'Choose the projects parent folder': [None, str(folder)],
        'Choose an archived Crossref JSON': [str(archive)],
        'Choose a standalone save folder': [str(standalone)],
        'Choose a saved categorization JSON': [str(saved)],
        'Choose a journal analysis project folder': [str(directory)],
    }
    code = next(cell for cell in reversed(notebook['cells']) if cell['cell_type'] == 'code')
    code['source'] = ''.join(code['source']) + f'''
# Synthetic OS-dialog responses for this temporary browser test only.
_native_dialog_responses = {responses!r}
async def native_path_dialog(**request):
    import asyncio
    await asyncio.sleep(0.05)
    return _native_dialog_responses[request['title']].pop(0)
'''


def selector(view, label):
    return view.locator('.journal-path-selector').filter(
        has=view.get_by_role('textbox', name=label, exact=True))


def assert_fit(browser):
    result = browser.evaluate('''root => [...root.querySelectorAll('*')].filter(e =>
        e.getClientRects().length && e.clientWidth &&
        !e.matches('input, select, option, textarea') &&
        e.scrollWidth > e.clientWidth + 1).map(e =>
            [e.tagName, e.className, e.clientWidth, e.scrollWidth])''')
    assert not result, result[:8]


def check_creation_selectors(page, view, directory):
    directory = Path(directory).resolve()
    folder = directory/'Selector ü folder'
    archive = folder/('long_metadata_'*12 + '.JSON')
    parent = selector(view, 'Projects parent:')
    field = view.get_by_role('textbox', name='Projects parent:', exact=True)
    original = field.input_value()
    button = parent.get_by_role('button', name='Browse…', exact=True)
    button.click()
    expect(button).to_be_enabled()
    expect(field).to_have_value(original)  # Native cancellation.
    button.click()
    expect(field).to_have_value(str(folder))
    for width in (900, 520, 320):
        page.set_viewport_size({'width': width, 'height': 850})
        assert_fit(parent)
    expect(view.locator('.journal-path-browser')).to_have_count(0)
    view.get_by_text('Publication date, reproducibility and offline replay', exact=True).click()
    picker = selector(view, 'Archived JSON:')
    picker.get_by_role('button', name='Browse…', exact=True).click()
    expect(view.get_by_role('textbox', name='Archived JSON:', exact=True)).to_have_value(str(archive))
    assert_fit(picker)
    view.get_by_text('Publication date, reproducibility and offline replay', exact=True).click()


def check_paper_selectors(page, view, directory):
    directory = Path(directory).resolve()
    standalone = directory/'Standalone ü'
    saved = standalone/'saved categorization.json'
    folder = selector(view, 'Save folder:')
    folder.get_by_role('button', name='Browse…', exact=True).click()
    expect(view.get_by_role('textbox', name='Save folder:', exact=True)).to_have_value(str(standalone))
    picker = selector(view, 'JSON path:')
    picker.get_by_role('button', name='Browse…', exact=True).click()
    expect(view.get_by_role('textbox', name='JSON path:', exact=True)).to_have_value(str(saved))
    expect(view.get_by_role('textbox', name='Cleaned paper:', exact=True)).to_have_value('')
    project = selector(view, 'Project folder:')
    project.get_by_role('button', name='Browse…', exact=True).click()
    expect(view.get_by_role('textbox', name='Project folder:', exact=True)).to_have_value(str(directory))
    for width in (1440, 900, 520, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert_fit(project)
    expect(view.locator('.journal-path-browser')).to_have_count(0)
