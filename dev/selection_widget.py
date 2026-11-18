"""Development source for the inline, offline notebook selection editor.

Embedded verbatim in the notebook so generated projects remain self-contained.
"""
try:
    import anywidget
except ImportError as error:
    raise ImportError("Install requirements.txt (including anywidget) in the Jupyter environment, restart the service and run all cells again.") from error
import traitlets


class PaperSelectionEditor(anywidget.AnyWidget):
    value = traitlets.Unicode('').tag(sync=True)
    selection = traitlets.Dict().tag(sync=True)
    _esm = r'''
    function render({ model, el }) {
      el.classList.add('paper-selection-editor');
      const label = document.createElement('label');
      label.textContent = 'Cleaned paper:';
      const area = document.createElement('textarea');
      area.setAttribute('aria-label', 'Cleaned paper:');
      area.spellcheck = false;
      area.value = model.get('value');
      label.append(area); el.append(label);
      const status = document.createElement('div');
      status.setAttribute('aria-live','polite'); el.append(status);
      // JS indices are UTF-16; model indices count Unicode code points like Python.
      const capture = () => {
        const value = area.value;
        const start = Array.from(value.slice(0,area.selectionStart)).length;
        const end = Array.from(value.slice(0,area.selectionEnd)).length;
        model.set('selection', {start, end, text:Array.from(value).slice(start,end).join(''), snapshot:value});
        model.save_changes();
        status.textContent = start === end ? 'Select text to mark a heading or assign a category.' : `${end-start} characters selected.`;
      };
      const input = () => { model.set('value',area.value); model.save_changes(); capture(); };
      const update = () => {
        if (area.value !== model.get('value')) { area.value=model.get('value'); status.textContent='Select text to mark a heading or assign a category.'; }
      };
      area.addEventListener('input',input);
      for (const event of ['select','mouseup','keyup','blur']) area.addEventListener(event,capture);
      model.on('change:value',update);
      status.textContent='Select text to mark a heading or assign a category.';
      return () => { model.off('change:value',update); area.removeEventListener('input',input);
        for (const event of ['select','mouseup','keyup','blur']) area.removeEventListener(event,capture); };
    }
    export default { render };
    '''
    _css = '''
    .paper-selection-editor { width:100%; min-width:0; }
    .paper-selection-editor label { display:block; font-weight:600; }
    .paper-selection-editor textarea { display:block; width:100%; height:300px; box-sizing:border-box;
      padding:10px; resize:vertical; font:14px/1.5 monospace; color:var(--jp-ui-font-color1,#222);
      background:var(--jp-layout-color0,white); border:1px solid #aab3bf; }
    .paper-selection-editor > div { min-height:24px; font-size:12px; }
    '''
