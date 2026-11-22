"""Run the two real notebook views and exercise the dashboard service lifecycle."""
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request

import psutil

from app.notebook_services import DASHBOARD, NotebookService, SERVICES


def check_dashboard(case, notebook_root, log_dir):
    service = NotebookService(DASHBOARD, notebook_root, log_dir=log_dir)

    def read(path):
        request = Request(service.base_url + path, headers={'Authorization': f'token {service.token}'})
        with service._opener.open(request, timeout=45) as response:
            return response.read().decode('utf-8')

    try:
        service.start()
        case.assertEqual(service.request('api/kernels'), [])
        with service._opener.open(service.base_url, timeout=5) as response:
            case.assertIn('/login?', response.geturl())
        case.assertIn('Clean and categorize papers', read(''))
        for path in ('voila/api/contents', 'voila/render/other.ipynb',
                     'voila/files/' + SERVICES[0].notebook, 'api/contents'):
            with case.assertRaises(HTTPError) as blocked:
                read(path)
            case.assertIn(blocked.exception.code, (403, 404))

        for spec in SERVICES:
            html = read('voila/render/' + spec.notebook)
            case.assertIn('application/vnd.jupyter.widget-view+json', html)
            case.assertFalse('class="jp-InputArea-editor' in html, 'Notebook code cells are visible')
            case.assertFalse('cdn.jsdelivr.net/npm/@fortawesome/' in html, 'Notebook requires remote styles')
        case.assertEqual(len(service.request('api/kernels')), 2)
        case.assertEqual(service.kill_kernels(), 2)
        case.assertEqual(service.request('api/kernels'), [])

        read('voila/render/' + SERVICES[1].notebook)
        case.assertEqual(len(service.request('api/kernels')), 1)
        service.track_children()
        owned = service._children | {psutil.Process(service.process.pid)}
        service.stop()
        case.assertIsNone(service.url)
        case.assertFalse(any(process.is_running() for process in owned))
    finally:
        service.force_stop()


class VoilaServiceTests(unittest.TestCase):
    def test_dashboard_renders_widgets_and_stops_its_kernels(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='voila-test-') as logs:
            check_dashboard(self, root, logs)
