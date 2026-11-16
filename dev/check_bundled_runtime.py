"""Executed by the relocated bundle's Python, without any development packages."""
import json
import re
from pathlib import Path
import sys
import runpy
import unittest
import uuid
from urllib.parse import urlencode


def check(package):
    package = Path(package).resolve()
    runtime = package/'app/python'
    if not Path(sys.executable).resolve().is_relative_to(runtime):
        raise RuntimeError('Verification is not using bundled Python.')
    if not Path(sys.prefix).resolve().is_relative_to(runtime):
        raise RuntimeError('Bundled Python depends on another installation.')
    import tkinter
    window = tkinter.Tk()
    window.withdraw()
    window.destroy()
    sys.path.insert(0, str(package))
    from app.notebook_services import NotebookService, SERVICES
    import websocket
    import psutil

    services = [NotebookService(spec, package) for spec in SERVICES]
    try:
        for service in services:
            service.start()
            with service._opener.open(service.url, timeout=10) as response:
                assert response.status == 200
        assert services[0].port != services[1].port
        for service in services:
            kernel = service.request('api/kernels', 'POST')
            url = service.base_url.replace('http://', 'ws://')+'api/kernels/'+kernel['id']+'/channels?'+urlencode({'token': service.token})
            client = websocket.create_connection(url, origin=service.base_url.rstrip('/'),
                                                 timeout=90, http_no_proxy=['127.0.0.1', 'localhost'])
            try:
                code = (
                    'import sys, os, json\nfrom pathlib import Path\n'
                    f'assert Path(sys.executable).resolve().is_relative_to(Path({str(runtime)!r}))\n'
                    f'assert Path(sys.prefix).resolve().is_relative_to(Path({str(runtime)!r}))\n'
                    f'os.chdir({str(package)!r})\n'
                    f'notebook=json.loads(Path({service.spec.notebook!r}).read_text(encoding="utf-8"))\n'
                    'for cell in notebook["cells"]:\n'
                    '    if cell["cell_type"]=="code":\n'
                    '        exec(compile("".join(cell["source"]), "bundled notebook", "exec"))\n'
                )
                message_id = uuid.uuid4().hex
                client.send(json.dumps(dict(
                    header=dict(msg_id=message_id, username='bundle-check', session=uuid.uuid4().hex,
                                msg_type='execute_request', version='5.3'),
                    parent_header={}, metadata={}, channel='shell',
                    content=dict(code=code, silent=False, store_history=False,
                                 user_expressions={}, allow_stdin=False, stop_on_error=True))))
                while True:
                    reply = json.loads(client.recv())
                    if (reply.get('msg_type', reply.get('header', {}).get('msg_type')) == 'execute_reply'
                            and reply['parent_header'].get('msg_id') == message_id):
                        if reply['content']['status'] != 'ok':
                            raise RuntimeError('Bundled notebook failed: '+str(reply['content']))
                        break
            finally:
                client.close()
            assert service.kill_kernels() == 1
            assert service.request('api/kernels') == []
            print('Verified bundled notebook and kernel:', service.spec.notebook, flush=True)
        # Exercise graceful and forced shutdown, including a newly started kernel.
        services[0].request('api/kernels', 'POST')
        for index, service in enumerate(services):
            service.track_children()
            owned = set(service._children)
            owned.add(psutil.Process(service.process.pid))
            service.force_stop() if index == 0 else service.stop()
            assert not any(process.is_running() for process in owned)
    except Exception:
        for service in services:
            if service.log_path.is_file():
                log = service.log_path.read_text(encoding='utf-8', errors='replace')
                if service.token:
                    log = log.replace(service.token, '<redacted>')
                log = re.sub(r'token=[^\s&]+', 'token=<redacted>', log)
                print(service.spec.key+' log:\n'+log[-5000:], file=sys.stderr)
        raise
    finally:
        for service in services:
            service.force_stop()
    # The bundled Tk/runtime must support the actual controls and close handler.
    gui = runpy.run_path(str(Path(__file__).with_name('tests')/'test_launcher_gui.py'))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(gui['LauncherWindowTests'])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise RuntimeError('Bundled launcher GUI check failed.')


if __name__ == '__main__':
    check(sys.argv[1])
