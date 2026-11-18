"""Mac bundles must work alone and keep user notebooks outside signed resources."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import macos_bootstrap
from dev.build_notebook_launchers import APP_NAME, install, validate_macos_app
from dev.bundle_python import runtime_python
from dev.package_release import copy_sources

ROOT = Path(__file__).resolve().parents[2]


class WorkspaceTests(unittest.TestCase):
    def make_tools(self, root):
        tools=root/'tools';tools.mkdir()
        for name in macos_bootstrap.NOTEBOOKS:(tools/name).write_text('template '+name,encoding='utf-8')
        return tools

    def test_updates_preserve_edited_notebooks_and_recover_missing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tools=self.make_tools(root);base=root/'user notebooks'
            first=macos_bootstrap.prepare_workspace(tools,base)
            edited=first/macos_bootstrap.NOTEBOOKS[0];edited.write_text('User edits',encoding='utf-8')
            (first/macos_bootstrap.NOTEBOOKS[1]).unlink()
            self.assertEqual(macos_bootstrap.prepare_workspace(tools,base),first)
            self.assertEqual(edited.read_text(encoding='utf-8'),'User edits')
            self.assertTrue((first/macos_bootstrap.NOTEBOOKS[1]).exists())
            (tools/macos_bootstrap.NOTEBOOKS[0]).write_text('Updated template',encoding='utf-8')
            second=macos_bootstrap.prepare_workspace(tools,base)
            self.assertNotEqual(first,second)
            self.assertEqual(edited.read_text(encoding='utf-8'),'User edits')
            self.assertFalse(list(base.glob('.notebooks-*')))

    def test_bootstrap_sets_writable_root_and_ignores_unrelated_python_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);tools=self.make_tools(root)
            with patch.dict(os.environ,{'JOURNAL_TOOLS_WORKSPACE':str(root/'workspace'),
                     'PYTHONHOME':'wrong','PYTHONPATH':'wrong','TCL_LIBRARY':'wrong'}), \
                 patch.object(sys,'argv',['bootstrap.py',str(tools),'--check']), \
                 patch.object(sys,'path',list(sys.path)),patch.object(sys,'dont_write_bytecode',True), \
                 patch('app.launcher.main') as launch:
                macos_bootstrap.main()
                launch.assert_called_once()
                self.assertTrue(Path(os.environ['JOURNAL_TOOLS_NOTEBOOK_ROOT']).is_dir())
                self.assertNotIn('PYTHONHOME',os.environ)
                self.assertNotIn('PYTHONPATH',os.environ)
                self.assertEqual(sys.argv,['bootstrap.py','--check'])
                self.assertEqual(sys.path[0],str(tools.resolve()))

    def test_runtime_lookup_prefers_the_embedded_mac_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);embedded=root/APP_NAME/'Contents/Resources/JournalTools/app/python'
            embedded.mkdir(parents=True)
            self.assertEqual(runtime_python(root,'macos-x86_64'),embedded/'bin/python3')
            self.assertEqual(runtime_python(root,'windows-x86_64'),root/'app/python/python.exe')


@unittest.skipUnless(sys.platform=='darwin','Native Finder app required')
class NativeAppTests(unittest.TestCase):
    def test_compiled_app_alone_uses_embedded_tools_and_keeps_its_signature(self):
        with tempfile.TemporaryDirectory(prefix="journal's native Mac ä ") as temporary:
            root=Path(temporary);tools=root/'tools';copy_sources(ROOT,tools)
            runtime=tools/'app/python/bin';runtime.mkdir(parents=True)
            trace=root/'python-args.txt'
            # Default unit tests use a tiny interpreter wrapper. The release workflow
            # separately runs the actual bundled Python with system Python unavailable.
            wrapper=runtime/'python3'
            wrapper.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > '+shlex.quote(str(trace))+
                               '\nexec '+shlex.quote(sys.executable)+' "$@"\n',encoding='utf-8')
            # The native unit test needs only stdlib. Complete GUI/Jupyter startup
            # is exercised by the real-runtime package verification separately.
            (tools/'app/launcher.py').write_text(
                'import os,sys\nfrom pathlib import Path\ndef main():\n'
                '    assert "--check" in sys.argv\n'
                '    assert Path(os.environ["JOURNAL_TOOLS_NOTEBOOK_ROOT"]).is_dir()\n'
                '    Path('+repr(str(root/'chosen-workspace.txt'))+').write_text(os.environ["JOURNAL_TOOLS_NOTEBOOK_ROOT"])\n',encoding='utf-8')
            wrapper.chmod(0o755)
            shutil.copyfile('/usr/bin/true',runtime/'signature-probe')
            app=install(tools,root/'compiled',portable=True)
            isolated=root/'isolated';isolated.mkdir();moved=isolated/APP_NAME;app.rename(moved)
            env=dict(os.environ,JOURNAL_TOOLS_APP_CHECK='1',JOURNAL_TOOLS_NO_DIALOG='1',
                     JOURNAL_TOOLS_WORKSPACE=str(root/'notebooks'),PATH='/usr/bin:/bin',
                     PYTHONHOME=str(root/'bad-python'),PYTHONPATH=str(root/'bad-packages'))
            result=subprocess.run([str(moved/'Contents/MacOS/applet')],env=env,cwd=root,
                                  capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(trace.exists(),'Native run handler did not invoke embedded Python')
            args=trace.read_text(encoding='utf-8').splitlines()
            self.assertEqual(args[:2],['-I','-B'])
            self.assertEqual(args[-1],'--check')
            self.assertEqual(len(list((root/'notebooks').glob('*/*.ipynb'))),2, (root/'chosen-workspace.txt').read_text())
            probe=moved/'Contents/Resources/JournalTools/app/python/bin/signature-probe'
            subprocess.run(['/usr/bin/codesign','--verify','--strict',str(probe)],check=True,capture_output=True)
            validate_macos_app(moved)
